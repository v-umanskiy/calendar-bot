import asyncio
import json
import os
from typing import Optional

from google.api_core import exceptions as google_api_exceptions
from google import genai

from src.utils import logging_utils
from src.utils.constants import (
    MODEL_PROVIDER_LIMIT_REACHED_MESSAGE,
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
)
from . import gemini_tools
from . import gemini_decision_service
from . import gemini_tool_executor
from src.services import secret_service
from src.utils import datetime_utils

ModelHistory = list[dict]
ModelReply = dict

MAX_TOOL_CALLS_PER_TURN = 5
ACTION_CONTINUE_WITH_MODEL = "continue_with_model"
ACTION_CONTINUE_BACKEND = "continue_backend"
ACTION_TERMINAL_PROTOCOL = "terminal_protocol"

_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_CLIENT = genai.Client(api_key=secret_service.get_secret("GEMINI_API_KEY"))


async def generate_reply(
    prompt: str,
    chat_id: str,
    history: Optional[ModelHistory] = None,
) -> ModelReply:
    gemini_history = _convert_history(history)
    contents = _build_contents(gemini_history, [{"text": prompt}])
    try:
        return await asyncio.to_thread(
            _run_with_tools,
            contents,
            chat_id,
            prompt,
            history,
        )
    except (
        google_api_exceptions.ResourceExhausted,
        google_api_exceptions.TooManyRequests,
    ) as err:
        print(f"Gemini API quota exhausted: {err}")
        return {"type": "text", "text": MODEL_PROVIDER_LIMIT_REACHED_MESSAGE}
    except Exception as exc:
        print("GEMINI_CALL_ERROR:", repr(exc))
        return {"type": "text", "text": MODEL_PROVIDER_UNAVAILABLE_MESSAGE}


def _run_with_tools(
    contents: list[dict],
    chat_id: str,
    prompt: str,
    raw_history: Optional[ModelHistory],
) -> ModelReply:
    system_instruction = (
        f"{gemini_tools.EVENT_DRAFT_TOOL_SYSTEM_INSTRUCTION}\n\n"
        f"{datetime_utils.current_time_context_block().strip()}"
    )
    logging_utils.log_prefixed_fields(
        "Calling Gemini.",
        ("PROMPT", prompt),
        ("HISTORY", raw_history),
        ("SYSTEM_PROMPT", system_instruction),
    )

    tool_config = {
        "systemInstruction": system_instruction,
        "tools": gemini_tools.EVENT_DRAFT_TOOLS,
    }
    response = _CLIENT.models.generate_content(
        model=_MODEL_NAME,
        contents=contents,
        config=tool_config,
    )

    function_calls = gemini_tools.extract_function_calls(response)
    if not function_calls:
        return {"type": "text", "text": response.text or "No response"}
    tool_names = [str(call.get("name") or "") for call in function_calls]
    logging_utils.log_prefixed_fields(
        "GEMINI_TOOL_CALLS",
        ("chat_id", chat_id),
        ("count", len(function_calls)),
        ("names", tool_names),
    )
    if len(function_calls) > MAX_TOOL_CALLS_PER_TURN:
        logging_utils.log_prefixed_fields(
            "GEMINI_TOOL_VALIDATION_ERROR",
            ("chat_id", chat_id),
            ("count", len(function_calls)),
            ("names", tool_names),
            ("detail", f"expected at most {MAX_TOOL_CALLS_PER_TURN} function calls"),
        )
        return {"type": "text", "text": MODEL_PROVIDER_UNAVAILABLE_MESSAGE}

    return _execute_tool_calls_and_build_reply(
        contents=contents,
        chat_id=chat_id,
        tool_config=tool_config,
        function_calls=function_calls,
    )


