"""Tile four scene frames onto one sheet and score them by scene id."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw


@dataclass(frozen=True)
class SheetDefect:
    scene_id: str
    fix_type: str


def build_sheets(frames: list[tuple[str, Image.Image]]) -> list[Image.Image]:
    sheets = []
    slots = list(frames)
    while len(slots) % 4:
        slots.append(("EMPTY_SLOT", Image.new("RGB", (960, 480), (58, 79, 102))))
    for offset in range(0, len(slots), 4):
        sheet = Image.new("RGB", (1920, 1080), (27, 27, 29))
        draw = ImageDraw.Draw(sheet)
        for index, (scene_id, frame) in enumerate(slots[offset : offset + 4]):
            column = index % 2
            row = index // 2
            x = column * 960
            y = row * 540
            sheet.paste(frame.resize((960, 480)), (x, y + 60))
            draw.rectangle([x, y, x + 960, y + 60], fill=(58, 79, 102))
            draw.text((x + 16, y + 18), scene_id, fill=(233, 226, 210))
        sheets.append(sheet)
    return sheets


def review(frames: list[tuple[str, Image.Image]], judge) -> list[SheetDefect]:
    sheets = build_sheets(frames)
    if len(sheets) != math.ceil(len(frames) / 4):
        raise RuntimeError("sheet count drifted")
    defects = []
    for sheet_index, sheet in enumerate(sheets):
        chunk = frames[sheet_index * 4 : sheet_index * 4 + 4]
        ids = [scene_id for scene_id, _frame in chunk]
        for item in judge(sheet, ids):
            if item["scene_id"] == "EMPTY_SLOT" or item["scene_id"] not in ids:
                continue
            defects.append(SheetDefect(item["scene_id"], item["fix_type"]))
    return defects
