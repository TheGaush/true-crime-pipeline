"""Monochrome stickman keyframes for Flow start and end plates.

Bone lengths and the degree convention match ``StickFigureGeometry``:
0 keeps a bone on its parent rest direction, and positive degrees rotate
toward screen-left in y-down space. Flow plates are limited to ink,
parchment, slate, and amber. Crimson is remapped before it is drawn.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

INK = (0x1B, 0x1B, 0x1D)
PARCHMENT = (0xE9, 0xE2, 0xD2)
SLATE = (0x3A, 0x4F, 0x66)
AMBER = (0xB8, 0x86, 0x0B)
CRIMSON = (0xC9, 0x2A, 0x2A)
FLOW_PALETTE = (INK, PARCHMENT, SLATE, AMBER)

FRAME_720 = (1280, 720)
FRAME_1080 = (1920, 1080)
SUPERSAMPLE = 2
HEAD_RADIUS = 22.0
TORSO_LEN = 70.0
UPPER_ARM = 36.0
FOREARM = 32.0
THIGH = 46.0
SHIN = 42.0
STROKE_720 = 6
STROKE_1080 = 9

POSE_IDS = (
    "idle",
    "walking",
    "pointing",
    "seated",
    "evidence_hold",
    "doorway_entry",
    "detective_silhouette",
    "arms_crossed",
)

_TEXT_KINDS = frozenset({"caption", "watermark", "timestamp", "label", "text"})
_LOG = logging.getLogger("python_motion.stickman")
_UP = (0.0, -1.0)


class StickmanRenderError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StickJoints:
    torso_deg: float = 0.0
    head_deg: float = 0.0
    upper_arm_left_deg: float = 16.0
    forearm_left_deg: float = 12.0
    upper_arm_right_deg: float = -16.0
    forearm_right_deg: float = -12.0
    thigh_left_deg: float = 8.0
    shin_left_deg: float = 4.0
    thigh_right_deg: float = -8.0
    shin_right_deg: float = -4.0


@dataclass(frozen=True)
class StickmanRenderRequest:
    pose: str
    width: int = FRAME_720[0]
    height: int = FRAME_720[1]
    background: str = "parchment"
    for_flow_keyframe: bool = True
    facing: str = "right"
    walk_phase: float = 0.0
    mode: str = "RGB"
    keyframe_props: tuple[dict[str, str], ...] = ()
    seed: int = 0


@dataclass(frozen=True)
class StickSockets:
    hip: tuple[float, float]
    neck: tuple[float, float]
    head: tuple[float, float]
    hand_left: tuple[float, float]
    hand_right: tuple[float, float]
    elbow_left: tuple[float, float]
    elbow_right: tuple[float, float]
    knee_left: tuple[float, float]
    knee_right: tuple[float, float]
    ankle_left: tuple[float, float]
    ankle_right: tuple[float, float]


@dataclass(frozen=True)
class StickmanFrame:
    image: Image.Image
    png_bytes: bytes
    sha256: str
    pose: str
    width: int
    height: int
    mode: str
    sockets: StickSockets
    joints: StickJoints
    warnings: tuple[dict[str, str], ...]
    stroke_px: int
    supersample_size: tuple[int, int]


class StickmanRenderer:
    """Draw one deterministic stick figure and write a PNG plate."""

    def render(self, request: StickmanRenderRequest) -> StickmanFrame:
        width, height = _frame_size(request.width, request.height)
        background = _background(request.background)
        facing = _facing(request.facing)
        mode = _mode(request.mode)
        if request.pose not in POSE_IDS:
            raise StickmanRenderError("POSE", f"unknown pose {request.pose}")
        if not math.isfinite(request.walk_phase):
            raise StickmanRenderError("PHASE", "walk_phase must be finite")
        if not isinstance(request.seed, int) or isinstance(request.seed, bool) or request.seed < 0:
            raise StickmanRenderError("SEED", "seed must be a non-negative integer and does not jitter pixels")
        joints = joints_for(request.pose, request.walk_phase)
        scale = height / 1080.0
        origin = (width * 0.5, height * 0.66)
        sockets = solve_sockets(joints, facing, scale, origin)
        warnings: list[dict[str, str]] = []
        big = (width * SUPERSAMPLE, height * SUPERSAMPLE)
        plate = Image.new("RGB", big, background)
        draw = ImageDraw.Draw(plate)
        stroke = stroke_px(height) * SUPERSAMPLE
        ink = _figure_ink(background)
        _draw_stage(draw, request, sockets, big, stroke, warnings)
        _draw_figure(draw, sockets, stroke, ink, request.pose == "detective_silhouette", big)
        array = np.asarray(plate)
        resized = cv2.resize(array, (width, height), interpolation=cv2.INTER_LANCZOS4)
        image = Image.fromarray(resized, mode="RGB")
        if mode == "RGBA":
            image = image.convert("RGBA")
        png_bytes = _png_bytes(image)
        return StickmanFrame(
            image=image,
            png_bytes=png_bytes,
            sha256=hashlib.sha256(png_bytes).hexdigest(),
            pose=request.pose,
            width=width,
            height=height,
            mode=mode,
            sockets=sockets,
            joints=joints,
            warnings=tuple(warnings),
            stroke_px=stroke_px(height),
            supersample_size=big,
        )

    def render_png(self, request: StickmanRenderRequest, path: str | Path) -> StickmanFrame:
        frame = self.render(request)
        Path(path).write_bytes(frame.png_bytes)
        return frame


def joints_for(pose: str, walk_phase: float = 0.0) -> StickJoints:
    if pose not in POSE_IDS:
        raise StickmanRenderError("POSE", f"unknown pose {pose}")
    if pose == "walking":
        swing = math.sin(2.0 * math.pi * walk_phase)
        return StickJoints(
            upper_arm_left_deg=16.0 - 24.0 * swing,
            upper_arm_right_deg=-16.0 + 24.0 * swing,
            thigh_left_deg=8.0 + 28.0 * swing,
            shin_left_deg=4.0 + 16.0 * max(swing, 0.0),
            thigh_right_deg=-8.0 - 28.0 * swing,
            shin_right_deg=-4.0 + 16.0 * max(-swing, 0.0),
        )
    if pose == "pointing":
        return StickJoints(upper_arm_right_deg=-96.0, forearm_right_deg=-6.0)
    if pose == "seated":
        return StickJoints(
            torso_deg=8.0,
            thigh_left_deg=-82.0,
            shin_left_deg=86.0,
            thigh_right_deg=-74.0,
            shin_right_deg=80.0,
            upper_arm_left_deg=22.0,
            upper_arm_right_deg=-28.0,
        )
    if pose == "evidence_hold":
        return StickJoints(
            upper_arm_left_deg=-48.0,
            forearm_left_deg=-42.0,
            upper_arm_right_deg=-78.0,
            forearm_right_deg=-36.0,
        )
    if pose == "doorway_entry":
        return StickJoints(
            torso_deg=-14.0,
            upper_arm_right_deg=-62.0,
            forearm_right_deg=-18.0,
            thigh_left_deg=-34.0,
            shin_left_deg=12.0,
            thigh_right_deg=16.0,
            shin_right_deg=8.0,
        )
    if pose == "arms_crossed":
        return StickJoints(
            upper_arm_left_deg=58.0,
            forearm_left_deg=108.0,
            upper_arm_right_deg=-58.0,
            forearm_right_deg=-108.0,
        )
    return StickJoints()


def solve_sockets(joints: StickJoints, facing: str, scale: float, origin: tuple[float, float]) -> StickSockets:
    radius = HEAD_RADIUS * scale
    torso_dir = _rotate(_UP, joints.torso_deg)
    down = (-torso_dir[0], -torso_dir[1])
    pelvis = (0.0, 0.0)
    neck = _add(pelvis, _mul(torso_dir, TORSO_LEN * scale))
    head_dir = _rotate(torso_dir, joints.head_deg)
    head = _add(neck, _mul(head_dir, radius))
    elbow_l, hand_l = _chain(neck, down, joints.upper_arm_left_deg, UPPER_ARM * scale, joints.forearm_left_deg, FOREARM * scale)
    elbow_r, hand_r = _chain(neck, down, joints.upper_arm_right_deg, UPPER_ARM * scale, joints.forearm_right_deg, FOREARM * scale)
    knee_l, ankle_l = _chain(pelvis, down, joints.thigh_left_deg, THIGH * scale, joints.shin_left_deg, SHIN * scale)
    knee_r, ankle_r = _chain(pelvis, down, joints.thigh_right_deg, THIGH * scale, joints.shin_right_deg, SHIN * scale)
    mirror = facing == "left"
    points = {
        "hip": pelvis,
        "neck": neck,
        "head": head,
        "hand_left": hand_l,
        "hand_right": hand_r,
        "elbow_left": elbow_l,
        "elbow_right": elbow_r,
        "knee_left": knee_l,
        "knee_right": knee_r,
        "ankle_left": ankle_l,
        "ankle_right": ankle_r,
    }
    placed = {name: _place(point, mirror, origin) for name, point in points.items()}
    return StickSockets(**placed)


def stroke_px(height: int) -> int:
    if height == FRAME_720[1]:
        return STROKE_720
    if height == FRAME_1080[1]:
        return STROKE_1080
    raise StickmanRenderError("SIZE", f"unsupported frame height {height}")


def supersample_size(width: int, height: int) -> tuple[int, int]:
    frame_w, frame_h = _frame_size(width, height)
    return (frame_w * SUPERSAMPLE, frame_h * SUPERSAMPLE)


def red_trigger_count(rgb: np.ndarray) -> int:
    return int(np.count_nonzero(red_trigger_mask(rgb)))


def red_trigger_mask(rgb: np.ndarray) -> np.ndarray:
    channels = rgb[..., :3].astype(np.float32)
    red = channels[..., 0]
    green = channels[..., 1]
    blue = channels[..., 2]
    return (red > 160.0) & (red > green * 1.8) & (red > blue * 1.8)


def ssim_luma(left: np.ndarray, right: np.ndarray) -> float:
    """Mean structural similarity of two RGB plates. Identical plates score 1."""
    if left.shape != right.shape:
        raise StickmanRenderError("SSIM", "plates must share a shape")
    ly = left[..., :3].astype(np.float64).mean(axis=2)
    ry = right[..., :3].astype(np.float64).mean(axis=2)
    kernel = 7
    mu_x = ndimage.uniform_filter(ly, kernel)
    mu_y = ndimage.uniform_filter(ry, kernel)
    sigma_x = ndimage.uniform_filter(ly * ly, kernel) - mu_x * mu_x
    sigma_y = ndimage.uniform_filter(ry * ry, kernel) - mu_y * mu_y
    sigma_xy = ndimage.uniform_filter(ly * ry, kernel) - mu_x * mu_y
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    numerator = (2.0 * mu_x * mu_y + c1) * (2.0 * sigma_xy + c2)
    denominator = (mu_x * mu_x + mu_y * mu_y + c1) * (sigma_x + sigma_y + c2)
    return float(np.mean(numerator / denominator))


def _draw_stage(
    draw: ImageDraw.ImageDraw,
    request: StickmanRenderRequest,
    sockets: StickSockets,
    big: tuple[int, int],
    stroke: int,
    warnings: list[dict[str, str]],
) -> None:
    width, height = big
    ground = int(height * 0.86)
    slate = _sample(SLATE, SUPERSAMPLE)
    draw.line([(int(width * 0.12), ground), (int(width * 0.88), ground)], fill=slate, width=max(stroke // 2, 2))
    if request.pose in {"doorway_entry"}:
        _doorway(draw, width, height, stroke)
    if request.pose in {"seated", "evidence_hold"}:
        _desk(draw, width, ground, stroke)
    if request.pose == "evidence_hold":
        _folder(draw, sockets, stroke)
    for prop in request.keyframe_props:
        _draw_prop(draw, prop, request.for_flow_keyframe, sockets, stroke, warnings)


def _draw_figure(
    draw: ImageDraw.ImageDraw,
    sockets: StickSockets,
    stroke: int,
    ink: tuple[int, int, int],
    silhouette: bool,
    big: tuple[int, int],
) -> None:
    width = stroke * 2 if silhouette else stroke
    color = _sample(ink, SUPERSAMPLE)
    pairs = (
        (sockets.hip, sockets.neck),
        (sockets.neck, sockets.head),
        (sockets.neck, sockets.elbow_left),
        (sockets.elbow_left, sockets.hand_left),
        (sockets.neck, sockets.elbow_right),
        (sockets.elbow_right, sockets.hand_right),
        (sockets.hip, sockets.knee_left),
        (sockets.knee_left, sockets.ankle_left),
        (sockets.hip, sockets.knee_right),
        (sockets.knee_right, sockets.ankle_right),
    )
    for start, end in pairs:
        draw.line([_px(start), _px(end)], fill=color, width=width)
    radius = HEAD_RADIUS * (big[1] / 1080.0)
    box = _circle_box(sockets.head, radius)
    if silhouette:
        draw.ellipse(box, fill=color)
        _fedora(draw, sockets.head, radius, color)
    else:
        draw.ellipse(box, outline=color, width=max(width // 2, 2))


def _doorway(draw: ImageDraw.ImageDraw, width: int, height: int, stroke: int) -> None:
    color = _sample(SLATE, SUPERSAMPLE)
    left = int(width * 0.30)
    right = int(width * 0.70)
    top = int(height * 0.18)
    bottom = int(height * 0.86)
    draw.line([(left, bottom), (left, top), (right, top), (right, bottom)], fill=color, width=stroke)


def _desk(draw: ImageDraw.ImageDraw, width: int, ground: int, stroke: int) -> None:
    color = _sample(SLATE, SUPERSAMPLE)
    top = ground - stroke * 3
    draw.rectangle([int(width * 0.22), top, int(width * 0.78), top + stroke], fill=color)


def _folder(draw: ImageDraw.ImageDraw, sockets: StickSockets, stroke: int) -> None:
    left = _px(sockets.hand_left)
    right = _px(sockets.hand_right)
    x0 = min(left[0], right[0]) - stroke
    x1 = max(left[0], right[0]) + stroke
    if x1 - x0 < stroke * 4:
        mid = (x0 + x1) // 2
        x0, x1 = mid - stroke * 3, mid + stroke * 3
    y = (left[1] + right[1]) // 2
    draw.rectangle([x0, y - stroke * 2, x1, y + stroke], fill=_sample(SLATE, SUPERSAMPLE))
    draw.rectangle([x0, y - stroke * 2, x1, y - stroke], fill=_sample(AMBER, SUPERSAMPLE))


def _fedora(draw: ImageDraw.ImageDraw, head: tuple[float, float], radius: float, color: tuple[int, int, int]) -> None:
    cx, cy = _px(head)
    brim_y = int(cy - radius * 0.15)
    draw.polygon(
        [
            (int(cx - radius * 1.7), brim_y),
            (int(cx + radius * 1.7), brim_y),
            (int(cx + radius * 1.15), brim_y + int(radius * 0.28)),
            (int(cx - radius * 1.15), brim_y + int(radius * 0.28)),
        ],
        fill=color,
    )
    draw.rectangle(
        [int(cx - radius * 0.72), int(cy - radius * 1.35), int(cx + radius * 0.72), brim_y],
        fill=color,
    )


def _draw_prop(
    draw: ImageDraw.ImageDraw,
    prop: dict[str, str],
    for_flow: bool,
    sockets: StickSockets,
    stroke: int,
    warnings: list[dict[str, str]],
) -> None:
    kind = str(prop.get("kind", "")).strip().lower()
    if kind in _TEXT_KINDS:
        warnings.append({"code": "TEXT_STRIPPED", "prop": kind, "to": ""})
        _warn(warnings[-1])
        return
    requested = _parse_hex(str(prop.get("color_hex", "#3A4F66")))
    color, remapped = _flow_color(requested, for_flow, kind)
    if remapped:
        warning = {
            "code": "CRIMSON_REMAPPED",
            "prop": kind or "marker",
            "from": _hex(requested),
            "to": _hex(color),
        }
        warnings.append(warning)
        _warn(warning)
    paint = _sample(color, SUPERSAMPLE)
    hip = _px(sockets.hip)
    if kind == "lamp":
        draw.ellipse([hip[0] + stroke * 4, hip[1] - stroke * 10, hip[0] + stroke * 8, hip[1] - stroke * 6], fill=paint)
        return
    badge = [hip[0] - stroke * 6, hip[1] - stroke * 4, hip[0] - stroke, hip[1] + stroke * 2]
    draw.rectangle(badge, fill=paint)


def _flow_color(color: tuple[int, int, int], for_flow: bool, kind: str) -> tuple[tuple[int, int, int], bool]:
    if not for_flow:
        return color, False
    if color in FLOW_PALETTE and not _is_trigger(color):
        return color, False
    if _is_trigger(color) or color == CRIMSON:
        target = AMBER if kind == "lamp" else SLATE
        return target, True
    nearest = min(FLOW_PALETTE, key=lambda swatch: sum((a - b) ** 2 for a, b in zip(color, swatch, strict=True)))
    return nearest, nearest != color


def _is_trigger(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return red > 160 and red > green * 1.8 and red > blue * 1.8


def _figure_ink(background: tuple[int, int, int]) -> tuple[int, int, int]:
    return PARCHMENT if background == INK else INK


def _chain(
    origin: tuple[float, float],
    parent_down: tuple[float, float],
    upper_deg: float,
    upper_len: float,
    lower_deg: float,
    lower_len: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    upper_dir = _rotate(parent_down, upper_deg)
    elbow = _add(origin, _mul(upper_dir, upper_len))
    lower_dir = _rotate(upper_dir, lower_deg)
    hand = _add(elbow, _mul(lower_dir, lower_len))
    return elbow, hand


def _place(point: tuple[float, float], mirror: bool, origin: tuple[float, float]) -> tuple[float, float]:
    local = (-point[0], point[1]) if mirror else point
    return ((local[0] + origin[0]) * SUPERSAMPLE, (local[1] + origin[1]) * SUPERSAMPLE)


def _rotate(vector: tuple[float, float], deg: float) -> tuple[float, float]:
    rad = math.radians(deg)
    cos = math.cos(rad)
    sin = math.sin(rad)
    return (cos * vector[0] - sin * vector[1], sin * vector[0] + cos * vector[1])


def _add(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    return (left[0] + right[0], left[1] + right[1])


def _mul(vector: tuple[float, float], scalar: float) -> tuple[float, float]:
    return (vector[0] * scalar, vector[1] * scalar)


def _px(point: tuple[float, float]) -> tuple[int, int]:
    return (int(round(point[0])), int(round(point[1])))


def _circle_box(center: tuple[float, float], radius: float) -> list[int]:
    cx, cy = center
    return [int(cx - radius), int(cy - radius), int(cx + radius), int(cy + radius)]


def _sample(color: tuple[int, int, int], _scale: int) -> tuple[int, int, int]:
    return color


def _frame_size(width: int, height: int) -> tuple[int, int]:
    if (width, height) not in {FRAME_720, FRAME_1080}:
        raise StickmanRenderError("SIZE", "frames must be 1280x720 or 1920x1080")
    return width, height


def _background(name: str) -> tuple[int, int, int]:
    if name == "parchment":
        return PARCHMENT
    if name == "charcoal":
        return INK
    raise StickmanRenderError("BACKGROUND", "background must be parchment or charcoal")


def _facing(name: str) -> str:
    if name not in {"left", "right"}:
        raise StickmanRenderError("FACING", "facing must be left or right")
    return name


def _mode(name: str) -> str:
    if name not in {"RGB", "RGBA"}:
        raise StickmanRenderError("MODE", "mode must be RGB or RGBA")
    return name


def _parse_hex(text: str) -> tuple[int, int, int]:
    raw = text.strip().lstrip("#")
    if len(raw) != 6:
        raise StickmanRenderError("COLOR", f"color {text} is not a 6-digit hex")
    try:
        value = int(raw, 16)
    except ValueError as error:
        raise StickmanRenderError("COLOR", f"color {text} is not hex") from error
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255)


def _hex(color: tuple[int, int, int]) -> str:
    return f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


def _warn(payload: dict[str, str]) -> None:
    _LOG.warning(json.dumps(payload, sort_keys=True))
