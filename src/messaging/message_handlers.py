import asyncio
import json
import time
import uuid

from src.services import cleanup_service
from src.services import history_table_service
from src.services import s3_service
from src.services import telegram_service
from src.services import transcription_aws_service
from src.services import transcription_table_service
from src.services import google_oauth_service
from src.services import google_calendar_service
from src.services import google_event_links_table_service
from src.services import event_draft_table_service
from .message_processor_simple import (
    handle_text_message as process_text_message,
)
from src.utils import logging_utils
from src.utils.constants import (
    WELCOME_MESSAGE,
    CLEAR_HISTORY_MESSAGE,
    HISTORY_CLEARED_MESSAGE,
    GOOGLE_CONNECT_MESSAGE,
    GOOGLE_CONNECT_BUTTON_TEXT,
    UNSUPPORTED_INPUT_MESSAGE,
    EVENT_CREATED_REPLY_PREFIX,
    EVENT_EDIT_PREVIEW_REPLY_PREFIX,
    EVENT_REMOVE_PREVIEW_REPLY_PREFIX,
    EVENT_REMOVE_BUTTON_TEXT,
    EVENT_REMOVE_CALLBACK_DATA,
    EVENT_EDIT_CONFIRM_BUTTON_TEXT,
    EVENT_EDIT_CONFIRM_CALLBACK_DATA,
    EVENT_REMOVE_CONFIRM_BUTTON_TEXT,
    EVENT_REMOVED_MESSAGE,
    EVENT_UPDATED_MESSAGE,
    EVENT_NOT_FOUND_MESSAGE,
    EVENT_REMOVE_FAILED_MESSAGE,
    EVENT_UPDATE_FAILED_MESSAGE,
    EVENT_RECONNECT_REQUIRED_MESSAGE,
    CLEAR_HISTORY_KEYBOARD,
    CLEAR_HISTORY_CONFIRM_CALLBACK_DATA,
    CLEAR_HISTORY_CANCEL_CALLBACK_DATA,
)


