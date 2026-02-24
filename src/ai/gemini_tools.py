import asyncio
import json
from typing import Optional

from src.services import event_draft_table_service


EVENT_DRAFT_TOOL_NAME = "upsert_event_draft"
NEW_EVENT_DRAFT_TOOL_NAME = "create_new_event_draft"
EVENT_DRAFT_TOOL_SYSTEM_INSTRUCTION = (
    "You are a calendar assistant. "
    "If a user asks unrelated questions, briefly decline and redirect to calendar help. "
    "Short follow-ups inside an active draft flow are expected and should be interpreted in calendar context. "
    "When the user wants to add, update, reschedule, or rename the current calendar event draft, "
    "you must call the upsert_event_draft function with any known fields. "
    "When the user clearly starts a different/new event, call create_new_event_draft to replace the current draft. "
    "Use only these optional fields: start, end, title. "
    "Mandatory fields for a complete draft are title and start. "
    "For start/end, provide RFC3339 datetime with timezone offset (example: 2026-02-24T15:30:00+03:00). "
    "If date/time is ambiguous or incomplete, ask a clarifying question first and do not call the tool yet. "
    "Examples that require clarification before tool call: 'at 6', 'tomorrow evening', 'next Friday morning'. "
    "Only call the tool when you can provide normalized RFC3339 values."
)

EVENT_DRAFT_TOOL_CONFIG = {
    "systemInstruction": EVENT_DRAFT_TOOL_SYSTEM_INSTRUCTION,
    "tools": [
        {
            "functionDeclarations": [
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
    ],
}


def execute_function_calls(function_calls: list[dict], chat_id: Optional[str]) -> list[dict]:
    results: list[dict] = []
    for function_call in function_calls:
        result = execute_tool_call(function_call, chat_id)
        results.append(
            {
                "name": function_call["name"],
                "result": result,
            }
        )
    return results


def execute_tool_call(function_call: dict, chat_id: Optional[str]) -> dict:
    function_name = function_call["name"]
    if function_name not in {EVENT_DRAFT_TOOL_NAME, NEW_EVENT_DRAFT_TOOL_NAME}:
        return {"ok": False, "error": "unsupported_function"}

    if chat_id is None:
        return {"ok": False, "error": "missing_chat_id"}

    args = function_call.get("args") or {}
    if not isinstance(args, dict):
        return {"ok": False, "error": "invalid_arguments"}

    start = args.get("start")
    end = args.get("end")
    title = args.get("title")

    try:
        normalized_chat_id = int(chat_id) if str(chat_id).isdigit() else str(chat_id)
        normalized_start = start if start is None else str(start)
        normalized_end = end if end is None else str(end)
        normalized_title = title if title is None else str(title)
        if function_name == EVENT_DRAFT_TOOL_NAME:
            return asyncio.run(
                event_draft_table_service.upsert_event_draft(
                    chat_id=normalized_chat_id,
                    start=normalized_start,
                    end=normalized_end,
                    title=normalized_title,
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


def find_event_draft_result(function_results: list[dict]) -> Optional[dict]:
    for item in function_results:
        if item.get("name") not in {EVENT_DRAFT_TOOL_NAME, NEW_EVENT_DRAFT_TOOL_NAME}:
            continue
        result = item.get("result")
        if isinstance(result, dict):
            return result
    return None


def tool_results_to_json(function_results: list[dict]) -> str:
    try:
        return json.dumps(function_results, ensure_ascii=True)
    except Exception:
        return "[]"


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
