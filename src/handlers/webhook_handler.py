import asyncio

from src.services import cleanup_service
from src.services import telegram_service
from src.messaging import message_handlers


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

    await telegram_service.send_chat_action(chat_id, "typing")
    indicator = asyncio.create_task(_chat_action_indicator(chat_id, "typing"))
    try:
        if voice:
            await message_handlers.handle_voice_message(voice, chat_id)
        elif document:
            await message_handlers.handle_unsupported_message(chat_id)
        elif text:
            await message_handlers.handle_text_message(chat_id, text)
        else:
            await message_handlers.handle_unsupported_message(chat_id)
    except Exception as exc:
        print("Error while processing Telegram webhook:", exc)
    finally:
        indicator.cancel()
        try:
            await indicator
        except asyncio.CancelledError:
            pass
        await cleanup_service.cleanup_chat_history(chat_id)
        return {"ok": True}


async def _chat_action_indicator(chat_id: str, action: str):
    try:
        while True:
            await telegram_service.send_chat_action(chat_id, action)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
