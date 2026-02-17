import asyncio
import os
import threading
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

from langfuse import Langfuse

from . import secret_service

_client: Optional[Langfuse] = None
_trace_var: ContextVar[Any] = ContextVar("langfuse_trace", default=None)
_client_init_logged = False
_client_disabled_logged = False
_UNSET = object()


def _langfuse_enabled() -> bool:
    value = os.getenv(" ")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _build_client() -> Optional[Langfuse]:
    global _client_init_logged
    global _client_disabled_logged
    if not _langfuse_enabled():
        if not _client_disabled_logged:
            print("Langfuse disabled via LANGFUSE_ENABLED")
            _client_disabled_logged = True
        return None
    public_key = secret_service.get_secret("LANGFUSE_PUBLIC_KEY")
    secret_key = secret_service.get_secret("LANGFUSE_SECRET_KEY")
    host = secret_service.get_secret("LANGFUSE_BASE_URL")
    if not public_key or not secret_key:
        if not _client_init_logged:
            print("Langfuse disabled: missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY")
            _client_init_logged = True
        return None

    kwargs = {"public_key": public_key, "secret_key": secret_key}
    if host:
        kwargs["host"] = host
    if not _client_init_logged:
        try:
            from importlib import metadata as importlib_metadata

            version = importlib_metadata.version("langfuse")
        except Exception:
            version = "unknown"
        print(f"Langfuse init: host={host or 'default'}, sdk={version}")
        _client_init_logged = True
    return Langfuse(**kwargs)


def get_client() -> Optional[Langfuse]:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def get_current_trace():
    return _trace_var.get()


def _safe_update(obj, **kwargs) -> None:
    if not obj:
        return
    try:
        obj.update(**kwargs)
    except TypeError:
        if "metadata" in kwargs:
            try:
                obj.update(metadata=kwargs.get("metadata"))
            except Exception:
                pass


def _merge_metadata(kwargs: dict) -> dict:
    metadata = dict(kwargs.get("metadata") or {})
    for key in ("user_id", "session_id", "tags", "status"):
        value = kwargs.get(key)
        if value is not None:
            metadata[key] = value
    return metadata


def start_trace(
    name: str,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    input: Any = None,
    metadata: Optional[dict] = None,
    tags: Optional[list[str]] = None,
):
    client = get_client()
    if not client:
        return None
    merged_metadata = dict(metadata or {})
    if user_id:
        merged_metadata["user_id"] = user_id
    if session_id:
        merged_metadata["session_id"] = session_id
    if tags:
        merged_metadata["tags"] = tags

    trace = client.start_span(
        name=name,
        input=input,
        metadata=merged_metadata or None,
    )
    if trace is None:
        print("Langfuse trace not created: start_span returned None")
    else:
        try:
            trace_id = getattr(trace, "id", None)
        except Exception:
            trace_id = None
        print(f"Langfuse trace started: id={trace_id}")
    _trace_var.set(trace)
    return trace


def update_trace(trace, **kwargs) -> None:
    if not trace:
        return
    metadata = _merge_metadata(kwargs)
    output = kwargs.get("output")
    _safe_update(trace, output=output, metadata=metadata)


def end_trace(trace, **kwargs) -> None:
    if not trace:
        return
    metadata = _merge_metadata(kwargs)
    output = kwargs.get("output")
    _safe_update(trace, output=output, metadata=metadata)
    end_time = kwargs.get("end_time")

    def _finish_trace() -> None:
        try:
            if end_time is not None:
                trace.end(end_time=end_time)
            else:
                trace.end()
            client = get_client()
            if client:
                try:
                    client.flush()
                except Exception:
                    pass
            try:
                trace_id = getattr(trace, "id", None)
            except Exception:
                trace_id = None
            print(f"Langfuse trace ended: id={trace_id}")
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and not loop.is_closed():
        loop.create_task(asyncio.to_thread(_finish_trace))
    else:
        threading.Thread(target=_finish_trace, daemon=True).start()
    _trace_var.set(None)


def _flush_client_nonblocking(client: Langfuse) -> None:
    def _flush() -> None:
        try:
            client.flush()
        except Exception:
            pass

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and not loop.is_closed():
        loop.create_task(asyncio.to_thread(_flush))
    else:
        threading.Thread(target=_flush, daemon=True).start()


