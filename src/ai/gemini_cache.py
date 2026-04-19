import os
import threading
import time
from datetime import datetime, timezone

from src.utils import logging_utils

_CACHE_TTL_SECONDS = int(os.getenv("GEMINI_CONTEXT_CACHE_TTL_SECONDS", "3600"))
_CACHE_ID: str | None = None
_CACHE_EXPIRES_AT: float | None = None
_CACHE_LOCK = threading.Lock()


def _create_cache(*, client, model_name: str, system_instruction: str, tools: list[dict]) -> str:
    global _CACHE_ID, _CACHE_EXPIRES_AT

    cache = client.caches.create(
        model=f"models/{model_name}",
        config={
            "display_name": "tg-calendar-bot-static-context",
            "system_instruction": system_instruction,
            "tools": tools,
            "ttl": f"{_CACHE_TTL_SECONDS}s",
        },
    )
    _CACHE_ID = str(cache.name)
    expire_time = getattr(cache, "expire_time", None)
    if isinstance(expire_time, datetime):
        dt = expire_time.astimezone(timezone.utc) if expire_time.tzinfo else expire_time.replace(tzinfo=timezone.utc)
        _CACHE_EXPIRES_AT = dt.timestamp()
    else:
        _CACHE_EXPIRES_AT = time.time() + _CACHE_TTL_SECONDS
    logging_utils.log_prefixed_fields(
        "GEMINI_CACHE_CREATE",
        ("cache_id", _CACHE_ID),
        ("expires_at_epoch", _CACHE_EXPIRES_AT),
        ("ttl_seconds", _CACHE_TTL_SECONDS),
    )
    return _CACHE_ID


def _ensure_cache_id(
    *,
    client,
    model_name: str,
    system_instruction: str,
    tools: list[dict],
    force_recreate: bool = False,
) -> str:
    global _CACHE_ID

    with _CACHE_LOCK:
        now = time.time()
        is_expired = _CACHE_EXPIRES_AT is not None and now >= _CACHE_EXPIRES_AT
        if force_recreate:
            return _create_cache(
                client=client,
                model_name=model_name,
                system_instruction=system_instruction,
                tools=tools,
            )
        if _CACHE_ID and not is_expired:
            logging_utils.log_prefixed_fields(
                "GEMINI_CACHE_REUSE",
                ("cache_id", _CACHE_ID),
                ("expires_at_epoch", _CACHE_EXPIRES_AT),
            )
            return _CACHE_ID
        return _create_cache(
            client=client,
            model_name=model_name,
            system_instruction=system_instruction,
            tools=tools,
        )


def _is_cache_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "cached" in text and (
        "not found" in text
        or "expired" in text
        or "invalid" in text
        or "failed precondition" in text
    )


def generate_with_cached_context(
    *,
    client,
    model_name: str,
    contents: list[dict],
    system_instruction: str,
    tools: list[dict],
):
    cache_id = _ensure_cache_id(
        client=client,
        model_name=model_name,
        system_instruction=system_instruction,
        tools=tools,
    )
    try:
        return client.models.generate_content(
            model=model_name,
            contents=contents,
            config={"cached_content": cache_id},
        )
    except Exception as exc:
        if not _is_cache_error(exc):
            raise
        logging_utils.log_prefixed_fields(
            "GEMINI_CACHE_RECREATE_ON_ERROR",
            ("error", repr(exc)),
            ("cache_id", cache_id),
        )
        new_cache_id = _ensure_cache_id(
            client=client,
            model_name=model_name,
            system_instruction=system_instruction,
            tools=tools,
            force_recreate=True,
        )
        return client.models.generate_content(
            model=model_name,
            contents=contents,
            config={"cached_content": new_cache_id},
        )
