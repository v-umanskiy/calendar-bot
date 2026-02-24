import asyncio
import time
import uuid

from src.services import cleanup_service
from src.services import history_table_service
from src.services import s3_service
from src.services import telegram_service
from src.services import transcription_aws_service
from src.services import transcription_table_service
from .message_processor_simple import (
    handle_text_message as process_text_message,
    handle_photo_message as process_photo_message,
)
from src.utils import logging_utils
from src.utils.constants import (
    WELCOME_MESSAGE,
    CLEAR_HISTORY_MESSAGE,
    HISTORY_CLEARED_MESSAGE,
    CLEAR_HISTORY_KEYBOARD,
    CLEAR_HISTORY_CONFIRM_CALLBACK_DATA,
    CLEAR_HISTORY_CANCEL_CALLBACK_DATA,
)


async def handle_text_message(chat_id: str, text: str, *, is_transcribed: bool = False) -> str | None:
    command_reply = await _handle_message_codes(chat_id, text)
    if command_reply is not None:
        return command_reply

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

    await telegram_service.send_message(chat_id, reply)
    await history_table_service.save_turn(chat_id, "user", text)
    await history_table_service.save_turn(chat_id, "assistant", reply)
    return reply


async def handle_photo_message(file_id: str, caption: str, chat_id: str) -> str | None:
    indicator = asyncio.create_task(_chat_action_indicator(chat_id, "typing"))
    try:
        reply, file_url, file_key = await process_photo_message(file_id, caption, chat_id)
        await telegram_service.send_message(chat_id, reply)
        await history_table_service.save_turn(chat_id, "user", caption, file_url, file_key)
        await history_table_service.save_turn(chat_id, "assistant", reply)
        return reply
    finally:
        indicator.cancel()
        try:
            await indicator
        except asyncio.CancelledError:
            pass


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


async def handle_document_message(document: dict, chat_id: str) -> str:
    file_name = document.get("file_name")
    if file_name:
        message = f"Sorry, I can't process files like {file_name} yet. Try sending text, a voice note, or a photo."
    else:
        message = "Sorry, I can't process file attachments yet. Try sending text, a voice note, or a photo."
    await telegram_service.send_message(chat_id, message)
    return message


async def handle_unsupported_message(chat_id: str) -> str:
    message = "Sorry, I'm not sure how to handle that. Try sending text, a voice note, or a photo."
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
        await telegram_service.send_message(chat_id, WELCOME_MESSAGE)
        return WELCOME_MESSAGE
    if stripped_text == "/clear":
        await telegram_service.send_message_with_reply_markup(
            chat_id,
            CLEAR_HISTORY_MESSAGE,
            CLEAR_HISTORY_KEYBOARD,
        )
        return CLEAR_HISTORY_MESSAGE
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
    if not message or data not in {
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
