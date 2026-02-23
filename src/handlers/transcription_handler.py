import json
from urllib.parse import unquote_plus

from src.utils import logging_utils
from src.messaging import message_handlers
from src.services import cleanup_service
from src.services import s3_service
from src.services import transcription_table_service


async def handle_transcription_data(event: any) -> any:
    try:
        return await _handle_transcription_data(event)
    except Exception as exc:
        print("Unhandled error while processing transcription event:", exc)
        return {"ok": True}


async def _handle_transcription_data(event: any) -> any:
    obj_key = unquote_plus(event["detail"]["object"]["key"])

    if obj_key.endswith(".temp"):
        return {"status": "ignored"}

    file_bytes = await s3_service.download_file_from_s3(obj_key)
    if file_bytes is None:
        return {"status": "failed"}

    try:
        transcript_json = json.loads(file_bytes)
        logging_utils.log_prefixed_message("Transcript JSON loaded", transcript_json)
    except json.JSONDecodeError:
        return {"status": "invalid_json"}

    job_id = transcript_json.get("jobName")

    transcription_job = await transcription_table_service.get_by_job_id(job_id)
    if not transcription_job:
        return {"status": "missing_transcription_job"}
    if transcription_job["status"] != "pending":
        return {"status": "transcription_job_not_pending"}

    if not transcription_job["chat_id"]:
        return {"status": "missing_chat_id"}

    updated = transcription_table_service.mark_job_done(job_id)
    if not updated:
        return {"status": "transcription_job_not_pending"}

    transcripts = transcript_json.get("results", {}).get("transcripts", [])
    if not transcripts:
        return {"status": "empty_transcript"}

    reply = transcripts[0]["transcript"]
    await message_handlers.handle_text_message(
        transcription_job["chat_id"],
        reply,
        is_transcribed=True,
    )

    await cleanup_service.cleanup_transcription_job(transcription_job, obj_key)

    return {"status": "ok"}
