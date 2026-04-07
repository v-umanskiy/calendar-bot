import asyncio
import pytest
from unittest.mock import AsyncMock, call
from unittest.mock import MagicMock

from tests.services import testing_helpers
from src.messaging import message_handlers
from src.utils.constants import (
    WELCOME_MESSAGE,
    GOOGLE_CONNECT_MESSAGE,
    GOOGLE_CONNECT_BUTTON_TEXT,
    EVENT_RECONNECT_REQUIRED_MESSAGE,
    EVENT_EDIT_CONFIRM_BUTTON_TEXT,
    EVENT_EDIT_CONFIRM_CALLBACK_DATA,
    EVENT_REMOVE_CONFIRM_BUTTON_TEXT,
    EVENT_REMOVE_CALLBACK_DATA,
    EVENT_REMOVED_MESSAGE,
    EVENT_UPDATED_MESSAGE,
    EVENT_NOT_FOUND_MESSAGE,
    UNSUPPORTED_INPUT_MESSAGE,
    VOICE_TOO_LONG_MESSAGE,
)


def test_handle_text_message_regular_flow(monkeypatch):
    chat_id = "chat-123"
    text = "Tell me a joke"
    history = [{"role": "user", "text": "prior"}]
    reply = {"type": "text", "text": "Here is a joke"}

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
    monkeypatch.setattr(message_handlers, "generate_reply", process_text_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    handle_codes_mock.assert_awaited_once_with(chat_id, text)
    load_history_mock.assert_awaited_once_with(chat_id)
    process_text_mock.assert_awaited_once_with(prompt=text, chat_id=chat_id, history=history)
    send_message_mock.assert_awaited_once_with(chat_id, "Here is a joke")
    assert save_turn_mock.await_args_list == [
        call(chat_id, "user", text),
        call(chat_id, "assistant", "Here is a joke"),
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
    monkeypatch.setattr(message_handlers, "generate_reply", process_text_mock)

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
    connect_url = "https://accounts.google.com/o/oauth2/v2/auth?x=1"

    build_url_mock = lambda _chat_id: connect_url
    monkeypatch.setattr(message_handlers.google_oauth_service, "build_oauth_connect_url", build_url_mock)

    send_with_markup_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message_with_reply_markup", send_with_markup_mock)

    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))
    reply_markup = {
        "inline_keyboard": [
            [{"text": GOOGLE_CONNECT_BUTTON_TEXT, "url": connect_url}],
        ]
    }
    send_with_markup_mock.assert_awaited_once_with(chat_id, WELCOME_MESSAGE, reply_markup)
    save_turn_mock.assert_not_awaited()


def test_handle_message_code_connect(monkeypatch):
    chat_id = "chat-789"
    text = "/connect"
    connect_url = "https://accounts.google.com/o/oauth2/v2/auth?x=1"

    build_url_mock = lambda _chat_id: connect_url
    monkeypatch.setattr(message_handlers.google_oauth_service, "build_oauth_connect_url", build_url_mock)

    send_with_markup_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message_with_reply_markup", send_with_markup_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    expected = GOOGLE_CONNECT_MESSAGE
    reply_markup = {
        "inline_keyboard": [
            [{"text": GOOGLE_CONNECT_BUTTON_TEXT, "url": connect_url}],
        ]
    }
    send_with_markup_mock.assert_awaited_once_with(chat_id, expected, reply_markup)


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
    summary = "Saved to Google Calendar.\nTitle: Sync\nStart: 2026-03-10 10:00\nEnd: 2026-03-10 11:00"
    reply = {
        "type": "event_created",
        "summary": summary,
        "calendar_id": "primary",
        "google_event_id": "evt-1",
    }

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)
    load_history_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)
    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)
    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)
    process_text_mock = AsyncMock(return_value=reply)
    monkeypatch.setattr(message_handlers, "generate_reply", process_text_mock)

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


def test_handle_text_message_reconnect_reply_sends_connect_button(monkeypatch):
    chat_id = "chat-222"
    text = "check calendar"
    connect_url = "https://accounts.google.com/o/oauth2/v2/auth?x=1"

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)
    load_history_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)
    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)
    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)
    process_text_mock = AsyncMock(return_value={"type": "text", "text": EVENT_RECONNECT_REQUIRED_MESSAGE})
    monkeypatch.setattr(message_handlers, "generate_reply", process_text_mock)
    monkeypatch.setattr(message_handlers.google_oauth_service, "build_oauth_connect_url", lambda _chat_id: connect_url)

    send_message_mock = AsyncMock()
    send_with_markup_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message_with_reply_markup", send_with_markup_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    send_message_mock.assert_not_awaited()
    reply_markup = {
        "inline_keyboard": [
            [{"text": GOOGLE_CONNECT_BUTTON_TEXT, "url": connect_url}],
        ]
    }
    send_with_markup_mock.assert_awaited_once_with(chat_id, EVENT_RECONNECT_REQUIRED_MESSAGE, reply_markup)
    assert save_turn_mock.await_args_list == [
        call(chat_id, "user", text),
        call(chat_id, "assistant", EVENT_RECONNECT_REQUIRED_MESSAGE),
    ]


