import asyncio
from unittest.mock import AsyncMock

from src.services import google_oauth_token_service


def test_persist_oauth_tokens_saves_new_refresh_token(monkeypatch):
    get_connection_mock = AsyncMock(return_value=None)
    put_connection_mock = AsyncMock()

    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "get_connection",
        get_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "put_connection",
        put_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service,
        "_encrypt_value",
        AsyncMock(side_effect=["enc_access", "enc_refresh"]),
    )

    result = asyncio.run(
        google_oauth_token_service.persist_oauth_tokens(
            "123",
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "scope": "scope-x",
                "token_type": "Bearer",
                "expires_in": 3599,
            },
        )
    )

    assert result["ok"] is True
    assert result["has_refresh_token"] is True
    assert result["refresh_token_reused"] is False
    get_connection_mock.assert_awaited_once_with("123")
    put_connection_mock.assert_awaited_once()
    saved = put_connection_mock.await_args.args[0]
    assert saved["access_token_enc"] == "enc_access"
    assert saved["refresh_token_enc"] == "enc_refresh"


def test_persist_oauth_tokens_reuses_existing_refresh_token(monkeypatch):
    get_connection_mock = AsyncMock(return_value={"refresh_token_enc": "enc_old_refresh"})
    put_connection_mock = AsyncMock()

    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "get_connection",
        get_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "put_connection",
        put_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service,
        "_encrypt_value",
        AsyncMock(return_value="enc_access_new"),
    )

    result = asyncio.run(
        google_oauth_token_service.persist_oauth_tokens(
            "123",
            {
                "access_token": "access-new",
                "scope": "scope-y",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
    )

    assert result["ok"] is True
    assert result["has_refresh_token"] is True
    assert result["refresh_token_reused"] is True
    get_connection_mock.assert_awaited_once_with("123")
    put_connection_mock.assert_awaited_once()
    saved = put_connection_mock.await_args.args[0]
    assert saved["access_token_enc"] == "enc_access_new"
    assert saved["refresh_token_enc"] == "enc_old_refresh"


def test_get_valid_access_token_refreshes_when_expired(monkeypatch):
    get_connection_mock = AsyncMock(
        return_value={
            "chat_id": "123",
            "access_token_enc": "enc_old_access",
            "refresh_token_enc": "enc_refresh",
            "expires_in": 1,
            "updated_at": 0,
        }
    )
    persist_mock = AsyncMock(return_value={"ok": True})
    refresh_mock = AsyncMock(return_value=(True, {"access_token": "new_access", "expires_in": 3600, "token_type": "Bearer"}))

    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "get_connection",
        get_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service,
        "_decrypt_value",
        AsyncMock(return_value="refresh_plain"),
    )
    monkeypatch.setattr(google_oauth_token_service, "_refresh_access_token", refresh_mock)
    monkeypatch.setattr(google_oauth_token_service, "persist_oauth_tokens", persist_mock)

    result = asyncio.run(google_oauth_token_service.get_valid_access_token("123"))

    assert result == {"ok": True, "access_token": "new_access"}
    refresh_mock.assert_awaited_once_with("123", "refresh_plain")
    persist_mock.assert_awaited_once()


def test_get_valid_access_token_requires_reconnect_when_no_refresh_token(monkeypatch):
    get_connection_mock = AsyncMock(
        return_value={
            "chat_id": "123",
            "access_token_enc": "enc_old_access",
            "expires_in": 1,
            "updated_at": 0,
        }
    )
    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "get_connection",
        get_connection_mock,
    )

    result = asyncio.run(google_oauth_token_service.get_valid_access_token("123"))

    assert result == {"ok": False, "error": "reconnect_required"}


def test_persist_oauth_tokens_preserves_existing_timezone(monkeypatch):
    get_connection_mock = AsyncMock(return_value={"refresh_token_enc": "enc_old_refresh", "timezone": "Europe/Berlin"})
    put_connection_mock = AsyncMock()

    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "get_connection",
        get_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "put_connection",
        put_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service,
        "_encrypt_value",
        AsyncMock(return_value="enc_access_new"),
    )

    result = asyncio.run(
        google_oauth_token_service.persist_oauth_tokens(
            "123",
            {
                "access_token": "access-new",
                "scope": "scope-y",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )
    )

    assert result["ok"] is True
    saved = put_connection_mock.await_args.args[0]
    assert saved["timezone"] == "Europe/Berlin"


def test_persist_oauth_tokens_uses_provided_timezone(monkeypatch):
    get_connection_mock = AsyncMock(return_value={"refresh_token_enc": "enc_old_refresh", "timezone": "Europe/Berlin"})
    put_connection_mock = AsyncMock()

    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "get_connection",
        get_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service.google_oauth_repository,
        "put_connection",
        put_connection_mock,
    )
    monkeypatch.setattr(
        google_oauth_token_service,
        "_encrypt_value",
        AsyncMock(return_value="enc_access_new"),
    )

    result = asyncio.run(
        google_oauth_token_service.persist_oauth_tokens(
            "123",
            {
                "access_token": "access-new",
                "scope": "scope-y",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
            timezone="UTC",
        )
    )

    assert result["ok"] is True
    saved = put_connection_mock.await_args.args[0]
    assert saved["timezone"] == "UTC"