async def handle_text_message(chat_id: str, text: str, *, is_transcribed: bool = False) -> str | None:
    command_reply = await _handle_message_codes(chat_id, text)
    if command_reply is not None:
        return command_reply
    if not text.strip():
        raise ValueError("Text message must not be empty.")

    indicator = asyncio.create_task(_chat_action_indicator(chat_id, "typing"))
    reply = None
    try:
        history = await history_table_service.load_model_history(chat_id)
        reply = await process_text_message(chat_id, text, is_transcribed, history)
    finally:
        indicator.cancel()
        try:
            await indicator
        except asyncio.CancelledError:
            pass

    if reply is None:
        raise RuntimeError("Gemini reply missing; call_gemini returned None")

    assistant_reply = reply
    if isinstance(reply, str) and reply.startswith(EVENT_CREATED_REPLY_PREFIX):
        payload = _parse_event_created_reply(reply)
        if payload:
            summary = str(payload.get("summary") or "")
            reply_markup = {
                "inline_keyboard": [
                    [{"text": EVENT_REMOVE_BUTTON_TEXT, "callback_data": EVENT_REMOVE_CALLBACK_DATA}],
                ]
            }
            sent = await telegram_service.send_message_with_reply_markup(chat_id, summary, reply_markup)
            if isinstance(sent, dict) and sent.get("message_id") is not None:
                await google_event_links_table_service.save_event_link(
                    chat_id=chat_id,
                    telegram_message_id=sent.get("message_id"),
                    calendar_id=str(payload.get("calendar_id") or "primary"),
                    google_event_id=str(payload.get("google_event_id") or ""),
                )
            assistant_reply = summary
        else:
            await telegram_service.send_message(chat_id, reply)
    elif isinstance(reply, str) and reply.startswith(EVENT_EDIT_PREVIEW_REPLY_PREFIX):
        preview = reply[len(EVENT_EDIT_PREVIEW_REPLY_PREFIX):]
        if preview:
            reply_markup = {
                "inline_keyboard": [
                    [{"text": EVENT_EDIT_CONFIRM_BUTTON_TEXT, "callback_data": EVENT_EDIT_CONFIRM_CALLBACK_DATA}],
                ]
            }
            sent = await telegram_service.send_message_with_reply_markup(chat_id, preview, reply_markup)
            if isinstance(sent, dict) and sent.get("message_id") is not None:
                draft = await event_draft_table_service.load_event_draft(chat_id)
                if isinstance(draft, dict) and draft.get("google_event_id"):
                    await google_event_links_table_service.save_event_link(
                        chat_id=chat_id,
                        telegram_message_id=sent.get("message_id"),
                        calendar_id="primary",
                        google_event_id=str(draft.get("google_event_id") or ""),
                    )
            assistant_reply = preview
        else:
            await telegram_service.send_message(chat_id, reply)
    elif isinstance(reply, str) and reply.startswith(EVENT_REMOVE_PREVIEW_REPLY_PREFIX):
        parsed = _parse_event_remove_preview_reply(reply)
        if parsed:
            preview = str(parsed.get("preview") or "")
            google_event_id = str(parsed.get("google_event_id") or "")
            reply_markup = {
                "inline_keyboard": [
                    [{"text": EVENT_REMOVE_CONFIRM_BUTTON_TEXT, "callback_data": EVENT_REMOVE_CALLBACK_DATA}],
                ]
            }
            sent = await telegram_service.send_message_with_reply_markup(chat_id, preview, reply_markup)
            if isinstance(sent, dict) and sent.get("message_id") is not None and google_event_id:
                await google_event_links_table_service.save_event_link(
                    chat_id=chat_id,
                    telegram_message_id=sent.get("message_id"),
                    calendar_id="primary",
                    google_event_id=google_event_id,
                )
            assistant_reply = preview
        else:
            await telegram_service.send_message(chat_id, reply)
    else:
        if reply == EVENT_RECONNECT_REQUIRED_MESSAGE:
            url = google_oauth_service.build_oauth_connect_url(chat_id)
            reply_markup = {
                "inline_keyboard": [
                    [{"text": GOOGLE_CONNECT_BUTTON_TEXT, "url": url}],
                ]
            }
            await telegram_service.send_message_with_reply_markup(chat_id, reply, reply_markup)
        else:
            await telegram_service.send_message(chat_id, reply)
    await history_table_service.save_turn(chat_id, "user", text)
    await history_table_service.save_turn(chat_id, "assistant", assistant_reply)
    return assistant_reply


async def handle_voice_message(voice: any, chat_id: str) -> str | None:
    file_id = voice["file_id"]
    file_bytes = await telegram_service.download_file_from_telegram(file_id)
    if file_bytes:
        job_id = f"tg-{uuid.uuid4()}"
        file_key = f"voices/{file_id}.ogg"
        file_url, _ = await s3_service.upload_file_to_s3(file_bytes, file_key)
        await transcription_table_service.save_transcription_job(chat_id, job_id, file_url, file_key)
        transcription_aws_service.transcribe(job_id, file_key)
        return None
    else:
        message = "Sorry, I couldn’t download your voice message"
        await telegram_service.send_message(chat_id, message)
        return message


async def handle_unsupported_message(chat_id: str) -> str:
    message = UNSUPPORTED_INPUT_MESSAGE
    await telegram_service.send_message(
        chat_id,
        message,
    )
    return message


