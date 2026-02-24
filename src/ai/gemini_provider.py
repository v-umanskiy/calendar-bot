import asyncio
import os
from typing import Optional

from google.api_core import exceptions as google_api_exceptions
from google import genai

from src.utils import logging_utils
from src.utils.constants import (
    MODEL_PROVIDER_LIMIT_REACHED_MESSAGE,
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
)
from .model_provider import ModelProvider, ModelHistory
from . import gemini_tools
from src.services import secret_service

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
        if prompt_text:
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
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=gemini_tools.EVENT_DRAFT_TOOL_CONFIG,
        )
        usage = self._extract_usage(response)
        function_calls = gemini_tools.extract_function_calls(response)
        if not function_calls:
            return response.text or "No response", usage

        function_results = gemini_tools.execute_function_calls(function_calls, chat_id)
        upsert_result = gemini_tools.find_upsert_result(function_results)
        if upsert_result and upsert_result.get("ok"):
            missing_required = upsert_result.get("missing_required") or []
            invalid_fields = upsert_result.get("invalid_fields") or []
            if not missing_required and not invalid_fields:
                return gemini_tools.build_complete_draft_summary(upsert_result.get("draft") or {}), usage

        follow_up_response = self._client.models.generate_content(
            model=self._model_name,
            contents=self._build_follow_up_contents(contents, function_results),
        )
        follow_up_text = follow_up_response.text or ""
        if follow_up_text:
            return follow_up_text, usage
        return response.text or "No response", usage

    @staticmethod
    def _build_follow_up_contents(contents: list[dict], function_results: list[dict]) -> list[dict]:
        follow_up_instruction = (
            "Tool calls were executed. Use this JSON result to continue the conversation:\n"
            f"{gemini_tools.tool_results_to_json(function_results)}\n\n"
            "If missing_required has entries, ask the user only for those missing mandatory fields.\n"
            "If invalid_fields has entries, ask user to correct those exact fields.\n"
            "Be concise and ask only one focused follow-up question when possible.\n"
            "Do not mention internal tools."
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
