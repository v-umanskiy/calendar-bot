import asyncio
import os
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
transcriptions_table = dynamodb.Table(os.getenv("TRANSCRIPTIONS_TABLE_NAME"))


async def put_job(item: dict):
    return await asyncio.to_thread(transcriptions_table.put_item, Item=item)


async def get_job_by_id(job_id: str) -> dict | None:
    resp = transcriptions_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("job_id").eq(job_id),
        Limit=1,
        ScanIndexForward=False,
    )

    items = resp.get("Items", [])
    return items[0] if items else None


def update_status_if_pending(job_id: str, new_status: str) -> bool:
    try:
        resp = transcriptions_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :new_status",
            ConditionExpression="#s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":new_status": new_status, ":pending": "pending"},
            ReturnValues="UPDATED_NEW",
        )
        return True
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False


async def delete_job(job_id: str) -> None:
    await asyncio.to_thread(
        transcriptions_table.delete_item,
        Key={"job_id": job_id},
    )
