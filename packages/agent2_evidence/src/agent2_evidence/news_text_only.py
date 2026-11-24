"""Extract plain article text from HTML with zero retained media bytes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

DOC_TYPE = "news_text_only"

_MEDIA_TAGS = frozenset({"img", "video", "picture", "source", "audio"})

_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "tr",
        "blockquote",
        "section",
        "article",
        "header",
        "footer",
        "hr",
    }
)

_DATA_BASE64_RE = re.compile(
    r"data:[^;\"'\s>]+;base64,[A-Za-z0-9+/=\s]+",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NewsTextOnlyResult:
    doc_type: str
    text: str
    retained_media_bytes: int


def extract_news_text_only(html: str) -> NewsTextOnlyResult:
    """Strip embedded media and return article text tagged ``news_text_only``."""
    sanitized = _strip_data_base64_payloads(html)
    text = _extract_visible_text(sanitized)
    retained = measure_retained_media_bytes(text.encode("utf-8"))
    return NewsTextOnlyResult(
        doc_type=DOC_TYPE,
        text=text,
        retained_media_bytes=retained,
    )


def measure_retained_media_bytes(payload: bytes) -> int:
    """Count media bytes still present in extracted text (must stay 0)."""
    decoded = payload.decode("utf-8", errors="surrogateescape")
    total = sum(
        len(match.group(0).encode("utf-8")) for match in _DATA_BASE64_RE.finditer(decoded)
    )
    lowered = decoded.lower()
    for needle in ("<img", "<video"):
        start = 0
        while True:
            idx = lowered.find(needle, start)
            if idx == -1:
                break
            total += len(needle.encode("utf-8"))
            start = idx + len(needle)
    return total


def _strip_data_base64_payloads(markup: str) -> str:
    return _DATA_BASE64_RE.sub("", markup)


def _extract_visible_text(markup: str) -> str:
    parser = _NewsTextParser()
    parser.feed(markup)
    parser.close()
    return _collapse_whitespace("".join(parser.parts))


def _collapse_whitespace(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        folded = " ".join(line.split())
        if folded:
            lines.append(folded)
    return "\n".join(lines).strip()


class _NewsTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l in _MEDIA_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_l in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in _MEDIA_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag_l in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l in _MEDIA_TAGS:
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if _DATA_BASE64_RE.search(data):
            data = _DATA_BASE64_RE.sub("", data)
        self.parts.append(data)