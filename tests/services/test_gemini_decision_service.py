import asyncio
from unittest.mock import AsyncMock

from src.ai import gemini_decision_service


def test_preview_primary_event_edit_sends_preview_with_bold_changes(monkeypatch):
    get_event_mock = AsyncMock(
        return_value={
            "ok": True,
            "event": {
                "google_event_id": "evt-1",
                "title": "Old title",
                "start": "2026-03-10T10:00:00+00:00",
                "end": "2026-03-10T11:00:00+00:00",
            },
        }
    )
    load_draft_mock = AsyncMock(
        return_value={
            "chat_id": "123",
            "title": "New title",
            "mode": "edit",
            "draft_revision": "rev-1",
        }
    )
    send_message_mock = AsyncMock(return_value={"message_id": 777})

    monkeypatch.setattr(gemini_decision_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)
    monkeypatch.setattr(gemini_decision_service.event_draft_table_service, "load_event_draft", load_draft_mock)
    monkeypatch.setattr(gemini_decision_service.telegram_service, "send_message", send_message_mock)

    result = asyncio.run(gemini_decision_service.preview_primary_event_edit("123", "evt-1"))

    assert result["ok"] is True
    assert result["message_id"] == 777
    assert "**New title**" in result["preview"]
    assert "Event ID: evt-1" in result["preview"]
    get_event_mock.assert_awaited_once_with("123", google_event_id="evt-1")
    load_draft_mock.assert_awaited_once_with("123")
    send_message_mock.assert_awaited_once()


def test_preview_primary_event_edit_not_found_sends_error_message(monkeypatch):
    get_event_mock = AsyncMock(return_value={"ok": False, "error": "not_found"})
    send_message_mock = AsyncMock(return_value={"message_id": 778})

    monkeypatch.setattr(gemini_decision_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)
    monkeypatch.setattr(gemini_decision_service.telegram_service, "send_message", send_message_mock)

    result = asyncio.run(gemini_decision_service.preview_primary_event_edit("123", "evt-missing"))

    assert result == {
        "ok": False,
        "error": "not_found",
        "message": "Event not found in Google Calendar.",
    }
    send_message_mock.assert_awaited_once_with("123", "Event not found in Google Calendar.")