async def _chat_action_indicator(chat_id: str, action: str):
    try:
        while True:
            await telegram_service.send_chat_action(chat_id, action)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def _handle_message_codes(chat_id: str, text: str) -> str | None:
    stripped_text = text.strip()

    if stripped_text == "/start":
        url = google_oauth_service.build_oauth_connect_url(chat_id)
        reply_markup = {
            "inline_keyboard": [
                [{"text": GOOGLE_CONNECT_BUTTON_TEXT, "url": url}],
            ]
        }
        await telegram_service.send_message_with_reply_markup(chat_id, WELCOME_MESSAGE, reply_markup)
        return WELCOME_MESSAGE
    if stripped_text == "/clear":
        await telegram_service.send_message_with_reply_markup(
            chat_id,
            CLEAR_HISTORY_MESSAGE,
            CLEAR_HISTORY_KEYBOARD,
        )
        return CLEAR_HISTORY_MESSAGE
    if stripped_text == "/connect":
        url = google_oauth_service.build_oauth_connect_url(chat_id)
        message = GOOGLE_CONNECT_MESSAGE
        reply_markup = {
            "inline_keyboard": [
                [{"text": GOOGLE_CONNECT_BUTTON_TEXT, "url": url}],
            ]
        }
        logging_utils.log_prefixed_fields("GOOGLE_OAUTH_CONNECT_LINK_GENERATED", ("chat_id", chat_id))
        await telegram_service.send_message_with_reply_markup(chat_id, message, reply_markup)
        return message
    if stripped_text == "/events":
        message = await google_calendar_service.list_primary_events_for_date(chat_id)
        await telegram_service.send_message(chat_id, message)
        return message
    return None


