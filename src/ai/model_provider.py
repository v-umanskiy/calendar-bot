import os
from abc import ABC, abstractmethod
from typing import Optional

ModelHistory = list[dict]


class ModelProvider(ABC):
    @abstractmethod
    async def generate_reply(
        self,
        prompt: Optional[str] = None,
        history: Optional[ModelHistory] = None,
        file_bytes: Optional[bytes] = None,
        chat_id: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

_provider: ModelProvider | None = None


def get_model_provider() -> ModelProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider


def _build_provider() -> ModelProvider:
    provider_name = os.getenv("MODEL_PROVIDER", "gemini").strip().lower()
    if provider_name == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()

    from .gemini_provider import GeminiProvider

    return GeminiProvider()
