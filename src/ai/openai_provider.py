import asyncio
import os
from typing import Optional

from openai import OpenAI

from src.utils import logging_utils
from src.utils.constants import (
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
)
from .model_provider import ModelProvider, ModelHistory, ModelReply
from src.services import secret_service


def _convert_history(history: Optional[ModelHistory]) -> list[dict]:
    converted: list[dict] = []
    if not history:
        return converted

    for turn in history:
        content_parts: list[dict] = []

        text = turn.get("text")
        if text:
            content_parts.append({"type": "text", "text": text})

        if not content_parts:
            continue

        role = "user" if turn.get("role") == "user" else "assistant"
        converted.append(
            {
                "role": role,
                "content": content_parts,
            }
        )
    return converted


class OpenAIProvider(ModelProvider):
    def __init__(self):
        api_key = secret_service.get_secret("OPENAI_API_KEY")
        self._client = OpenAI(api_key=api_key)
        self._chat_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    async def generate_reply(
        self,
        prompt: str,
        chat_id: str,
        history: Optional[ModelHistory] = None,
    ) -> ModelReply:
        logging_utils.log_prefixed_fields(
            "Calling OpenAI.",
            ("PROMPT", prompt),
        )

        messages = _convert_history(history)
        content = [{"type": "text", "text": prompt}]
        messages.append({"role": "user", "content": content})

        try:
            response_text, _ = await asyncio.to_thread(self._send_completion, messages)
        except Exception as exc:
            print("OPENAI_CALL_ERROR:", repr(exc))
            return {"type": "text", "text": MODEL_PROVIDER_UNAVAILABLE_MESSAGE}

        return {"type": "text", "text": response_text}

    def _send_completion(self, messages: list[dict]) -> tuple[str, Optional[dict]]:
        response = self._client.chat.completions.create(
            model=self._chat_model,
            messages=messages,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = self._normalize_usage(getattr(response, "usage", None))
        if isinstance(content, list):
            combined = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
            return combined.strip() or "No response", usage
        return content.strip() or "No response", usage

    @staticmethod
    def _normalize_usage(usage) -> Optional[dict]:
        if usage is None:
            return None
        if isinstance(usage, dict):
            return usage
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        usage_dict = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if value is not None:
                usage_dict[key] = value
        return usage_dict or None
