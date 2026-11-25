"""Sharp 1080p illustrated scenes. Shapes and type are drawn with smooth edges."""

from __future__ import annotations

import subprocess
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - the test machine has Pillow
    raise RuntimeError(
        "The sharp pictures need Pillow. On the Mac, run this once, then run the live command again:\n"
        "  python3 -m pip install pillow"
    ) from exc

WIDTH = 1920
HEIGHT = 1080
FPS = 24
PICTURE_VERSION = "4"

NAVY = (16, 32, 48)
SKY = (36, 64, 88)
GROUND = (22, 36, 48)
CREAM = (244, 236, 220)
INK = (18, 20, 24)
AMBER = (224, 164, 48)
WALL = (232, 224, 208)
DOOR = (122, 78, 48)
FOLDER = (196, 132, 52)
BODY = (42, 52, 64)
PAPER = (252, 248, 240)
BLUE = (46, 104, 158)
GREEN = (46, 140, 96)
GLASS = (186, 214, 224)

_FONTS: dict[int, ImageFont.FreeTypeFont] = {}


def render_infographic(out_file: Path, seconds: float, kit: str, heading: str) -> None:
    """Draw a moving illustrated scene at 1080p and save a silent mp4."""
    frames = max(FPS * 2, int(round(min(seconds, 30.0) * FPS)))
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(out_file),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in range(frames):
            progress = frame / max(1, frames - 1)
            process.stdin.write(_frame(kit, heading, progress))
    finally:
        process.stdin.close()
    code = process.wait()
    if code != 0 or not out_file.is_file():
        raise RuntimeError("The illustrated scene could not be drawn.")


def _frame(kit: str, heading: str, progress: float) -> bytes:
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 140, WIDTH, 900), fill=SKY)
    draw.rectangle((0, 860, WIDTH, HEIGHT), fill=GROUND)
    draw.rectangle((0, 128, WIDTH, 140), fill=AMBER)
    draw.text((72, 36), _label(heading), font=_font(58), fill=CREAM)
    drawer = {
        "porch": _porch,
        "document": _document,
        "merge": _merge,
        "desk": _desk,
        "scale": _scale,
    }.get(kit, _overview)
    drawer(draw, progress)
    return image.tobytes()


def _font(size: int) -> ImageFont.FreeTypeFont:
    cached = _FONTS.get(size)
    if cached is not None:
        return cached
    face = ImageFont.truetype(_font_file(), size)
    _FONTS[size] = face
    return face


def _font_file() -> str:
    candidates = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("No outline font was found for the scene titles.")


def _label(heading: str) -> str:
    cleaned = "".join(character if character.isprintable() else " " for character in heading)
    return " ".join(cleaned.split())[:42] or "Scene"


def _slide(start: float, end: float, progress: float, begin: float = 0.0, duration: float = 0.45) -> float:
    amount = max(0.0, min(1.0, (progress - begin) / duration))
    eased = amount * amount * (3 - 2 * amount)
    return start + (end - start) * eased


def _round(draw: ImageDraw.ImageDraw, box: tuple, fill: tuple, radius: int = 28) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=INK)
    inset = 8
    inner = (box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset)
    draw.rounded_rectangle(inner, radius=max(8, radius - 6), fill=fill)


def _person(draw: ImageDraw.ImageDraw, x: float, y: float, scale: float = 1.0) -> None:
    head = 34 * scale
    draw.ellipse((x - head, y - head, x + head, y + head), fill=CREAM, outline=INK, width=8)
    draw.ellipse((x - 12 * scale, y - 8 * scale, x - 4 * scale, y), fill=INK)
    draw.ellipse((x + 4 * scale, y - 8 * scale, x + 12 * scale, y), fill=INK)
    draw.arc((x - 14 * scale, y + 2 * scale, x + 14 * scale, y + 22 * scale), 20, 160, fill=INK, width=4)
    body = (x - 42 * scale, y + 36 * scale, x + 42 * scale, y + 150 * scale)
    draw.rounded_rectangle(body, radius=24, fill=BLUE, outline=INK, width=8)
    draw.rounded_rectangle((x - 70 * scale, y + 48 * scale, x - 42 * scale, y + 120 * scale), radius=12, fill=CREAM, outline=INK, width=6)
    draw.rounded_rectangle((x + 42 * scale, y + 48 * scale, x + 70 * scale, y + 120 * scale), radius=12, fill=CREAM, outline=INK, width=6)


