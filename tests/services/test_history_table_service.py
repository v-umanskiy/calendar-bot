import asyncio

from src.services import history_table_service


def test_turns_to_model_history_ignores_file_fields_and_keeps_text_only():
    turns = [
        {"role": "user", "text": "hello", "file_key": "unused-key"},
        {"role": "assistant", "text": "world", "file_url": "https://example.com/file"},
        {"role": "user", "file_key": "no-text"},
    ]

    result = asyncio.run(history_table_service.turns_to_model_history(turns))

    assert result == [
        {"role": "user", "text": "hello"},
        {"role": "assistant", "text": "world"},
    ]
