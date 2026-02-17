import asyncio
import base64
import os
from typing import Optional

from openai import OpenAI

from src.utils import logging_utils
from src.utils.constants import (
    CLASSIFICATION_PROMPT_TEMPLATE,
    MODEL_PROVIDER_UNAVAILABLE_MESSAGE,
)
from src.utils.classifier_utils import parse_classifier_response
from .model_provider import ModelProvider, ModelHistory
from src.services import langfuse_service
from src.services import secret_service


def _image_content_from_bytes(file_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    encoded = base64.b64encode(file_bytes).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
    }


def _convert_history(history: Optional[ModelHistory]) -> list[dict]:
    converted: list[dict] = []
    if not history:
        return converted

    for turn in history:
        content_parts: list[dict] = []

        text = turn.get("text")
        if text:
            content_parts.append({"type": "text", "text": text})

        for file_entry in turn.get("files", []) or []:
            data = file_entry.get("data") if isinstance(file_entry, dict) else None
            if not data:
                continue
            mime_type = file_entry.get("mime_type", "image/jpeg") if isinstance(file_entry, dict) else "image/jpeg"
            content_parts.append(_image_content_from_bytes(data, mime_type))

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
        self._classifier_model = os.getenv("OPENAI_CLASSIFIER_MODEL", self._chat_model)

    async def generate_reply(
        self,
        prompt: Optional[str] = None,
        history: Optional[ModelHistory] = None,
        file_bytes: Optional[bytes] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        prompt_text = prompt or ""
        logging_utils.log_prefixed_fields(
            "Calling OpenAI.",
            ("PROMPT", prompt_text),
            ("HAS_FILE", bool(file_bytes)),
        )

        messages = _convert_history(history)
        content = []
        if prompt_text:
            content.append({"type": "text", "text": prompt_text})
        if file_bytes:
            content.append(_image_content_from_bytes(file_bytes))
        if not content:
            content.append({"type": "text", "text": ""})
        messages.append({"role": "user", "content": content})

        metadata = {"history_length": len(history or [])}
        try:
            with langfuse_service.generation_context(
                name="openai.generate_reply",
                model=self._chat_model,
                input={"prompt": prompt_text, "has_file": bool(file_bytes)},
                metadata=metadata,
                tags=["openai", "chat"],
            ) as generation:
                response_text, usage = await asyncio.to_thread(self._send_completion, messages)
                generation.record_output(response_text, usage=usage)
        except Exception as exc:
            print("OPENAI_CALL_ERROR:", repr(exc))
            return MODEL_PROVIDER_UNAVAILABLE_MESSAGE

        return response_text

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

    async def classify_user_message(self, message: str) -> str:
        prompt = CLASSIFICATION_PROMPT_TEMPLATE + (message or "")
        logging_utils.log_prefixed_fields(
            "Calling OpenAI classifier.",
            ("PROMPT", prompt),
        )

        payload = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
        try:
            with langfuse_service.generation_context(
                name="openai.classify",
                model=self._classifier_model,
                input=prompt,
                tags=["openai", "classifier"],
            ) as generation:
                response_text, usage = await asyncio.to_thread(self._send_completion, payload)
                generation.record_output(response_text, usage=usage)
        except Exception as exc:
            print("OPENAI_CLASSIFY_CALL_ERROR:", repr(exc))
            return "other"

        logging_utils.log_prefixed_message(
            "OpenAI classifier raw response",
            response_text,
        )
        return parse_classifier_response(response_text)