def test_handle_text_message_edit_preview_payload_sends_confirm_button(monkeypatch):
    chat_id = "chat-333"
    text = "move event to tomorrow"
    preview_text = (
        "Do you confirm the update?\n\n"
        "Title: Planning\n"
        "Start: 2026-04-08 13:00 -> 2026-04-09 13:00\n"
        "End: 2026-04-08 14:00 -> 2026-04-09 14:00"
    )
    reply = {"type": "event_edit_preview", "text": preview_text}

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)
    load_history_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)
    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)
    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)
    process_text_mock = AsyncMock(return_value=reply)
    monkeypatch.setattr(message_handlers, "generate_reply", process_text_mock)

    send_message_mock = AsyncMock()
    send_with_markup_mock = AsyncMock()
    load_draft_for_preview_mock = AsyncMock(return_value={"google_event_id": "evt-7"})
    save_link_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(
        message_handlers.telegram_service,
        "send_message_with_reply_markup",
        AsyncMock(return_value={"message_id": 77}),
    )
    monkeypatch.setattr(message_handlers.event_draft_table_service, "load_event_draft", load_draft_for_preview_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "save_event_link", save_link_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    send_message_mock.assert_not_awaited()
    reply_markup = {
        "inline_keyboard": [
            [{"text": EVENT_EDIT_CONFIRM_BUTTON_TEXT, "callback_data": EVENT_EDIT_CONFIRM_CALLBACK_DATA}],
        ]
    }
    message_handlers.telegram_service.send_message_with_reply_markup.assert_awaited_once_with(chat_id, preview_text, reply_markup)
    save_link_mock.assert_awaited_once_with(
        chat_id=chat_id,
        telegram_message_id=77,
        calendar_id="primary",
        google_event_id="evt-7",
    )
    assert save_turn_mock.await_args_list == [
        call(chat_id, "user", text),
        call(chat_id, "assistant", preview_text),
    ]


def test_handle_text_message_remove_preview_payload_sends_confirm_button(monkeypatch):
    chat_id = "chat-334"
    text = "delete event"
    preview_text = (
        "Do you confirm removal?\n\n"
        "Title: Demo\n"
        "Start: 2026-04-08 13:00\n"
        "End: 2026-04-08 14:00"
    )
    reply = {"type": "event_remove_preview", "text": preview_text, "google_event_id": "evt-77", "calendar_id": "primary"}

    handle_codes_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(message_handlers, "_handle_message_codes", handle_codes_mock)
    load_history_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(message_handlers.history_table_service, "load_model_history", load_history_mock)
    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)
    indicator_mock = AsyncMock()
    monkeypatch.setattr(message_handlers, "_chat_action_indicator", indicator_mock)
    process_text_mock = AsyncMock(return_value=reply)
    monkeypatch.setattr(message_handlers, "generate_reply", process_text_mock)

    send_message_mock = AsyncMock()
    save_link_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(
        message_handlers.telegram_service,
        "send_message_with_reply_markup",
        AsyncMock(return_value={"message_id": 78}),
    )
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "save_event_link", save_link_mock)

    asyncio.run(message_handlers.handle_text_message(chat_id, text))

    send_message_mock.assert_not_awaited()
    reply_markup = {
        "inline_keyboard": [
            [{"text": EVENT_REMOVE_CONFIRM_BUTTON_TEXT, "callback_data": EVENT_REMOVE_CALLBACK_DATA}],
        ]
    }
    message_handlers.telegram_service.send_message_with_reply_markup.assert_awaited_once_with(chat_id, preview_text, reply_markup)
    save_link_mock.assert_awaited_once_with(
        chat_id=chat_id,
        telegram_message_id=78,
        calendar_id="primary",
        google_event_id="evt-77",
    )
    assert save_turn_mock.await_args_list == [
        call(chat_id, "user", text),
        call(chat_id, "assistant", preview_text),
    ]


