import asyncio
from datetime import timedelta, timezone
import uuid
from unittest.mock import ANY
from unittest.mock import AsyncMock

from src.services import event_draft_table_service


def _set_server_tz(monkeypatch, hours: int):
    monkeypatch.setattr(
        event_draft_table_service,
        "_get_server_tzinfo",
        lambda: timezone(timedelta(hours=hours)),
    )


def test_upsert_event_draft_skips_db_on_invalid_start(monkeypatch):
    _set_server_tz(monkeypatch, 3)
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
            "reason": "invalid_rfc3339",
            "value": "tomorrow evening",
        }
    ]
    upsert_mock.assert_not_awaited()


def test_upsert_event_draft_persists_blank_start_and_reports_missing_after_save(monkeypatch):
    _set_server_tz(monkeypatch, 3)
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
            "mode": "create",
            "draft_revision": ANY,
        },
    )


def test_upsert_event_draft_skips_db_on_invalid_end(monkeypatch):
    _set_server_tz(monkeypatch, 3)
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
            "reason": "invalid_rfc3339",
            "value": "bad-value",
        }
    ]
    upsert_mock.assert_not_awaited()


def test_upsert_event_draft_defaults_end_to_start_plus_one_hour(monkeypatch):
    _set_server_tz(monkeypatch, 3)
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
            "mode": "create",
            "draft_revision": ANY,
        },
    )
    assert result["ok"] is True
    assert result["invalid_fields"] == []


def test_replace_event_draft_defaults_end_to_start_plus_one_hour(monkeypatch):
    _set_server_tz(monkeypatch, 3)
    replace_mock = AsyncMock(return_value={})
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "replace_draft_item",
        replace_mock,
    )

    result = asyncio.run(
        event_draft_table_service.replace_event_draft(
            chat_id=123,
            start="2026-02-24T10:00:00+03:00",
            title="Fresh event",
        )
    )

    replace_mock.assert_awaited_once_with(
        {
            "chat_id": "123",
            "start": "2026-02-24T10:00:00+03:00",
            "end": "2026-02-24T11:00:00+03:00",
            "title": "Fresh event",
            "mode": "create",
            "draft_revision": ANY,
        }
    )
    assert result["ok"] is True
    assert result["invalid_fields"] == []


def test_replace_event_draft_skips_db_on_invalid_start(monkeypatch):
    _set_server_tz(monkeypatch, 3)
    replace_mock = AsyncMock()
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "replace_draft_item",
        replace_mock,
    )

    result = asyncio.run(
        event_draft_table_service.replace_event_draft(
            chat_id=123,
            start="next friday morning",
            title="Fresh event",
        )
    )

    assert result["ok"] is True
    assert result["invalid_fields"] == [
        {
            "field": "start",
            "reason": "invalid_rfc3339",
            "value": "next friday morning",
        }
    ]
    replace_mock.assert_not_awaited()


def test_upsert_event_draft_normalizes_offsetless_datetime_to_server_timezone(monkeypatch):
    _set_server_tz(monkeypatch, 3)
    upsert_mock = AsyncMock(
        return_value={
            "Attributes": {
                "title": "Therms",
                "start": "2026-03-05T17:00:00+03:00",
                "end": "2026-03-05T18:00:00+03:00",
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
            start="2026-03-05T17:00:00",
            title="Therms",
        )
    )

    upsert_mock.assert_awaited_once_with(
        "123",
        {
            "start": "2026-03-05T17:00:00+03:00",
            "end": "2026-03-05T18:00:00+03:00",
            "title": "Therms",
            "mode": "create",
            "draft_revision": ANY,
        },
    )
    assert result["ok"] is True


def test_upsert_event_draft_refreshes_draft_revision_on_each_persist(monkeypatch):
    _set_server_tz(monkeypatch, 3)
    upsert_mock = AsyncMock(return_value={"Attributes": {}})
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "upsert_draft_fields",
        upsert_mock,
    )

    asyncio.run(
        event_draft_table_service.upsert_event_draft(
            chat_id=123,
            start="2026-03-05T17:00:00+03:00",
            title="Therms",
        )
    )
    asyncio.run(
        event_draft_table_service.upsert_event_draft(
            chat_id=123,
            start="2026-03-05T18:00:00+03:00",
            title="Therms",
        )
    )

    first_revision = upsert_mock.await_args_list[0].args[1]["draft_revision"]
    second_revision = upsert_mock.await_args_list[1].args[1]["draft_revision"]
    assert first_revision != second_revision
    assert str(uuid.UUID(first_revision)) == first_revision
    assert str(uuid.UUID(second_revision)) == second_revision


def test_load_event_draft_delegates_to_repository(monkeypatch):
    get_mock = AsyncMock(return_value={"chat_id": "123", "title": "Planning"})
    monkeypatch.setattr(
        event_draft_table_service.event_draft_repository,
        "get_draft",
        get_mock,
    )

    result = asyncio.run(event_draft_table_service.load_event_draft(123))

    assert result == {"chat_id": "123", "title": "Planning"}
    get_mock.assert_awaited_once_with("123")
