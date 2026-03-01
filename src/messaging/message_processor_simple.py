from src.ai.model_provider import get_model_provider
from src.utils.constants import (
    TRANSCRIBED_VOICE_PROMPT_TEMPLATE,
)

model_provider = get_model_provider()


async def handle_text_message(chat_id: str, text: str, is_transcribed: bool, history):
    prompt = text
    if is_transcribed:
        prompt = TRANSCRIBED_VOICE_PROMPT_TEMPLATE.format(message=text)
    reply = await model_provider.generate_reply(prompt, history, chat_id=chat_id)

    return reply
