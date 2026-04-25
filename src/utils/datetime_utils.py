from datetime import datetime, timezone

def current_time_context_block(*, tzinfo) -> str:
    now_local = datetime.now(tz=tzinfo)
    current_time_iso = now_local.replace(tzinfo=None).isoformat(timespec="seconds")
    weekday_name = now_local.strftime("%A")
    return (
        f"current_datetime_rfc3339_local: {current_time_iso}\n"
        f"current_weekday_local: {weekday_name}"
    )


def parse_rfc3339_datetime_utc(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
