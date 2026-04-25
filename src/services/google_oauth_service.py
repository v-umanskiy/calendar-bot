import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse

import httpx

from src.utils import logging_utils
from src.repository import google_oauth_repository
from . import secret_service
from . import google_oauth_token_service
from . import telegram_service
from . import history_table_service


GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_PRIMARY_CALENDAR_URL = "https://www.googleapis.com/calendar/v3/calendars/primary"
GOOGLE_PRIMARY_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
DEFAULT_GOOGLE_OAUTH_SCOPE = "https://www.googleapis.com/auth/calendar.events"
STATE_TTL_SECONDS = 600


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _state_secret() -> str:
    return secret_service.get_secret("GOOGLE_OAUTH_STATE_SECRET") or ""


def _sign_state(payload_part: str) -> str:
    digest = hmac.new(
        _state_secret().encode("utf-8"),
        payload_part.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(digest)


def build_oauth_state(chat_id: str | int) -> str:
    now = int(time.time())
    payload = {
        "chat_id": str(chat_id),
        "nonce": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + STATE_TTL_SECONDS,
    }
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature_part = _sign_state(payload_part)
    return f"{payload_part}.{signature_part}"


def parse_and_verify_oauth_state(state: str) -> dict | None:
    if not state or "." not in state:
        return None

    payload_part, signature_part = state.split(".", 1)
    expected_signature = _sign_state(payload_part)
    if not hmac.compare_digest(signature_part, expected_signature):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_part).decode("utf-8"))
    except Exception:
        return None

    now = int(time.time())
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < now:
        return None

    if not payload.get("chat_id"):
        return None
    return payload


def build_oauth_connect_url(chat_id: str | int) -> str:
    client_id = secret_service.get_secret("GOOGLE_CLIENT_ID")
    redirect_uri = secret_service.get_secret("GOOGLE_OAUTH_REDIRECT_URI")
    scope = os.getenv("GOOGLE_OAUTH_SCOPE", DEFAULT_GOOGLE_OAUTH_SCOPE)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
        "state": build_oauth_state(chat_id),
    }
    return f"{GOOGLE_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


async def _revoke_google_token(token: str) -> bool:
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(
                GOOGLE_OAUTH_REVOKE_URL,
                data={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except Exception as exc:
            logging_utils.log_prefixed_fields(
                "GOOGLE_OAUTH_REVOKE_REQUEST_ERROR",
                ("error", repr(exc)),
            )
            return False
    return response.is_success


async def disconnect_google_calendar(chat_id: str | int) -> dict:
    normalized_chat_id = str(chat_id)
    item = await google_oauth_repository.get_connection(normalized_chat_id)
    if not isinstance(item, dict):
        return {"ok": True, "was_connected": False, "revoked": False}

    token_to_revoke: str | None = None
    refresh_token_enc = item.get("refresh_token_enc")
    access_token_enc = item.get("access_token_enc")

    try:
        if isinstance(refresh_token_enc, str) and refresh_token_enc.strip():
            token_to_revoke = await google_oauth_token_service._decrypt_value(refresh_token_enc, normalized_chat_id)
        elif isinstance(access_token_enc, str) and access_token_enc.strip():
            token_to_revoke = await google_oauth_token_service._decrypt_value(access_token_enc, normalized_chat_id)
    except Exception as exc:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_REVOKE_TOKEN_DECRYPT_ERROR",
            ("chat_id", normalized_chat_id),
            ("error", repr(exc)),
        )
        token_to_revoke = None

    revoked = False
    if token_to_revoke:
        revoked = await _revoke_google_token(token_to_revoke)
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_REVOKE_RESULT",
            ("chat_id", normalized_chat_id),
            ("revoked", revoked),
        )

    await google_oauth_repository.delete_connection(normalized_chat_id)
    return {"ok": True, "was_connected": True, "revoked": revoked}


