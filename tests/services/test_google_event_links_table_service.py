import asyncio
from unittest.mock import AsyncMock

from src.services import google_event_links_table_service


def test_save_event_link_persists_expected_item(monkeypatch):
    put_mock = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        google_event_links_table_service.google_event_links_repository,
        "put_event_link",
        put_mock,
    )

    asyncio.run(
        google_event_links_table_service.save_event_link(
            chat_id=123,
            telegram_message_id=456,
            calendar_id="primary",
            google_event_id="evt_1",
        )
    )

    put_mock.assert_awaited_once()
    saved_item = put_mock.await_args.args[0]
    assert saved_item["chat_id"] == "123"
    assert saved_item["telegram_message_id"] == "456"
    assert saved_item["calendar_id"] == "primary"
    assert saved_item["google_event_id"] == "evt_1"
    assert isinstance(saved_item["created_at"], int)


def test_get_event_link_delegates_to_repository(monkeypatch):
    get_mock = AsyncMock(return_value={"chat_id": "123", "telegram_message_id": "456"})
    monkeypatch.setattr(
        google_event_links_table_service.google_event_links_repository,
        "get_event_link",
        get_mock,
    )

    result = asyncio.run(google_event_links_table_service.get_event_link(123, 456))

    assert result == {"chat_id": "123", "telegram_message_id": "456"}
    get_mock.assert_awaited_once_with("123", "456")


def test_delete_event_link_delegates_to_repository(monkeypatch):
    delete_mock = AsyncMock(return_value={})
    monkeypatch.setattr(
        google_event_links_table_service.google_event_links_repository,
        "delete_event_link",
        delete_mock,
    )

    asyncio.run(google_event_links_table_service.delete_event_link(123, 456))

    delete_mock.assert_awaited_once_with("123", "456")
