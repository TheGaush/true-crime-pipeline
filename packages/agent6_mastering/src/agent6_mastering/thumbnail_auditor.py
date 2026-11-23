"""Reject gore, clutter, and a repeated thumbnail archetype."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

ARCHETYPES = ("doorway_silhouette", "desk_evidence_closeup", "map_trajectory_split", "redacted_dossier_reveal")
MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class ThumbVerdict:
    approved: bool
    reasons: tuple[str, ...]
    archetype: str


def audit(image: Image.Image, words: list[str], archetype: str, history: list[str]) -> ThumbVerdict:
    reasons = []
    if image.size != (1280, 720):
        reasons.append("SIZE")
    if len(words) > 4:
        reasons.append("WORD_COUNT")
    encoded = _png(image)
    if len(encoded) > MAX_BYTES:
        reasons.append("FILE_SIZE")
    if _blood(np.asarray(image.convert("RGB"))):
        reasons.append("GORE")
    if archetype in history[-1:]:
        reasons.append("REPEATED_ARCHETYPE")
    return ThumbVerdict(not reasons, tuple(reasons), archetype)


def next_archetype(history: list[str]) -> str:
    for name in ARCHETYPES:
        if name not in history[-5:]:
            return name
    return ARCHETYPES[len(history) % len(ARCHETYPES)]


def render_candidate(archetype: str, words: list[str]) -> Image.Image:
    image = Image.new("RGB", (1280, 720), (233, 226, 210))
    draw = ImageDraw.Draw(image)
    draw.rectangle([80, 80, 420, 640], fill=(27, 27, 29))
    draw.text((480, 300), " ".join(words[:4]), fill=(27, 27, 29))
    draw.text((480, 80), archetype, fill=(58, 79, 102))
    return image


def _blood(rgb: np.ndarray) -> bool:
    red = rgb[..., 0].astype(np.int16)
    green = rgb[..., 1].astype(np.int16)
    blue = rgb[..., 2].astype(np.int16)
    mask = (red > 160) & (red > green * 1.8) & (red > blue * 1.8)
    stamp = np.zeros(mask.shape, dtype=bool)
    stamp[40:80, 980:1200] = True
    return int(np.count_nonzero(mask & ~stamp)) > 80


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
