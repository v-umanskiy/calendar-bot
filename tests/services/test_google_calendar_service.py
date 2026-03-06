import asyncio
from datetime import timedelta, timezone
from unittest.mock import AsyncMock

from src.services import google_calendar_service


def test_delete_event_returns_not_found_on_http_410(monkeypatch):
    token_mock = AsyncMock(return_value={"ok": True, "access_token": "token-1"})
    delete_mock = AsyncMock(return_value=(False, 410))

    monkeypatch.setattr(google_calendar_service.google_oauth_token_service, "get_valid_access_token", token_mock)
    monkeypatch.setattr(google_calendar_service, "_delete_event", delete_mock)

    result = asyncio.run(
        google_calendar_service.delete_event(
            "chat-111",
            calendar_id="primary",
            google_event_id="evt-1",
        )
    )

    assert result == {"ok": False, "error": "not_found"}
    token_mock.assert_awaited_once_with("chat-111")
    delete_mock.assert_awaited_once_with(
        "token-1",
        calendar_id="primary",
        google_event_id="evt-1",
    )


def test_search_primary_events_by_query_uses_fixed_window(monkeypatch):
    token_mock = AsyncMock(return_value={"ok": True, "access_token": "token-1"})
    list_mock = AsyncMock(return_value=(True, 200, {"items": []}))

    monkeypatch.setattr(google_calendar_service.google_oauth_token_service, "get_valid_access_token", token_mock)
    monkeypatch.setattr(google_calendar_service, "_list_events_in_range", list_mock)

    result = asyncio.run(
        google_calendar_service.search_primary_events(
            "chat-111",
            start=None,
            end=None,
        )
    )

    assert result == {"ok": False, "error": "invalid_time_range"}
    list_mock.assert_not_awaited()


def test_search_primary_events_by_query_uses_query_and_fixed_window(monkeypatch):
    token_mock = AsyncMock(return_value={"ok": True, "access_token": "token-1"})
    list_mock = AsyncMock(return_value=(True, 200, {"items": []}))

    monkeypatch.setattr(google_calendar_service.google_oauth_token_service, "get_valid_access_token", token_mock)
    monkeypatch.setattr(google_calendar_service, "_list_events_in_range", list_mock)

    result = asyncio.run(
        google_calendar_service.search_primary_events_by_query(
            "chat-111",
            query="danang",
        )
    )

    assert result["ok"] is True
    kwargs = list_mock.await_args.kwargs
    time_min = kwargs["time_min"]
    time_max = kwargs["time_max"]
    assert kwargs["query"] == "danang"
    assert time_min.tzinfo == timezone.utc
    assert time_max.tzinfo == timezone.utc
    assert (time_max - time_min) == timedelta(
        days=google_calendar_service.EVENT_LOOKUP_PAST_DAYS + google_calendar_service.EVENT_LOOKUP_FUTURE_DAYS
    )


def test_search_primary_events_fills_missing_end_with_30_days(monkeypatch):
    token_mock = AsyncMock(return_value={"ok": True, "access_token": "token-1"})
    list_mock = AsyncMock(return_value=(True, 200, {"items": []}))

    monkeypatch.setattr(google_calendar_service.google_oauth_token_service, "get_valid_access_token", token_mock)
    monkeypatch.setattr(google_calendar_service, "_list_events_in_range", list_mock)

    start = "2026-03-05T10:00:00+00:00"
    result = asyncio.run(
        google_calendar_service.search_primary_events(
            "chat-111",
            start=start,
        )
    )

    assert result["ok"] is True
    kwargs = list_mock.await_args.kwargs
    assert (kwargs["time_max"] - kwargs["time_min"]) == timedelta(
        days=google_calendar_service.EVENT_LOOKUP_ONE_SIDED_DAYS
    )


def test_search_primary_events_fills_missing_start_with_30_days(monkeypatch):
    token_mock = AsyncMock(return_value={"ok": True, "access_token": "token-1"})
    list_mock = AsyncMock(return_value=(True, 200, {"items": []}))

    monkeypatch.setattr(google_calendar_service.google_oauth_token_service, "get_valid_access_token", token_mock)
    monkeypatch.setattr(google_calendar_service, "_list_events_in_range", list_mock)

    end = "2026-03-05T10:00:00+00:00"
    result = asyncio.run(
        google_calendar_service.search_primary_events(
            "chat-111",
            end=end,
        )
    )

    assert result["ok"] is True
    kwargs = list_mock.await_args.kwargs
    assert (kwargs["time_max"] - kwargs["time_min"]) == timedelta(
        days=google_calendar_service.EVENT_LOOKUP_ONE_SIDED_DAYS
    )
