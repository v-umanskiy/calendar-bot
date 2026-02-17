import asyncio
import types
from unittest.mock import AsyncMock, Mock, call

from src.messaging import message_processor_rag
from src.messaging.message_processor_rag import RagMessageProcessor


def test_handle_text_message_returns_fallback_when_no_files(monkeypatch):
    processor = RagMessageProcessor()
    chat_id = "chat-1"
    text = "Where is the doc?"
    history = ["h"]
    extended_prompt = "extended"
    fallback_reply = "no info"

    get_reply_mock = AsyncMock(side_effect=[extended_prompt, fallback_reply])
    monkeypatch.setattr(message_processor_rag, "model_provider", types.SimpleNamespace(generate_reply=get_reply_mock))

    select_files_mock = Mock(return_value=[])
    monkeypatch.setattr(message_processor_rag.pinecone_service, "select_relevant_files", select_files_mock)

    result = asyncio.run(processor.handle_text_message(chat_id, text, False, history))

    assert result == fallback_reply
    select_files_mock.assert_called_once_with(extended_prompt)
    assert get_reply_mock.await_args_list == [
        call(message_processor_rag.EXTENSION_PROMPT + text, chat_id=chat_id),
        call(message_processor_rag.ANSWER_NOT_FOUND_PROMPT + text, chat_id=chat_id),
    ]


def test_handle_text_message_uses_selected_file(monkeypatch):
    processor = RagMessageProcessor()
    chat_id = "chat-1"
    text = "Give me spec"
    history = ["h"]
    extended_prompt = "extended prompt"
    selected_files = [{"filename": "doc.md"}]
    knowledge = "Document body"
    final_reply = "answer"

    get_reply_mock = AsyncMock(side_effect=[extended_prompt, final_reply])
    monkeypatch.setattr(message_processor_rag, "model_provider", types.SimpleNamespace(generate_reply=get_reply_mock))

    select_files_mock = Mock(return_value=selected_files)
    monkeypatch.setattr(message_processor_rag.pinecone_service, "select_relevant_files", select_files_mock)

    get_content_mock = Mock(return_value=knowledge)
    monkeypatch.setattr(message_processor_rag.file_service, "get_content", get_content_mock)

    result = asyncio.run(processor.handle_text_message(chat_id, text, False, history))

    expected_prompt = (
        message_processor_rag.RAG_PROMPT.replace("{question}", text)
        .replace("{knowledge}", knowledge)
    )

    assert result == final_reply
    select_files_mock.assert_called_once_with(extended_prompt)
    get_content_mock.assert_called_once_with("doc.md")
    assert get_reply_mock.await_args_list == [
        call(message_processor_rag.EXTENSION_PROMPT + text, chat_id=chat_id),
        call(expected_prompt, history, chat_id=chat_id),
    ]
