from unittest.mock import AsyncMock

from src.ai import gemini_tools


def test_execute_tool_call_routes_to_upsert(monkeypatch):
    upsert_mock = AsyncMock(return_value={"ok": True})
    replace_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(gemini_tools.event_draft_table_service, "upsert_event_draft", upsert_mock)
    monkeypatch.setattr(gemini_tools.event_draft_table_service, "replace_event_draft", replace_mock)

    result = gemini_tools.execute_tool_call(
        {
            "name": gemini_tools.EVENT_DRAFT_TOOL_NAME,
            "args": {"title": "Old", "start": "2026-02-24T10:00:00+03:00"},
        },
        "123",
    )

    assert result == {"ok": True}
    upsert_mock.assert_awaited_once_with(
        chat_id=123,
        start="2026-02-24T10:00:00+03:00",
        end=None,
        title="Old",
    )
    replace_mock.assert_not_awaited()


def test_execute_tool_call_routes_to_replace_for_new_event(monkeypatch):
    upsert_mock = AsyncMock(return_value={"ok": True})
    replace_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(gemini_tools.event_draft_table_service, "upsert_event_draft", upsert_mock)
    monkeypatch.setattr(gemini_tools.event_draft_table_service, "replace_event_draft", replace_mock)

    result = gemini_tools.execute_tool_call(
        {
            "name": gemini_tools.NEW_EVENT_DRAFT_TOOL_NAME,
            "args": {"title": "New", "start": "2026-02-25T09:00:00+03:00"},
        },
        "chat-1",
    )

    assert result == {"ok": True}
    replace_mock.assert_awaited_once_with(
        chat_id="chat-1",
        start="2026-02-25T09:00:00+03:00",
        end=None,
        title="New",
    )
    upsert_mock.assert_not_awaited()


def test_build_complete_draft_summary_for_new_event_action():
    text = gemini_tools.build_complete_draft_summary(
        {
            "title": "Planning",
            "start": "2026-02-25T09:00:00+03:00",
            "end": "2026-02-25T10:00:00+03:00",
        },
        tool_name=gemini_tools.NEW_EVENT_DRAFT_TOOL_NAME,
    )

    assert "Action: Started a new draft event" in text
