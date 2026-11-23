"""Project an anchor from still pixels into a 1920x1080 plate.

The ring follows the anchor. An edge-clamped crop does not pin the ring
to screen center. Labels flip to stay inside the title-safe margin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

SCREEN_W = 1920
SCREEN_H = 1080
SAFE_X = 96
SAFE_Y = 54
CRIMSON = (0xC9, 0x2A, 0x2A)


@dataclass(frozen=True)
class ScreenPoint:
    x: float
    y: float


@dataclass(frozen=True)
class LabelBox:
    x: float
    y: float
    width: float
    height: float


def project(anchor_x: float, anchor_y: float, x0: float, y0: float, crop_w: float, crop_h: float) -> ScreenPoint:
    return ScreenPoint(
        ((anchor_x - x0) / crop_w) * SCREEN_W,
        ((anchor_y - y0) / crop_h) * SCREEN_H,
    )


def unproject(point: ScreenPoint, x0: float, y0: float, crop_w: float, crop_h: float) -> tuple[float, float]:
    return (
        x0 + (point.x / SCREEN_W) * crop_w,
        y0 + (point.y / SCREEN_H) * crop_h,
    )


def place_label(point: ScreenPoint, width: float = 220.0, height: float = 36.0) -> LabelBox:
    x = point.x + 28.0
    y = point.y - height - 16.0
    if y < SAFE_Y:
        y = point.y + 28.0
    if x < SAFE_X:
        x = SAFE_X
    if x + width > SCREEN_W - SAFE_X:
        x = SCREEN_W - SAFE_X - width
    if y + height > SCREEN_H - SAFE_Y:
        y = SCREEN_H - SAFE_Y - height
    return LabelBox(x, y, width, height)


def render_ring(point: ScreenPoint) -> Image.Image:
    image = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = 18
    draw.ellipse([point.x - radius, point.y - radius, point.x + radius, point.y + radius], fill=CRIMSON)
    return image


def ring_centroid(image: Image.Image) -> tuple[float, float]:
    rgb = np.asarray(image)
    mask = (rgb[..., 0] > 160) & (rgb[..., 1] < 80) & (rgb[..., 2] < 80)
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        raise ValueError("no crimson ring")
    return float(xs.mean()), float(ys.mean())
