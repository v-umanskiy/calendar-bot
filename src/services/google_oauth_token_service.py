import asyncio
import base64
import os
import time

import boto3

from src.repository import google_oauth_repository


kms = boto3.client("kms")


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


async def persist_oauth_tokens(chat_id: str, token_response: dict) -> dict:
    access_token = token_response.get("access_token")
    if not access_token:
        return {"ok": False, "error": "missing_access_token"}

    refresh_token = token_response.get("refresh_token")
    existing_refresh_token_enc = None
    if not refresh_token:
        existing_item = await google_oauth_repository.get_connection(chat_id)
        if isinstance(existing_item, dict):
            existing_refresh_token_enc = existing_item.get("refresh_token_enc")

    access_token_enc = await _encrypt_value(str(access_token), chat_id)
    refresh_token_enc = existing_refresh_token_enc
    if refresh_token:
        refresh_token_enc = await _encrypt_value(str(refresh_token), chat_id)

    item = {
        "chat_id": chat_id,
        "access_token_enc": access_token_enc,
        "scope": token_response.get("scope"),
        "token_type": token_response.get("token_type"),
        "expires_in": int(token_response.get("expires_in", 0) or 0),
        "updated_at": int(time.time()),
    }
    if refresh_token_enc:
        item["refresh_token_enc"] = refresh_token_enc

    await google_oauth_repository.put_connection(item)
    return {
        "ok": True,
        "has_refresh_token": bool(refresh_token_enc),
        "refresh_token_reused": bool(existing_refresh_token_enc and not refresh_token),
    }
