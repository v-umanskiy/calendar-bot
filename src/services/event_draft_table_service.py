from datetime import datetime, timedelta

from src.utils import logging_utils
from src.repository import event_draft_repository

MANDATORY_FIELDS = ("title", "start")


def _is_non_blank(value) -> bool:
    return value is not None and bool(str(value).strip())


def _is_blank(value) -> bool:
    return value is None or not str(value).strip()


def _build_validation_result(
    *,
    title: str | None,
    start: str | None,
    end: str | None,
    invalid_fields: list[dict],
    missing_required: list[str] | None = None,
) -> dict:
    return {
        "ok": True,
        "draft": {
            "title": title,
            "start": start,
            "end": end,
        },
        "missing_required": missing_required or [],
        "invalid_fields": invalid_fields,
    }


def _parse_rfc3339_with_offset(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _validate_draft(draft: dict) -> tuple[list[str], list[dict]]:
    missing_required: list[str] = []
    for field in MANDATORY_FIELDS:
        value = draft.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_required.append(field)

    invalid_fields: list[dict] = []

    start_value = draft.get("start")
    end_value = draft.get("end")

    start_dt = None
    end_dt = None
    if _is_non_blank(start_value):
        start_dt = _parse_rfc3339_with_offset(str(start_value))
        if start_dt is None:
            invalid_fields.append(
                {
                    "field": "start",
                    "reason": "invalid_rfc3339_with_offset",
                    "value": str(start_value),
                }
            )
    if _is_non_blank(end_value):
        end_dt = _parse_rfc3339_with_offset(str(end_value))
        if end_dt is None:
            invalid_fields.append(
                {
                    "field": "end",
                    "reason": "invalid_rfc3339_with_offset",
                    "value": str(end_value),
                }
            )

    if start_dt is not None and end_dt is not None and end_dt <= start_dt:
        invalid_fields.append(
            {
                "field": "end",
                "reason": "must_be_after_start",
                "value": str(end_value),
            }
        )

    return missing_required, invalid_fields


def _normalize_and_prevalidate_datetimes(
    *,
    title: str | None,
    start: str | None,
    end: str | None,
) -> tuple[str | None, dict | None]:
    start_dt = _parse_rfc3339_with_offset(start) if _is_non_blank(start) else None
    if _is_non_blank(start) and start_dt is None:
        return end, _build_validation_result(
            title=title,
            start=start,
            end=end,
            invalid_fields=[
                {
                    "field": "start",
                    "reason": "invalid_rfc3339_with_offset",
                    "value": str(start),
                }
            ],
        )

    normalized_end = end
    if start_dt is not None and _is_blank(end):
        normalized_end = (start_dt + timedelta(hours=1)).isoformat(timespec="seconds")

    end_dt = _parse_rfc3339_with_offset(normalized_end) if _is_non_blank(normalized_end) else None
    if _is_non_blank(normalized_end) and end_dt is None:
        return normalized_end, _build_validation_result(
            title=title,
            start=start,
            end=normalized_end,
            invalid_fields=[
                {
                    "field": "end",
                    "reason": "invalid_rfc3339_with_offset",
                    "value": str(normalized_end),
                }
            ],
        )

    if start_dt is not None and end_dt is not None and end_dt <= start_dt:
        return normalized_end, _build_validation_result(
            title=title,
            start=start,
            end=normalized_end,
            invalid_fields=[
                {
                    "field": "end",
                    "reason": "must_be_after_start",
                    "value": str(normalized_end),
                }
            ],
        )

    return normalized_end, None


async def upsert_event_draft(
    chat_id: int,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
):
    normalized_end, prevalidation_result = _normalize_and_prevalidate_datetimes(
        title=title,
        start=start,
        end=end,
    )
    if prevalidation_result is not None:
        return prevalidation_result

    fields: dict = {}

    if start is not None:
        fields["start"] = start
    if normalized_end is not None:
        fields["end"] = normalized_end
    if title is not None:
        fields["title"] = title

    if not fields:
        logging_utils.log_prefixed_message_full(
            "Upsert event draft skipped: no fields provided",
            {"chat_id": str(chat_id)},
        )
        return {
            "ok": False,
            "error": "no_fields_provided",
        }

    logging_utils.log_prefixed_message_full(
        "Upserting event draft",
        {"chat_id": str(chat_id), "fields": fields},
    )
    result = await event_draft_repository.upsert_draft_fields(str(chat_id), fields)
    attributes = result.get("Attributes") if isinstance(result, dict) else {}
    draft = {
        "title": attributes.get("title"),
        "start": attributes.get("start"),
        "end": attributes.get("end"),
    }
    missing_required, invalid_fields = _validate_draft(draft)
    return {
        "ok": True,
        "draft": draft,
        "missing_required": missing_required,
        "invalid_fields": invalid_fields,
    }


async def replace_event_draft(
    chat_id: int,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
):
    normalized_end, prevalidation_result = _normalize_and_prevalidate_datetimes(
        title=title,
        start=start,
        end=end,
    )
    if prevalidation_result is not None:
        return prevalidation_result

    item = {"chat_id": str(chat_id)}

    if start is not None:
        item["start"] = start
    if normalized_end is not None:
        item["end"] = normalized_end
    if title is not None:
        item["title"] = title

    logging_utils.log_prefixed_message_full("Replacing event draft", item)
    await event_draft_repository.replace_draft_item(item)
    draft = {
        "title": item.get("title"),
        "start": item.get("start"),
        "end": item.get("end"),
    }
    missing_required, invalid_fields = _validate_draft(draft)
    return {
        "ok": True,
        "draft": draft,
        "missing_required": missing_required,
        "invalid_fields": invalid_fields,
    }


async def delete_event_draft(chat_id: int):
    return await event_draft_repository.delete_draft(str(chat_id))
