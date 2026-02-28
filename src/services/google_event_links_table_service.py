import time

from src.repository import google_event_links_repository
from src.utils import logging_utils


async def save_event_link(
    chat_id: str | int,
    telegram_message_id: str | int,
    calendar_id: str,
    google_event_id: str,
):
    item = {
        "chat_id": str(chat_id),
        "telegram_message_id": str(telegram_message_id),
        "calendar_id": calendar_id,
        "google_event_id": google_event_id,
        "created_at": int(time.time()),
    }
    logging_utils.log_prefixed_message_full("Saving Google event link", item)
    return await google_event_links_repository.put_event_link(item)


async def get_event_link(chat_id: str | int, telegram_message_id: str | int) -> dict | None:
    return await google_event_links_repository.get_event_link(
        str(chat_id),
        str(telegram_message_id),
    )


async def delete_event_link(chat_id: str | int, telegram_message_id: str | int):
    return await google_event_links_repository.delete_event_link(
        str(chat_id),
        str(telegram_message_id),
    )
