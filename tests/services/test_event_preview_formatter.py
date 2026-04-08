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


def test_build_event_edit_preview_text_hides_arrow_when_value_is_unchanged():
    text = event_preview_formatter.build_event_edit_preview_text(
        {
            "google_event_id": "evt-1",
            "title": "doctor's appointment",
            "start": "2026-04-10T12:00:00+00:00",
            "end": "2026-04-10T13:00:00+00:00",
        },
        {
            "title": "doctor's appointment",
            "start": "2026-04-10T13:00:00+00:00",
            "end": "2026-04-10T14:00:00+00:00",
        },
    )

    assert "Title: doctor's appointment -> doctor's appointment" not in text
    assert "Title: doctor's appointment" in text
    assert "Start: 2026-04-10 12:00 -> 2026-04-10 13:00" in text
    assert "End: 2026-04-10 13:00 -> 2026-04-10 14:00" in text


def test_build_event_remove_preview_text_formats_expected_layout():
    text = event_preview_formatter.build_event_remove_preview_text(
        {
            "title": "Old title",
            "start": "2026-03-10T10:00:00+00:00",
            "end": "2026-03-10T11:00:00+00:00",
        }
    )

    assert "Do you confirm removal?" in text
    assert "Title: Old title" in text
    assert "Start: 2026-03-10 10:00" in text
    assert "End: 2026-03-10 11:00" in text
