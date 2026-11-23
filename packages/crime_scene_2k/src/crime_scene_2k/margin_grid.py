"""External-margin A-J / 1-10 inspection copy.

The clean still is never overwritten. Ticks live in the 64px charcoal
margin, so the inner pixels stay byte-for-byte identical.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw

MARGIN = 64
INK = (0x1B, 0x1B, 0x1D)
PARCHMENT = (0xE9, 0xE2, 0xD2)
COLS = "ABCDEFGHIJ"


def render_margin_grid(source: Image.Image) -> Image.Image:
    width, height = source.size
    canvas = Image.new("RGB", (width + MARGIN * 2, height + MARGIN * 2), INK)
    canvas.paste(source.convert("RGB"), (MARGIN, MARGIN))
    draw = ImageDraw.Draw(canvas)
    for index in range(10):
        x = MARGIN + int(round((index + 0.5) * width / 10))
        y = MARGIN + int(round((index + 0.5) * height / 10))
        draw.text((x - 4, 24), COLS[index], fill=PARCHMENT)
        draw.text((x - 4, height + MARGIN + 24), COLS[index], fill=PARCHMENT)
        draw.text((24, y - 6), str(index + 1), fill=PARCHMENT)
        draw.text((width + MARGIN + 24, y - 6), str(index + 1), fill=PARCHMENT)
        tick_x = MARGIN + int(round(index * width / 10))
        tick_y = MARGIN + int(round(index * height / 10))
        draw.line([(tick_x, 8), (tick_x, MARGIN - 4)], fill=PARCHMENT)
        draw.line([(8, tick_y), (MARGIN - 4, tick_y)], fill=PARCHMENT)
    return canvas


def write_preview(source_path: str, dest_path: str) -> Image.Image:
    source = Path(source_path).resolve()
    dest = Path(dest_path).resolve()
    if source == dest:
        raise ValueError("inspection copy must not replace the clean still")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with Image.open(source) as image:
        preview = render_margin_grid(image)
    dest.parent.mkdir(parents=True, exist_ok=True)
    preview.save(dest, format="PNG")
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != after:
        raise ValueError("clean still changed while writing the inspection copy")
    return preview


def interior_matches(source: Image.Image, preview: Image.Image) -> bool:
    width, height = source.size
    crop = preview.crop((MARGIN, MARGIN, MARGIN + width, MARGIN + height))
    return list(source.convert("RGB").getdata()) == list(crop.getdata())
