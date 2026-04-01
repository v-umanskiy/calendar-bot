from src.services import event_draft_table_service
from src.services import event_preview_formatter
from src.services import google_calendar_service
from src.utils.constants import EVENT_RECONNECT_REQUIRED_MESSAGE


async def prepare_primary_event_edit_preview(chat_id: str, google_event_id: str) -> dict:
    event_result = await google_calendar_service.get_primary_event_by_id(
        chat_id,
        google_event_id=google_event_id,
    )
    if not event_result.get("ok"):
        error = event_result.get("error")
        if error == "not_found":
            message = "Event not found in Google Calendar."
        elif error in {"reconnect_required", "not_connected", "missing_access_token"}:
            message = EVENT_RECONNECT_REQUIRED_MESSAGE
        else:
            message = "Could not load event details from Google Calendar right now."
        return {"ok": False, "error": error, "message": message}

    draft = await event_draft_table_service.load_event_draft(chat_id)
    safe_draft = draft or {}
    if (
        safe_draft.get("title") is None
        and safe_draft.get("start") is None
        and safe_draft.get("end") is None
    ):
        return {
            "ok": False,
            "error": "missing_edit_patch",
            "message": "No draft changes found for edit preview. Tell me what to change first.",
        }

    preview_text = event_preview_formatter.build_event_edit_preview_text(event_result["event"], safe_draft)
    return {
        "ok": True,
        "google_event_id": google_event_id,
        "preview": preview_text,
    }
