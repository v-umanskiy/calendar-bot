import asyncio
from unittest.mock import AsyncMock

from src.services import event_draft_table_service


def test_upsert_event_draft_skips_db_on_invalid_start(monkeypatch):
    upsert_mock = AsyncMock()
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "upsert_draft_fields",
        upsert_mock,
    )

    result = asyncio.run(
        event_draft_table_service.upsert_event_draft(
            chat_id=123,
            start="tomorrow evening",
            title="Dinner",
        )
    )

    assert result["ok"] is True
    assert result["invalid_fields"] == [
        {
            "field": "start",
            "reason": "invalid_rfc3339_with_offset",
            "value": "tomorrow evening",
        }
    ]
    upsert_mock.assert_not_awaited()


def test_upsert_event_draft_persists_blank_start_and_reports_missing_after_save(monkeypatch):
    upsert_mock = AsyncMock(
        return_value={
            "Attributes": {
                "title": "Dinner",
                "start": "   ",
                "end": None,
            }
        }
    )
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "upsert_draft_fields",
        upsert_mock,
    )

    result = asyncio.run(
        event_draft_table_service.upsert_event_draft(
            chat_id=123,
            start="   ",
            title="Dinner",
        )
    )

    assert result["ok"] is True
    assert result["missing_required"] == ["start"]
    assert result["invalid_fields"] == []
    upsert_mock.assert_awaited_once_with(
        "123",
        {
            "start": "   ",
            "title": "Dinner",
        },
    )


def test_upsert_event_draft_skips_db_on_invalid_end(monkeypatch):
    upsert_mock = AsyncMock()
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "upsert_draft_fields",
        upsert_mock,
    )

    result = asyncio.run(
        event_draft_table_service.upsert_event_draft(
            chat_id=123,
            start="2026-02-24T10:00:00+03:00",
            end="bad-value",
            title="Meeting",
        )
    )

    assert result["ok"] is True
    assert result["invalid_fields"] == [
        {
            "field": "end",
            "reason": "invalid_rfc3339_with_offset",
            "value": "bad-value",
        }
    ]
    upsert_mock.assert_not_awaited()


def test_upsert_event_draft_defaults_end_to_start_plus_one_hour(monkeypatch):
    upsert_mock = AsyncMock(
        return_value={
            "Attributes": {
                "title": "Sync",
                "start": "2026-02-24T10:00:00+03:00",
                "end": "2026-02-24T11:00:00+03:00",
            }
        }
    )
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "upsert_draft_fields",
        upsert_mock,
    )

    result = asyncio.run(
        event_draft_table_service.upsert_event_draft(
            chat_id=123,
            start="2026-02-24T10:00:00+03:00",
            title="Sync",
        )
    )

    upsert_mock.assert_awaited_once_with(
        "123",
        {
            "start": "2026-02-24T10:00:00+03:00",
            "end": "2026-02-24T11:00:00+03:00",
            "title": "Sync",
        },
    )
    assert result["ok"] is True
    assert result["invalid_fields"] == []
