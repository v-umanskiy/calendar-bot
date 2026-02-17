import asyncio
import os
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
history_table = dynamodb.Table(os.getenv("HISTORY_TABLE_NAME"))


async def save_turn_item(item: dict):
    return await asyncio.to_thread(history_table.put_item, Item=item)


async def query_turns(chat_id: str, limit: int):
    def _query():
        resp = history_table.query(
            KeyConditionExpression=Key("chat_id").eq(chat_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return list(reversed(resp.get("Items", [])))
    return await asyncio.to_thread(_query)


async def delete_turns(chat_id: str, keep: int | None = None) -> list[dict]:
    def _cleanup():
        resp = history_table.query(
            KeyConditionExpression=Key("chat_id").eq(chat_id),
            ScanIndexForward=True
        )
        all_items = resp.get("Items", [])
        if keep is None:
            to_delete = list(all_items)
        else:
            to_delete = all_items[:-keep] if keep > 0 else list(all_items)
        if not to_delete:
            return []
        with history_table.batch_writer() as batch:
            for item in to_delete:
                batch.delete_item(Key={"chat_id": item["chat_id"], "ts": item["ts"]})
        return to_delete
    return await asyncio.to_thread(_cleanup)
