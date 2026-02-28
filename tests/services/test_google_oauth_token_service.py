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
    get_connection_mock.assert_not_awaited()
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
