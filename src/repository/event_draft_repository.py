import asyncio
import os

import boto3

dynamodb = boto3.resource("dynamodb")
event_draft_table = dynamodb.Table(os.getenv("EVENT_DRAFT_TABLE_NAME", "event_draft_dev"))


async def replace_draft_item(item: dict):
    return await asyncio.to_thread(event_draft_table.put_item, Item=item)


async def upsert_draft_fields(chat_id: str, fields: dict):
    expression_attribute_names = {}
    expression_attribute_values = {}
    set_clauses = []

    for key, value in fields.items():
        name_token = f"#{key}"
        value_token = f":{key}"
        expression_attribute_names[name_token] = key
        expression_attribute_values[value_token] = value
        set_clauses.append(f"{name_token} = {value_token}")

    update_expression = "SET " + ", ".join(set_clauses)
    return await asyncio.to_thread(
        event_draft_table.update_item,
        Key={"chat_id": chat_id},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
        ReturnValues="ALL_NEW",
    )
