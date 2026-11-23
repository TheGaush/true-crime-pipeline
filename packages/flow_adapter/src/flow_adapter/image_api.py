"""Offline still generator and a room-locked multi-turn edit.

The transport is injected. A plate under 2048 px wide is refused.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


class ImageResolutionError(RuntimeError):
    pass


class ImageSafetyError(RuntimeError):
    pass


@dataclass(frozen=True)
class StillResult:
    image: Image.Image
    width: int
    height: int
    ssim: float | None
    warning: str | None


def generate_clean_2k_still(prompt: str, case_bible: dict, transport) -> StillResult:
    image = transport.generate(prompt, case_bible, "2K")
    _gate(image)
    return StillResult(image, image.width, image.height, None, None)


def edit_still_multiturn(base: Image.Image, instruction: str, seed: int, transport) -> StillResult:
    edited = transport.edit(base, instruction, seed)
    _gate(edited)
    score = _outside_ssim(base, edited)
    warning = None if score >= 0.85 else "ROOM_LOCK"
    return StillResult(edited, edited.width, edited.height, score, warning)


def _gate(image: Image.Image) -> None:
    if image.width < 2048 or image.height < 1152:
        raise ImageResolutionError("still is below 2048x1152")
    rgb = np.asarray(image.convert("RGB"))
    red = rgb[..., 0].astype(np.int16)
    green = rgb[..., 1].astype(np.int16)
    blue = rgb[..., 2].astype(np.int16)
    if int(np.count_nonzero((red > 160) & (red > green * 1.8) & (red > blue * 1.8))) > 35:
        raise ImageSafetyError("crimson cluster")


def _outside_ssim(base: Image.Image, edited: Image.Image) -> float:
    left = np.asarray(base.convert("L"), dtype=np.float32)
    right = np.asarray(edited.convert("L"), dtype=np.float32)
    if left.shape != right.shape:
        return 0.0
    height, width = left.shape
    mask = np.ones_like(left, dtype=bool)
    mask[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4] = False
    a = left[mask]
    b = right[mask]
    c2 = (0.03 * 255) ** 2
    mu_a = float(a.mean())
    mu_b = float(b.mean())
    var_a = float(a.var())
    var_b = float(b.var())
    cov = float(((a - mu_a) * (b - mu_b)).mean())
    return ((2 * mu_a * mu_b + c2) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c2) * (var_a + var_b + c2))
