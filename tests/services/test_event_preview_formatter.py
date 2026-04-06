from src.services import event_preview_formatter


def test_build_event_edit_preview_text_formats_updated_layout():
    text = event_preview_formatter.build_event_edit_preview_text(
        {
            "google_event_id": "evt-1",
            "title": "Old title",
            "start": "2026-03-10T10:00:00+00:00",
            "end": "2026-03-10T11:00:00+00:00",
        },
        {
            "title": "New title",
        },
    )

    assert "Do you confirm the update?" in text
    assert "Title: Old title -> New title" in text
    assert "Start: 2026-03-10 10:00" in text
    assert "End: 2026-03-10 11:00" in text


def test_build_event_edit_preview_text_shows_current_values_when_draft_missing():
    text = event_preview_formatter.build_event_edit_preview_text(
        {
            "google_event_id": "evt-1",
            "title": "Old title",
            "start": "2026-03-10T10:00:00+00:00",
            "end": "2026-03-10T11:00:00+00:00",
        },
        None,
    )

    assert "Title: Old title" in text
    assert "Start: 2026-03-10 10:00" in text
    assert "End: 2026-03-10 11:00" in text
