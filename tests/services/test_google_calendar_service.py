import asyncio
from unittest.mock import AsyncMock

from src.services import google_calendar_service


def test_delete_event_returns_not_found_on_http_410(monkeypatch):
    token_mock = AsyncMock(return_value={"ok": True, "access_token": "token-1"})
    delete_mock = AsyncMock(return_value=(False, 410))

    monkeypatch.setattr(google_calendar_service.google_oauth_token_service, "get_valid_access_token", token_mock)
    monkeypatch.setattr(google_calendar_service, "_delete_event", delete_mock)

    result = asyncio.run(
        google_calendar_service.delete_event(
            "chat-111",
            calendar_id="primary",
            google_event_id="evt-1",
        )
    )

    assert result == {"ok": False, "error": "not_found"}
    token_mock.assert_awaited_once_with("chat-111")
    delete_mock.assert_awaited_once_with(
        "token-1",
        calendar_id="primary",
        google_event_id="evt-1",
    )
