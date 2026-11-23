"""Read-only loader for pre-locked spatial anchors on a clean 2K still."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

COLS = "ABCDEFGHIJ"


class AnchorBoundsError(ValueError):
    pass


class Missing2KAssetError(FileNotFoundError):
    pass


class BakedGridError(ValueError):
    pass


@dataclass(frozen=True)
class SpatialAnchor:
    anchor_id: str
    col: str
    row: int
    span_cols: int
    span_rows: int
    x_px: float
    y_px: float
    target_zoom: float


def load_anchors(image_path: str, records: list[dict]) -> list[SpatialAnchor]:
    path = Path(image_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise Missing2KAssetError(f"missing 2K still {image_path}")
    with Image.open(path) as image:
        width, height = image.size
        if width < 1920 or height < 1080:
            raise AnchorBoundsError(f"still {width}x{height} is below 1920x1080")
        _reject_baked_grid(image)
    loaded: list[SpatialAnchor] = []
    for index, record in enumerate(records):
        loaded.append(_one(record, width, height, index))
    return loaded


def _one(record: dict, width: int, height: int, index: int) -> SpatialAnchor:
    col = str(record.get("col", "")).upper()
    if col not in COLS:
        raise AnchorBoundsError(f"anchor {index} col must be A-J")
    row = int(record["row"])
    span_cols = int(record["span_cols"])
    span_rows = int(record["span_rows"])
    if not 1 <= row <= 10 or not 1 <= span_cols <= 10 or not 1 <= span_rows <= 10:
        raise AnchorBoundsError(f"anchor {index} span or row is outside 1..10")
    derived_x = (COLS.index(col) + 0.5) / 10.0 * width
    derived_y = (row - 1 + 0.5) / 10.0 * height
    x_px = float(record["x_px"]) if "x_px" in record else derived_x
    y_px = float(record["y_px"]) if "y_px" in record else derived_y
    if "x_px" in record and abs(x_px - derived_x) > width / 10.0:
        raise AnchorBoundsError(f"anchor {index} x_px disagrees with column {col}")
    if "y_px" in record and abs(y_px - derived_y) > height / 10.0:
        raise AnchorBoundsError(f"anchor {index} y_px disagrees with row {row}")
    if not 0.0 <= x_px <= width or not 0.0 <= y_px <= height:
        raise AnchorBoundsError(f"anchor {index} is outside the still")
    zoom = float(record.get("target_zoom", 1.6))
    return SpatialAnchor(str(record.get("anchor_id", f"a{index}")), col, row, span_cols, span_rows, x_px, y_px, zoom)


def _reject_baked_grid(image: Image.Image) -> None:
    rgb = image.convert("RGB")
    width, height = rgb.size
    dark_rows = 0
    for index in range(1, 10):
        y = int(round(index * height / 10))
        row = [rgb.getpixel((x, min(height - 1, y))) for x in range(0, width, max(1, width // 40))]
        if sum(1 for pixel in row if pixel[0] < 40 and pixel[1] < 40 and pixel[2] < 40) > len(row) * 0.8:
            dark_rows += 1
    if dark_rows >= 6:
        raise BakedGridError("still contains a baked 10 by 10 grid")
