from src.utils import logging_utils
from src.repository import event_draft_repository


async def upsert_event_draft(
    chat_id: int,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
):
    fields: dict = {}

    if start is not None:
        fields["start"] = start
    if end is not None:
        fields["end"] = end
    if title is not None:
        fields["title"] = title

    if not fields:
        logging_utils.log_prefixed_message_full(
            "Upsert event draft skipped: no fields provided",
            {"chat_id": str(chat_id)},
        )
        return None

    logging_utils.log_prefixed_message_full(
        "Upserting event draft",
        {"chat_id": str(chat_id), "fields": fields},
    )
    return await event_draft_repository.upsert_draft_fields(str(chat_id), fields)


async def replace_event_draft(
    chat_id: int,
    start: str | None = None,
    end: str | None = None,
    title: str | None = None,
):
    item = {"chat_id": str(chat_id)}

    if start is not None:
        item["start"] = start
    if end is not None:
        item["end"] = end
    if title is not None:
        item["title"] = title

    logging_utils.log_prefixed_message_full("Replacing event draft", item)
    return await event_draft_repository.replace_draft_item(item)
