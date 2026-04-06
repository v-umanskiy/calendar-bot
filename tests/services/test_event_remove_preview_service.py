import asyncio
from unittest.mock import AsyncMock

from src.services import event_remove_preview_service


def test_prepare_primary_event_remove_preview_success(monkeypatch):
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
    monkeypatch.setattr(event_remove_preview_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)

    result = asyncio.run(event_remove_preview_service.prepare_primary_event_remove_preview("123", "evt-1"))

    assert result["ok"] is True
    assert result["google_event_id"] == "evt-1"
    assert "Do you confirm removal?" in result["preview"]
    assert "Title: Old title" in result["preview"]


def test_prepare_primary_event_remove_preview_not_found(monkeypatch):
    get_event_mock = AsyncMock(return_value={"ok": False, "error": "not_found"})
    monkeypatch.setattr(event_remove_preview_service.google_calendar_service, "get_primary_event_by_id", get_event_mock)

    result = asyncio.run(event_remove_preview_service.prepare_primary_event_remove_preview("123", "evt-x"))

    assert result == {
        "ok": False,
        "error": "not_found",
        "message": "Event not found in Google Calendar.",
    }
