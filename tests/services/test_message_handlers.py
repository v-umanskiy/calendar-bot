import asyncio
import pytest
from unittest.mock import AsyncMock, call

from tests.services import testing_helpers
from src.messaging import message_handlers
from src.utils.constants import (
    WELCOME_MESSAGE,
    GOOGLE_CONNECT_MESSAGE_TEMPLATE,
    EVENT_CREATED_REPLY_PREFIX,
    EVENT_REMOVE_CALLBACK_DATA,
    EVENT_REMOVED_MESSAGE,
    EVENT_NOT_FOUND_MESSAGE,
    UNSUPPORTED_INPUT_MESSAGE,
)


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


def test_handle_text_message_raises_on_empty_text(monkeypatch):
    chat_id = "chat-empty"
    text = "   "

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)

    load_history_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)

    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)

    with pytest.raises(ValueError, match="must not be empty"):
        asyncio.run(message_handlers.handle_text_message(chat_id, text))

    load_history_mock.assert_not_awaited()
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


def test_handle_message_code_events(monkeypatch):
    chat_id = "chat-999"
    text = "/events"
    events_reply = "Events for 2026-03-10 (UTC):\n- 10:00 Standup"

    list_events_mock = AsyncMock(return_value=events_reply)
    monkeypatch.setattr(message_handlers.google_calendar_service, "list_primary_events_for_date", list_events_mock)

    send_message_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    list_events_mock.assert_awaited_once_with(chat_id)
    send_message_mock.assert_awaited_once_with(chat_id, events_reply)


def test_handle_text_message_event_created_payload_sends_remove_button(monkeypatch):
    chat_id = "chat-111"
    text = "create sync"
    summary = "Saved to Google Calendar.\nTitle: Sync\nStart: 2026-03-10T10:00:00+03:00\nEnd: 2026-03-10T11:00:00+03:00"
    reply = (
        f"{EVENT_CREATED_REPLY_PREFIX}"
        "{\"summary\":\"Saved to Google Calendar.\\nTitle: Sync\\nStart: 2026-03-10T10:00:00+03:00\\nEnd: 2026-03-10T11:00:00+03:00\",\"calendar_id\":\"primary\",\"google_event_id\":\"evt-1\"}"
    )

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)
    load_history_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)
    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)
    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)
    process_text_mock = AsyncMock(return_value=reply)
    monkeypatch.setattr(message_handlers, "process_text_message", process_text_mock)

    send_with_markup_mock = AsyncMock(return_value={"message_id": 42})
    send_message_mock = AsyncMock()
    save_link_mock = AsyncMock()

    monkeypatch.setattr(message_handlers.telegram_service, "send_message_with_reply_markup", send_with_markup_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "save_event_link", save_link_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    send_message_mock.assert_not_awaited()
    send_with_markup_mock.assert_awaited_once()
    args = send_with_markup_mock.await_args.args
    assert args[0] == chat_id
    assert args[1] == summary
    assert args[2]["inline_keyboard"][0][0]["callback_data"] == EVENT_REMOVE_CALLBACK_DATA
    save_link_mock.assert_awaited_once_with(
        chat_id=chat_id,
        telegram_message_id=42,
        calendar_id="primary",
        google_event_id="evt-1",
    )


def test_handle_callback_query_remove_event_happy_path(monkeypatch):
    callback_query = {
        "id": "cb-1",
        "data": EVENT_REMOVE_CALLBACK_DATA,
        "message": {
            "chat": {"id": "chat-111"},
            "message_id": 42,
        },
        "from": {"id": "chat-111"},
    }

    answer_mock = AsyncMock()
    get_link_mock = AsyncMock(return_value={"calendar_id": "primary", "google_event_id": "evt-1"})
    delete_event_mock = AsyncMock(return_value={"ok": True})
    delete_link_mock = AsyncMock()
    clear_markup_mock = AsyncMock()
    send_message_mock = AsyncMock()
    save_turn_mock = AsyncMock()

    monkeypatch.setattr(message_handlers.telegram_service, "answer_callback_query", answer_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "get_event_link", get_link_mock)
    monkeypatch.setattr(message_handlers.google_calendar_service, "delete_event", delete_event_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "delete_event_link", delete_link_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "clear_message_reply_markup", clear_markup_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    asyncio.run(message_handlers.handle_callback_query(callback_query))

    answer_mock.assert_awaited_once_with("cb-1")
    get_link_mock.assert_awaited_once_with("chat-111", 42)
    delete_event_mock.assert_awaited_once_with("chat-111", calendar_id="primary", google_event_id="evt-1")
    delete_link_mock.assert_awaited_once_with("chat-111", 42)
    clear_markup_mock.assert_awaited_once_with("chat-111", 42)
    send_message_mock.assert_awaited_once_with("chat-111", EVENT_REMOVED_MESSAGE)
    assert save_turn_mock.await_args_list == [
        call("chat-111", "user", "User attempted to remove the event."),
        call("chat-111", "assistant", EVENT_REMOVED_MESSAGE),
    ]


def test_handle_callback_query_remove_event_not_found(monkeypatch):
    callback_query = {
        "id": "cb-2",
        "data": EVENT_REMOVE_CALLBACK_DATA,
        "message": {
            "chat": {"id": "chat-111"},
            "message_id": 42,
        },
        "from": {"id": "chat-111"},
    }

    answer_mock = AsyncMock()
    get_link_mock = AsyncMock(return_value={"calendar_id": "primary", "google_event_id": "evt-1"})
    delete_event_mock = AsyncMock(return_value={"ok": False, "error": "not_found"})
    delete_link_mock = AsyncMock()
    clear_markup_mock = AsyncMock()
    send_message_mock = AsyncMock()
    save_turn_mock = AsyncMock()

    monkeypatch.setattr(message_handlers.telegram_service, "answer_callback_query", answer_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "get_event_link", get_link_mock)
    monkeypatch.setattr(message_handlers.google_calendar_service, "delete_event", delete_event_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "delete_event_link", delete_link_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "clear_message_reply_markup", clear_markup_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    asyncio.run(message_handlers.handle_callback_query(callback_query))

    answer_mock.assert_awaited_once_with("cb-2")
    get_link_mock.assert_awaited_once_with("chat-111", 42)
    delete_event_mock.assert_awaited_once_with("chat-111", calendar_id="primary", google_event_id="evt-1")
    delete_link_mock.assert_awaited_once_with("chat-111", 42)
    clear_markup_mock.assert_awaited_once_with("chat-111", 42)
    send_message_mock.assert_awaited_once_with("chat-111", EVENT_NOT_FOUND_MESSAGE)
    assert save_turn_mock.await_args_list == [
        call("chat-111", "user", "User attempted to remove the event."),
        call("chat-111", "assistant", EVENT_NOT_FOUND_MESSAGE),
    ]


def test_handle_unsupported_message_mentions_text_and_voice_only(monkeypatch):
    chat_id = "chat-333"

    send_message_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    result = asyncio.run(message_handlers.handle_unsupported_message(chat_id))

    assert result == UNSUPPORTED_INPUT_MESSAGE
    send_message_mock.assert_awaited_once_with(chat_id, UNSUPPORTED_INPUT_MESSAGE)
