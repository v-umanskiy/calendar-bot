import pytest
import html
from src.utils.util import to_html


def test_bullet_points():
    text = "* item1\n- item2\n** subitem"
    expected = "• item1\n• item2\n• subitem"
    assert to_html(text) == html.escape(expected, quote=False)


def test_inline_code():
    text = "Use `print()` here"
    expected = "Use <code>print()</code> here"
    assert to_html(text) == expected


def test_inline_code_with_asterisk_stays_literal():
    text = "Compute `10 * 3` please"
    expected = "Compute <code>10 * 3</code> please"
    assert to_html(text) == expected


def test_plain_math_asterisk_remains_literal():
    text = "Result: 10 * 3 = 30\nThen 10*3+3"
    expected = "Result: 10 * 3 = 30\nThen 10*3+3"
    assert to_html(text) == expected


def test_bold_and_italic():
    text = "This is **bold** and *italic*"
    expected = "This is <b>bold</b> and <i>italic</i>"
    assert to_html(text) == expected


def test_multi_line_italic():
    text = "*First line\nsecond line*"
    expected = "<i>First line\nsecond line</i>"
    assert to_html(text) == expected


def test_blockquote_conversion():
    text = "> Quote line 1\n> Quote line 2\nText"
    expected = "<blockquote>Quote line 1\nQuote line 2</blockquote>\nText"
    assert to_html(text) == expected


def test_blockquote_keeps_inner_formatting():
    text = "> **Bold** and *italic* inside quote"
    expected = "<blockquote><b>Bold</b> and <i>italic</i> inside quote</blockquote>"
    assert to_html(text) == expected


def test_links():
    text = "Go to [OpenAI](https://openai.com)"
    expected = 'Go to <a href="https://openai.com">OpenAI</a>'
    assert to_html(text) == expected


def test_code_block():
    text = """```
def foo():
    return 42
```"""
    expected = "<pre><code>def foo():\n    return 42</code></pre>"
    assert to_html(text).strip() == expected


def test_mixed_content():
    text = "* Item with [link](https://example.com) and `code`"
    out = to_html(text)
    assert "• Item with " in out
    assert '<a href="https://example.com">link</a>' in out
    assert "<code>code</code>" in out


def test_heading_line_turns_bold_with_blank_line():
    text = "### Conclusion\nNext"
    expected = "<b>Conclusion</b>\n\nNext"
    assert to_html(text) == expected


def test_heading_at_end_adds_linebreak():
    text = "### Outro"
    expected = "<b>Outro</b>\n"
    assert to_html(text) == expected


def test_bold_with_nested_italic():
    text = "**Why Modern PHP (PHP 7.x, 8.x) is *Good*:**"
    expected = "<b>Why Modern PHP (PHP 7.x, 8.x) is <i>Good</i>:</b>"
    assert to_html(text) == expected


def test_bold_italic_combo():
    text = "***Bold italic***"
    expected = "<b><i>Bold italic</i></b>"
    assert to_html(text) == expected