def _execute_tool_calls_and_build_reply(
    *,
    contents: list[dict],
    chat_id: str,
    tool_config: dict,
    function_calls: list[dict],
) -> ModelReply:
    pending_calls = function_calls
    current_contents = list(contents)
    backend_messages: list[dict] = []

    while pending_calls:
        if len(pending_calls) > MAX_TOOL_CALLS_PER_TURN:
            tool_names = [str(call.get("name") or "") for call in pending_calls]
            logging_utils.log_prefixed_fields(
                "GEMINI_TOOL_VALIDATION_ERROR",
                ("chat_id", chat_id),
                ("count", len(pending_calls)),
                ("names", tool_names),
                ("detail", f"expected at most {MAX_TOOL_CALLS_PER_TURN} function calls"),
            )
            return {"type": "text", "text": MODEL_PROVIDER_UNAVAILABLE_MESSAGE}

        tool_results = _execute_tool_batch(chat_id=chat_id, function_calls=pending_calls)

        model_results: list[dict] = []
        for tool_result in tool_results:
            action = tool_result.get("next_action")
            if action == ACTION_TERMINAL_PROTOCOL:
                continue
            if action == ACTION_CONTINUE_WITH_MODEL:
                model_results.append(
                    {
                        "name": tool_result.get("name"),
                        "result": tool_result.get("result"),
                    }
                )
                continue
            if action == ACTION_CONTINUE_BACKEND:
                reply = gemini_decision_service._resolve_tool_decision(
                    client=_CLIENT,
                    model_name=_MODEL_NAME,
                    chat_id=chat_id,
                    contents=current_contents,
                    function_result={
                        "name": tool_result.get("name"),
                        "result": tool_result.get("result"),
                    },
                )
                if not reply:
                    continue
                if str(reply.get("type") or "") in {
                    "event_created",
                    "event_edit_preview",
                    "event_remove_preview",
                }:
                    return reply
                backend_messages.append(reply)

        if not model_results:
            return backend_messages[-1] if backend_messages else {"type": "text", "text": MODEL_PROVIDER_UNAVAILABLE_MESSAGE}

        current_contents = _build_multi_tool_follow_up_contents(
            current_contents,
            tool_results=model_results,
        )
        response = _CLIENT.models.generate_content(
            model=_MODEL_NAME,
            contents=current_contents,
            config=tool_config,
        )
        pending_calls = gemini_tools.extract_function_calls(response)
        if not pending_calls:
            return {
                "type": "text",
                "text": response.text or (
                    str(backend_messages[-1].get("text") or "")
                    if backend_messages
                    else MODEL_PROVIDER_UNAVAILABLE_MESSAGE
                ),
            }

        tool_names = [str(call.get("name") or "") for call in pending_calls]
        logging_utils.log_prefixed_fields(
            "GEMINI_TOOL_CALLS",
            ("chat_id", chat_id),
            ("count", len(pending_calls)),
            ("names", tool_names),
        )
    return backend_messages[-1] if backend_messages else {"type": "text", "text": MODEL_PROVIDER_UNAVAILABLE_MESSAGE}


def _execute_tool_batch(*, chat_id: str, function_calls: list[dict]) -> list[dict]:
    results: list[dict] = []
    for call in function_calls:
        function_name = str(call.get("name") or "")
        result = gemini_tool_executor.execute_tool_call(call, chat_id)
        results.append(
            {
                "name": call.get("name"),
                "result": result,
                "next_action": _resolve_next_action(function_name, result),
            }
        )
    return results


def _resolve_next_action(function_name: str, result: dict | None = None) -> str:
    if function_name in {
        gemini_tools.EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME,
        gemini_tools.EVENT_LOOKUP_BY_TITLE_TOOL_NAME,
    }:
        if _is_lookup_auth_error(result):
            return ACTION_CONTINUE_BACKEND
        return ACTION_CONTINUE_WITH_MODEL
    if function_name in {
        gemini_tools.EVENT_DRAFT_TOOL_NAME,
        gemini_tools.EVENT_EDIT_DRAFT_TOOL_NAME,
        gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
        gemini_tools.EVENT_REMOVE_PREVIEW_TOOL_NAME,
        gemini_tools.NEW_EVENT_DRAFT_TOOL_NAME,
    }:
        return ACTION_CONTINUE_BACKEND
    return ACTION_TERMINAL_PROTOCOL


def _is_lookup_auth_error(result: dict | None) -> bool:
    return gemini_decision_service.is_auth_connection_error(result)


def _build_multi_tool_follow_up_contents(
    contents: list[dict],
    tool_results: list[dict],
) -> list[dict]:
    results_json = json.dumps(tool_results, ensure_ascii=True)
    instruction = (
        "Tool calls were executed in order. Use this JSON result to continue:\n"
        f"{results_json}\n"
    )
    next_contents = list(contents)
    next_contents.append({"role": "user", "parts": [{"text": instruction}]})
    return next_contents


def _build_contents(history: list[dict], parts: list[dict]) -> list[dict]:
    contents = list(history)
    contents.append({"role": "user", "parts": parts})
    return contents


def _convert_history(history: Optional[ModelHistory]) -> list[dict]:
    converted: list[dict] = []
    if not history:
        return converted

    for turn in history:
        parts: list[dict] = []
        text = turn.get("text")
        if text:
            parts.append({"text": text})

        if not parts:
            continue

        role = "user" if turn.get("role") == "user" else "model"
        converted.append({"role": role, "parts": parts})
    return converted
