from src.utils.logging_utils import (
    sanitize_for_logging,
    log_prefixed_message,
    log_prefixed_message_full,
)


SHORT_TEXT = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!!??"
LONG_TEXT = "A" * 2100
SHORT_BYTES = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
LONG_BYTES = b"B" * 1200
NESTED_DICT = {
    "text": "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod",
    "items": [
        "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium",
    ],
}


def test_sanitize_for_logging_returns_full_short_str():
    result = sanitize_for_logging(SHORT_TEXT)
    assert result == SHORT_TEXT


def test_sanitize_for_logging_truncates_long_str():
    result = sanitize_for_logging(LONG_TEXT)
    expected_prefix = "<str len=2100 data='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    assert result.startswith(expected_prefix)
    assert result.endswith("...>")


def test_sanitize_for_logging_truncates_bytes():
    result = sanitize_for_logging(LONG_BYTES)
    assert result.startswith("<bytes len=1200 data=b'BBBB")
    assert result.endswith("...>")


def test_sanitize_for_logging_handles_nested_structures():
    result = sanitize_for_logging(NESTED_DICT)

    assert result["text"] == NESTED_DICT["text"]
    assert result["items"][0] == NESTED_DICT["items"][0]


def test_log_prefixed_message_uses_sanitizer(capsys):
    log_prefixed_message("Test", SHORT_TEXT)
    captured = capsys.readouterr().out.strip()
    assert captured == f"Test: {SHORT_TEXT}"


def test_log_prefixed_message_full_outputs_raw(capsys):
    raw = "Full output should remain entirely visible."
    log_prefixed_message_full("FullTest", raw)
    captured = capsys.readouterr().out.strip()
    assert captured == f"FullTest: {raw}"
    assert "<str len=" not in captured


def test_log_prefixed_message_handles_json_like_dict(capsys):
    payload = {
        "ok": False,
        "error_code": 400,
        "description": "Bad Request: wrong file_id",
        "parameters": {"retry_after": 1},
    }
    log_prefixed_message("TelegramError", payload)
    captured = capsys.readouterr().out.strip()
    expected = f"TelegramError: {sanitize_for_logging(payload)}"
    assert captured == expected

    log_prefixed_message_full("TelegramErrorFull", payload)
    captured_full = capsys.readouterr().out.strip()
    assert captured_full == f"TelegramErrorFull: {payload}"
