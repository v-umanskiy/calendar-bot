import asyncio
from unittest.mock import AsyncMock

from src.handlers import webhook_handler


def test_webhook_photo_routes_to_unsupported(monkeypatch):
    data = {
        "message": {
            "chat": {"id": "chat-photo"},
            "photo": [{"file_id": "a"}, {"file_id": "b"}],
            "caption": "pic",
        }
    }

    unsupported_mock = AsyncMock(return_value="unsupported")
    handle_text_mock = AsyncMock()
    handle_voice_mock = AsyncMock()
    cleanup_mock = AsyncMock()
    chat_action_mock = AsyncMock()

    monkeypatch.setattr(webhook_handler.message_handlers, "handle_unsupported_message", unsupported_mock)
    monkeypatch.setattr(webhook_handler.message_handlers, "handle_text_message", handle_text_mock)
    monkeypatch.setattr(webhook_handler.message_handlers, "handle_voice_message", handle_voice_mock)
    monkeypatch.setattr(webhook_handler.cleanup_service, "cleanup_chat_history", cleanup_mock)
    monkeypatch.setattr(webhook_handler.telegram_service, "send_chat_action", chat_action_mock)

    result = asyncio.run(webhook_handler._handle_telegram_webhook_data(data))

    assert result == {"ok": True}
    unsupported_mock.assert_awaited_once_with("chat-photo")
    handle_text_mock.assert_not_awaited()
    handle_voice_mock.assert_not_awaited()
    cleanup_mock.assert_awaited_once_with("chat-photo")


def test_webhook_document_routes_to_unsupported(monkeypatch):
    data = {
        "message": {
            "chat": {"id": "chat-doc"},
            "document": {"file_name": "router_training_2000_en.csv"},
        }
    }

    unsupported_mock = AsyncMock(return_value="unsupported")
    handle_text_mock = AsyncMock()
    handle_voice_mock = AsyncMock()
    cleanup_mock = AsyncMock()
    chat_action_mock = AsyncMock()

    monkeypatch.setattr(webhook_handler.message_handlers, "handle_unsupported_message", unsupported_mock)
    monkeypatch.setattr(webhook_handler.message_handlers, "handle_text_message", handle_text_mock)
    monkeypatch.setattr(webhook_handler.message_handlers, "handle_voice_message", handle_voice_mock)
    monkeypatch.setattr(webhook_handler.cleanup_service, "cleanup_chat_history", cleanup_mock)
    monkeypatch.setattr(webhook_handler.telegram_service, "send_chat_action", chat_action_mock)

    result = asyncio.run(webhook_handler._handle_telegram_webhook_data(data))

    assert result == {"ok": True}
    unsupported_mock.assert_awaited_once_with("chat-doc")
    handle_text_mock.assert_not_awaited()
    handle_voice_mock.assert_not_awaited()
    cleanup_mock.assert_awaited_once_with("chat-doc")


def test_webhook_text_still_routes_to_text_handler(monkeypatch):
    data = {
        "message": {
            "chat": {"id": "chat-text"},
            "text": "hello",
        }
    }

    handle_text_mock = AsyncMock(return_value="ok")
    unsupported_mock = AsyncMock()
    cleanup_mock = AsyncMock()
    chat_action_mock = AsyncMock()

    monkeypatch.setattr(webhook_handler.message_handlers, "handle_text_message", handle_text_mock)
    monkeypatch.setattr(webhook_handler.message_handlers, "handle_unsupported_message", unsupported_mock)
    monkeypatch.setattr(webhook_handler.cleanup_service, "cleanup_chat_history", cleanup_mock)
    monkeypatch.setattr(webhook_handler.telegram_service, "send_chat_action", chat_action_mock)

    result = asyncio.run(webhook_handler._handle_telegram_webhook_data(data))

    assert result == {"ok": True}
    handle_text_mock.assert_awaited_once_with("chat-text", "hello")
    unsupported_mock.assert_not_awaited()
    cleanup_mock.assert_awaited_once_with("chat-text")
