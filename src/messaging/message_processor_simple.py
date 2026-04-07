from src.ai.gemini_provider import generate_reply
from src.utils.constants import (
    TRANSCRIBED_VOICE_PROMPT_TEMPLATE,
)


async def handle_text_message(chat_id: str, text: str, is_transcribed: bool, history):
    prompt = text
    if is_transcribed:
        prompt = TRANSCRIBED_VOICE_PROMPT_TEMPLATE.format(message=text)
    reply = await generate_reply(prompt=prompt, chat_id=chat_id, history=history)

    return reply
