import httpx
from typing import Any

LOG_STRING_LENGTH_LIMIT = 1000


def sanitize_for_logging(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        truncated = value[:LOG_STRING_LENGTH_LIMIT]
        suffix = "..." if len(value) > LOG_STRING_LENGTH_LIMIT else ""
        return f"<{type(value).__name__} len={len(value)} data={truncated!r}{suffix}>"

    if isinstance(value, str):
        if len(value) <= LOG_STRING_LENGTH_LIMIT:
            return value
        truncated = value[:LOG_STRING_LENGTH_LIMIT]
        suffix = "..." if len(value) > LOG_STRING_LENGTH_LIMIT else ""
        return f"<str len={len(value)} data={truncated!r}{suffix}>"

    if isinstance(value, list):
        return [sanitize_for_logging(item) for item in value]

    if isinstance(value, dict):
        return {key: sanitize_for_logging(val) for key, val in value.items()}

    return value


def log_http_result(prefix: str, response: httpx.Response) -> None:
    try:
        data = response.json()
    except Exception:
        data = response.text

    body = sanitize_for_logging(data)
    status = "OK" if response.is_success else "ERROR"
    print(f"{prefix}_{status}: status={response.status_code} body={body}")


def log_prefixed_message(prefix: str, value: Any) -> None:
    print(f"{prefix}: {sanitize_for_logging(value)}")


def log_prefixed_fields(prefix: str, *fields: tuple[str, Any]) -> None:
    if not fields:
        print(prefix)
        return

    parts = [prefix]
    for name, field_value in fields:
        parts.append(f"{name}: {sanitize_for_logging(field_value)}")

    print(" ".join(parts))


def log_prefixed_message_full(prefix: str, value: Any) -> None:
    print(f"{prefix}: {value}")


def log_prefixed_fields_full(prefix: str, *fields: tuple[str, Any]) -> None:
    if not fields:
        print(prefix)
        return

    parts = [prefix]
    for name, field_value in fields:
        parts.append(f"{name}: {field_value}")

    print(" ".join(parts))
