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
from . import secret_service


GOOGLE_OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_GOOGLE_OAUTH_SCOPE = "https://www.googleapis.com/auth/calendar"
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

    logging_utils.log_prefixed_fields(
        "GOOGLE_OAUTH_TOKEN_EXCHANGE_SUCCESS",
        ("correlation_id", correlation_id),
        ("chat_id", chat_id),
        ("scope", result.get("scope")),
        ("token_type", result.get("token_type")),
        ("expires_in", result.get("expires_in")),
    )
    return 200, "<h3>Google Calendar connected</h3><p>You can return to Telegram.</p>"