async def exchange_code_for_tokens(code: str) -> tuple[bool, dict]:
    payload = {
        "code": code,
        "client_id": secret_service.get_secret("GOOGLE_CLIENT_ID"),
        "client_secret": secret_service.get_secret("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": secret_service.get_secret("GOOGLE_OAUTH_REDIRECT_URI"),
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.post(GOOGLE_OAUTH_TOKEN_URL, data=payload)
        except Exception as exc:
            return False, {"error": "token_exchange_request_failed", "detail": repr(exc)}

    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}

    if not response.is_success:
        return False, data if isinstance(data, dict) else {"error": "token_exchange_failed"}

    if not isinstance(data, dict):
        return False, {"error": "invalid_token_response"}
    return True, data


async def _resolve_primary_events_list_timezone(access_token: str) -> str | None:
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {
        "maxResults": "1",
        "singleEvents": "true",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(
                GOOGLE_PRIMARY_EVENTS_URL,
                headers=headers,
                params=params,
            )
        except Exception as exc:
            logging_utils.log_prefixed_fields(
                "GOOGLE_PRIMARY_EVENTS_TIMEZONE_REQUEST_ERROR",
                ("error", repr(exc)),
            )
            return None

    if not response.is_success:
        logging_utils.log_http_result("GOOGLE_PRIMARY_EVENTS_TIMEZONE_RESPONSE", response)
        return None

    try:
        payload = response.json()
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None
    timezone_name = payload.get("timeZone")
    if not isinstance(timezone_name, str) or not timezone_name.strip():
        return None
    resolved_timezone = timezone_name.strip()
    logging_utils.log_prefixed_fields(
        "GOOGLE_PRIMARY_EVENTS_TIMEZONE_RESOLVED",
        ("status_code", response.status_code),
        ("timezone", resolved_timezone),
    )
    return resolved_timezone


async def process_oauth_callback(
    *,
    code: str | None,
    state: str | None,
    error: str | None,
) -> tuple[int, str]:
    correlation_id = secrets.token_hex(6)
    if not state:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_CALLBACK_ERROR",
            ("correlation_id", correlation_id),
            ("reason", "missing_state"),
        )
        return 400, "<h3>Google Calendar connection failed</h3><p>Missing state parameter.</p>"

    state_payload = parse_and_verify_oauth_state(state)
    if state_payload is None:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_CALLBACK_ERROR",
            ("correlation_id", correlation_id),
            ("reason", "invalid_state"),
        )
        return 400, "<h3>Google Calendar connection failed</h3><p>Invalid or expired state.</p>"

    chat_id = state_payload.get("chat_id")

    if error:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_CALLBACK_ERROR",
            ("correlation_id", correlation_id),
            ("chat_id", chat_id),
            ("reason", "provider_error"),
            ("provider_error", error),
        )
        return 400, "<h3>Google Calendar connection failed</h3><p>Authorization was not completed.</p>"

    if not code:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_CALLBACK_ERROR",
            ("correlation_id", correlation_id),
            ("chat_id", chat_id),
            ("reason", "missing_code"),
        )
        return 400, "<h3>Google Calendar connection failed</h3><p>Missing authorization code.</p>"

    ok, result = await exchange_code_for_tokens(code)
    if not ok:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_TOKEN_EXCHANGE_ERROR",
            ("correlation_id", correlation_id),
            ("chat_id", chat_id),
            ("error", result.get("error") if isinstance(result, dict) else "unknown"),
        )
        return 502, "<h3>Google Calendar connection failed</h3><p>Token exchange failed. Please try /connect again.</p>"

    resolved_timezone: str | None = None
    access_token = result.get("access_token")
    if isinstance(access_token, str) and access_token.strip():
        resolved_timezone = await _resolve_primary_events_list_timezone(access_token.strip())
        if not resolved_timezone:
            logging_utils.log_prefixed_fields(
                "GOOGLE_OAUTH_TIMEZONE_NOT_RESOLVED",
                ("correlation_id", correlation_id),
                ("chat_id", chat_id),
            )
    else:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_TIMEZONE_NOT_RESOLVED",
            ("correlation_id", correlation_id),
            ("chat_id", chat_id),
            ("reason", "missing_access_token_in_exchange_payload"),
        )

    persist_result = await google_oauth_token_service.persist_oauth_tokens(
        str(chat_id),
        result,
        timezone=resolved_timezone,
    )
    if not persist_result.get("ok"):
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_TOKEN_PERSIST_ERROR",
            ("correlation_id", correlation_id),
            ("chat_id", chat_id),
            ("error", persist_result.get("error")),
        )
        return 500, "<h3>Google Calendar connection failed</h3><p>Could not store tokens. Please try /connect again.</p>"

    telegram_chat_id: str | int = str(chat_id)
    if isinstance(chat_id, str):
        normalized_chat_id = chat_id.strip()
        if normalized_chat_id and normalized_chat_id.lstrip("-").isdigit():
            telegram_chat_id = int(normalized_chat_id)
    connect_message = "Google Calendar connected."
    try:
        sent = await telegram_service.send_message(telegram_chat_id, connect_message)
        if sent is not None:
            await history_table_service.save_turn(str(chat_id), "assistant", connect_message)
    except Exception as exc:
        logging_utils.log_prefixed_fields(
            "GOOGLE_OAUTH_TELEGRAM_NOTIFY_ERROR",
            ("correlation_id", correlation_id),
            ("chat_id", chat_id),
            ("error", repr(exc)),
        )

    logging_utils.log_prefixed_fields(
        "GOOGLE_OAUTH_TIMEZONE_PERSISTED",
        ("correlation_id", correlation_id),
        ("chat_id", chat_id),
        ("timezone", resolved_timezone),
    )

    logging_utils.log_prefixed_fields(
        "GOOGLE_OAUTH_TOKEN_EXCHANGE_SUCCESS",
        ("correlation_id", correlation_id),
        ("chat_id", chat_id),
        ("scope", result.get("scope")),
        ("token_type", result.get("token_type")),
        ("expires_in", result.get("expires_in")),
        ("has_refresh_token", persist_result.get("has_refresh_token")),
        ("refresh_token_reused", persist_result.get("refresh_token_reused")),
    )
    return 200, "<h3>Google Calendar connected</h3><p>You can return to Telegram.</p>"
