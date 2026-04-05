from src.ai import gemini_decision_service
from src.ai import gemini_tools


def test_resolve_tool_decision_returns_edit_preview_text():
    result = gemini_decision_service._resolve_tool_decision(
        client=None,
        model_name="unused",
        chat_id="123",
        contents=[],
        function_result={
            "name": gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
            "result": {
                "ok": True,
                "preview": "Edit preview:\nTitle: Old -> **New**",
            },
        },
    )

    assert result == "Edit preview:\nTitle: Old -> **New**"


def test_resolve_tool_decision_returns_error_message_for_edit_preview_failure():
    result = gemini_decision_service._resolve_tool_decision(
        client=None,
        model_name="unused",
        chat_id="123",
        contents=[],
        function_result={
            "name": gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
            "result": {
                "ok": False,
                "message": "Event not found in Google Calendar.",
            },
        },
    )

    assert result == "Event not found in Google Calendar."


def test_resolve_tool_decision_does_not_create_event_for_edit_mode(monkeypatch):
    create_mock = lambda *_args, **_kwargs: "__EVENT_CREATED__:unexpected"
    monkeypatch.setattr(gemini_decision_service, "_create_calendar_event", create_mock)

    result = gemini_decision_service._resolve_tool_decision(
        client=None,
        model_name="unused",
        chat_id="123",
        contents=[],
        function_result={
            "name": gemini_tools.EVENT_EDIT_DRAFT_TOOL_NAME,
            "result": {
                "ok": True,
                "draft": {
                    "mode": "edit",
                    "title": "Edited",
                    "start": "2026-04-05T20:00:00+00:00",
                    "end": "2026-04-05T21:00:00+00:00",
                },
                "missing_required": [],
                "invalid_fields": [],
            },
        },
    )

    assert result is None
