import asyncio
from typing import Optional

from . import gemini_tool_executor
from . import gemini_tools
from src.services import google_calendar_service
from src.utils import logging_utils
from src.utils.constants import (
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
    EVENT_SAVE_SUCCESS_MESSAGE_TEMPLATE,
    EVENT_SAVE_FAILED_MESSAGE,
    EVENT_RECONNECT_REQUIRED_MESSAGE,
    EVENT_EDIT_PREVIEW_REPLY_PREFIX,
)

MAX_INVALID_REPAIR_ATTEMPTS = 2
AUTH_CONNECTION_ERRORS = {"reconnect_required", "not_connected", "missing_access_token"}


def is_auth_connection_error(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("ok") is not False:
        return False
    error = result.get("error")
    return isinstance(error, str) and error in AUTH_CONNECTION_ERRORS


def call_tool_and_build_reply(
    *,
    client,
    model_name: str,
    contents: list[dict],
    chat_id: str,
    function_call: dict,
    tool_config: dict,
) -> Optional[str]:
    function_result = _execute_tool_lifecycle(
        client=client,
        model_name=model_name,
        contents=contents,
        chat_id=chat_id,
        function_call=function_call,
        tool_config=tool_config,
    )
    return _resolve_tool_decision(
        client=client,
        model_name=model_name,
        chat_id=chat_id,
        contents=contents,
        function_result=function_result,
    )


def _execute_tool_lifecycle(
    *,
    client,
    model_name: str,
    contents: list[dict],
    chat_id: str,
    function_call: dict,
    tool_config: dict,
) -> dict:
    function_result = {
        "name": function_call.get("name"),
        "result": gemini_tool_executor.execute_tool_call(function_call, chat_id),
    }
    result = function_result.get("result")
    if isinstance(result, dict) and result.get("ok"):
        function_result = _repair_invalid_result_if_needed(
            client=client,
            model_name=model_name,
            contents=contents,
            chat_id=chat_id,
            function_result=function_result,
            tool_config=tool_config,
        )
    return function_result


def _resolve_tool_decision(
    *,
    client,
    model_name: str,
    chat_id: str,
    contents: list[dict],
    function_result: dict,
) -> Optional[str]:
    function_name = str(function_result.get("name") or "")
    if function_name in {
        gemini_tools.EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME,
        gemini_tools.EVENT_LOOKUP_BY_TITLE_TOOL_NAME,
    }:
        lookup_result = function_result.get("result") or {}
        if is_auth_connection_error(lookup_result):
            return EVENT_RECONNECT_REQUIRED_MESSAGE
        follow_up_contents = _build_lookup_follow_up_contents(contents, function_result)
        return _generate_follow_up_reply(
            client=client,
            model_name=model_name,
            follow_up_contents=follow_up_contents,
        ) or MODEL_PROVIDER_UNAVAILABLE_MESSAGE

    if function_name == gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME:
        preview_result = function_result.get("result") or {}
        if preview_result.get("ok"):
            preview_text = str(preview_result.get("preview") or "")
            return f"{EVENT_EDIT_PREVIEW_REPLY_PREFIX}{preview_text}"
        text = preview_result.get("message")
        return text or MODEL_PROVIDER_UNAVAILABLE_MESSAGE

    event_draft_update_result = function_result.get("result")
    if not isinstance(event_draft_update_result, dict) or not event_draft_update_result.get("ok"):
        return None

    draft = event_draft_update_result["draft"]
    draft_mode = draft.get("mode")
    missing_required = event_draft_update_result.get("missing_required") or []
    invalid_fields = event_draft_update_result.get("invalid_fields") or []
    if not missing_required and not invalid_fields and draft_mode == "create":
        return _create_calendar_event(chat_id, draft)
    if not missing_required and not invalid_fields and draft_mode == "edit":
        return None
    if invalid_fields:
        return MODEL_PROVIDER_UNAVAILABLE_MESSAGE
    if missing_required:
        follow_up_contents = _build_missing_follow_up_contents(contents, function_result)
        return _generate_follow_up_reply(client=client, model_name=model_name, follow_up_contents=follow_up_contents)
    return None


def _create_calendar_event(chat_id: str, draft: dict) -> str:
    create_result = asyncio.run(
        google_calendar_service.create_primary_event(
            str(chat_id),
            title=str(draft.get("title") or ""),
            start=str(draft.get("start") or ""),
            end=str(draft.get("end") or ""),
        )
    )
    if not create_result.get("ok"):
        if create_result.get("error") in {"reconnect_required", "not_connected", "missing_access_token"}:
            return EVENT_RECONNECT_REQUIRED_MESSAGE
        return EVENT_SAVE_FAILED_MESSAGE
    summary = EVENT_SAVE_SUCCESS_MESSAGE_TEMPLATE.format(
        title=str(draft.get("title") or ""),
        start=str(draft.get("start") or ""),
        end=str(draft.get("end") or ""),
    )
    return gemini_tools.build_event_created_reply(
        summary,
        str(create_result.get("calendar_id") or "primary"),
        str(create_result.get("google_event_id") or ""),
    )


def _generate_follow_up_reply(*, client, model_name: str, follow_up_contents: list[dict]) -> Optional[str]:
    follow_up_response = client.models.generate_content(
        model=model_name,
        contents=follow_up_contents,
    )
    follow_up_text = follow_up_response.text or ""
    if follow_up_text:
        return follow_up_text
    return None


def _repair_invalid_result_if_needed(
    *,
    client,
    model_name: str,
    contents: list[dict],
    chat_id: str,
    function_result: dict,
    tool_config: dict,
) -> dict:
    current_result = function_result

    for _ in range(MAX_INVALID_REPAIR_ATTEMPTS):
        current_event_draft_result = current_result.get("result") or {}
        invalid_fields = current_event_draft_result.get("invalid_fields") or []
        if not invalid_fields:
            break

        repair_contents = _build_invalid_repair_contents(contents, current_result)
        repair_response = client.models.generate_content(
            model=model_name,
            contents=repair_contents,
            config=tool_config,
        )
        repair_calls = gemini_tools.extract_function_calls(repair_response)
        if not repair_calls:
            break
        repair_tool_names = [str(call.get("name") or "") for call in repair_calls]
        logging_utils.log_prefixed_fields(
            "GEMINI_REPAIR_TOOL_CALLS",
            ("chat_id", chat_id),
            ("count", len(repair_calls)),
            ("names", repair_tool_names),
        )
        if len(repair_calls) > 1:
            logging_utils.log_prefixed_fields(
                "GEMINI_TOOL_VALIDATION_ERROR",
                ("chat_id", chat_id),
                ("count", len(repair_calls)),
                ("names", repair_tool_names),
                ("detail", "expected at most one repair function call"),
            )
            break

        current_result = {
            "name": repair_calls[0].get("name"),
            "result": gemini_tool_executor.execute_tool_call(repair_calls[0], chat_id),
        }
        next_event_draft_result = current_result.get("result")
        if not next_event_draft_result or not next_event_draft_result.get("ok"):
            break

    return current_result



def _build_invalid_repair_contents(contents: list[dict], function_result: dict) -> list[dict]:
    repair_instruction = (
        "Tool call results indicate invalid_fields. This is your formatting/normalization failure.\n"
        f"Tool results JSON:\n{gemini_tools.tool_results_to_json(function_result)}\n\n"
        "Try to correct invalid fields to RFC3339 datetime and call the relevant event draft tool again.\n"
        "Only include corrected values for invalid fields.\n"
        "If you cannot confidently normalize from context, do not guess; ask the user a concise clarification question."
    )
    updated_contents = list(contents)
    updated_contents.append({"role": "user", "parts": [{"text": repair_instruction}]})
    return updated_contents



def _build_missing_follow_up_contents(contents: list[dict], function_result: dict) -> list[dict]:
    follow_up_instruction = (
        "Tool calls were executed. Use this JSON result to continue the conversation:\n"
        f"{gemini_tools.tool_results_to_json(function_result)}\n\n"
        "If missing_required has entries, ask the user only for those missing mandatory fields.\n"
        "Be concise and ask only one focused follow-up question when possible.\n"
        "Do not mention internal tools."
    )
    updated_contents = list(contents)
    updated_contents.append({"role": "user", "parts": [{"text": follow_up_instruction}]})
    return updated_contents


def _build_lookup_follow_up_contents(contents: list[dict], function_result: dict) -> list[dict]:
    follow_up_instruction = (
        "Tool calls were executed. Use this JSON result to answer the user's request:\n"
        f"{gemini_tools.tool_results_to_json(function_result)}\n\n"
        "Answer naturally and directly.\n"
        "If there are no events, state that clearly and optionally suggest creating one.\n"
        "If there are multiple events, summarize the most relevant options concisely.\n"
        "Do not mention internal tools."
    )
    updated_contents = list(contents)
    updated_contents.append({"role": "user", "parts": [{"text": follow_up_instruction}]})
    return updated_contents
