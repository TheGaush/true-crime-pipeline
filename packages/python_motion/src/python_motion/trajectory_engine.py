"""Deterministic map and trajectory plates.

Splines are Catmull-Rom. A zero-length path becomes a stationary marker.
Manim is not required; frames are rasterized with Pillow and optional FFmpeg.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

INK = (0x1B, 0x1B, 0x1D)
PARCHMENT = (0xE9, 0xE2, 0xD2)
SLATE = (0x3A, 0x4F, 0x66)
CRIMSON = (0xC9, 0x2A, 0x2A)
FRAME = (1920, 1080)
FPS = 30


class TrajectoryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TrajectoryRequest:
    waypoints: tuple[tuple[float, float], ...]
    duration_sec: float
    out_path: str | None = None
    for_flow_keyframe: bool = False
    show_target: bool = True


def ease_in_out_cubic(progress: float) -> float:
    value = min(1.0, max(0.0, progress))
    if value < 0.5:
        return 4.0 * value * value * value
    tail = -2.0 * value + 2.0
    return 1.0 - (tail * tail * tail) / 2.0


def frame_count(duration_sec: float) -> int:
    if not math.isfinite(duration_sec) or duration_sec <= 0:
        raise TrajectoryError("DURATION", "duration_sec must be positive")
    return max(1, int(round(duration_sec * FPS)))


def progress_at(frame_idx: int, nb_frames: int) -> float:
    if frame_idx < 0 or frame_idx >= nb_frames:
        raise TrajectoryError("FRAME", "frame index is outside the clip")
    return frame_idx / max(1, nb_frames - 1)


def path_length(points: list[tuple[float, float]]) -> float:
    total = 0.0
    for start, end in zip(points, points[1:], strict=False):
        total += math.hypot(end[0] - start[0], end[1] - start[1])
    return total


def rdp(points: list[tuple[float, float]], epsilon: float = 1.5) -> list[tuple[float, float]]:
    if len(points) < 3:
        return list(points)
    start = points[0]
    end = points[-1]
    span = math.hypot(end[0] - start[0], end[1] - start[1])
    farthest = 0.0
    index = 0
    for cursor, point in enumerate(points[1:-1], start=1):
        distance = _perp(point, start, end, span)
        if distance > farthest:
            farthest = distance
            index = cursor
    if farthest > epsilon and index > 0:
        left = rdp(points[: index + 1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def catmull_rom(points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    if not points:
        raise TrajectoryError("WAYPOINTS", "at least one waypoint is required")
    if path_length(points) < 1e-6:
        return points[0]
    simplified = rdp(points) if len(points) > 200 else points
    count = len(simplified)
    if count == 1:
        return simplified[0]
    eased = ease_in_out_cubic(progress)
    span = eased * (count - 1)
    index = min(count - 2, int(math.floor(span)))
    local = span - index
    p0 = simplified[max(0, index - 1)]
    p1 = simplified[index]
    p2 = simplified[index + 1]
    p3 = simplified[min(count - 1, index + 2)]
    return _catmull(p0, p1, p2, p3, local)


def bearing_deg(start: tuple[float, float], end: tuple[float, float]) -> float:
    return math.degrees(math.atan2(end[0] - start[0], -(end[1] - start[1]))) % 360.0


class TrajectoryRenderer:
    def render_frame(self, request: TrajectoryRequest, frame_idx: int) -> Image.Image:
        frames = frame_count(request.duration_sec)
        point = catmull_rom(list(request.waypoints), progress_at(frame_idx, frames))
        plate = Image.new("RGB", FRAME, PARCHMENT)
        draw = ImageDraw.Draw(plate)
        samples = [catmull_rom(list(request.waypoints), index / 32) for index in range(33)]
        draw.line(samples, fill=SLATE, width=6)
        traveled = max(2, int(round(progress_at(frame_idx, frames) * 32)) + 1)
        draw.line(samples[:traveled], fill=INK, width=8)
        color = INK if request.for_flow_keyframe or not request.show_target else CRIMSON
        radius = 16
        draw.ellipse([point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius], outline=color, width=4)
        return plate

    def render_mp4(self, request: TrajectoryRequest) -> dict[str, object]:
        if request.out_path is None:
            raise TrajectoryError("OUTPUT", "out_path is required")
        frames = frame_count(request.duration_sec)
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{FRAME[0]}x{FRAME[1]}",
            "-r",
            str(FPS),
            "-i",
            "-",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "ultrafast",
            "-r",
            str(FPS),
            request.out_path,
        ]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdin is not None
        for index in range(frames):
            image = self.render_frame(request, index)
            big = image.resize((FRAME[0] * 2, FRAME[1] * 2), Image.Resampling.BOX)
            small = big.resize(FRAME, Image.Resampling.LANCZOS)
            process.stdin.write(small.tobytes())
        process.stdin.close()
        stderr = process.stderr.read().decode("utf8", "replace") if process.stderr is not None else ""
        code = process.wait()
        if code != 0:
            raise TrajectoryError("FFMPEG", stderr[-500:])
        return {"nb_frames": frames, "path": request.out_path}


def _catmull(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    t2 = t * t
    t3 = t2 * t
    def axis(i: int) -> float:
        return 0.5 * (
            (2.0 * p1[i])
            + (-p0[i] + p2[i]) * t
            + (2.0 * p0[i] - 5.0 * p1[i] + 4.0 * p2[i] - p3[i]) * t2
            + (-p0[i] + 3.0 * p1[i] - 3.0 * p2[i] + p3[i]) * t3
        )
    return (axis(0), axis(1))


def _perp(point, start, end, span: float) -> float:
    if span < 1e-9:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    return abs((end[0] - start[0]) * (start[1] - point[1]) - (start[0] - point[0]) * (end[1] - start[1])) / span
