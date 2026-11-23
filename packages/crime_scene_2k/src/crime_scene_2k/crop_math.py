"""Span-based zoom and an edge-clamped 16:9 crop window."""

from __future__ import annotations

from dataclasses import dataclass

ZOOM_MIN = 1.6
ZOOM_MAX = 3.8
COLS = "ABCDEFGHIJ"


class CropMathError(ValueError):
    pass


@dataclass(frozen=True)
class CropWindow:
    x0: float
    y0: float
    crop_w: float
    crop_h: float
    zoom: float
    clamped: bool

    def assert_inside(self, width: float, height: float) -> None:
        if not (0.0 <= self.x0 <= self.x0 + self.crop_w <= width + 1e-6):
            raise CropMathError("crop leaves the still horizontally")
        if not (0.0 <= self.y0 <= self.y0 + self.crop_h <= height + 1e-6):
            raise CropMathError("crop leaves the still vertically")
        if abs((self.crop_w / self.crop_h) - (16.0 / 9.0)) > 1e-4:
            raise CropMathError("crop is not 16:9")


def crop_window(
    width: int,
    height: int,
    col: str,
    row: int,
    span_cols: int,
    span_rows: int,
    x_px: float | None = None,
    y_px: float | None = None,
    target_zoom: float | None = None,
) -> CropWindow:
    if width <= 0 or height <= 0:
        raise CropMathError("still size must be positive")
    if not 1 <= span_cols <= 10 or not 1 <= span_rows <= 10:
        raise CropMathError("spans must be inside 1..10")
    column = COLS.index(col.upper())
    center_x = (column + 0.5) / 10.0 * width if x_px is None else x_px
    center_y = (row - 1 + 0.5) / 10.0 * height if y_px is None else y_px
    zoom_x = 1.0 / ((span_cols / 10.0) * 1.25)
    zoom_y = 1.0 / ((span_rows / 10.0) * 1.25)
    zoom = min(zoom_x, zoom_y)
    if target_zoom is not None and ZOOM_MIN <= target_zoom <= ZOOM_MAX:
        zoom = target_zoom
    zoom = min(ZOOM_MAX, max(ZOOM_MIN, zoom))
    crop_w = width / zoom
    crop_h = crop_w * 9.0 / 16.0
    if crop_h > height:
        crop_h = float(height)
        crop_w = crop_h * 16.0 / 9.0
        zoom = width / crop_w
    naive_x = center_x - crop_w / 2.0
    naive_y = center_y - crop_h / 2.0
    x0 = _clamp(naive_x, 0.0, width - crop_w)
    y0 = _clamp(naive_y, 0.0, height - crop_h)
    window = CropWindow(x0, y0, crop_w, crop_h, zoom, x0 != naive_x or y0 != naive_y)
    window.assert_inside(width, height)
    return window


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))
