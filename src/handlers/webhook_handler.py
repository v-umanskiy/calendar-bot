from src.services import cleanup_service
from src.services import langfuse_service
from src.messaging import message_handlers
from . import transcription_handler


async def handle_telegram_webhook_data(data: any) -> any:
    try:
        return await _handle_telegram_webhook_data(data)
    except Exception as exc:
        print("Unhandled error while processing Telegram webhook:", exc)
        return {"ok": True}


async def _handle_telegram_webhook_data(data: any) -> any:
    callback_query = data.get("callback_query")
    if callback_query:
        await message_handlers.handle_callback_query(callback_query)
        return {"ok": True}

    message = data.get("message")
    if not message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    photos = message.get("photo")
    voice = message.get("voice")
    document = message.get("document")
    text = message.get("text")

    trace = langfuse_service.start_trace(
        name="telegram_webhook",
        user_id=str(chat_id),
        session_id=str(chat_id),
        input=text if text else None,
        metadata={
            "message_id": message.get("message_id"),
            "has_photo": bool(photos),
            "has_voice": bool(voice),
            "has_document": bool(document),
            "has_text": bool(text),
        },
        tags=["telegram"],
    )

    reply = None
    try:
        if photos:
            file_id = photos[-1]["file_id"]
            caption = message.get("caption")
            reply = await message_handlers.handle_photo_message(file_id, caption, chat_id)
        elif voice:
            reply = await message_handlers.handle_voice_message(voice, chat_id)
        elif document:
            reply = await message_handlers.handle_document_message(document, chat_id)
        elif text:
            reply = await message_handlers.handle_text_message(chat_id, text)
        else:
            reply = await message_handlers.handle_unsupported_message(chat_id)
        langfuse_service.end_trace(
            trace,
            status="ok",
            output=reply,
        )
    except Exception as exc:
        langfuse_service.end_trace(
            trace,
            status="error",
            metadata={"error": repr(exc)},
        )
    finally:
        await cleanup_service.cleanup_chat_history(chat_id)
        return {"ok": True}


async def handle_transcription_data(event: any) -> any:
    return await transcription_handler.handle_transcription_data(event)