async def handle_callback_query(callback_query: dict):
    callback_id = callback_query.get("id")
    if callback_id:
        start = time.monotonic()
        await telegram_service.answer_callback_query(callback_id)
        logging_utils.log_prefixed_fields(
            "ANSWER_CALLBACK_QUERY_DURATION",
            ("chat_id", callback_query.get("from", {}).get("id")),
            ("ms", int((time.monotonic() - start) * 1000)),
        )

    data = callback_query.get("data")
    message = callback_query.get("message")
    if not message:
        return
    if data == EVENT_REMOVE_CALLBACK_DATA:
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        await history_table_service.save_turn(chat_id, "user", "User attempted to remove the event.")
        link = await google_event_links_table_service.get_event_link(chat_id, message_id)
        if not isinstance(link, dict):
            await telegram_service.send_message(chat_id, EVENT_NOT_FOUND_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_NOT_FOUND_MESSAGE)
            return
        delete_result = await google_calendar_service.delete_event(
            str(chat_id),
            calendar_id=str(link.get("calendar_id") or "primary"),
            google_event_id=str(link.get("google_event_id") or ""),
        )
        if delete_result.get("ok"):
            await google_event_links_table_service.delete_event_link(chat_id, message_id)
            await telegram_service.clear_message_reply_markup(chat_id, message_id)
            await telegram_service.send_message(chat_id, EVENT_REMOVED_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_REMOVED_MESSAGE)
            return
        if delete_result.get("error") == "not_found":
            await google_event_links_table_service.delete_event_link(chat_id, message_id)
            await telegram_service.clear_message_reply_markup(chat_id, message_id)
            await telegram_service.send_message(chat_id, EVENT_NOT_FOUND_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_NOT_FOUND_MESSAGE)
            return
        if delete_result.get("error") in {"reconnect_required", "not_connected", "missing_access_token"}:
            await telegram_service.send_message(chat_id, EVENT_RECONNECT_REQUIRED_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_RECONNECT_REQUIRED_MESSAGE)
            return
        await telegram_service.send_message(chat_id, EVENT_REMOVE_FAILED_MESSAGE)
        await history_table_service.save_turn(chat_id, "assistant", EVENT_REMOVE_FAILED_MESSAGE)
        return
    if data == EVENT_EDIT_CONFIRM_CALLBACK_DATA:
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        await history_table_service.save_turn(chat_id, "user", "User confirmed event update.")
        link = await google_event_links_table_service.get_event_link(chat_id, message_id)
        if not isinstance(link, dict):
            await telegram_service.send_message(chat_id, EVENT_NOT_FOUND_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_NOT_FOUND_MESSAGE)
            return
        draft = await event_draft_table_service.load_event_draft(chat_id)
        if not isinstance(draft, dict):
            await telegram_service.send_message(chat_id, EVENT_UPDATE_FAILED_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_UPDATE_FAILED_MESSAGE)
            return
        update_result = await google_calendar_service.update_event(
            str(chat_id),
            calendar_id=str(link.get("calendar_id") or "primary"),
            google_event_id=str(link.get("google_event_id") or ""),
            title=draft.get("title"),
            start=draft.get("start"),
            end=draft.get("end"),
        )
        if update_result.get("ok"):
            await google_event_links_table_service.delete_event_link(chat_id, message_id)
            await event_draft_table_service.delete_event_draft(chat_id)
            await telegram_service.clear_message_reply_markup(chat_id, message_id)
            await telegram_service.send_message(chat_id, EVENT_UPDATED_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_UPDATED_MESSAGE)
            return
        if update_result.get("error") == "not_found":
            await google_event_links_table_service.delete_event_link(chat_id, message_id)
            await telegram_service.clear_message_reply_markup(chat_id, message_id)
            await telegram_service.send_message(chat_id, EVENT_NOT_FOUND_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_NOT_FOUND_MESSAGE)
            return
        if update_result.get("error") in {"reconnect_required", "not_connected", "missing_access_token"}:
            await telegram_service.send_message(chat_id, EVENT_RECONNECT_REQUIRED_MESSAGE)
            await history_table_service.save_turn(chat_id, "assistant", EVENT_RECONNECT_REQUIRED_MESSAGE)
            return
        await telegram_service.send_message(chat_id, EVENT_UPDATE_FAILED_MESSAGE)
        await history_table_service.save_turn(chat_id, "assistant", EVENT_UPDATE_FAILED_MESSAGE)
        return

    if data not in {
        CLEAR_HISTORY_CONFIRM_CALLBACK_DATA,
        CLEAR_HISTORY_CANCEL_CALLBACK_DATA,
    }:
        return

    chat_id = message["chat"]["id"]
    message_id = message["message_id"]

    markup_start = time.monotonic()
    await telegram_service.clear_message_reply_markup(chat_id, message_id)
    logging_utils.log_prefixed_fields(
        "CLEAR_REPLY_MARKUP_DURATION",
        ("chat_id", chat_id),
        ("message_id", message_id),
        ("ms", int((time.monotonic() - markup_start) * 1000)),
    )

    if data == CLEAR_HISTORY_CONFIRM_CALLBACK_DATA:
        cleanup_start = time.monotonic()
        await cleanup_service.cleanup_chat_history(chat_id, full=True)
        logging_utils.log_prefixed_fields(
            "CLEANUP_HISTORY_DURATION",
            ("chat_id", chat_id),
            ("ms", int((time.monotonic() - cleanup_start) * 1000)),
        )
        send_start = time.monotonic()
        await telegram_service.send_message(chat_id, HISTORY_CLEARED_MESSAGE)
        logging_utils.log_prefixed_fields(
            "SEND_HISTORY_CLEARED_DURATION",
            ("chat_id", chat_id),
            ("ms", int((time.monotonic() - send_start) * 1000)),
        )


def _parse_event_created_reply(reply: str) -> dict | None:
    if not reply.startswith(EVENT_CREATED_REPLY_PREFIX):
        return None
    raw = reply[len(EVENT_CREATED_REPLY_PREFIX):]
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if not payload.get("summary") or not payload.get("google_event_id"):
        return None
    return payload


def _parse_event_remove_preview_reply(reply: str) -> dict | None:
    if not reply.startswith(EVENT_REMOVE_PREVIEW_REPLY_PREFIX):
        return None
    raw = reply[len(EVENT_REMOVE_PREVIEW_REPLY_PREFIX):]
    if "\n" not in raw:
        return None
    google_event_id, preview = raw.split("\n", 1)
    if not google_event_id or not preview:
        return None
    return {"google_event_id": google_event_id, "preview": preview}
