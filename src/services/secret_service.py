import json
import os

import boto3

secrets = {}
sm = boto3.client("secretsmanager")
_secrets_payload = None

_SECRETS_ARN_ENV = "SECRETS_ARN"
_DEFAULT_SECRETS_NAME = "SECRET"


def _get_secrets_source() -> str:
    return os.getenv(_SECRETS_ARN_ENV) or _DEFAULT_SECRETS_NAME


def _load_secrets_payload() -> dict:
    global _secrets_payload
    if _secrets_payload is not None:
        return _secrets_payload

    response = sm.get_secret_value(SecretId=_get_secrets_source())
    secret_string = response.get("SecretString", "")
    _secrets_payload = json.loads(secret_string) if secret_string else {}
    return _secrets_payload

def get_secret(secret_key: str) -> str:
    cached = secrets.get(secret_key)
    if cached is not None:
        return cached

    payload = _load_secrets_payload()
    secrets[secret_key] = payload.get(secret_key)
    return secrets[secret_key]

    
