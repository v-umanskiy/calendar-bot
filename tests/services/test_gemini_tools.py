from unittest.mock import AsyncMock

from src.ai import gemini_tools
from src.ai import gemini_tool_executor


def test_execute_tool_call_routes_to_upsert(monkeypatch):
    upsert_mock = AsyncMock(return_value={"ok": True})
    replace_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(gemini_tool_executor.event_draft_table_service, "upsert_event_draft", upsert_mock)
    monkeypatch.setattr(gemini_tool_executor.event_draft_table_service, "replace_event_draft", replace_mock)

    result = gemini_tool_executor.execute_tool_call(
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
    monkeypatch.setattr(gemini_tool_executor.event_draft_table_service, "upsert_event_draft", upsert_mock)
    monkeypatch.setattr(gemini_tool_executor.event_draft_table_service, "replace_event_draft", replace_mock)

    result = gemini_tool_executor.execute_tool_call(
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


def test_execute_tool_call_routes_to_event_lookup(monkeypatch):
    search_mock = AsyncMock(return_value={"ok": True, "events": []})
    monkeypatch.setattr(gemini_tool_executor.google_calendar_service, "search_primary_events", search_mock)

    result = gemini_tool_executor.execute_tool_call(
        {
            "name": gemini_tools.EVENT_LOOKUP_BY_DATE_RANGE_TOOL_NAME,
            "args": {
                "start": "2026-03-04T00:00:00+01:00",
                "end": "2026-03-05T00:00:00+01:00",
            },
        },
        "123",
    )

    assert result == {"ok": True, "events": []}
    search_mock.assert_awaited_once_with(
        "123",
        start="2026-03-04T00:00:00+01:00",
        end="2026-03-05T00:00:00+01:00",
    )


def test_execute_tool_call_routes_to_query_lookup_tool(monkeypatch):
    search_mock = AsyncMock(return_value={"ok": True, "events": []})
    monkeypatch.setattr(gemini_tool_executor.google_calendar_service, "search_primary_events_by_query", search_mock)

    result = gemini_tool_executor.execute_tool_call(
        {
            "name": gemini_tools.EVENT_LOOKUP_BY_TITLE_TOOL_NAME,
            "args": {
                "query": "danang",
            },
        },
        "123",
    )

    assert result == {"ok": True, "events": []}
    search_mock.assert_awaited_once_with(
        "123",
        query="danang",
    )


def test_execute_tool_call_routes_to_edit_preview_tool(monkeypatch):
    preview_mock = AsyncMock(return_value={"ok": True, "preview": "Edit preview"})
    monkeypatch.setattr(gemini_tool_executor.event_edit_preview_service, "prepare_primary_event_edit_preview", preview_mock)

    result = gemini_tool_executor.execute_tool_call(
        {
            "name": gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
            "args": {
                "google_event_id": "evt-1",
            },
        },
        "123",
    )

    assert result == {"ok": True, "preview": "Edit preview"}
    preview_mock.assert_awaited_once_with("123", "evt-1")


def test_execute_tool_call_returns_error_when_edit_preview_id_is_missing():
    result = gemini_tool_executor.execute_tool_call(
        {
            "name": gemini_tools.EVENT_EDIT_PREVIEW_TOOL_NAME,
            "args": {},
        },
        "123",
    )

    assert result == {"ok": False, "error": "missing_google_event_id"}


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
