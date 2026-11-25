"""Flat illustrated scenes with motion. This is the picture used for the live film."""

from __future__ import annotations

import subprocess
from pathlib import Path

WIDTH = 1280
HEIGHT = 720
FPS = 12
PICTURE_VERSION = "3"

NAVY = (14, 24, 34)
NAVY_2 = (28, 44, 58)
CREAM = (236, 228, 210)
INK = (22, 24, 28)
AMBER = (214, 162, 64)
WALL = (214, 208, 196)
DOOR = (112, 78, 52)
FOLDER = (176, 122, 58)
BODY = (36, 44, 54)
PAPER = (244, 240, 230)
RED = (176, 48, 42)
GREEN = (58, 122, 86)

# 5x7 glyphs, top row first.
_GLYPHS = {
    "A": "01110100011000111111100011000110001",
    "B": "11110100011111010001100011111010000",
    "C": "01110100011000010000100010111000000",
    "D": "11110100011000110001100011111000000",
    "E": "11111100001111010000100001111100000",
    "F": "11111100001111010000100001000000000",
    "G": "01110100011000010111100010111000000",
    "H": "10001100011111110001100011000100000",
    "I": "11111001000010000100001000111110000",
    "J": "00111000100001000010100010011100000",
    "K": "10001100101110010010100011000100000",
    "L": "10000100001000010000100001111100000",
    "M": "10001110111010110001100011000100000",
    "N": "10001110011010110011100011000100000",
    "O": "01110100011000110001100010111000000",
    "P": "11110100011000111110100001000000000",
    "R": "11110100011000111110101011000100000",
    "S": "01110100001000001110000010111000000",
    "T": "11111001000010000100001000010000000",
    "U": "10001100011000110001100010111000000",
    "V": "10001100011000110001010100010000000",
    "W": "10001100011000110101101011000100000",
    "X": "10001010100010001010100011000100000",
    "Y": "10001010100010000100001000010000000",
    " ": "00000000000000000000000000000000000",
    "-": "00000000001111100000000000000000000",
}


def render_infographic(out_file: Path, seconds: float, kit: str, heading: str) -> None:
    """Draw a moving illustrated scene and save a silent mp4."""
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
    buffer = bytearray(WIDTH * HEIGHT * 3)
    # The bytearray trick above repeats one byte. Fill the real background.
    _fill(buffer, 0, 0, WIDTH, HEIGHT, NAVY)
    _fill(buffer, 0, 560, WIDTH, 160, NAVY_2)
    _fill(buffer, 0, 108, WIDTH, 8, AMBER)
    _text(buffer, _label(heading), 56, 36, 4, CREAM)
    drawer = {
        "porch": _porch,
        "document": _document,
        "merge": _merge,
        "desk": _desk,
        "scale": _scale,
    }.get(kit, _overview)
    drawer(buffer, progress)
    return bytes(buffer)


def _label(heading: str) -> str:
    cleaned = "".join(character if character.upper() in _GLYPHS else " " for character in heading.upper())
    return " ".join(cleaned.split())[:28] or "SCENE"


def _fill(buffer: bytearray, x: float, y: float, width: float, height: float, color: tuple[int, int, int]) -> None:
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(WIDTH, int(x + width))
    y1 = min(HEIGHT, int(y + height))
    if x1 <= x0 or y1 <= y0:
        return
    row = bytes(color) * (x1 - x0)
    stride = WIDTH * 3
    for yy in range(y0, y1):
        start = yy * stride + x0 * 3
        buffer[start : start + len(row)] = row


def _panel(buffer: bytearray, x: float, y: float, width: float, height: float, fill: tuple[int, int, int]) -> None:
    _fill(buffer, x, y, width, height, INK)
    _fill(buffer, x + 8, y + 8, width - 16, height - 16, fill)


def _circle(buffer: bytearray, cx: float, cy: float, radius: float, color: tuple[int, int, int]) -> None:
    radius = int(radius)
    for dy in range(-radius, radius + 1):
        span = int((radius * radius - dy * dy) ** 0.5)
        _fill(buffer, cx - span, cy + dy, span * 2, 1, color)


def _text(buffer: bytearray, text: str, x: float, y: float, scale: int, color: tuple[int, int, int]) -> None:
    cursor = x
    for character in text:
        rows = _GLYPHS.get(character, _GLYPHS[" "])
        for row_index in range(7):
            bits = rows[row_index * 5 : row_index * 5 + 5]
            for column, bit in enumerate(bits):
                if bit == "1":
                    _fill(buffer, cursor + column * scale, y + row_index * scale, scale, scale, color)
        cursor += 6 * scale


def _slide(start: float, end: float, progress: float, begin: float = 0.0, duration: float = 0.45) -> float:
    amount = max(0.0, min(1.0, (progress - begin) / duration))
    eased = amount * amount * (3 - 2 * amount)
    return start + (end - start) * eased


