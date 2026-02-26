import asyncio
from unittest.mock import AsyncMock, call

from tests.services import testing_helpers
from src.messaging import message_handlers
from src.utils.constants import WELCOME_MESSAGE, GOOGLE_CONNECT_MESSAGE_TEMPLATE


def test_handle_text_message_regular_flow(monkeypatch):
    chat_id = "chat-123"
    text = "Tell me a joke"
    history = [{"role": "user", "text": "prior"}]
    reply = "Here is a joke"

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)

    load_history_mock = AsyncMock(return_value=history)
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)

    send_message_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)

    process_text_mock = AsyncMock(return_value=reply)
    monkeypatch.setattr(message_handlers, "process_text_message", process_text_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    handle_codes_mock.assert_awaited_once_with(chat_id, text)
    load_history_mock.assert_awaited_once_with(chat_id)
    process_text_mock.assert_awaited_once_with(chat_id, text, False, history)
    send_message_mock.assert_awaited_once_with(chat_id, reply)
    assert save_turn_mock.await_args_list == [
        call(chat_id, "user", text),
        call(chat_id, "assistant", reply),
    ]
    indicator_mock.assert_called_once_with(chat_id, "typing")


def test_handle_text_message_returns_when_code_handled(monkeypatch):
    chat_id = "chat-456"
    text = "/start"

    handle_codes_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)

    load_history_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)

    send_message_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)

    process_text_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "process_text_message", process_text_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    handle_codes_mock.assert_awaited_once_with(chat_id, text)
    process_text_mock.assert_not_awaited()
    load_history_mock.assert_not_awaited()
    send_message_mock.assert_not_awaited()
    save_turn_mock.assert_not_awaited()
    indicator_mock.assert_not_called()


def test_handle_message_code_start(monkeypatch):
    chat_id = "chat-456"
    text = "/start"

    send_message_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))
    send_message_mock.assert_awaited_once_with(chat_id, WELCOME_MESSAGE)
    save_turn_mock.assert_not_awaited()


def test_handle_message_code_connect(monkeypatch):
    chat_id = "chat-789"
    text = "/connect"
    connect_url = "https://accounts.google.com/o/oauth2/v2/auth?x=1"

    build_url_mock = lambda _chat_id: connect_url
    monkeypatch.setattr(message_handlers.google_oauth_service, "build_oauth_connect_url", build_url_mock)

    send_message_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    expected = GOOGLE_CONNECT_MESSAGE_TEMPLATE.format(url=connect_url)
    send_message_mock.assert_awaited_once_with(chat_id, expected)
