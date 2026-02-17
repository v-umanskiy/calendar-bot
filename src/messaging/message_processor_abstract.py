from abc import ABC, abstractmethod

class MessageProcessor(ABC):
    @abstractmethod
    async def handle_text_message(self, chat_id: str, text: str, is_transcribed: bool, history):
        pass


    @abstractmethod
    async def handle_photo_message(self, file_id: str, caption: str, chat_id: str):
        pass
