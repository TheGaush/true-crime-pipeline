"""Frame-accurate plans for a multi-anchor still tour.

The plan's frame count is ``round(duration_sec * 30)``. Peak zoom stays
at or under 3.8. Opposite corners dip through a wider apex.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

FPS = 30
ZOOM_MAX = 3.8


class TourError(ValueError):
    pass


@dataclass(frozen=True)
class Anchor:
    x_px: float
    y_px: float
    zoom: float = 2.4


@dataclass(frozen=True)
class TourFrame:
    index: int
    cx: float
    cy: float
    zoom: float
    anchor_index: int | None


@dataclass(frozen=True)
class TourPlan:
    frames: tuple[TourFrame, ...]
    duration_sec: float

    @property
    def nb_frames(self) -> int:
        return len(self.frames)

    @property
    def peak_zoom(self) -> float:
        return max(frame.zoom for frame in self.frames)


def plan_tour(
    duration_sec: float,
    anchors: list[Anchor],
    width: int = 2560,
    height: int = 1440,
    cue_sec: float | None = None,
) -> TourPlan:
    if not math.isfinite(duration_sec) or duration_sec <= 0:
        raise TourError("duration_sec must be positive")
    total = int(round(duration_sec * FPS))
    if not anchors:
        frames = _push(total, width / 2, height / 2)
    else:
        travel = 1.2
        if cue_sec is not None and cue_sec < 1.5:
            travel = min(2.0, max(0.45, cue_sec))
        frames = _route(total, anchors, width, height, travel)
    if len(frames) != total:
        raise TourError("segment frames drifted from the scene clock")
    if any(frame.zoom > ZOOM_MAX + 1e-6 for frame in frames):
        raise TourError("zoom exceeded 3.8")
    return TourPlan(tuple(frames), duration_sec)


def _push(total: int, cx: float, cy: float) -> list[TourFrame]:
    frames: list[TourFrame] = []
    for index in range(total):
        progress = index / max(1, total - 1)
        frames.append(TourFrame(index, cx, cy, 1.0 + 0.18 * progress, None))
    return frames


def _route(total: int, anchors: list[Anchor], width: int, height: int, travel_sec: float) -> list[TourFrame]:
    stops = [Anchor(width / 2, height / 2, 1.2), *anchors]
    travel_frames = max(1, int(round(travel_sec * FPS)))
    hops = len(stops) - 1
    travel_budget = min(total - hops, travel_frames * hops)
    per_hop = max(1, travel_budget // hops)
    hold_budget = total - per_hop * hops
    holds = _split(hold_budget, len(stops))
    frames: list[TourFrame] = []
    for index, stop in enumerate(stops):
        for _ in range(holds[index]):
            frames.append(TourFrame(len(frames), stop.x_px, stop.y_px, min(stop.zoom, ZOOM_MAX), None if index == 0 else index - 1))
        if index == hops:
            break
        nxt = stops[index + 1]
        apex = _apex(stop, nxt, width, height)
        for step in range(per_hop):
            progress = step / max(1, per_hop - 1)
            frames.append(_blend(len(frames), stop, nxt, progress, apex))
    if len(frames) < total:
        last = frames[-1]
        while len(frames) < total:
            frames.append(TourFrame(len(frames), last.cx, last.cy, last.zoom, last.anchor_index))
    return frames[:total]


def _blend(index: int, start: Anchor, end: Anchor, progress: float, apex: float | None) -> TourFrame:
    eased = progress * progress * (3.0 - 2.0 * progress)
    zoom = start.zoom + (end.zoom - start.zoom) * eased
    if apex is not None:
        dip = 1.0 - (2.0 * eased - 1.0) ** 2
        zoom = zoom * (1.0 - dip) + apex * dip
    return TourFrame(
        index,
        start.x_px + (end.x_px - start.x_px) * eased,
        start.y_px + (end.y_px - start.y_px) * eased,
        min(ZOOM_MAX, max(1.0, zoom)),
        None,
    )


def _apex(start: Anchor, end: Anchor, width: int, height: int) -> float | None:
    span = math.hypot((end.x_px - start.x_px) / width, (end.y_px - start.y_px) / height)
    if span < 0.75:
        return None
    return min(start.zoom, end.zoom, 1.15)


def _split(total: int, parts: int) -> list[int]:
    base = total // parts
    extra = total % parts
    return [base + (1 if index < extra else 0) for index in range(parts)]
