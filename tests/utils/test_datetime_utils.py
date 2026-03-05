from datetime import datetime, timezone

from src.utils.datetime_utils import parse_rfc3339_datetime_utc


def test_parse_rfc3339_datetime_utc_accepts_zulu():
    result = parse_rfc3339_datetime_utc("2026-03-05T12:30:00Z")
    assert result == datetime(2026, 3, 5, 12, 30, 0, tzinfo=timezone.utc)


def test_parse_rfc3339_datetime_utc_converts_offset_to_utc():
    result = parse_rfc3339_datetime_utc("2026-03-05T12:30:00+01:00")
    assert result == datetime(2026, 3, 5, 11, 30, 0, tzinfo=timezone.utc)


def test_parse_rfc3339_datetime_utc_treats_naive_as_utc():
    result = parse_rfc3339_datetime_utc("2026-03-05T12:30:00")
    assert result == datetime(2026, 3, 5, 12, 30, 0, tzinfo=timezone.utc)


def test_parse_rfc3339_datetime_utc_rejects_invalid():
    assert parse_rfc3339_datetime_utc("tomorrow at noon") is None
