import time
import os
from src.utils import logging_utils
from . import s3_service
from src.repository import history_repository


async def save_turn(chat_id: int, role: str, text: str = None,
                    file_url: str = None, file_key: str = None):
    item = {
        "chat_id": str(chat_id),
        "ts": int(time.time() * 1000),
        "role": role,
    }
    if text:
        item["text"] = text
    if file_url:
        item["file_url"] = file_url
    if file_key:
        item["file_key"] = file_key

    logging_utils.log_prefixed_message("Saving turn", item)
    return await history_repository.save_turn_item(item)


async def load_last_turns(chat_id: int) -> list[dict]:
    window_turns = int(os.getenv("WINDOW_TURNS", "12"))
    return await history_repository.query_turns(str(chat_id), window_turns)


async def delete_turns(chat_id: int, keep: int | None = None) -> list[dict]:
    return await history_repository.delete_turns(str(chat_id), keep=keep)


async def turns_to_model_history(turns: list[dict]) -> list[dict]:
    hist = []
    for turn in turns:
        entry: dict = {
            "role": "user" if turn["role"] == "user" else "assistant",
        }

        if turn.get("text"):
            entry["text"] = turn["text"]

        files = []
        if turn.get("file_key"):
            try:
                file_bytes = await s3_service.download_file_from_s3(turn["file_key"])
                if file_bytes:
                    files.append(
                        {
                            "mime_type": "image/jpeg",
                            "data": file_bytes,
                        }
                    )
            except IndexError:
                logging_utils.log_prefixed_message("Invalid S3 URL format", turn.get("file_url"))
            except Exception as exc:
                print(f"Failed to process S3 file for history: {repr(exc)}")

        if files:
            entry["files"] = files

        if entry.get("text") or entry.get("files"):
            hist.append(entry)
    return hist


async def load_model_history(chat_id: int) -> list[dict]:
    turns = await load_last_turns(chat_id)
    return await turns_to_model_history(turns)
