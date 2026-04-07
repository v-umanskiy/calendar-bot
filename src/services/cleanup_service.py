import os
from src.utils import logging_utils

from . import event_draft_table_service
from . import history_table_service
from . import s3_service


WINDOW_TURNS = int(os.getenv("WINDOW_TURNS", "12"))


async def cleanup_chat_history(chat_id: int, *, full: bool = False) -> None:
    logging_utils.log_prefixed_fields("Starting cleanup", ("chat_id", chat_id), ("full", full))
    try:
        keep = None if full else WINDOW_TURNS
        deleted_turns = await history_table_service.delete_turns(chat_id, keep=keep)
        if full:
            await event_draft_table_service.delete_event_draft(chat_id)

        deleted_turns = deleted_turns or []
        file_keys = [item["file_key"] for item in deleted_turns if item.get("file_key")]
        logging_utils.log_prefixed_message_full(
            "Cleanup summary",
            {
                "chat_id": chat_id,
                "mode": "full" if full else "partial",
                "deleted_turns": len(deleted_turns),
                "files_to_delete": len(file_keys),
            },
        )
        if not file_keys:
            return

        await s3_service.delete_files_from_s3(file_keys)
    except Exception as exc:
        print(f"Cleanup for chat_id {chat_id} failed: {repr(exc)}")

