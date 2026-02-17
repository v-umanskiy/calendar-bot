import html
import math
import re

TELEGRAM_HTML_LENGTH_LIMIT = 4096

# markdown headings (### Title …) to be converted into bold lines
HEADING_RE    = re.compile(r"(?m)^[ \t\u00A0\u202F]*#{3,6}[ \t\u00A0\u202F]+(.+?)[ \t\u00A0\u202F]*#*\s*$")
# line-start bullets: *, **, ***, or -
BULLET_RE     = re.compile(r"(?m)^[ \t\u00A0\u202F]*(\*{1,3}|-)[ \t\u00A0\u202F]+")
# blockquote lines: > text
BLOCKQUOTE_RE = re.compile(r"^[ \t\u00A0\u202F]*>(.*)$")
# fenced code blocks: ```[lang]? \n ... \n```
CODEBLOCK_RE  = re.compile(r"```(?:[a-zA-Z0-9_+\-]+)?\n([\s\S]*?)```", re.MULTILINE)
# inline code: `code`
INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")

def to_html(text: str) -> str:
    s = text.replace("\r\n", "\n")

    # 0) Extract fenced code blocks first and stash them
    code_blocks = []
    def _store(m):
        body = m.group(1).rstrip("\n")
        # Escape inside code, no <br>; Telegram wants <pre><code>…</code></pre>
        esc = html.escape(body, quote=False)
        token = f"__CODEBLOCK_{len(code_blocks)}__"
        code_blocks.append((token, f"<pre><code>{esc}</code></pre>"))
        return token
    s = CODEBLOCK_RE.sub(_store, s)

    # 1) Convert ### headings into bold text so Telegram renders them prominently
    def _heading_sub(match: re.Match[str]) -> str:
        heading_text = match.group(1).strip()
        # Ensure a blank line follows headings for clearer separation
        return f"**{heading_text}**\n"

    s = HEADING_RE.sub(_heading_sub, s)

    # 2) Normalize bullets at start of line → "• "
    s = BULLET_RE.sub("• ", s)

    # 3) Convert quote lines into blockquote markers so Markdown inside still processes
    def _wrap_blockquotes(text: str) -> str:
        lines = text.split("\n")
        out: list[str] = []
        in_block = False

        def _open_block():
            out.append("__BLOCKQUOTE_START__")

        def _close_block():
            out.append("__BLOCKQUOTE_END__")

        for line in lines:
            m = BLOCKQUOTE_RE.match(line)
            if m:
                if not in_block:
                    _open_block()
                    in_block = True
                content = m.group(1)
                if content.startswith(" "):
                    content = content[1:]
                out.append(content)
            else:
                if in_block:
                    _close_block()
                    in_block = False
                out.append(line)

        if in_block:
            _close_block()

        return "\n".join(out)

    s = _wrap_blockquotes(s)

    # 4) Escape everything so raw < > & can’t break HTML
    s = html.escape(s, quote=False)

    # 5) Inline code requires protection from later formatting (italic/bold)
    inline_codes: list[tuple[str, str]] = []
    def _store_inline(match: re.Match[str]) -> str:
        token = f"__INLINECODE_{len(inline_codes)}__"
        inline_codes.append((token, f"<code>{match.group(1)}</code>"))
        return token
    s = INLINE_CODE_RE.sub(_store_inline, s)

    # 6) Minimal Markdown → Telegram-HTML
    # links: [text](url)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
    # bold+italic: ***text***
    s = re.sub(r"\*\*\*((?:(?!\*\*\*).)+?)\*\*\*", r"<b><i>\1</i></b>", s, flags=re.DOTALL)
    # bold: **text**  (line-scoped)
    s = re.sub(r"\*\*((?:(?!\*\*).)+?)\*\*", r"<b>\1</b>", s, flags=re.DOTALL)
    # italic: *text* (ensure non-whitespace right after/before the markers to avoid math symbols)
    s = re.sub(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)", r"<i>\1</i>", s, flags=re.DOTALL)

    # 7) Restore inline code and block code placeholders
    for token, inline_html in inline_codes:
        s = s.replace(token, inline_html)
    for token, block in code_blocks:
        s = s.replace(token, block)

    # 8) Restore blockquote markers last so they can wrap converted HTML
    s = s.replace("__BLOCKQUOTE_START__\n", "<blockquote>")
    s = s.replace("__BLOCKQUOTE_START__", "<blockquote>")
    s = s.replace("\n__BLOCKQUOTE_END__", "</blockquote>")
    s = s.replace("__BLOCKQUOTE_END__", "</blockquote>")

    # 9) Keep newlines as-is (Telegram HTML uses \n for breaks; <br> is not supported)
    return s


def split_html_message(html_text: str, max_length: int = TELEGRAM_HTML_LENGTH_LIMIT) -> list[str]:
    """Split HTML-formatted text into Telegram-sized chunks.

    Telegram refuses messages longer than 4096 characters. We try to split
    oversized payloads along double-newline boundaries (paragraphs) to avoid
    breaking HTML tags, recursively halving the paragraph list. If a chunk still
    violates the limit because a single paragraph is too large, we fall back to
    cutting on the last newline before the limit (or a hard cut as a last resort).
    """

    if max_length <= 0:
        raise ValueError("max_length must be positive")

    if len(html_text) <= max_length:
        return [html_text]

    def _split(content: str) -> list[str]:
        if len(content) <= max_length:
            return [content]

        paragraphs = [p for p in content.split("\n\n") if p]
        if len(paragraphs) > 1:
            mid = math.ceil(len(paragraphs) / 2)
            head = "\n\n".join(paragraphs[:mid])
            tail = "\n\n".join(paragraphs[mid:])
        else:
            split_at = content.rfind("\n", 0, max_length)
            if split_at <= 0:
                split_at = max_length
            head = content[:split_at]
            tail = content[split_at:]

        if not head or not tail:
            return _split(head or tail)

        return _split(head) + _split(tail)

    return _split(html_text)
