import asyncio

from src.services import event_draft_table_service
from src.services import event_edit_preview_service
from src.services import google_calendar_service

from . import gemini_tools


def execute_tool_call(function_call: dict, chat_id: str) -> dict:
    function_name = function_call["name"]
    if function_name not in {
        gemini_tools.EVENT_DRAFT_TOOL_NAME,
        gemini_tools.EVENT_EDIT_DRAFT_TOOL_NAME,
        gemini_tools.NEW_EVENT_DRAFT_TOOL_NAME,
        gemini_tools.EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME,
        gemini_tools.EVENT_LOOKUP_BY_TITLE_TOOL_NAME,
        gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
    }:
        return {"ok": False, "error": "unsupported_function"}

    args = function_call.get("args") or {}
    if not isinstance(args, dict):
        return {"ok": False, "error": "invalid_arguments"}

    start = args.get("start")
    end = args.get("end")
    title = args.get("title")
    query = args.get("query")
    google_event_id = args.get("google_event_id")

    try:
        normalized_chat_id = int(chat_id) if str(chat_id).isdigit() else str(chat_id)
        normalized_start = start if start is None else str(start)
        normalized_end = end if end is None else str(end)
        normalized_title = title if title is None else str(title)
        normalized_query = query if query is None else str(query)
        normalized_google_event_id = google_event_id if google_event_id is None else str(google_event_id)
        if function_name == gemini_tools.EVENT_DRAFT_TOOL_NAME:
            return asyncio.run(
                event_draft_table_service.upsert_event_draft(
                    chat_id=normalized_chat_id,
                    start=normalized_start,
                    end=normalized_end,
                    title=normalized_title,
                )
            )
        if function_name == gemini_tools.EVENT_EDIT_DRAFT_TOOL_NAME:
            return asyncio.run(
                event_draft_table_service.upsert_event_edit_draft(
                    chat_id=normalized_chat_id,
                    start=normalized_start,
                    end=normalized_end,
                    title=normalized_title,
                )
            )
        if function_name == gemini_tools.EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME:
            return asyncio.run(
                google_calendar_service.search_primary_events(
                    str(normalized_chat_id),
                    start=normalized_start,
                    end=normalized_end,
                )
            )
        if function_name == gemini_tools.EVENT_LOOKUP_BY_TITLE_TOOL_NAME:
            return asyncio.run(
                google_calendar_service.search_primary_events_by_query(
                    str(normalized_chat_id),
                    query=normalized_query,
                )
            )
        if function_name == gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME:
            if normalized_google_event_id is None or not normalized_google_event_id.strip():
                return {"ok": False, "error": "missing_google_event_id"}
            return asyncio.run(
                event_edit_preview_service.prepare_primary_event_edit_preview(
                    str(normalized_chat_id),
                    normalized_google_event_id,
                )
            )
        return asyncio.run(
            event_draft_table_service.replace_event_draft(
                chat_id=normalized_chat_id,
                start=normalized_start,
                end=normalized_end,
                title=normalized_title,
            )
        )
    except Exception as exc:
        print("GEMINI_TOOL_EXECUTION_ERROR:", repr(exc))
        return {"ok": False, "error": "tool_execution_failed"}
