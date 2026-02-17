from src.utils.util import split_html_message


def test_split_returns_single_chunk_when_within_limit():
    text = "Short text"
    assert split_html_message(text, max_length=50) == [text]


def test_split_prefers_paragraph_halves():
    paragraphs = [f"Paragraph {i}" for i in range(1, 6)]
    text = "\n\n".join(paragraphs)

    parts = split_html_message(text, max_length=len("\n\n".join(paragraphs[:3])))

    assert len(parts) == 2
    assert parts[0] == "\n\n".join(paragraphs[:3])
    assert parts[1] == "\n\n".join(paragraphs[3:])


def test_split_falls_back_to_length_when_no_paragraph_split_possible():
    text = "Line 1\nLine 2\nLine 3"
    parts = split_html_message(text, max_length=8)

    assert len(parts) > 1
    assert all(len(part) <= 8 for part in parts)
    assert "".join(parts) == text
