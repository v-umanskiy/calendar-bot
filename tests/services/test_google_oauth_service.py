import asyncio
from unittest.mock import AsyncMock

from src.services import google_oauth_service


def test_disconnect_google_calendar_deletes_connection_and_revokes_refresh_token(monkeypatch):
    get_connection_mock = AsyncMock(
        return_value={
            "chat_id": "123",
            "refresh_token_enc": "enc-refresh",
            "access_token_enc": "enc-access",
        }
    )
    delete_connection_mock = AsyncMock()
    decrypt_mock = AsyncMock(return_value="refresh-token-plain")
    revoke_mock = AsyncMock(return_value=True)

    monkeypatch.setattr(google_oauth_service.google_oauth_repository, "get_connection", get_connection_mock)
    monkeypatch.setattr(google_oauth_service.google_oauth_repository, "delete_connection", delete_connection_mock)
    monkeypatch.setattr(google_oauth_service.google_oauth_token_service, "_decrypt_value", decrypt_mock)
    monkeypatch.setattr(google_oauth_service, "_revoke_google_token", revoke_mock)

    result = asyncio.run(google_oauth_service.disconnect_google_calendar("123"))

    assert result == {"ok": True, "was_connected": True, "revoked": True}
    get_connection_mock.assert_awaited_once_with("123")
    decrypt_mock.assert_awaited_once_with("enc-refresh", "123")
    revoke_mock.assert_awaited_once_with("refresh-token-plain")
    delete_connection_mock.assert_awaited_once_with("123")


def test_disconnect_google_calendar_returns_not_connected_when_missing_item(monkeypatch):
    get_connection_mock = AsyncMock(return_value=None)
    delete_connection_mock = AsyncMock()
    revoke_mock = AsyncMock()

    monkeypatch.setattr(google_oauth_service.google_oauth_repository, "get_connection", get_connection_mock)
    monkeypatch.setattr(google_oauth_service.google_oauth_repository, "delete_connection", delete_connection_mock)
    monkeypatch.setattr(google_oauth_service, "_revoke_google_token", revoke_mock)

    result = asyncio.run(google_oauth_service.disconnect_google_calendar("123"))

    assert result == {"ok": True, "was_connected": False, "revoked": False}
    get_connection_mock.assert_awaited_once_with("123")
    revoke_mock.assert_not_awaited()
    delete_connection_mock.assert_not_awaited()
