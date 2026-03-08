from datetime import date, datetime, time, timedelta, timezone

import httpx

from src.utils import datetime_utils
from src.utils import logging_utils
from . import google_oauth_token_service


GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
EVENT_LOOKUP_LIMIT = 20
EVENT_LOOKUP_PAST_DAYS = 50
EVENT_LOOKUP_FUTURE_DAYS = 180
EVENT_LOOKUP_ONE_SIDED_DAYS = 30


def _parse_target_date(date_input: str | None) -> tuple[date | None, str | None]:
    if date_input is None:
        return datetime.now(timezone.utc).date(), None
    normalized = date_input.strip()
    if not normalized:
        return datetime.now(timezone.utc).date(), None
    try:
        return date.fromisoformat(normalized), None
    except ValueError:
        return None, "Date format is invalid. Use /events."


def _format_event_line(item: dict) -> str:
    start = item.get("start") or {}
    title = item.get("summary") or "(no title)"

    start_dt = start.get("dateTime")
    if isinstance(start_dt, str) and "T" in start_dt:
        return f"- {start_dt[11:16]} {title}"

    start_date = start.get("date")
    if isinstance(start_date, str):
        return f"- (all day) {title}"

    return f"- {title}"


async def _list_events_in_range(
    access_token: str,
    *,
    time_min: datetime,
    time_max: datetime,
    query: str | None = None,
) -> tuple[bool, int, dict]:
    params = {
        "timeMin": time_min.isoformat().replace("+00:00", "Z"),
        "timeMax": time_max.isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    if query and query.strip():
        params["q"] = query.strip()
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(
                GOOGLE_CALENDAR_EVENTS_URL,
                headers=headers,
                params=params,
            )
        except Exception as exc:
            return False, 0, {"error": "events_request_failed", "detail": repr(exc)}

    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response.is_success, response.status_code, payload if isinstance(payload, dict) else {}


def _extract_event_bounds(item: dict) -> tuple[str | None, str | None]:
    start = item.get("start") if isinstance(item, dict) else {}
    end = item.get("end") if isinstance(item, dict) else {}
    start_dt = start.get("dateTime") if isinstance(start, dict) else None
    end_dt = end.get("dateTime") if isinstance(end, dict) else None
    if isinstance(start_dt, str) and isinstance(end_dt, str):
        return start_dt, end_dt
    start_date = start.get("date") if isinstance(start, dict) else None
    end_date = end.get("date") if isinstance(end, dict) else None
    return start_date if isinstance(start_date, str) else None, end_date if isinstance(end_date, str) else None


def _map_events(items: list) -> list[dict]:
    events: list[dict] = []
    for item in items:
        current = item if isinstance(item, dict) else {}
        start_value, end_value = _extract_event_bounds(current)
        events.append(
            {
                "google_event_id": str(current.get("id") or ""),
                "title": str(current.get("summary") or "(no title)"),
                "start": start_value,
                "end": end_value,
            }
        )
        if len(events) >= EVENT_LOOKUP_LIMIT:
            break
    return events


async def _search_events(
    chat_id: str,
    *,
    parsed_start: datetime,
    parsed_end: datetime,
    query: str | None = None,
) -> dict:
    token_result = await google_oauth_token_service.get_valid_access_token(str(chat_id))
    if not token_result.get("ok"):
        return {"ok": False, "error": token_result.get("error")}

    ok, status_code, payload = await _list_events_in_range(
        str(token_result["access_token"]),
        time_min=parsed_start,
        time_max=parsed_end,
        query=query,
    )
    if not ok and status_code == 401:
        refreshed = await google_oauth_token_service.get_valid_access_token(str(chat_id), force_refresh=True)
        if not refreshed.get("ok"):
            return {"ok": False, "error": "reconnect_required"}
        ok, status_code, payload = await _list_events_in_range(
            str(refreshed["access_token"]),
            time_min=parsed_start,
            time_max=parsed_end,
            query=query,
        )

    if not ok:
        logging_utils.log_prefixed_fields(
            "GOOGLE_CALENDAR_EVENTS_SEARCH_ERROR",
            ("chat_id", chat_id),
            ("status_code", status_code),
            ("error", payload.get("error") if isinstance(payload, dict) else "unknown"),
        )
        return {"ok": False, "error": "search_failed"}

    items = payload.get("items") if isinstance(payload, dict) else []
    items = items if isinstance(items, list) else []
    events = _map_events(items)
    return {
        "ok": True,
        "range_label": f"{parsed_start.isoformat()} to {parsed_end.isoformat()}",
        "events": events,
        "has_more": len(items) > EVENT_LOOKUP_LIMIT,
    }


async def _insert_event(
    access_token: str,
    *,
    title: str,
    start: str,
    end: str,
) -> tuple[bool, int, dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "summary": title,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                GOOGLE_CALENDAR_EVENTS_URL,
                headers=headers,
                json=payload,
            )
        except Exception as exc:
            return False, 0, {"error": "event_insert_request_failed", "detail": repr(exc)}

    try:
        response_payload = response.json()
    except Exception:
        response_payload = {"raw": response.text}
    return response.is_success, response.status_code, response_payload if isinstance(response_payload, dict) else {}


async def _delete_event(
    access_token: str,
    *,
    calendar_id: str,
    google_event_id: str,
) -> tuple[bool, int]:
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{google_event_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.delete(url, headers=headers)
        except Exception:
            return False, 0
    return response.is_success, response.status_code


async def _get_primary_event(
    access_token: str,
    *,
    google_event_id: str,
) -> tuple[bool, int, dict]:
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{GOOGLE_CALENDAR_EVENTS_URL}/{google_event_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(url, headers=headers)
        except Exception as exc:
            return False, 0, {"error": "event_get_request_failed", "detail": repr(exc)}

    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    return response.is_success, response.status_code, payload if isinstance(payload, dict) else {}


async def list_primary_events_for_date(chat_id: str, date_input: str | None = None) -> str:
    target_date, parse_error = _parse_target_date(date_input)
    if parse_error:
        return parse_error
    assert target_date is not None

    token_result = await google_oauth_token_service.get_valid_access_token(str(chat_id))
    if not token_result.get("ok"):
        error = token_result.get("error")
        if error in {"not_connected", "missing_access_token", "reconnect_required"}:
            return "Google Calendar is not connected. Use /connect first."
        return "Could not access Google Calendar right now. Please try again."

    day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    ok, status_code, payload = await _list_events_in_range(
        str(token_result["access_token"]),
        time_min=day_start,
        time_max=day_end,
    )
    if not ok and status_code == 401:
        refreshed = await google_oauth_token_service.get_valid_access_token(str(chat_id), force_refresh=True)
        if not refreshed.get("ok"):
            return "Google Calendar authorization expired. Use /connect to reconnect."
        ok, status_code, payload = await _list_events_in_range(
            str(refreshed["access_token"]),
            time_min=day_start,
            time_max=day_end,
        )

    if not ok:
        logging_utils.log_prefixed_fields(
            "GOOGLE_CALENDAR_EVENTS_LIST_ERROR",
            ("chat_id", chat_id),
            ("status_code", status_code),
            ("error", payload.get("error") if isinstance(payload, dict) else "unknown"),
        )
        return "Could not load events from Google Calendar right now."

    items = payload.get("items") if isinstance(payload, dict) else []
    items = items if isinstance(items, list) else []
    if not items:
        return f"No events for {target_date.isoformat()} (UTC)."

    lines = [f"Events for {target_date.isoformat()} (UTC):"]
    for item in items[:20]:
        lines.append(_format_event_line(item if isinstance(item, dict) else {}))
    return "\n".join(lines)


async def search_primary_events(
    chat_id: str,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    parsed_start = datetime_utils.parse_rfc3339_datetime_utc(start)
    parsed_end = datetime_utils.parse_rfc3339_datetime_utc(end)
    if parsed_start is None and parsed_end is not None:
        parsed_start = parsed_end - timedelta(days=EVENT_LOOKUP_ONE_SIDED_DAYS)
    elif parsed_end is None and parsed_start is not None:
        parsed_end = parsed_start + timedelta(days=EVENT_LOOKUP_ONE_SIDED_DAYS)

    if parsed_start is None or parsed_end is None:
        return {"ok": False, "error": "invalid_time_range"}
    if parsed_end <= parsed_start:
        return {"ok": False, "error": "invalid_time_range"}

    return await _search_events(
        str(chat_id),
        parsed_start=parsed_start,
        parsed_end=parsed_end,
    )


async def search_primary_events_by_query(chat_id: str, *, query: str | None = None) -> dict:
    normalized_query = (query or "").strip()
    if not normalized_query:
        return {"ok": False, "error": "missing_query"}

    now = datetime.now(timezone.utc)
    parsed_start = now - timedelta(days=EVENT_LOOKUP_PAST_DAYS)
    parsed_end = now + timedelta(days=EVENT_LOOKUP_FUTURE_DAYS)

    return await _search_events(
        str(chat_id),
        parsed_start=parsed_start,
        parsed_end=parsed_end,
        query=normalized_query,
    )


async def create_primary_event(chat_id: str, *, title: str, start: str, end: str) -> dict:
    token_result = await google_oauth_token_service.get_valid_access_token(str(chat_id))
    if not token_result.get("ok"):
        return {"ok": False, "error": token_result.get("error")}

    ok, status_code, payload = await _insert_event(
        str(token_result["access_token"]),
        title=title,
        start=start,
        end=end,
    )
    if not ok and status_code == 401:
        refreshed = await google_oauth_token_service.get_valid_access_token(str(chat_id), force_refresh=True)
        if not refreshed.get("ok"):
            return {"ok": False, "error": "reconnect_required"}
        ok, status_code, payload = await _insert_event(
            str(refreshed["access_token"]),
            title=title,
            start=start,
            end=end,
        )
    if not ok:
        logging_utils.log_prefixed_fields(
            "GOOGLE_CALENDAR_EVENT_INSERT_ERROR",
            ("chat_id", chat_id),
            ("status_code", status_code),
            ("error", payload.get("error") if isinstance(payload, dict) else "unknown"),
        )
        return {"ok": False, "error": "insert_failed"}

    event_id = payload.get("id")
    if not event_id:
        return {"ok": False, "error": "missing_event_id"}
    return {
        "ok": True,
        "calendar_id": "primary",
        "google_event_id": str(event_id),
        "html_link": payload.get("htmlLink"),
    }


async def get_primary_event_by_id(chat_id: str, *, google_event_id: str) -> dict:
    token_result = await google_oauth_token_service.get_valid_access_token(str(chat_id))
    if not token_result.get("ok"):
        return {"ok": False, "error": token_result.get("error")}

    ok, status_code, payload = await _get_primary_event(
        str(token_result["access_token"]),
        google_event_id=google_event_id,
    )
    if not ok and status_code == 401:
        refreshed = await google_oauth_token_service.get_valid_access_token(str(chat_id), force_refresh=True)
        if not refreshed.get("ok"):
            return {"ok": False, "error": "reconnect_required"}
        ok, status_code, payload = await _get_primary_event(
            str(refreshed["access_token"]),
            google_event_id=google_event_id,
        )

    if not ok:
        if status_code in {404, 410}:
            return {"ok": False, "error": "not_found"}
        logging_utils.log_prefixed_fields(
            "GOOGLE_CALENDAR_EVENT_GET_ERROR",
            ("chat_id", chat_id),
            ("status_code", status_code),
            ("error", payload.get("error")),
        )
        return {"ok": False, "error": "get_failed"}

    start, end = _extract_event_bounds(payload)
    return {
        "ok": True,
        "event": {
            "google_event_id": str(payload.get("id") or ""),
            "title": str(payload.get("summary") or "(no title)"),
            "start": start,
            "end": end,
        },
    }


async def delete_event(chat_id: str, *, calendar_id: str, google_event_id: str) -> dict:
    token_result = await google_oauth_token_service.get_valid_access_token(str(chat_id))
    if not token_result.get("ok"):
        return {"ok": False, "error": token_result.get("error")}

    ok, status_code = await _delete_event(
        str(token_result["access_token"]),
        calendar_id=calendar_id,
        google_event_id=google_event_id,
    )
    if not ok and status_code == 401:
        refreshed = await google_oauth_token_service.get_valid_access_token(str(chat_id), force_refresh=True)
        if not refreshed.get("ok"):
            return {"ok": False, "error": "reconnect_required"}
        ok, status_code = await _delete_event(
            str(refreshed["access_token"]),
            calendar_id=calendar_id,
            google_event_id=google_event_id,
        )

    if ok:
        return {"ok": True}
    if status_code in {404, 410}:
        return {"ok": False, "error": "not_found"}
    return {"ok": False, "error": "delete_failed"}
