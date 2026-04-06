from datetime import datetime


def format_datetime_for_user(value) -> str:
    text = str(value or "")
    if not text:
        return text
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    return parsed.strftime("%Y-%m-%d %H:%M")


def build_event_edit_preview_text(event: dict, draft: dict | None) -> str:
    safe_event = event
    safe_draft = draft or {}
    title_patch = safe_draft.get("title")
    start_patch = safe_draft.get("start")
    end_patch = safe_draft.get("end")

    lines = [
        "Do you confirm the update?",
        "",
    ]

    def _line(label: str, current_value, patch_value):
        current_text = format_datetime_for_user(current_value) if label in {"Start", "End"} else str(current_value or "")
        if patch_value is None:
            return f"{label}: {current_text}"
        next_text = format_datetime_for_user(patch_value) if label in {"Start", "End"} else str(patch_value)
        return f"{label}: {current_text} -> {next_text}"

    lines.append(_line("Title", safe_event.get("title"), title_patch))
    lines.append(_line("Start", safe_event.get("start"), start_patch))
    lines.append(_line("End", safe_event.get("end"), end_patch))

    return "\n".join(lines)


def build_event_remove_preview_text(event: dict) -> str:
    safe_event = event or {}
    lines = [
        "Do you confirm removal?",
        "",
        f"Title: {str(safe_event.get('title') or '')}",
        f"Start: {format_datetime_for_user(safe_event.get('start'))}",
        f"End: {format_datetime_for_user(safe_event.get('end'))}",
    ]
    return "\n".join(lines)
