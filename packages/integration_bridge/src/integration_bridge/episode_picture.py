"""Offline 480p episode picture. Stdlib only, so a checkout needs FFmpeg and nothing else."""

from __future__ import annotations

import math

WIDTH = 854
HEIGHT = 480
DRAW_FPS = 6
DURATION_SEC = 90

PARCHMENT = (0xE9, 0xE2, 0xD2)
INK = (0x1B, 0x1B, 0x1D)
SLATE = (0x3A, 0x4F, 0x66)
AMBER = (0xB8, 0x86, 0x0B)
PAPER = (0xF4, 0xEF, 0xE4)
NIGHT = (0x1E, 0x27, 0x33)

# 3x5 glyphs. Each row is a 3-bit mask.
_GLYPHS: dict[str, tuple[int, ...]] = {
    " ": (0, 0, 0, 0, 0),
    "A": (2, 5, 7, 5, 5),
    "B": (6, 5, 6, 5, 6),
    "C": (3, 4, 4, 4, 3),
    "D": (6, 5, 5, 5, 6),
    "E": (7, 4, 6, 4, 7),
    "F": (7, 4, 6, 4, 4),
    "G": (3, 4, 5, 5, 3),
    "H": (5, 5, 7, 5, 5),
    "I": (7, 2, 2, 2, 7),
    "J": (1, 1, 1, 5, 2),
    "K": (5, 5, 6, 5, 5),
    "L": (4, 4, 4, 4, 7),
    "M": (5, 7, 7, 5, 5),
    "N": (5, 7, 7, 7, 5),
    "O": (2, 5, 5, 5, 2),
    "P": (6, 5, 6, 4, 4),
    "Q": (2, 5, 5, 3, 1),
    "R": (6, 5, 6, 5, 5),
    "S": (3, 4, 2, 1, 6),
    "T": (7, 2, 2, 2, 2),
    "U": (5, 5, 5, 5, 2),
    "V": (5, 5, 5, 5, 2),
    "W": (5, 5, 7, 7, 5),
    "X": (5, 5, 2, 5, 5),
    "Y": (5, 5, 2, 2, 2),
    "Z": (7, 1, 2, 4, 7),
    "0": (7, 5, 5, 5, 7),
    "1": (2, 6, 2, 2, 7),
    "2": (6, 1, 2, 4, 7),
    "3": (6, 1, 2, 1, 6),
    "4": (5, 5, 7, 1, 1),
    "5": (7, 4, 6, 1, 6),
    "6": (3, 4, 6, 5, 3),
    "7": (7, 1, 2, 2, 2),
    "8": (7, 5, 2, 5, 7),
    "9": (7, 5, 7, 1, 6),
    ".": (0, 0, 0, 0, 2),
    ",": (0, 0, 0, 2, 4),
    ":": (0, 2, 0, 2, 0),
    "-": (0, 0, 7, 0, 0),
    "'": (2, 2, 0, 0, 0),
    "|": (2, 2, 2, 2, 2),
}


