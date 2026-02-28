import asyncio
import os

import boto3

dynamodb = boto3.resource("dynamodb")
google_event_links_table = dynamodb.Table(
    os.getenv("GOOGLE_EVENT_LINKS_TABLE_NAME", "calendar_google_event_links_dev")
)


async def put_event_link(item: dict):
    return await asyncio.to_thread(
        google_event_links_table.put_item,
        Item=item,
    )


async def get_event_link(chat_id: str, telegram_message_id: str) -> dict | None:
    response = await asyncio.to_thread(
        google_event_links_table.get_item,
        Key={
            "chat_id": chat_id,
            "telegram_message_id": telegram_message_id,
        },
    )
    return response.get("Item") if isinstance(response, dict) else None


async def delete_event_link(chat_id: str, telegram_message_id: str):
    return await asyncio.to_thread(
        google_event_links_table.delete_item,
        Key={
            "chat_id": chat_id,
            "telegram_message_id": telegram_message_id,
        },
    )