def _camera(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    _round(draw, (x, y, x + 280, y + 180), BODY, 24)
    draw.rounded_rectangle((x + 36, y - 28, x + 110, y + 8), radius=8, fill=BODY, outline=INK, width=6)
    draw.ellipse((x + 90, y + 36, x + 190, y + 136), fill=AMBER, outline=INK, width=8)
    draw.ellipse((x + 118, y + 64, x + 162, y + 108), fill=INK)


def _page(draw: ImageDraw.ImageDraw, x: float, y: float, bars: float) -> None:
    _round(draw, (x, y, x + 320, y + 400), PAPER, 18)
    for index in range(4):
        width = 220 if index == 3 else 240 * bars
        draw.rounded_rectangle(
            (x + 36, y + 48 + index * 78, x + 36 + width, y + 84 + index * 78),
            radius=8,
            fill=INK,
        )


def _folder(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    draw.rounded_rectangle((x + 24, y, x + 130, y + 36), radius=8, fill=INK)
    _round(draw, (x, y + 24, x + 340, y + 230), FOLDER, 20)
    draw.text((x + 48, y + 90), "CASE FILE", font=_font(36), fill=INK)


def _overview(draw: ImageDraw.ImageDraw, progress: float) -> None:
    _camera(draw, _slide(-300, 180, progress), 360)
    _page(draw, _slide(2000, 1380, progress), 280, _slide(0.2, 1, progress, 0.2))
    _folder(draw, 760, _slide(980, 560, progress, 0.15))
    _person(draw, _slide(80, 420, progress, 0.1), 620)
    draw.text((520, 960), "Evidence moves into the file", font=_font(42), fill=CREAM)


def _porch(draw: ImageDraw.ImageDraw, progress: float) -> None:
    draw.polygon([(200, 430), (560, 230), (920, 430)], fill=(176, 84, 58), outline=INK)
    _round(draw, (230, 400, 890, 860), WALL, 12)
    _round(draw, (500, 520, 680, 860), DOOR, 10)
    draw.ellipse((630, 670, 654, 694), fill=AMBER, outline=INK, width=4)
    draw.rounded_rectangle((300, 470, 430, 580), radius=8, fill=(166, 206, 214), outline=INK, width=6)
    draw.rounded_rectangle((700, 470, 830, 580), radius=8, fill=(166, 206, 214), outline=INK, width=6)
    _camera(draw, 300, _slide(120, 250, progress))
    _person(draw, 1100, 640)
    checks = ("Time", "Place", "Real clip")
    for index, word in enumerate(checks):
        y = 300 + index * 130
        shown = _slide(0, 1, progress, 0.2 + index * 0.15, 0.2)
        _round(draw, (1280, y, 1780, y + 100), PAPER, 16)
        mark = GREEN if shown > 0.8 else SKY
        draw.rounded_rectangle((1310, y + 26, 1362, y + 78), radius=8, fill=mark, outline=INK, width=4)
        draw.text((1390, y + 28), word, font=_font(36), fill=INK)


def _document(draw: ImageDraw.ImageDraw, progress: float) -> None:
    _page(draw, 220, 240, _slide(0.25, 1, progress, 0.05))
    glass = _slide(1500, 1180, progress)
    draw.ellipse((glass - 110, 340, glass + 110, 560), fill=GLASS, outline=INK, width=10)
    draw.ellipse((glass - 70, 380, glass + 70, 520), fill=SKY, outline=INK, width=8)
    draw.line((glass + 70, 520, glass + 160, 640), fill=INK, width=16)
    draw.text((1180, 760), "Redacted", font=_font(54), fill=CREAM)
    draw.text((1180, 840), "Privacy stays covered", font=_font(36), fill=AMBER)
    _person(draw, 1680, 640)


def _merge(draw: ImageDraw.ImageDraw, progress: float) -> None:
    _camera(draw, _slide(40, 360, progress), 380)
    _page(draw, _slide(1700, 1240, progress), 300, 1)
    _folder(draw, 760, _slide(900, 620, progress, 0.2))
    draw.line((640, 470, _slide(640, 820, progress, 0.3), 470), fill=AMBER, width=14)
    draw.line((_slide(1240, 1100, progress, 0.3), 470, 1240, 470), fill=AMBER, width=14)
    draw.text((620, 960), "Two records, one file", font=_font(46), fill=CREAM)


def _desk(draw: ImageDraw.ImageDraw, progress: float) -> None:
    draw.rounded_rectangle((180, 700, 1500, 760), radius=8, fill=DOOR, outline=INK, width=8)
    draw.rectangle((240, 760, 1440, 800), fill=(72, 50, 34))
    for index, word in enumerate(("Notes", "Clip", "File")):
        x = 340 + index * 340
        y = _slide(-220, 420, progress, index * 0.12, 0.4)
        fill = PAPER if index < 2 else FOLDER
        _round(draw, (x, y, x + 260, y + 260), fill, 16)
        draw.text((x + 48, y + 100), word, font=_font(40), fill=INK)
    _person(draw, 1680, 640)
    draw.text((560, 960), "Sorted for review", font=_font(46), fill=CREAM)


def _scale(draw: ImageDraw.ImageDraw, progress: float) -> None:
    tilt = _slide(-28, 28, progress, 0.1, 0.8)
    draw.rounded_rectangle((760, 780, 1160, 830), radius=10, fill=BODY, outline=INK, width=8)
    draw.rectangle((940, 360, 980, 790), fill=AMBER, outline=INK)
    draw.polygon(
        [(700, 390 + tilt), (1220, 360 - tilt * 0.3), (1220, 390 - tilt * 0.3), (700, 420 + tilt)],
        fill=AMBER,
        outline=INK,
    )
    _round(draw, (620, 430 + tilt, 860, 490 + tilt), PAPER, 12)
    _round(draw, (1080, 390 - tilt * 0.3, 1320, 450 - tilt * 0.3), PAPER, 12)
    draw.text((640, 520 + tilt), "Accuracy", font=_font(36), fill=CREAM)
    draw.text((1100, 500 - tilt * 0.2), "Privacy", font=_font(36), fill=CREAM)
    draw.text((700, 960), "Keep the balance", font=_font(48), fill=CREAM)
    _person(draw, 280, 640)
