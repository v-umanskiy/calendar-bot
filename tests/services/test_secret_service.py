import json

from src.services import secret_service


class _DummySecretsManager:
    def __init__(self):
        self.calls = []

    def get_secret_value(self, *, SecretId: str):
        self.calls.append(SecretId)
        return {
            "SecretString": json.dumps(
                {"ONE": "value-for-ONE", "TWO": "value-for-TWO"}
            )
        }


def test_get_secret_caches_value(monkeypatch):
    dummy_manager = _DummySecretsManager()
    monkeypatch.setattr(secret_service, "sm", dummy_manager)
    monkeypatch.setattr(secret_service, "secrets", {})
    monkeypatch.setattr(secret_service, "_secrets_payload", None)
    monkeypatch.setenv("SECRETS_ARN", "SECRET")
    first = secret_service.get_secret("ONE")
    second = secret_service.get_secret("ONE")
    other = secret_service.get_secret("TWO")

    assert first == "value-for-ONE"
    assert second == "value-for-ONE"
    assert other == "value-for-TWO"
    assert dummy_manager.calls == ["SECRET"]
