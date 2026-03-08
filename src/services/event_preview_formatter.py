def build_event_edit_preview_text(event: dict, draft: dict | None) -> str:
    safe_event = event
    safe_draft = draft or {}
    title_patch = safe_draft.get("title")
    start_patch = safe_draft.get("start")
    end_patch = safe_draft.get("end")

    lines = [
        "Edit preview:",
        f"Event ID: {safe_event.get('google_event_id') or '(unknown)'}",
        "",
    ]

    def _line(label: str, current_value, patch_value):
        current_text = str(current_value or "")
        if patch_value is None:
            return f"{label}: {current_text}"
        next_text = str(patch_value)
        return f"{label}: {current_text} -> **{next_text}**"

    lines.append(_line("Title", safe_event.get("title"), title_patch))
    lines.append(_line("Start", safe_event.get("start"), start_patch))
    lines.append(_line("End", safe_event.get("end"), end_patch))

    return "\n".join(lines)
