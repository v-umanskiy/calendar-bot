from src.services import cleanup_service
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
    voice = message.get("voice")
    document = message.get("document")
    text = message.get("text")

    reply = None
    try:
        if voice:
            reply = await message_handlers.handle_voice_message(voice, chat_id)
        elif document:
            reply = await message_handlers.handle_document_message(document, chat_id)
        elif text:
            reply = await message_handlers.handle_text_message(chat_id, text)
        else:
            reply = await message_handlers.handle_unsupported_message(chat_id)
    except Exception as exc:
        print("Error while processing Telegram webhook:", exc)
    finally:
        await cleanup_service.cleanup_chat_history(chat_id)
        return {"ok": True}


async def handle_transcription_data(event: any) -> any:
    return await transcription_handler.handle_transcription_data(event)
