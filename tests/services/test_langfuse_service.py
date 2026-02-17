import pytest

from src.services import langfuse_service


def test_generation_context_records_output(monkeypatch):
    generation = object()
    start_mock = lambda **kwargs: generation
    end_calls = []

    def _end_generation(gen, **kwargs):
        end_calls.append((gen, kwargs))

    monkeypatch.setattr(langfuse_service, "start_generation", start_mock)
    monkeypatch.setattr(langfuse_service, "end_generation", _end_generation)

    with langfuse_service.generation_context(
        name="test.run",
        model="test-model",
        input={"prompt": "hi"},
        metadata={"base": True},
        tags=["tag"],
    ) as ctx:
        ctx.record_output("ok", metadata={"extra": 1}, usage={"tokens": 2})

    assert end_calls == [
        (
            generation,
            {
                "output": "ok",
                "metadata": {"base": True, "extra": 1},
                "usage": {"tokens": 2},
            },
        )
    ]


def test_generation_context_records_error(monkeypatch):
    generation = object()
    start_mock = lambda **kwargs: generation
    end_calls = []

    def _end_generation(gen, **kwargs):
        end_calls.append((gen, kwargs))

    monkeypatch.setattr(langfuse_service, "start_generation", start_mock)
    monkeypatch.setattr(langfuse_service, "end_generation", _end_generation)

    with pytest.raises(RuntimeError, match="boom"):
        with langfuse_service.generation_context(
            name="test.error",
            metadata={"base": True},
        ):
            raise RuntimeError("boom")

    assert len(end_calls) == 1
    gen, kwargs = end_calls[0]
    assert gen is generation
    assert kwargs["metadata"] == {"base": True}
    assert "error" in kwargs and isinstance(kwargs["error"], RuntimeError)