def record_generation(
    name: str,
    *,
    model: Optional[str] = None,
    input: Any = None,
    output: Any = None,
    metadata: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    usage: Optional[dict] = None,
) -> None:
    trace = get_current_trace()
    if not trace:
        return
    merged_metadata = dict(metadata or {})
    if tags:
        merged_metadata["tags"] = tags
    usage_details = _normalize_usage_details(usage)
    generation = trace.start_generation(
        name=name,
        model=model,
        input=input,
        metadata=merged_metadata or None,
    )
    if output is not None:
        _safe_update(generation, output=output, usage_details=usage_details)
    elif usage_details:
        _safe_update(generation, usage_details=usage_details)
    try:
        generation.end()
    except Exception:
        pass


def start_generation(
    name: str,
    *,
    model: Optional[str] = None,
    input: Any = None,
    metadata: Optional[dict] = None,
    tags: Optional[list[str]] = None,
):
    trace = get_current_trace()
    if not trace:
        return None
    merged_metadata = dict(metadata or {})
    if tags:
        merged_metadata["tags"] = tags
    return trace.start_generation(
        name=name,
        model=model,
        input=input,
        metadata=merged_metadata or None,
    )


def end_generation(
    generation,
    *,
    output: Any = None,
    metadata: Optional[dict] = None,
    usage: Optional[dict] = None,
    error: Optional[Exception] = None,
) -> None:
    if not generation:
        return
    merged_metadata = dict(metadata or {})
    if error is not None:
        merged_metadata["error"] = repr(error)
    usage_details = _normalize_usage_details(usage)
    _safe_update(
        generation,
        output=output,
        metadata=merged_metadata or None,
        usage_details=usage_details,
    )
    try:
        generation.end()
    except Exception:
        pass


class GenerationContext:
    def __init__(
        self,
        name: str,
        *,
        model: Optional[str] = None,
        input: Any = None,
        metadata: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> None:
        self._name = name
        self._model = model
        self._input = input
        self._metadata = dict(metadata or {})
        self._tags = tags
        self._output: Any = _UNSET
        self._usage: Optional[dict] = None
        self._generation = None

    def __enter__(self):
        self._generation = start_generation(
            name=self._name,
            model=self._model,
            input=self._input,
            metadata=self._metadata or None,
            tags=self._tags,
        )
        return self

    def record_output(
        self,
        output: Any = _UNSET,
        *,
        metadata: Optional[dict] = None,
        usage: Optional[dict] = None,
    ) -> None:
        if output is not _UNSET:
            self._output = output
        if metadata:
            self._metadata.update(metadata)
        if usage:
            self._usage = usage

    def __exit__(self, exc_type, exc, tb):
        metadata = self._metadata or None
        if exc is not None:
            end_generation(
                self._generation,
                metadata=metadata,
                usage=self._usage,
                error=exc,
            )
            return False

        output = None if self._output is _UNSET else self._output
        end_generation(
            self._generation,
            output=output,
            metadata=metadata,
            usage=self._usage,
        )
        return False


def _normalize_usage_details(usage: Optional[dict]) -> Optional[dict]:
    if not usage:
        return None
    if "input" in usage or "output" in usage:
        return usage
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    usage_details = {}
    if prompt is not None:
        usage_details["input"] = prompt
    if completion is not None:
        usage_details["output"] = completion
    if total is not None:
        usage_details["total"] = total
    return usage_details or None


def generation_context(
    name: str,
    *,
    model: Optional[str] = None,
    input: Any = None,
    metadata: Optional[dict] = None,
    tags: Optional[list[str]] = None,
) -> GenerationContext:
    return GenerationContext(
        name=name,
        model=model,
        input=input,
        metadata=metadata,
        tags=tags,
    )


def record_generation_timed(
    name: str,
    *,
    model: Optional[str] = None,
    input: Any = None,
    output: Any = None,
    metadata: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    start_time: Optional[datetime] = None,
    usage: Optional[dict] = None,
) -> None:
    record_generation(
        name=name,
        model=model,
        input=input,
        output=output,
        metadata=metadata,
        tags=tags,
        start_time=start_time or now_utc(),
        end_time=now_utc(),
        usage=usage,
    )


def record_span(
    name: str,
    *,
    input: Any = None,
    output: Any = None,
    metadata: Optional[dict] = None,
    tags: Optional[list[str]] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> None:
    trace = get_current_trace()
    if not trace:
        return
    merged_metadata = dict(metadata or {})
    if tags:
        merged_metadata["tags"] = tags
    span = trace.start_span(
        name=name,
        input=input,
        metadata=merged_metadata or None,
    )
    if output is not None:
        _safe_update(span, output=output)
    try:
        span.end()
    except Exception:
        pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
