from .message_processor_abstract import MessageProcessor
from src.services import history_table_service
from src.services import s3_service
from src.services import telegram_service
from src.ai.model_provider import get_model_provider
from src.utils import capabilities_utils
from src.utils.constants import (
    TRANSCRIBED_VOICE_PROMPT_TEMPLATE,
    CATEGORY_LIMITATION_REASONS,
    MESSAGE_CATEGORIZATION_ENABLED,
)

model_provider = get_model_provider()


class SimpleMessageProcessor(MessageProcessor):
    async def handle_text_message(self, chat_id: str, text: str, is_transcribed: bool, history):
        if MESSAGE_CATEGORIZATION_ENABLED:
            category = await model_provider.classify_user_message(text)

            if category in CATEGORY_LIMITATION_REASONS:
                limitation_reason = CATEGORY_LIMITATION_REASONS[category]
                prompt = capabilities_utils.build_capability_limitation_prompt(text, limitation_reason)
                reply = await model_provider.generate_reply(prompt, chat_id=chat_id)
                return reply

        prompt = text
        if is_transcribed:
            prompt = TRANSCRIBED_VOICE_PROMPT_TEMPLATE.format(message=text)
        reply = await model_provider.generate_reply(prompt, history, chat_id=chat_id)

        return reply
    

    async def handle_photo_message(self, file_id: str, caption: str, chat_id: str):
        file_bytes = await telegram_service.download_file_from_telegram(file_id)
        if file_bytes is None:
            reply = "Sorry, I could not download your photo"
            return reply, None, None

        file_url, file_key = await s3_service.upload_file_to_s3(file_bytes, file_id)
        history = await history_table_service.load_model_history(chat_id)
        reply = await model_provider.generate_reply(caption, history, file_bytes)
        return reply, file_url, file_key
