from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.utils import datetime_utils
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


def test_current_time_context_block_uses_provided_timezone_without_reconverting(monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls(2026, 4, 25, 18, 22, 0, tzinfo=timezone.utc)
            return cls(2026, 4, 25, 11, 22, 0, tzinfo=tz)

        def astimezone(self, tz=None):
            if tz is None:
                return self.replace(hour=18, minute=22, tzinfo=timezone.utc)
            return super().astimezone(tz)

    monkeypatch.setattr(datetime_utils, "datetime", FakeDateTime)

    block = datetime_utils.current_time_context_block(
        tzinfo=ZoneInfo("America/Vancouver")
    )

    assert "current_datetime_rfc3339_local: 2026-04-25T11:22:00" in block
