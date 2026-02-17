import asyncio

from src.handlers import transcription_handler


def handler(event, _context):
    print("TRANSCRIPT_EVENT:", event)
    asyncio.run(transcription_handler.handle_transcription_data(event))
    return {"ok": True}