class _Plate:
    def __init__(self, color: tuple[int, int, int]) -> None:
        self.buf = bytearray(bytes(color) * (WIDTH * HEIGHT))

    def rect(self, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(WIDTH, x + w)
        y1 = min(HEIGHT, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        row = bytes(color) * (x1 - x0)
        span = (x1 - x0) * 3
        for yy in range(y0, y1):
            start = (yy * WIDTH + x0) * 3
            self.buf[start : start + span] = row

    def line(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], thick: int = 3) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        radius = thick // 2
        for step in range(steps + 1):
            x = x0 + (x1 - x0) * step // steps
            y = y0 + (y1 - y0) * step // steps
            self.rect(x - radius, y - radius, thick, thick, color)

    def circle(self, cx: int, cy: int, radius: int, color: tuple[int, int, int]) -> None:
        r2 = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r2:
                    self._pixel(x, y, color)

    def text(self, x: int, y: int, message: str, color: tuple[int, int, int], scale: int = 4) -> None:
        cursor = x
        for char in message.upper():
            rows = _GLYPHS.get(char, _GLYPHS[" "])
            for row_index, bits in enumerate(rows):
                for col in range(3):
                    if bits & (1 << (2 - col)):
                        self.rect(cursor + col * scale, y + row_index * scale, scale, scale, color)
            cursor += 4 * scale

    def _pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < WIDTH and 0 <= y < HEIGHT:
            start = (y * WIDTH + x) * 3
            self.buf[start : start + 3] = bytes(color)

    def to_bytes(self) -> bytes:
        return bytes(self.buf)


def iter_frames():
    count = DURATION_SEC * DRAW_FPS
    for index in range(count):
        yield paint(index / DRAW_FPS).to_bytes()


def paint(t: float) -> _Plate:
    if t < 12:
        plate = _title(t)
    elif t < 34:
        plate = _porch(t)
    elif t < 52:
        plate = _evidence(t)
    elif t < 70:
        plate = _affidavit(t)
    else:
        plate = _foia(t)
    plate.rect(0, HEIGHT - 36, WIDTH, 36, INK)
    plate.text(16, HEIGHT - 28, "ILLUSTRATIVE  |  SYNTHETIC DISCLOSURE  |  NOT A REAL PERSON", PARCHMENT, 2)
    return plate


def _title(t: float) -> _Plate:
    plate = _Plate(PARCHMENT)
    plate.rect(36, 36, WIDTH - 72, HEIGHT - 88, INK)
    plate.rect(48, 48, WIDTH - 96, HEIGHT - 112, PARCHMENT)
    shown = min(1.0, t / 2.5)
    plate.text(80, 90, "ILLUSTRATIVE CASE FILE", INK, 4)
    if shown > 0.35:
        plate.text(80, 160, "THE PORCH AT 10:14", SLATE, 5)
    if shown > 0.6:
        plate.text(80, 230, "MERCER COUNTY", AMBER, 4)
    if shown > 0.85:
        plate.text(80, 300, "A FICTIONAL FILE FOR THE OFFLINE PIPELINE", INK, 2)
    return plate


def _porch(t: float) -> _Plate:
    plate = _Plate(NIGHT)
    plate.circle(700, 70, 28, PARCHMENT)
    plate.rect(40, 300, 774, 140, (0x2C, 0x32, 0x28))
    plate.rect(80, 150, 280, 200, SLATE)
    plate.rect(110, 180, 50, 60, AMBER)
    plate.rect(190, 180, 50, 60, AMBER)
    plate.rect(250, 250, 50, 100, INK)
    progress = (t - 12) / 22
    _stick(plate, int(80 + progress * 520), 250, (t * 3) % 1.0)
    plate.text(40, 40, "STICKMAN STAGE", PARCHMENT, 3)
    plate.text(40, 80, "A SILHOUETTE CROSSES THE PORCH", AMBER, 2)
    return plate


def _evidence(t: float) -> _Plate:
    plate = _Plate(PARCHMENT)
    plate.rect(40, 40, WIDTH - 80, HEIGHT - 100, PAPER)
    plate.rect(40, 40, WIDTH - 80, 48, SLATE)
    plate.text(56, 52, "AUDIO EVIDENCE CARD", PARCHMENT, 3)
    plate.text(70, 120, "AT 10:14 PM A SILHOUETTE", INK, 3)
    plate.text(70, 160, "CROSSED THE PORCH.", INK, 3)
    for index in range(48):
        height = 20 + int(70 * abs(math.sin(index * 0.45 + t * 4)))
        plate.rect(70 + index * 15, 320 - height, 8, height, SLATE if index % 4 else AMBER)
    return plate


def _affidavit(t: float) -> _Plate:
    plate = _Plate(SLATE)
    plate.rect(140, 36, 574, HEIGHT - 90, PAPER)
    plate.text(170, 56, "AFFIDAVIT", INK, 4)
    lines = (
        "THE WITNESS STATED THAT",
        "A FIGURE PASSED THE LAMP",
        "AND DID NOT STOP.",
    )
    reveal = min(1.0, (t - 52) / 14)
    for index, line in enumerate(lines):
        y = 140 + index * 50
        plate.text(180, y, line, INK, 3)
        cover = int((1.0 - reveal) * 460)
        if cover > 0:
            plate.rect(170, y - 4, cover, 28, INK)
    plate.text(170, 320, "REDACTED DOCUMENT", AMBER, 3)
    return plate


def _foia(t: float) -> _Plate:
    plate = _Plate(INK)
    plate.rect(70, 40, WIDTH - 140, HEIGHT - 100, NIGHT)
    plate.rect(90, 60, WIDTH - 180, HEIGHT - 140, (0x24, 0x33, 0x2A))
    plate.rect(120, 220, 200, 90, SLATE)
    plate.rect(250, 250, 30, 60, INK)
    _stick(plate, 430, 200, 0.2)
    seconds = int(t) % 60
    plate.text(100, 80, f"FOIA COPY   22:14:{seconds:02d}", PARCHMENT, 3)
    plate.text(100, 130, "FILED FRAME  |  NO CLOUD CLIP", AMBER, 2)
    return plate


def _stick(plate: _Plate, x: int, y: int, phase: float) -> None:
    import math

    swing = int(math.sin(phase * math.tau) * 18)
    plate.circle(x, y - 78, 16, PARCHMENT)
    plate.line(x, y - 62, x, y - 10, PARCHMENT, 4)
    plate.line(x, y - 50, x - 28, y - 20 + swing, PARCHMENT, 4)
    plate.line(x, y - 50, x + 28, y - 20 - swing, PARCHMENT, 4)
    plate.line(x, y - 10, x - 18 - swing, y + 46, PARCHMENT, 4)
    plate.line(x, y - 10, x + 18 + swing, y + 46, PARCHMENT, 4)
