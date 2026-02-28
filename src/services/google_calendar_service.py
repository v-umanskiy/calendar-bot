from datetime import date, datetime, time, timedelta, timezone

import httpx

from src.utils import logging_utils
from . import google_oauth_token_service


GOOGLE_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _parse_target_date(date_input: str | None) -> tuple[date | None, str | None]:
    if date_input is None:
        return datetime.now(timezone.utc).date(), None
    normalized = date_input.strip()
    if not normalized:
        return datetime.now(timezone.utc).date(), None
    try:
        return date.fromisoformat(normalized), None
    except ValueError:
        return None, "Date format is invalid. Use /events or /events YYYY-MM-DD."


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


async def _list_events(access_token: str, target_date: date) -> tuple[bool, int, dict]:
    day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "timeMin": day_start.isoformat().replace("+00:00", "Z"),
        "timeMax": day_end.isoformat().replace("+00:00", "Z"),
        "singleEvents": "true",
        "orderBy": "startTime",
    }
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

    ok, status_code, payload = await _list_events(str(token_result["access_token"]), target_date)
    if not ok and status_code == 401:
        refreshed = await google_oauth_token_service.get_valid_access_token(str(chat_id), force_refresh=True)
        if not refreshed.get("ok"):
            return "Google Calendar authorization expired. Use /connect to reconnect."
        ok, status_code, payload = await _list_events(str(refreshed["access_token"]), target_date)

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
