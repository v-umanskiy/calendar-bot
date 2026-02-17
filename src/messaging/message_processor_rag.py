from src.messaging.message_processor_abstract import MessageProcessor
from src.rag import pinecone_service
from src.rag import file_service
from src.ai.model_provider import get_model_provider
from src.utils.constants import (
    EXTENSION_PROMPT,
    RAG_PROMPT,
    ANSWER_NOT_FOUND_PROMPT,
    RAG_PHOTO_NOT_SUPPORTED_PROMPT,
)


model_provider = get_model_provider()


class RagMessageProcessor(MessageProcessor):
    async def handle_text_message(self, chat_id: str, text: str, is_transcribed: bool, history):
        extended_prompt = await model_provider.generate_reply(EXTENSION_PROMPT + text, chat_id=chat_id)
        selected_files = pinecone_service.select_relevant_files(extended_prompt)

        if not selected_files:
            reply = await model_provider.generate_reply(ANSWER_NOT_FOUND_PROMPT + text, chat_id=chat_id)
        else:
            content = file_service.get_content(selected_files[0]["filename"])
            prompt = RAG_PROMPT.replace("{question}", text).replace("{knowledge}", content)
            reply = await model_provider.generate_reply(prompt, history, chat_id=chat_id)

        return reply
    

    async def handle_photo_message(self, file_id: str, caption: str, chat_id: str):
        return RAG_PHOTO_NOT_SUPPORTED_PROMPT, None, None
