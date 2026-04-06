import asyncio
from unittest.mock import AsyncMock

from src.services import event_edit_preview_service


def test_prepare_primary_event_edit_preview_success(monkeypatch):
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
    load_draft_mock = AsyncMock(return_value={"title": "New title"})
    set_target_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(event_edit_preview_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)
    monkeypatch.setattr(event_edit_preview_service.event_draft_table_service, "load_event_draft", load_draft_mock)
    monkeypatch.setattr(event_edit_preview_service.event_draft_table_service, "set_edit_target_event", set_target_mock)

    result = asyncio.run(event_edit_preview_service.prepare_primary_event_edit_preview("123", "evt-1"))

    assert result["ok"] is True
    assert result["google_event_id"] == "evt-1"
    assert "Do you confirm the update?" in result["preview"]
    assert "Title: Old title -> New title" in result["preview"]
    set_target_mock.assert_awaited_once_with("123", "evt-1")


def test_prepare_primary_event_edit_preview_not_found(monkeypatch):
    get_event_mock = AsyncMock(return_value={"ok": False, "error": "not_found"})
    monkeypatch.setattr(event_edit_preview_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)

    result = asyncio.run(event_edit_preview_service.prepare_primary_event_edit_preview("123", "evt-x"))

    assert result == {
        "ok": False,
        "error": "not_found",
        "message": "Event not found in Google Calendar.",
    }


def test_prepare_primary_event_edit_preview_requires_pending_draft_changes(monkeypatch):
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
    load_draft_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(event_edit_preview_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)
    monkeypatch.setattr(event_edit_preview_service.event_draft_table_service, "load_event_draft", load_draft_mock)

    result = asyncio.run(event_edit_preview_service.prepare_primary_event_edit_preview("123", "evt-1"))

    assert result == {
        "ok": False,
        "error": "missing_edit_patch",
        "message": "No draft changes found for edit preview. Tell me what to change first.",
    }
