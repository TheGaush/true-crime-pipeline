"""Find crisp glyphs in the YouTube overlay margins. The master file is not edited."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ZoneHit:
    scene_id: str
    margin_side: str
    timestamp_sec: float


def scan_frame(rgb: np.ndarray, scene_id: str, timestamp_sec: float, exempt_safe_zone_foia: bool = False) -> list[ZoneHit]:
    if exempt_safe_zone_foia:
        return []
    height, width = rgb.shape[:2]
    zones = {
        "bottom": rgb[int(height * 0.90) :, :],
        "top": rgb[: int(height * 0.06), :],
        "left": rgb[:, : int(width * 0.05)],
        "right": rgb[:, int(width * 0.94) :],
    }
    hits = []
    for side, band in zones.items():
        if band.size == 0:
            continue
        gray = cv2.cvtColor(band, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        density = float(edges.mean())
        red = band[..., 0].astype(np.int16)
        green = band[..., 1].astype(np.int16)
        blue = band[..., 2].astype(np.int16)
        crimson = float(np.mean((red > 160) & (red > green * 1.8) & (red > blue * 1.8)))
        if density > 1.0 or crimson > 0.002:
            hits.append(ZoneHit(scene_id, side, timestamp_sec))
    return hits
