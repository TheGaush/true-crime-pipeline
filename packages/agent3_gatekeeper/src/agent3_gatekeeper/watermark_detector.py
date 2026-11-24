"""Corner watermark scanner for Agent 3 compliance (zero broadcaster logo invariant).

Samples the outer 15% corner Safe-Zones across injected frame payloads and
confirms labels via an injected vision client (no live Vision API, no network).
Official agency bodycam OSD (``AXON BODY``, ``WatchGuard HUD``) passes; CourtTV,
Fox, and YouTube corner logos reject only when they persist on at least two
sampled frames so one-frame vision noise does not false-reject.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

CORNER_FRACTION = 0.15
MIN_PERSIST_FRAMES = 2

CORNER_NAMES = ("top_left", "top_right", "bottom_left", "bottom_right")

VisionClient = Callable[["VideoFrame", "CornerSafeZone"], str]

_REASON_BROADCASTER_LOGO = "broadcaster_corner_logo"
_REASON_CLEAN = "corner_safe"

# Normalized agency OSD tokens that always pass (Axon / WatchGuard bodycam HUD).
_AGENCY_OSD_LABELS: frozenset[str] = frozenset(
    {
        "axon body",
        "axon body cam",
        "axon",
        "watchguard hud",
        "watchguard",
    }
)

# Broadcaster / platform corner marks that fail the zero-watermark invariant.
_BROADCASTER_REJECT_LABELS: frozenset[str] = frozenset(
    {
        "courttv",
        "court tv",
        "fox",
        "fox news",
        "fox logo",
        "youtube",
        "youtube logo",
    }
)

_BROADCASTER_ALIASES: dict[str, str] = {
    "court-tv": "courttv",
    "court_tv": "courttv",
    "foxnews": "fox",
    "fox news channel": "fox",
    "yt": "youtube",
    "youtube.com": "youtube",
}


@dataclass(frozen=True)
class VideoFrame:
    """One sampled video frame (dimensions + opaque bytes for crop plumbing)."""

    frame_index: int
    width: int
    height: int
    payload: bytes = b""

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.frame_index < 0:
            raise ValueError("frame_index must be >= 0")


@dataclass(frozen=True)
class CornerSafeZone:
    """Pixel-anchored outer-corner crop (15% of width and height per axis)."""

    name: str
    x0: int
    y0: int
    x1: int
    y1: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "name": self.name,
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
        }


@dataclass(frozen=True)
class CornerHit:
    frame_index: int
    corner: str
    raw_label: str
    normalized_label: str


@dataclass
class WatermarkScanResult:
    watermark_clean: int
    passed: bool
    reason: str
    rejected_label: str | None = None
    persistence_frames: int = 0
    corner_hits: list[CornerHit] = field(default_factory=list)
    agency_osd_hits: list[CornerHit] = field(default_factory=list)

    def to_audit_fields(self) -> dict[str, Any]:
        return {
            "watermark_clean": self.watermark_clean,
            "watermark_reject_reason": None if self.passed else self.reason,
            "watermark_rejected_label": self.rejected_label,
            "watermark_persistence_frames": self.persistence_frames,
        }


def corner_safe_zones(width: int, height: int) -> tuple[CornerSafeZone, ...]:
    """Return the four outer 15% corner crops for a ``width`` x ``height`` frame."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    cw = max(1, int(round(width * CORNER_FRACTION)))
    ch = max(1, int(round(height * CORNER_FRACTION)))
    return (
        CornerSafeZone("top_left", 0, 0, cw, ch),
        CornerSafeZone("top_right", width - cw, 0, width, ch),
        CornerSafeZone("bottom_left", 0, height - ch, cw, height),
        CornerSafeZone("bottom_right", width - cw, height - ch, width, height),
    )


def _normalize_label(raw: str) -> str:
    text = " ".join(raw.strip().lower().split())
    if not text or text in {"none", "clean", "empty", "no logo", "no_logo"}:
        return ""
    if text in _BROADCASTER_ALIASES:
        return _BROADCASTER_ALIASES[text]
    for agency in _AGENCY_OSD_LABELS:
        if agency in text or text in agency:
            return agency
    for reject in _BROADCASTER_REJECT_LABELS:
        if reject in text or text in reject:
            if reject.startswith("fox") or reject == "fox":
                return "fox"
            if "court" in reject:
                return "courttv"
            if "youtube" in reject:
                return "youtube"
            return reject
    if "axon" in text:
        return "axon body"
    if "watchguard" in text:
        return "watchguard hud"
    if "courttv" in text.replace(" ", "").replace("-", ""):
        return "courttv"
    if "youtube" in text:
        return "youtube"
    if text == "fox" or text.startswith("fox "):
        return "fox"
    return text


