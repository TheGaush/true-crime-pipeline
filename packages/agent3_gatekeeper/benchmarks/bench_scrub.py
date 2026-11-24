"""Deterministic local scrub benchmark: music-gated Demucs vs unconditional + PII.

Uses synthetic clip durations only — no real Demucs, OpenCV, YOLO, or network.
Models peak RAM, relative cost units, and bodycam pre-slice windows (+/- 5s).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

PEAK_RAM_CAP_GB = 4.0
BODYCAM_PRE_SLICE_PAD_S = 5.0
_MUSIC_KIND_911 = frozenset({"call_911_wav"})

# Relative cost units (synthetic; not dollars).
_COST_MUSIC_DETECT_PER_S = 0.02
_COST_DEMUCS_PER_S = 1.8
_COST_PII_PER_BOX = 0.05
_COST_PII_BASE_PER_S = 0.04
_COST_YOLO_FRAME_PER_S = 0.06

# Analytical peak-RAM model (GB).
_RAM_BASE_GB = 0.35
_RAM_PER_S_GB = 0.018
_RAM_DEMUCS_OVERHEAD_GB = 1.2
_RAM_PER_PII_BOX_GB = 0.008
_RAM_YOLO_PER_S_GB = 0.022


@dataclass(frozen=True, slots=True)
class SyntheticClipSpec:
    """Synthetic FOIA clip descriptor (duration in seconds, no real media)."""

    clip_id: str
    media_kind: str
    duration_s: float
    music_detected: bool = False
    event_timestamps_s: tuple[float, ...] = ()
    visual_pii_boxes: int = 0
    sample_rate_hz: int = 48000
    has_video_track: bool = True


@dataclass(frozen=True, slots=True)
class ScrubWindow:
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return max(0.0, self.end_s - self.start_s)


@dataclass(frozen=True, slots=True)
class ScrubBenchmarkResult:
    clip_id: str
    demucs_skipped: bool
    demucs_applied: bool
    music_detected: bool
    estimated_cost: float
    unconditional_demucs_cost: float
    peak_ram_gb: float
    demucs_audio_s: float
    pre_slice_windows: tuple[ScrubWindow, ...]
    pii_boxes_scrubbed: int


def is_911_telephony_bypass(spec: SyntheticClipSpec) -> bool:
    if spec.media_kind in _MUSIC_KIND_911 and spec.sample_rate_hz <= 8000:
        return True
    return False


def pre_slice_bodycam_windows(
    total_duration_s: float,
    event_timestamps_s: Sequence[float],
    *,
    pad_s: float = BODYCAM_PRE_SLICE_PAD_S,
) -> tuple[ScrubWindow, ...]:
    """Slice a long bodycam to event +/- pad seconds before Demucs."""
    if total_duration_s <= 0:
        return ()
    if not event_timestamps_s:
        return (ScrubWindow(0.0, total_duration_s),)

    raw: list[ScrubWindow] = []
    for ts in sorted(event_timestamps_s):
        start = max(0.0, ts - pad_s)
        end = min(total_duration_s, ts + pad_s)
        if end > start:
            raw.append(ScrubWindow(start, end))

    merged: list[ScrubWindow] = []
    for window in raw:
        if not merged or window.start_s > merged[-1].end_s:
            merged.append(window)
        else:
            prev = merged[-1]
            merged[-1] = ScrubWindow(prev.start_s, max(prev.end_s, window.end_s))
    return tuple(merged)


def _pii_cost(duration_s: float, box_count: int) -> float:
    return _COST_PII_BASE_PER_S * duration_s + _COST_PII_PER_BOX * box_count


def _yolo_cost(duration_s: float, has_video: bool) -> float:
    if not has_video:
        return 0.0
    return _COST_YOLO_FRAME_PER_S * duration_s


def estimate_peak_ram_gb(
    *,
    analyze_duration_s: float,
    demucs_applied: bool,
    visual_pii_boxes: int,
    has_video_track: bool,
) -> float:
    """Upper-bound peak RAM for the analyzed segment (10s–60s clips stay < 4 GB)."""
    ram = _RAM_BASE_GB + _RAM_PER_S_GB * analyze_duration_s
    if demucs_applied:
        ram += _RAM_DEMUCS_OVERHEAD_GB
    ram += _RAM_PER_PII_BOX_GB * visual_pii_boxes
    if has_video_track:
        ram += _RAM_YOLO_PER_S_GB * analyze_duration_s
    return ram


def estimate_unconditional_cost(spec: SyntheticClipSpec) -> float:
    """Always run Demucs on the full clip plus PII/YOLO scrub."""
    demucs = _COST_DEMUCS_PER_S * spec.duration_s
    detect = _COST_MUSIC_DETECT_PER_S * spec.duration_s
    pii = _pii_cost(spec.duration_s, spec.visual_pii_boxes)
    yolo = _yolo_cost(spec.duration_s, spec.has_video_track)
    return demucs + detect + pii + yolo


def benchmark_music_gated_scrub(spec: SyntheticClipSpec) -> ScrubBenchmarkResult:
    """Music-gated Demucs + simulated OpenCV/YOLO PII scrub on synthetic clip."""
    if spec.duration_s <= 0:
        raise ValueError("duration_s must be positive")

    bypass_911 = is_911_telephony_bypass(spec)
    music = bool(spec.music_detected) and not bypass_911

    is_long_bodycam = (
        spec.media_kind == "bodycam_mp4" and spec.duration_s >= 60.0 * 10.0
    )
    if is_long_bodycam and spec.event_timestamps_s:
        windows = pre_slice_bodycam_windows(
            spec.duration_s, spec.event_timestamps_s
        )
    elif music:
        windows = (ScrubWindow(0.0, spec.duration_s),)
    else:
        windows = ()

    demucs_audio_s = sum(w.duration_s for w in windows) if music else 0.0
    demucs_applied = music and demucs_audio_s > 0.0
    demucs_skipped = not demucs_applied

    detect_cost = _COST_MUSIC_DETECT_PER_S * spec.duration_s
    demucs_cost = _COST_DEMUCS_PER_S * demucs_audio_s if demucs_applied else 0.0
    pii_cost = _pii_cost(spec.duration_s, spec.visual_pii_boxes)
    yolo_cost = _yolo_cost(spec.duration_s, spec.has_video_track)
    estimated_cost = detect_cost + demucs_cost + pii_cost + yolo_cost

    analyze_s = max((w.duration_s for w in windows), default=0.0)
    if not windows:
        analyze_s = spec.duration_s

    peak_ram = estimate_peak_ram_gb(
        analyze_duration_s=analyze_s,
        demucs_applied=demucs_applied,
        visual_pii_boxes=spec.visual_pii_boxes,
        has_video_track=spec.has_video_track,
    )

    unconditional = estimate_unconditional_cost(spec)

    return ScrubBenchmarkResult(
        clip_id=spec.clip_id,
        demucs_skipped=demucs_skipped,
        demucs_applied=demucs_applied,
        music_detected=music,
        estimated_cost=estimated_cost,
        unconditional_demucs_cost=unconditional,
        peak_ram_gb=peak_ram,
        demucs_audio_s=demucs_audio_s,
        pre_slice_windows=windows,
        pii_boxes_scrubbed=spec.visual_pii_boxes,
    )


def ram_within_cap(peak_ram_gb: float, cap_gb: float = PEAK_RAM_CAP_GB) -> bool:
    return peak_ram_gb < cap_gb