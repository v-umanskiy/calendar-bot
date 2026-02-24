import asyncio
from unittest.mock import AsyncMock

from src.services import cleanup_service


def test_cleanup_chat_history_full_also_deletes_event_draft(monkeypatch):
    delete_turns_mock = AsyncMock(return_value=[])
    delete_draft_mock = AsyncMock()
    delete_files_mock = AsyncMock()

    monkeypatch.setattr(cleanup_service.history_table_service, "delete_turns", delete_turns_mock)
    monkeypatch.setattr(cleanup_service.event_draft_table_service, "delete_event_draft", delete_draft_mock)
    monkeypatch.setattr(cleanup_service.s3_service, "delete_files_from_s3", delete_files_mock)

    asyncio.run(cleanup_service.cleanup_chat_history(123, full=True))

    delete_turns_mock.assert_awaited_once_with(123, keep=None)
    delete_draft_mock.assert_awaited_once_with(123)
    delete_files_mock.assert_not_awaited()


def test_cleanup_chat_history_partial_does_not_delete_event_draft(monkeypatch):
    delete_turns_mock = AsyncMock(return_value=[])
    delete_draft_mock = AsyncMock()
    delete_files_mock = AsyncMock()

    monkeypatch.setattr(cleanup_service.history_table_service, "delete_turns", delete_turns_mock)
    monkeypatch.setattr(cleanup_service.event_draft_table_service, "delete_event_draft", delete_draft_mock)
    monkeypatch.setattr(cleanup_service.s3_service, "delete_files_from_s3", delete_files_mock)

    asyncio.run(cleanup_service.cleanup_chat_history(123, full=False))

    delete_turns_mock.assert_awaited_once()
    delete_draft_mock.assert_not_awaited()
    delete_files_mock.assert_not_awaited()
