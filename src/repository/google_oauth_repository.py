import asyncio
import os

import boto3

dynamodb = boto3.resource("dynamodb")
google_oauth_table = dynamodb.Table(
    os.getenv("GOOGLE_OAUTH_TABLE_NAME", "calendar_google_oauth_dev")
)


async def get_connection(chat_id: str) -> dict | None:
    response = await asyncio.to_thread(
        google_oauth_table.get_item,
        Key={"chat_id": chat_id},
    )
    return response.get("Item") if isinstance(response, dict) else None


async def put_connection(item: dict):
    return await asyncio.to_thread(
        google_oauth_table.put_item,
        Item=item,
    )
