from datetime import datetime

def current_time_context_block() -> str:
    now_local = datetime.now().astimezone()
    current_time_iso = now_local.replace(tzinfo=None).isoformat(timespec="seconds")
    weekday_name = now_local.strftime("%A")
    return (
        f"current_datetime_rfc3339_local: {current_time_iso}\n"
        f"current_weekday_local: {weekday_name}"
    )