"""Sub-pixel pan and zoom through OpenCV Lanczos warps.

Callout rings are drawn after the warp, on the 1920x1080 plate. The clip
is ungraded: no grain and no vignette.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import cv2
import numpy as np

SCREEN = (1920, 1080)
FPS = 30


class LanczosRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class CameraWaypoint:
    cx: float
    cy: float
    zoom: float


def smoothstep(progress: float) -> float:
    value = min(1.0, max(0.0, progress))
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def sample_camera(start: CameraWaypoint, end: CameraWaypoint, progress: float) -> CameraWaypoint:
    eased = smoothstep(progress)
    return CameraWaypoint(
        start.cx + (end.cx - start.cx) * eased,
        start.cy + (end.cy - start.cy) * eased,
        start.zoom + (end.zoom - start.zoom) * eased,
    )


def warp_frame(image: np.ndarray, camera: CameraWaypoint) -> np.ndarray:
    height, width = image.shape[:2]
    crop_w = width / camera.zoom
    crop_h = crop_w * 9.0 / 16.0
    x0 = min(max(camera.cx - crop_w / 2.0, 0.0), width - crop_w)
    y0 = min(max(camera.cy - crop_h / 2.0, 0.0), height - crop_h)
    scale_x = SCREEN[0] / crop_w
    scale_y = SCREEN[1] / crop_h
    matrix = np.array([[scale_x, 0.0, -x0 * scale_x], [0.0, scale_y, -y0 * scale_y]], dtype=np.float32)
    warped = cv2.warpAffine(image, matrix, SCREEN, flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    return _ring(warped, camera, x0, y0, crop_w, crop_h)


def render_mp4(image: np.ndarray, start: CameraWaypoint, end: CameraWaypoint, duration_sec: float, out_path: str) -> int:
    frames = max(1, int(round(duration_sec * FPS)))
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{SCREEN[0]}x{SCREEN[1]}",
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
        "-crf",
        "15",
        "-r",
        str(FPS),
        out_path,
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdin is None or process.stderr is None:
        raise LanczosRenderError("ffmpeg pipe was not created")
    try:
        for index in range(frames):
            progress = index / max(1, frames - 1)
            plate = warp_frame(image, sample_camera(start, end, progress))
            process.stdin.write(np.ascontiguousarray(plate).tobytes())
    except BrokenPipeError as error:
        stderr = process.stderr.read().decode("utf8", "replace")
        raise LanczosRenderError(stderr[-800:]) from error
    process.stdin.close()
    stderr = process.stderr.read().decode("utf8", "replace")
    if process.wait() != 0:
        raise LanczosRenderError(stderr[-800:])
    return frames


def _ring(image: np.ndarray, camera: CameraWaypoint, x0: float, y0: float, crop_w: float, crop_h: float) -> np.ndarray:
    plate = image.copy()
    x = int(round(((camera.cx - x0) / crop_w) * SCREEN[0]))
    y = int(round(((camera.cy - y0) / crop_h) * SCREEN[1]))
    cv2.circle(plate, (x, y), 16, (42, 42, 201), 3)
    return plate