def is_agency_osd_label(label: str) -> bool:
    normalized = _normalize_label(label)
    return normalized in _AGENCY_OSD_LABELS


def is_broadcaster_reject_label(label: str) -> bool:
    normalized = _normalize_label(label)
    if not normalized:
        return False
    if normalized in _AGENCY_OSD_LABELS:
        return False
    root = normalized.replace(" ", "")
    if root in {"courttv", "fox", "youtube"}:
        return True
    return normalized in _BROADCASTER_REJECT_LABELS


def broadcaster_canonical(label: str) -> str | None:
    """Map a vision label to ``courttv`` / ``fox`` / ``youtube`` when rejectable."""
    normalized = _normalize_label(label)
    if not is_broadcaster_reject_label(label):
        return None
    root = normalized.replace(" ", "")
    if "court" in root:
        return "courttv"
    if root.startswith("fox") or normalized == "fox":
        return "fox"
    if "youtube" in root:
        return "youtube"
    return normalized


class CornerWatermarkScanner:
    """Temporal corner watermark gate with injected vision confirmation."""

    def __init__(
        self,
        vision_client: VisionClient,
        *,
        min_persist_frames: int = MIN_PERSIST_FRAMES,
        corner_fraction: float = CORNER_FRACTION,
    ) -> None:
        if min_persist_frames < 1:
            raise ValueError("min_persist_frames must be >= 1")
        if not (0.0 < corner_fraction < 0.5):
            raise ValueError("corner_fraction must be between 0 and 0.5")
        self._vision_client = vision_client
        self._min_persist_frames = min_persist_frames
        self._corner_fraction = corner_fraction

    def scan_frames(self, frames: Sequence[VideoFrame]) -> WatermarkScanResult:
        if not frames:
            return WatermarkScanResult(
                watermark_clean=1,
                passed=True,
                reason=_REASON_CLEAN,
            )

        broadcaster_frames: dict[str, set[int]] = {}
        corner_hits: list[CornerHit] = []
        agency_hits: list[CornerHit] = []

        for frame in frames:
            zones = _corner_safe_zones_for_fraction(
                frame.width, frame.height, self._corner_fraction
            )
            labels_this_frame: set[str] = set()
            for zone in zones:
                raw = self._vision_client(frame, zone)
                normalized = _normalize_label(raw)
                hit = CornerHit(
                    frame_index=frame.frame_index,
                    corner=zone.name,
                    raw_label=raw,
                    normalized_label=normalized,
                )
                if is_agency_osd_label(raw):
                    agency_hits.append(hit)
                    continue
                if is_broadcaster_reject_label(raw):
                    corner_hits.append(hit)
                    canon = broadcaster_canonical(raw)
                    if canon:
                        labels_this_frame.add(canon)
            for canon in labels_this_frame:
                broadcaster_frames.setdefault(canon, set()).add(frame.frame_index)

        worst_label: str | None = None
        worst_count = 0
        for label, frame_ids in broadcaster_frames.items():
            count = len(frame_ids)
            if count >= self._min_persist_frames and count > worst_count:
                worst_label = label
                worst_count = count

        if worst_label is not None:
            return WatermarkScanResult(
                watermark_clean=0,
                passed=False,
                reason=_REASON_BROADCASTER_LOGO,
                rejected_label=worst_label,
                persistence_frames=worst_count,
                corner_hits=corner_hits,
                agency_osd_hits=agency_hits,
            )

        return WatermarkScanResult(
            watermark_clean=1,
            passed=True,
            reason=_REASON_CLEAN,
            corner_hits=corner_hits,
            agency_osd_hits=agency_hits,
        )


def _corner_safe_zones_for_fraction(
    width: int, height: int, fraction: float
) -> tuple[CornerSafeZone, ...]:
    if abs(fraction - CORNER_FRACTION) < 1e-9:
        return corner_safe_zones(width, height)
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    cw = max(1, int(round(width * fraction)))
    ch = max(1, int(round(height * fraction)))
    return (
        CornerSafeZone("top_left", 0, 0, cw, ch),
        CornerSafeZone("top_right", width - cw, 0, width, ch),
        CornerSafeZone("bottom_left", 0, height - ch, cw, height),
        CornerSafeZone("bottom_right", width - cw, height - ch, width, height),
    )