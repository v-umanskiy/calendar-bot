import asyncio
import json
import os
from typing import Optional

from google.api_core import exceptions as google_api_exceptions
from google import genai

from src.utils import logging_utils
from src.utils.constants import (
    EVENT_CREATED_REPLY_PREFIX,
    MODEL_PROVIDER_LIMIT_REACHED_MESSAGE,
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
)
from .model_provider import ModelProvider, ModelHistory
from . import gemini_tools
from . import gemini_decision_service
from . import gemini_tool_executor
from src.services import secret_service
from src.utils import datetime_utils

MAX_TOOL_CALLS_PER_TURN = 5
ACTION_CONTINUE_WITH_MODEL = "continue_with_model"
ACTION_CONTINUE_BACKEND = "continue_backend"
ACTION_TERMINAL_PROTOCOL = "terminal_protocol"


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
        if len(function_calls) > MAX_TOOL_CALLS_PER_TURN:
            logging_utils.log_prefixed_fields(
                "GEMINI_TOOL_VALIDATION_ERROR",
                ("chat_id", chat_id),
                ("count", len(function_calls)),
                ("names", tool_names),
                ("detail", f"expected at most {MAX_TOOL_CALLS_PER_TURN} function calls"),
            )
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

        return self._execute_tool_calls_and_build_reply(
            contents=contents,
            chat_id=chat_id,
            tool_config=tool_config,
            function_calls=function_calls,
        )

    def _execute_tool_calls_and_build_reply(
        self,
        *,
        contents: list[dict],
        chat_id: str,
        tool_config: dict,
        function_calls: list[dict],
    ) -> str:
        pending_calls = function_calls
        current_contents = list(contents)
        backend_messages: list[str] = []

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
                return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

            tool_results = self._execute_tool_batch(chat_id=chat_id, function_calls=pending_calls)

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
                        client=self._client,
                        model_name=self._model_name,
                        chat_id=chat_id,
                        contents=current_contents,
                        function_result={
                            "name": tool_result.get("name"),
                            "result": tool_result.get("result"),
                        },
                    )
                    if not reply:
                        continue
                    if str(reply).startswith(EVENT_CREATED_REPLY_PREFIX):
                        return reply
                    backend_messages.append(str(reply))

            if not model_results:
                return backend_messages[-1] if backend_messages else MODEL_PROVIDER_UNAVAILABLE_MESSAGE

            current_contents = self._build_multi_tool_follow_up_contents(
                current_contents,
                tool_results=model_results,
            )
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=current_contents,
                config=tool_config,
            )
            pending_calls = gemini_tools.extract_function_calls(response)
            if not pending_calls:
                return response.text or (backend_messages[-1] if backend_messages else MODEL_PROVIDER_UNAVAILABLE_MESSAGE)

            tool_names = [str(call.get("name") or "") for call in pending_calls]
            logging_utils.log_prefixed_fields(
                "GEMINI_TOOL_CALLS",
                ("chat_id", chat_id),
                ("count", len(pending_calls)),
                ("names", tool_names),
            )
        return backend_messages[-1] if backend_messages else MODEL_PROVIDER_UNAVAILABLE_MESSAGE

    def _execute_tool_batch(self, *, chat_id: str, function_calls: list[dict]) -> list[dict]:
        return [
            {
                "name": call.get("name"),
                "result": gemini_tool_executor.execute_tool_call(call, chat_id),
                "next_action": self._resolve_next_action(str(call.get("name") or "")),
            }
            for call in function_calls
        ]

    def _resolve_next_action(self, function_name: str) -> str:
        if function_name in {
            gemini_tools.EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME,
            gemini_tools.EVENT_LOOKUP_BY_TITLE_TOOL_NAME,
            gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
        }:
            return ACTION_CONTINUE_WITH_MODEL
        if function_name in {
            gemini_tools.EVENT_DRAFT_TOOL_NAME,
            gemini_tools.EVENT_EDIT_DRAFT_TOOL_NAME,
            gemini_tools.NEW_EVENT_DRAFT_TOOL_NAME,
        }:
            return ACTION_CONTINUE_BACKEND
        return ACTION_TERMINAL_PROTOCOL

    def _build_multi_tool_follow_up_contents(
        self,
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
