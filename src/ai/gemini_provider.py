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
        prompt: Optional[str] = None,
        history: Optional[ModelHistory] = None,
        file_bytes: Optional[bytes] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        gemini_history = self._convert_history(history)
        try:
            if file_bytes:
                return await self._call_with_photo(file_bytes, prompt, history, gemini_history)
            return await self._call_with_text(prompt or "", history, gemini_history, chat_id=chat_id)
        except (
            google_api_exceptions.ResourceExhausted,
            google_api_exceptions.TooManyRequests,
        ) as err:
            print(f"Gemini API quota exhausted: {err}")
            return MODEL_PROVIDER_LIMIT_REACHED_MESSAGE
        except Exception as exc:
            print("GEMINI_CALL_ERROR:", repr(exc))
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

    async def _call_with_text(
        self,
        prompt: str,
        raw_history: Optional[ModelHistory],
        gemini_history: list[dict],
        *,
        chat_id: Optional[str],
    ) -> str:
        self._log_call(prompt, raw_history)
        contents = self._build_contents(gemini_history, [{"text": prompt}])
        response, _ = await asyncio.to_thread(self._run_with_tools, contents, chat_id)
        return response

    async def _call_with_photo(
        self,
        file_bytes: bytes,
        prompt: Optional[str],
        raw_history: Optional[ModelHistory],
        gemini_history: list[dict],
    ) -> str:
        self._log_call(prompt, raw_history, is_photo=True)
        parts: list[dict] = []
        prompt_text = prompt or ""
        parts.append({"text": prompt_text})
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": file_bytes,
            }
        })
        contents = self._build_contents(gemini_history, parts)
        response, _ = await asyncio.to_thread(self._send_to_gemini, contents)
        return response

    def _log_call(
        self,
        prompt: Optional[str],
        history: Optional[ModelHistory],
        *,
        is_photo: bool = False,
    ) -> None:
        prefix = "Calling Gemini with photo." if is_photo else "Calling Gemini."
        logging_utils.log_prefixed_fields(
            prefix,
            ("PROMPT", prompt),
            ("HISTORY", history),
        )

    def _send_to_gemini(self, contents: list[dict]) -> tuple[str, Optional[dict]]:
        self._log_prompts(contents, config=None, stage="plain")
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
        )
        return response.text or "No response", self._extract_usage(response)

    def _run_with_tools(
        self,
        contents: list[dict],
        chat_id: Optional[str],
    ) -> tuple[str, Optional[dict]]:
        tool_config = gemini_tools.build_event_draft_tool_config(datetime_utils.current_time_context_block())
        self._log_prompts(contents, config=tool_config, stage="tool_call")
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=tool_config,
        )
        usage = self._extract_usage(response)
        function_calls = gemini_tools.extract_function_calls(response)
        if not function_calls:
            return response.text or "No response", usage
        if len(function_calls) > 1:
            print("GEMINI_TOOL_VALIDATION_ERROR: expected at most one function call")
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE, usage

        event_draft_tool_name = function_calls[0].get("name")
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
                    return MODEL_PROVIDER_UNAVAILABLE_MESSAGE, usage
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
                        return EVENT_RECONNECT_REQUIRED_MESSAGE, usage
                    return EVENT_SAVE_FAILED_MESSAGE, usage
                summary = EVENT_SAVE_SUCCESS_MESSAGE_TEMPLATE.format(
                    title=str(draft.get("title") or ""),
                    start=str(draft.get("start") or ""),
                    end=str(draft.get("end") or ""),
                )
                return gemini_tools.build_event_created_reply(
                    summary,
                    str(create_result.get("calendar_id") or "primary"),
                    str(create_result.get("google_event_id") or ""),
                ), usage
            if invalid_fields:
                follow_up_contents = self._build_invalid_follow_up_contents(contents, function_results)
                self._log_prompts(follow_up_contents, config=None, stage="invalid_follow_up")
                follow_up_response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=follow_up_contents,
                )
                follow_up_text = follow_up_response.text or ""
                if follow_up_text:
                    return follow_up_text, usage
            elif missing_required:
                follow_up_contents = self._build_missing_follow_up_contents(contents, function_results)
                self._log_prompts(follow_up_contents, config=None, stage="missing_follow_up")
                follow_up_response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=follow_up_contents,
                )
                follow_up_text = follow_up_response.text or ""
                if follow_up_text:
                    return follow_up_text, usage

        fallback_contents = self._build_missing_follow_up_contents(contents, function_results)
        self._log_prompts(fallback_contents, config=None, stage="fallback_follow_up")
        follow_up_response = self._client.models.generate_content(
            model=self._model_name,
            contents=fallback_contents,
        )
        follow_up_text = follow_up_response.text or ""
        if follow_up_text:
            return follow_up_text, usage
        return response.text or "No response", usage

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
            self._log_prompts(repair_contents, config=tool_config, stage="repair")
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

    def _log_prompts(self, contents: list[dict], config: Optional[dict], *, stage: str) -> None:
        user_prompt = self._extract_last_user_prompt(contents)
        system_prompt = self._extract_system_prompt(config)
        logging_utils.log_prefixed_fields_full(
            "LLM_PROMPT",
            ("STAGE", stage),
            ("SYSTEM_PROMPT", self._trim_prompt_for_log(system_prompt)),
            ("USER_PROMPT", self._trim_prompt_for_log(user_prompt)),
        )

    @staticmethod
    def _extract_last_user_prompt(contents: list[dict]) -> str:
        for item in reversed(contents):
            if not isinstance(item, dict):
                continue
            if item.get("role") != "user":
                continue
            parts = item.get("parts")
            if not isinstance(parts, list):
                continue
            text_parts: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    text_parts.append(text)
            if text_parts:
                return "\n\n".join(text_parts)
        return ""

    @staticmethod
    def _extract_system_prompt(config: Optional[dict]) -> str:
        if not isinstance(config, dict):
            return ""
        value = config.get("systemInstruction")
        if isinstance(value, str):
            return value
        return ""

    @staticmethod
    def _trim_prompt_for_log(value: str) -> str:
        if len(value) <= PROMPT_LOG_MAX_CHARS:
            return value
        omitted = len(value) - PROMPT_LOG_MAX_CHARS
        return f"{value[:PROMPT_LOG_MAX_CHARS]}\n...[trimmed {omitted} chars]"

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

    @staticmethod
    def _extract_usage(response) -> Optional[dict]:
        usage_metadata = getattr(response, "usage_metadata", None)
        if not usage_metadata:
            return None
        if isinstance(usage_metadata, dict):
            prompt_tokens = usage_metadata.get("prompt_token_count")
            completion_tokens = usage_metadata.get("candidates_token_count")
            total_tokens = usage_metadata.get("total_token_count")
        else:
            prompt_tokens = getattr(usage_metadata, "prompt_token_count", None)
            completion_tokens = getattr(usage_metadata, "candidates_token_count", None)
            total_tokens = getattr(usage_metadata, "total_token_count", None)
        usage = {}
        if prompt_tokens is not None:
            usage["prompt_tokens"] = prompt_tokens
        if completion_tokens is not None:
            usage["completion_tokens"] = completion_tokens
        if total_tokens is not None:
            usage["total_tokens"] = total_tokens
        return usage or None

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

            for file_entry in turn.get("files", []):
                data = file_entry.get("data")
                if not data:
                    continue
                mime_type = file_entry.get("mime_type", "image/jpeg")
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": data,
                    }
                })

            if not parts:
                continue

            role = "user" if turn.get("role") == "user" else "model"
            converted.append({"role": role, "parts": parts})
        return converted
