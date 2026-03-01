import asyncio
import os
from typing import Optional

from google.api_core import exceptions as google_api_exceptions
from google import genai

from src.utils import logging_utils
from src.utils.constants import (
    MODEL_PROVIDER_LIMIT_REACHED_MESSAGE,
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
    EVENT_SAVE_SUCCESS_MESSAGE_TEMPLATE,
    EVENT_SAVE_FAILED_MESSAGE,
    EVENT_RECONNECT_REQUIRED_MESSAGE,
)
from .model_provider import ModelProvider, ModelHistory
from . import gemini_tools
from src.services import secret_service
from src.services import google_calendar_service
from src.utils import datetime_utils


MAX_INVALID_REPAIR_ATTEMPTS = 2
PROMPT_LOG_MAX_CHARS = int(os.getenv("PROMPT_LOG_MAX_CHARS", "12000"))


class GeminiProvider(ModelProvider):
    def __init__(self):
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._model_name = model_name
        self._client = genai.Client(api_key=secret_service.get_secret("GEMINI_API_KEY"))

    async def generate_reply(
        self,
        prompt: str,
        history: Optional[ModelHistory] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        gemini_history = self._convert_history(history)
        contents = self._build_contents(gemini_history, [{"text": prompt}])
        try:
            return await asyncio.to_thread(
                self._run_with_tools,
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
            return MODEL_PROVIDER_LIMIT_REACHED_MESSAGE
        except Exception as exc:
            print("GEMINI_CALL_ERROR:", repr(exc))
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

    def _run_with_tools(
        self,
        contents: list[dict],
        chat_id: Optional[str],
        prompt: str,
        raw_history: Optional[ModelHistory],
    ) -> str:
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
            "tools": gemini_tools.EVENT_DRAFT_TOOL_CONFIG["tools"],
        }
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=tool_config,
        )
        function_calls = gemini_tools.extract_function_calls(response)
        if not function_calls:
            return response.text or "No response"
        if len(function_calls) > 1:
            print("GEMINI_TOOL_VALIDATION_ERROR: expected at most one function call")
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

        function_results = gemini_tools.execute_function_calls(function_calls, chat_id)
        event_draft_result = gemini_tools.find_event_draft_result(function_results)
        if event_draft_result and event_draft_result.get("ok"):
            function_results, event_draft_result = self._repair_invalid_result_if_needed(
                contents,
                chat_id,
                function_results,
                event_draft_result,
                tool_config,
            )

        if event_draft_result and event_draft_result.get("ok"):
            missing_required = event_draft_result.get("missing_required") or []
            invalid_fields = event_draft_result.get("invalid_fields") or []
            if not missing_required and not invalid_fields:
                draft = event_draft_result.get("draft") or {}
                if chat_id is None:
                    return MODEL_PROVIDER_UNAVAILABLE_MESSAGE
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
            if invalid_fields:
                follow_up_contents = self._build_invalid_follow_up_contents(contents, function_results)
                follow_up_response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=follow_up_contents,
                )
                follow_up_text = follow_up_response.text or ""
                if follow_up_text:
                    return follow_up_text
            elif missing_required:
                follow_up_contents = self._build_missing_follow_up_contents(contents, function_results)
                follow_up_response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=follow_up_contents,
                )
                follow_up_text = follow_up_response.text or ""
                if follow_up_text:
                    return follow_up_text

        fallback_contents = self._build_missing_follow_up_contents(contents, function_results)
        follow_up_response = self._client.models.generate_content(
            model=self._model_name,
            contents=fallback_contents,
        )
        follow_up_text = follow_up_response.text or ""
        if follow_up_text:
            return follow_up_text
        return response.text or "No response"

    def _repair_invalid_result_if_needed(
        self,
        contents: list[dict],
        chat_id: Optional[str],
        function_results: list[dict],
        event_draft_result: dict,
        tool_config: dict,
    ) -> tuple[list[dict], dict]:
        current_results = function_results
        current_event_draft_result = event_draft_result

        for _ in range(MAX_INVALID_REPAIR_ATTEMPTS):
            invalid_fields = current_event_draft_result.get("invalid_fields") or []
            if not invalid_fields:
                break

            repair_contents = self._build_invalid_repair_contents(contents, current_results)
            repair_response = self._client.models.generate_content(
                model=self._model_name,
                contents=repair_contents,
                config=tool_config,
            )
            repair_calls = gemini_tools.extract_function_calls(repair_response)
            if not repair_calls:
                break
            if len(repair_calls) > 1:
                print("GEMINI_TOOL_VALIDATION_ERROR: expected at most one repair function call")
                break

            current_results = gemini_tools.execute_function_calls([repair_calls[0]], chat_id)
            next_event_draft_result = gemini_tools.find_event_draft_result(current_results)
            if not next_event_draft_result or not next_event_draft_result.get("ok"):
                break
            current_event_draft_result = next_event_draft_result

        return current_results, current_event_draft_result

    @staticmethod
    def _build_invalid_repair_contents(contents: list[dict], function_results: list[dict]) -> list[dict]:
        repair_instruction = (
            "Tool call results indicate invalid_fields. This is your formatting/normalization failure.\n"
            f"Tool results JSON:\n{gemini_tools.tool_results_to_json(function_results)}\n\n"
            "Try to correct invalid fields to RFC3339 datetime and call the relevant event draft tool again.\n"
            "Only include corrected values for invalid fields.\n"
            "If you cannot confidently normalize from context, do not guess; ask the user a concise clarification question."
        )
        updated_contents = list(contents)
        updated_contents.append({"role": "user", "parts": [{"text": repair_instruction}]})
        return updated_contents

    @staticmethod
    def _build_missing_follow_up_contents(contents: list[dict], function_results: list[dict]) -> list[dict]:
        follow_up_instruction = (
            "Tool calls were executed. Use this JSON result to continue the conversation:\n"
            f"{gemini_tools.tool_results_to_json(function_results)}\n\n"
            "If missing_required has entries, ask the user only for those missing mandatory fields.\n"
            "Be concise and ask only one focused follow-up question when possible.\n"
            "Do not mention internal tools."
        )
        updated_contents = list(contents)
        updated_contents.append({"role": "user", "parts": [{"text": follow_up_instruction}]})
        return updated_contents

    @staticmethod
    def _build_invalid_follow_up_contents(contents: list[dict], function_results: list[dict]) -> list[dict]:
        follow_up_instruction = (
            "Tool calls were executed. Use this JSON result to continue the conversation:\n"
            f"{gemini_tools.tool_results_to_json(function_results)}\n\n"
            "invalid_fields are still present after normalization attempts.\n"
            "Ask a neutral clarification question for explicit date/time.\n"
            "Do not blame the user and do not mention internal tools.\n"
            "Be concise and ask only one focused follow-up question."
        )
        updated_contents = list(contents)
        updated_contents.append({"role": "user", "parts": [{"text": follow_up_instruction}]})
        return updated_contents

    def _build_contents(self, history: list[dict], parts: list[dict]) -> list[dict]:
        contents = list(history)
        contents.append({"role": "user", "parts": parts})
        return contents

    def _convert_history(self, history: Optional[ModelHistory]) -> list[dict]:
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
