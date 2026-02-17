import time
from src.utils import logging_utils
from src.repository import transcription_repository


async def save_transcription_job(chat_id: int, job_id: str, file_url: str, file_key: str):
    item = {
        "chat_id": str(chat_id),
        "ts": int(time.time() * 1000),
        "job_id": job_id,
        "file_url": file_url,
        "file_key": file_key,
        "status": "pending",
    }
    logging_utils.log_prefixed_message_full("Saving transcription job", item)
    return await transcription_repository.put_job(item)


async def get_by_job_id(job_id: str) -> str | None:
    try:
        item = await transcription_repository.get_job_by_id(job_id)
        if not item:
            print(f"No transcription found for job_id={job_id}")
            return None
        return item
    except Exception as e:
        print(f"Error getting transcription {job_id}: {e}")
        return None


def mark_job_done(job_id: str) -> bool:
    """
    Mark a job as done. Returns True if we transitioned from pending -> done,
    False if it was already done (duplicate).
    """
    try:
        return transcription_repository.update_status_if_pending(job_id, "done")
    except Exception as e:
        print(f"Failed to mark job {job_id} as done: {e}")
        return False


async def delete_job(job_id: str) -> None:
    try:
        await transcription_repository.delete_job(job_id)
    except Exception as e:
        print(f"Failed to delete transcription job {job_id}: {e}")
