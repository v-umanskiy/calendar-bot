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
from . import gemini_decision_service
from src.services import secret_service
from src.utils import datetime_utils


class GeminiProvider(ModelProvider):
    def __init__(self):
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._model_name = model_name
        self._client = genai.Client(api_key=secret_service.get_secret("GEMINI_API_KEY"))

    async def generate_reply(
        self,
        prompt: str,
        chat_id: str,
        history: Optional[ModelHistory] = None,
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
        chat_id: str,
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
            "tools": gemini_tools.EVENT_DRAFT_TOOLS,
        }
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=tool_config,
        )

        function_calls = gemini_tools.extract_function_calls(response)
        if not function_calls:
            return response.text or "No response"
        tool_names = [str(call.get("name") or "") for call in function_calls]
        logging_utils.log_prefixed_fields(
            "GEMINI_TOOL_CALLS",
            ("chat_id", chat_id),
            ("count", len(function_calls)),
            ("names", tool_names),
        )
        if len(function_calls) > 1:
            logging_utils.log_prefixed_fields(
                "GEMINI_TOOL_VALIDATION_ERROR",
                ("chat_id", chat_id),
                ("count", len(function_calls)),
                ("names", tool_names),
                ("detail", "expected at most one function call"),
            )
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

        reply = gemini_decision_service.call_tool_and_build_reply(
            client=self._client,
            model_name=self._model_name,
            contents=contents,
            chat_id=chat_id,
            function_call=function_calls[0],
            tool_config=tool_config,
        )
        if reply:
            return reply
        return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

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
