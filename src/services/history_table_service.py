import time
import os
from src.utils import logging_utils
from src.repository import history_repository


async def save_turn(chat_id: int, role: str, text: str = None):
    item = {
        "chat_id": str(chat_id),
        "ts": int(time.time() * 1000),
        "role": role,
    }
    if text:
        item["text"] = text

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

        if entry.get("text"):
            hist.append(entry)
    return hist


async def load_model_history(chat_id: int) -> list[dict]:
    turns = await load_last_turns(chat_id)
    return await turns_to_model_history(turns)