def test_handle_callback_query_edit_confirm_happy_path(monkeypatch):
    callback_query = {
        "id": "cb-edit-1",
        "data": EVENT_EDIT_CONFIRM_CALLBACK_DATA,
        "message": {
            "chat": {"id": "chat-444"},
            "message_id": 88,
        },
        "from": {"id": "chat-444"},
    }

    answer_mock = AsyncMock()
    get_link_mock = AsyncMock(return_value={"calendar_id": "primary", "google_event_id": "evt-9"})
    load_draft_mock = AsyncMock(
        return_value={
            "title": "Edited",
            "start": "2026-04-09T10:00:00+00:00",
            "end": "2026-04-09T11:00:00+00:00",
        }
    )
    update_event_mock = AsyncMock(return_value={"ok": True})
    delete_link_mock = AsyncMock()
    delete_draft_mock = AsyncMock()
    clear_markup_mock = AsyncMock()
    send_message_mock = AsyncMock()
    save_turn_mock = AsyncMock()

    monkeypatch.setattr(message_handlers.telegram_service, "answer_callback_query", answer_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "get_event_link", get_link_mock)
    monkeypatch.setattr(message_handlers.event_draft_table_service, "load_event_draft", load_draft_mock)
    monkeypatch.setattr(message_handlers.google_calendar_service, "update_event", update_event_mock)
    monkeypatch.setattr(message_handlers.google_event_links_table_service, "delete_event_link", delete_link_mock)
    monkeypatch.setattr(message_handlers.event_draft_table_service, "delete_event_draft", delete_draft_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "clear_message_reply_markup", clear_markup_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    asyncio.run(message_handlers.handle_callback_query(callback_query))

    answer_mock.assert_awaited_once_with("cb-edit-1")
    get_link_mock.assert_awaited_once_with("chat-444", 88)
    update_event_mock.assert_awaited_once_with(
        "chat-444",
        calendar_id="primary",
        google_event_id="evt-9",
        title="Edited",
        start="2026-04-09T10:00:00+00:00",
        end="2026-04-09T11:00:00+00:00",
    )
    delete_link_mock.assert_awaited_once_with("chat-444", 88)
    delete_draft_mock.assert_awaited_once_with("chat-444")
    clear_markup_mock.assert_awaited_once_with("chat-444", 88)
    send_message_mock.assert_awaited_once_with("chat-444", EVENT_UPDATED_MESSAGE)


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


def test_handle_voice_message_rejects_duration_above_two_minutes(monkeypatch):
    chat_id = "chat-voice"
    voice = {"file_id": "voice-1", "duration": 121}

    send_message_mock = AsyncMock()
    download_mock = AsyncMock()
    save_turn_mock = AsyncMock()
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "download_file_from_telegram", download_mock)
    monkeypatch.setattr(message_handlers.history_table_service, "save_turn", save_turn_mock)

    result = asyncio.run(message_handlers.handle_voice_message(voice, chat_id))

    assert result == VOICE_TOO_LONG_MESSAGE
    send_message_mock.assert_awaited_once_with(chat_id, VOICE_TOO_LONG_MESSAGE)
    download_mock.assert_not_awaited()
    assert save_turn_mock.await_args_list == [
        call(chat_id, "user", "User sent a voice message with duration 121s (over 2 minutes)."),
        call(chat_id, "assistant", VOICE_TOO_LONG_MESSAGE),
    ]


def test_handle_voice_message_accepts_duration_equal_two_minutes(monkeypatch):
    chat_id = "chat-voice-ok"
    voice = {"file_id": "voice-2", "duration": 120}

    download_mock = AsyncMock(return_value=b"audio")
    whisper_mock = MagicMock(return_value="transcribed voice text")
    handle_text_mock = AsyncMock()
    send_message_mock = AsyncMock()

    monkeypatch.setattr(message_handlers.telegram_service, "download_file_from_telegram", download_mock)
    monkeypatch.setattr(message_handlers.whisper_service, "transcribe_audio_bytes", whisper_mock)
    monkeypatch.setattr(message_handlers, "handle_text_message", handle_text_mock)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    result = asyncio.run(message_handlers.handle_voice_message(voice, chat_id))

    assert result is None
    download_mock.assert_awaited_once_with("voice-2")
    whisper_mock.assert_called_once_with(b"audio", "ogg")
    handle_text_mock.assert_awaited_once_with(chat_id, "transcribed voice text", is_transcribed=True)
    send_message_mock.assert_not_awaited()


def test_handle_voice_message_handles_whisper_error(monkeypatch):
    chat_id = "chat-voice-fail"
    voice = {"file_id": "voice-3", "duration": 35}

    download_mock = AsyncMock(return_value=b"audio")
    send_message_mock = AsyncMock()

    def _raise_whisper_error(_file_bytes: bytes, _file_ext: str):
        raise RuntimeError("whisper failed")

    monkeypatch.setattr(message_handlers.telegram_service, "download_file_from_telegram", download_mock)
    monkeypatch.setattr(message_handlers.whisper_service, "transcribe_audio_bytes", _raise_whisper_error)
    monkeypatch.setattr(message_handlers.telegram_service, "send_message", send_message_mock)

    result = asyncio.run(message_handlers.handle_voice_message(voice, chat_id))

    assert result == "Sorry, I couldn’t transcribe your voice message"
    send_message_mock.assert_awaited_once_with(chat_id, "Sorry, I couldn’t transcribe your voice message")
