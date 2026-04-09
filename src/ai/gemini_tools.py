import json
from typing import Optional

from src.utils.constants import EVENT_CREATED_REPLY_PREFIX


EVENT_DRAFT_TOOL_NAME = "upsert_event_draft"
EVENT_EDIT_DRAFT_TOOL_NAME = "upsert_event_edit_draft"
NEW_EVENT_DRAFT_TOOL_NAME = "create_new_event_draft"
EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME = "find_calendar_events_by_date_range"
EVENT_LOOKUP_BY_TITLE_TOOL_NAME = "find_calendar_events_by_title"
EVENT_EDIT_PREVIEW_TOOL_NAME = "prepare_event_edit"
EVENT_REMOVE_PREVIEW_TOOL_NAME = "prepare_event_remove"
EVENT_DRAFT_TOOL_SYSTEM_INSTRUCTION = (
    "You are a calendar assistant. "
    "If a user asks unrelated questions, briefly decline and redirect to calendar help. "
    "Short follow-ups inside an active draft flow are expected and should be interpreted in calendar context. "
    "When the user wants to add a new event, "
    "you must call the upsert_event_draft function with any known fields. "
    "When the user clearly starts a different/new event, call create_new_event_draft to replace the current draft. "
    "Use only these optional fields: start, end, title. "
    "Mandatory fields for a complete draft are title and start. "
    "For start/end, provide RFC3339 datetime without timezone offset (example: 2026-02-24T15:30:00). "
    "If date/time is ambiguous or incomplete, ask a clarifying question first and do not call the tool yet. "
    "Examples that require clarification before tool call: 'at 6', 'tomorrow evening', 'next Friday morning'. "
    "Only call the tool when you can provide normalized RFC3339 values. "
    "If the user asks about existing events (including move/reschedule/edit requests), "
    "use find_calendar_events_by_date_range when time boundaries are available, "
    "and use find_calendar_events_by_title when they are not. "
    "For find_calendar_events_by_date_range, provide start and end in RFC3339 format. "
    "For find_calendar_events_by_title.query, prefer one word; use two words only in rare cases. "
    "If find_calendar_events_by_title returns no events and the user's request includes a time window, "
    "retry with find_calendar_events_by_date_range before saying that nothing was found. "
    "Edit flow: first call upsert_event_edit_draft with requested changed fields (title/start/end). "
    "Then identify the target event via lookup tools. "
    "If exactly one event is identified, call prepare_event_edit with google_event_id. "
    "If event match is ambiguous or missing, ask a clarification question and do not call prepare_event_edit yet. "
    "Remove flow: after identifying exactly one event to remove, call prepare_event_remove with google_event_id. "
    "You have limitations: "
    "- you can create / edit / remove only one event at a time, no batch processing." \
    "- you can only process events (no reminders) and only set start, end and title." \
    "- you can't create recurring events."
    "- you can only work with one calendar at a time - the primary calendar from the connected Google account." \
    "- you can't do other things apart from those enabled by your tools." \
    "If a user's request hits a limitation, advise to the user politely that that's outside of your capabilities." \
    "If a user asks anything regarding legal / data protection / data storage in the bot, advise to click /docs" \
    "in the menu and familirize themselves with the terms. Strictly avoid making up legal answers."
)

EVENT_DRAFT_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME,
                "description": (
                    "Find existing calendar events in Google Calendar using explicit start/end bounds."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "STRING"},
                        "end": {"type": "STRING"},
                    },
                },
            },
            {
                "name": EVENT_LOOKUP_BY_TITLE_TOOL_NAME,
                "description": (
                    "Find existing calendar events in Google Calendar by text query when time boundaries are unknown."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "query": {"type": "STRING"},
                    },
                },
            },
            {
                "name": EVENT_EDIT_PREVIEW_TOOL_NAME,
                "description": (
                    "Prepare an edit preview for an existing calendar event after the event was identified. "
                    "Uses current draft values as pending changes."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "google_event_id": {"type": "STRING"},
                    },
                },
            },
            {
                "name": EVENT_REMOVE_PREVIEW_TOOL_NAME,
                "description": (
                    "Prepare a removal preview for an existing calendar event after the event was identified."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "google_event_id": {"type": "STRING"},
                    },
                },
            },
            {
                "name": EVENT_EDIT_DRAFT_TOOL_NAME,
                "description": (
                    "Upsert the active edit draft for the current chat. "
                    "Call it when the user requests changes to an existing event."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "STRING"},
                        "end": {"type": "STRING"},
                        "title": {"type": "STRING"},
                    },
                },
            },
            {
                "name": EVENT_DRAFT_TOOL_NAME,
                "description": (
                    "Upsert the active event draft for the current chat. "
                    "Call it whenever the user wants to add or modify draft event details."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "STRING"},
                        "end": {"type": "STRING"},
                        "title": {"type": "STRING"},
                    },
                },
            },
            {
                "name": NEW_EVENT_DRAFT_TOOL_NAME,
                "description": (
                    "Create a new event draft for the current chat by replacing the existing one. "
                    "Call it when the user pivots to a different event."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "start": {"type": "STRING"},
                        "end": {"type": "STRING"},
                        "title": {"type": "STRING"},
                    },
                },
            },
        ]
    }
]

def tool_results_to_json(function_result: dict) -> str:
    try:
        return json.dumps(function_result, ensure_ascii=True)
    except Exception:
        return "{}"


def build_complete_draft_summary(draft: dict, tool_name: Optional[str] = None) -> str:
    title = draft.get("title") if isinstance(draft, dict) else None
    start = draft.get("start") if isinstance(draft, dict) else None
    end = draft.get("end") if isinstance(draft, dict) else None
    action = (
        "Started a new draft event"
        if tool_name == NEW_EVENT_DRAFT_TOOL_NAME
        else "Updated current draft event"
    )
    lines = [
        f"Action: {action}",
        f"Title: {title or '(missing)'}",
        f"Start: {start or '(missing)'}",
        f"End: {end or '(not set)'}",
    ]
    return "\n".join(lines)


def build_event_created_reply(summary: str, calendar_id: str, google_event_id: str) -> str:
    payload = {
        "summary": summary,
        "calendar_id": calendar_id,
        "google_event_id": google_event_id,
    }
    return f"{EVENT_CREATED_REPLY_PREFIX}{json.dumps(payload, ensure_ascii=True)}"


def extract_response_content(response):
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    content = getattr(candidates[0], "content", None)
    if content is None:
        return None
    return content.model_dump(exclude_none=True) if hasattr(content, "model_dump") else content


def extract_function_calls(response) -> list[dict]:
    raw_calls = getattr(response, "function_calls", None) or []
    normalized: list[dict] = []
    for raw_call in raw_calls:
        if isinstance(raw_call, dict):
            name = raw_call.get("name")
            args = raw_call.get("args")
        else:
            name = getattr(raw_call, "name", None)
            args = getattr(raw_call, "args", None)
        if not name:
            continue
        normalized.append({"name": str(name), "args": args})
    return normalized
