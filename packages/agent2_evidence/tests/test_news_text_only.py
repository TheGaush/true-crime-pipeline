"""Tests for the news text-only HTML extractor."""

from __future__ import annotations

import base64

from agent2_evidence.news_text_only import DOC_TYPE, extract_news_text_only

# Minimal PNG payload stands in for an embedded mugshot.
_MUGSHOT_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
).decode("ascii")

_ARTICLE_HTML = f"""<!DOCTYPE html>
<html>
<head><title>Booking report</title></head>
<body>
<article>
  <h1>Suspect booked after porch incident</h1>
  <p>Deputies confirmed an arrest late Tuesday.</p>
  <img alt="mugshot" src="data:image/png;base64,{_MUGSHOT_PNG}" />
  <picture>
    <source srcset="data:image/webp;base64,{_MUGSHOT_PNG}" type="image/webp" />
    <img src="data:image/png;base64,{_MUGSHOT_PNG}" />
  </picture>
  <video controls poster="data:image/png;base64,{_MUGSHOT_PNG}">
    <source src="data:video/mp4;base64,QUJDREVGRw==" type="video/mp4" />
  </video>
  <audio src="data:audio/wav;base64,UklGRg=="></audio>
  <p>Arraignment is scheduled for Monday morning.</p>
</article>
</body>
</html>
"""


def test_extract_news_text_only_strips_embedded_media() -> None:
    result = extract_news_text_only(_ARTICLE_HTML)
    body = result.text.encode("utf-8")

    assert result.doc_type == DOC_TYPE
    assert result.retained_media_bytes == 0
    assert "Suspect booked after porch incident" in result.text
    assert "Arraignment is scheduled for Monday morning." in result.text
    assert _MUGSHOT_PNG.encode("ascii") not in body
    assert b"<img" not in body
    assert b"<video" not in body


def test_extract_news_text_only_plain_paragraphs() -> None:
    html = "<html><body><p>Alpha</p><p>Beta</p></body></html>"
    result = extract_news_text_only(html)

    assert result.doc_type == DOC_TYPE
    assert result.retained_media_bytes == 0
    assert result.text == "Alpha\nBeta"