import asyncio
import base64
import os
import time

import boto3
import httpx

from src.repository import google_oauth_repository
from src.utils import logging_utils
from . import secret_service


kms = boto3.client("kms")
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
ACCESS_TOKEN_REFRESH_BUFFER_SECONDS = 300


def _kms_key_id() -> str:
    key_id = os.getenv("GOOGLE_OAUTH_KMS_KEY_ID")
    if not key_id:
        raise RuntimeError("GOOGLE_OAUTH_KMS_KEY_ID is not set")
    return key_id


def _encryption_context(chat_id: str) -> dict:
    return {
        "app": "tg-calendar-bot",
        "chat_id": chat_id,
        "purpose": "google_oauth_token",
    }


async def _encrypt_value(value: str, chat_id: str) -> str:
    response = await asyncio.to_thread(
        kms.encrypt,
        KeyId=_kms_key_id(),
        Plaintext=value.encode("utf-8"),
        EncryptionContext=_encryption_context(chat_id),
    )
    ciphertext = response.get("CiphertextBlob", b"")
    return base64.b64encode(ciphertext).decode("ascii")


async def _decrypt_value(value: str, chat_id: str) -> str:
    response = await asyncio.to_thread(
        kms.decrypt,
        CiphertextBlob=base64.b64decode(value.encode("ascii")),
        EncryptionContext=_encryption_context(chat_id),
    )
    plaintext = response.get("Plaintext", b"")
    return plaintext.decode("utf-8")


async def persist_oauth_tokens(chat_id: str, token_response: dict, *, timezone: str | None = None) -> dict:
    existing_item = await google_oauth_repository.get_connection(chat_id)
    existing_item = existing_item if isinstance(existing_item, dict) else {}

    access_token = token_response.get("access_token")
    if not access_token:
        return {"ok": False, "error": "missing_access_token"}

    refresh_token = token_response.get("refresh_token")
    existing_refresh_token_enc = existing_item.get("refresh_token_enc")

    access_token_enc = await _encrypt_value(str(access_token), chat_id)
    refresh_token_enc = existing_refresh_token_enc
    if refresh_token:
        refresh_token_enc = await _encrypt_value(str(refresh_token), chat_id)

    raw_expires_in = token_response.get("expires_in")
    if raw_expires_in is None:
        raw_expires_in = existing_item.get("expires_in", 0)
    expires_in = int(raw_expires_in or 0)

    item = {
        "chat_id": chat_id,
        "access_token_enc": access_token_enc,
        "scope": token_response.get("scope") or existing_item.get("scope"),
        "token_type": token_response.get("token_type") or existing_item.get("token_type"),
        "expires_in": expires_in,
        "updated_at": int(time.time()),
    }
    item["timezone"] = timezone if timezone is not None else existing_item.get("timezone")
    if refresh_token_enc:
        item["refresh_token_enc"] = refresh_token_enc

    await google_oauth_repository.put_connection(item)
    return {
        "ok": True,
        "has_refresh_token": bool(refresh_token_enc),
        "refresh_token_reused": bool(existing_refresh_token_enc and not refresh_token),
    }


def _token_needs_refresh(item: dict) -> bool:
    expires_in = int(item.get("expires_in", 0) or 0)
    updated_at = int(item.get("updated_at", 0) or 0)
    expires_at = updated_at + expires_in
    now = int(time.time())
    return expires_at - now <= ACCESS_TOKEN_REFRESH_BUFFER_SECONDS


async def _refresh_access_token(chat_id: str, refresh_token: str) -> tuple[bool, dict]:
    payload = {
        "client_id": secret_service.get_secret("GOOGLE_CLIENT_ID"),
        "client_secret": secret_service.get_secret("GOOGLE_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(GOOGLE_OAUTH_TOKEN_URL, data=payload)
        except Exception as exc:
            return False, {"error": "refresh_request_failed", "detail": repr(exc)}

    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}
    if not response.is_success:
        return False, data if isinstance(data, dict) else {"error": "refresh_failed"}
    if not isinstance(data, dict):
        return False, {"error": "invalid_refresh_response"}
    return True, data


async def get_valid_access_token(chat_id: str, *, force_refresh: bool = False) -> dict:
    item = await google_oauth_repository.get_connection(chat_id)
    if not isinstance(item, dict):
        return {"ok": False, "error": "not_connected"}

    access_token_enc = item.get("access_token_enc")
    if not access_token_enc:
        return {"ok": False, "error": "missing_access_token"}

    if not force_refresh and not _token_needs_refresh(item):
        access_token = await _decrypt_value(str(access_token_enc), chat_id)
        return {"ok": True, "access_token": access_token}

    refresh_token_enc = item.get("refresh_token_enc")
    if not refresh_token_enc:
        return {"ok": False, "error": "reconnect_required"}

    refresh_token = await _decrypt_value(str(refresh_token_enc), chat_id)
    logging_utils.log_prefixed_fields(
        "GOOGLE_OAUTH_REFRESH_ATTEMPT",
        ("chat_id", chat_id),
        ("reason", "forced_after_401" if force_refresh else "expired_or_expiring"),
    )
    ok, refreshed_payload = await _refresh_access_token(chat_id, refresh_token)
    if not ok:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_REFRESH_ERROR",
            ("chat_id", chat_id),
            ("error", refreshed_payload.get("error") if isinstance(refreshed_payload, dict) else "unknown"),
        )
        return {"ok": False, "error": "reconnect_required"}

    persist_result = await persist_oauth_tokens(chat_id, refreshed_payload)
    if not persist_result.get("ok"):
        return {"ok": False, "error": "token_persist_failed"}

    access_token = refreshed_payload.get("access_token")
    if not access_token:
        return {"ok": False, "error": "missing_access_token"}
    logging_utils.log_prefixed_fields(
        "GOOGLE_OAUTH_REFRESH_SUCCESS",
        ("chat_id", chat_id),
        ("expires_in", refreshed_payload.get("expires_in")),
        ("token_type", refreshed_payload.get("token_type")),
        ("refresh_token_reused", persist_result.get("refresh_token_reused")),
    )
    return {"ok": True, "access_token": str(access_token)}