def _person(buffer: bytearray, x: float, y: float, scale: float = 1.0) -> None:
    _circle(buffer, x, y, 28 * scale, CREAM)
    _fill(buffer, x - 34 * scale, y + 30 * scale, 68 * scale, 90 * scale, (48, 86, 122))
    _fill(buffer, x - 46 * scale, y + 40 * scale, 16 * scale, 54 * scale, CREAM)
    _fill(buffer, x + 30 * scale, y + 40 * scale, 16 * scale, 54 * scale, CREAM)


def _camera_icon(buffer: bytearray, x: float, y: float) -> None:
    _panel(buffer, x, y, 180, 120, BODY)
    _circle(buffer, x + 90, y + 64, 28, AMBER)
    _circle(buffer, x + 90, y + 64, 12, INK)
    _fill(buffer, x + 24, y - 18, 48, 22, BODY)


def _page_icon(buffer: bytearray, x: float, y: float, bars: float) -> None:
    _panel(buffer, x, y, 200, 250, PAPER)
    for index in range(3):
        _fill(buffer, x + 28, y + 48 + index * 58, 144 * bars, 22, INK)


def _folder_icon(buffer: bytearray, x: float, y: float) -> None:
    _fill(buffer, x + 16, y, 70, 24, INK)
    _panel(buffer, x, y + 16, 220, 150, FOLDER)
    _text(buffer, "CASE FILE", x + 36, y + 70, 3, INK)


def _overview(buffer: bytearray, progress: float) -> None:
    _camera_icon(buffer, _slide(-220, 120, progress), 250)
    _page_icon(buffer, _slide(1400, 920, progress), 200, _slide(0.15, 1, progress, 0.25))
    _folder_icon(buffer, 520, _slide(620, 390, progress, 0.15))
    _person(buffer, _slide(80, 250, progress, 0.2), 470)
    _text(buffer, "EVIDENCE MOVES INTO THE FILE", 300, 640, 3, CREAM)


def _porch(buffer: bytearray, progress: float) -> None:
    _panel(buffer, 160, 180, 620, 400, WALL)
    _fill(buffer, 160, 180, 620, 36, (168, 92, 64))
    _panel(buffer, 390, 300, 160, 280, DOOR)
    _circle(buffer, 520, 440, 8, AMBER)
    _camera_icon(buffer, 250, _slide(80, 210, progress))
    _person(buffer, 96, 470)
    checks = ("TIME", "PLACE", "REAL")
    for index, word in enumerate(checks):
        y = 220 + index * 90
        shown = _slide(0, 1, progress, 0.2 + index * 0.15, 0.2)
        _panel(buffer, 860, y, 280, 70, PAPER)
        _fill(buffer, 884, y + 18, 36, 36, GREEN if shown > 0.8 else NAVY_2)
        _text(buffer, word, 940, y + 24, 3, INK)


def _document(buffer: bytearray, progress: float) -> None:
    _page_icon(buffer, 220, 170, _slide(0.2, 1, progress, 0.1))
    glass = _slide(980, 780, progress)
    _circle(buffer, glass, 340, 78, (210, 230, 236))
    _circle(buffer, glass, 340, 50, NAVY)
    _text(buffer, "REDACTED", 760, 520, 4, CREAM)
    _text(buffer, "PRIVACY STAYS COVERED", 700, 600, 3, AMBER)


def _merge(buffer: bytearray, progress: float) -> None:
    _camera_icon(buffer, _slide(40, 300, progress), 280)
    _page_icon(buffer, _slide(1040, 760, progress), 220, 1)
    _folder_icon(buffer, 500, _slide(560, 400, progress, 0.2))
    _fill(buffer, 300, 330, _slide(0, 200, progress, 0.35), 16, AMBER)
    _fill(buffer, _slide(980, 760, progress, 0.35), 330, _slide(0, 200, progress, 0.35), 16, AMBER)
    _text(buffer, "TWO RECORDS ONE FILE", 300, 640, 3, CREAM)


def _desk(buffer: bytearray, progress: float) -> None:
    _panel(buffer, 180, 420, 920, 36, DOOR)
    _fill(buffer, 220, 456, 840, 28, (72, 50, 34))
    for index, word in enumerate(("NOTES", "CLIP", "FILE")):
        x = 280 + index * 240
        y = _slide(-180, 230, progress, index * 0.12, 0.4)
        _panel(buffer, x, y, 180, 180, PAPER if index < 2 else FOLDER)
        _text(buffer, word, x + 28, y + 78, 3, INK)
    _text(buffer, "SORTED FOR REVIEW", 360, 640, 3, CREAM)


def _scale(buffer: bytearray, progress: float) -> None:
    tilt = _slide(-18, 18, progress, 0.1, 0.8)
    _panel(buffer, 460, 500, 360, 28, BODY)
    _fill(buffer, 620, 250, 28, 250, AMBER)
    _fill(buffer, 400, 250 + tilt, 480, 18, AMBER)
    _panel(buffer, 390, 300 + tilt, 140, 22, PAPER)
    _panel(buffer, 760, 268 - tilt * 0.4, 140, 22, PAPER)
    _text(buffer, "ACCURACY", 390, 420, 3, CREAM)
    _text(buffer, "PRIVACY", 760, 420, 3, CREAM)
    _text(buffer, "KEEP THE BALANCE", 390, 640, 3, CREAM)
