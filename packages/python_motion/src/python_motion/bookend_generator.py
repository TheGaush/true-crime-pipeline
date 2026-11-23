"""Start and end keyframe pairs for hero scenes.

``TEXT_TO_VIDEO`` writes no plates. ``FIRST_FRAME`` writes a start plate.
``FIRST_AND_LAST_FRAME`` writes a continuous pair. Every plate is checked
with the Law 12 validator before it is saved.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

TEXT_TO_VIDEO = "TEXT_TO_VIDEO"
FIRST_FRAME = "FIRST_FRAME"
FIRST_AND_LAST_FRAME = "FIRST_AND_LAST_FRAME"
PROMPT_MODES = (TEXT_TO_VIDEO, FIRST_FRAME, FIRST_AND_LAST_FRAME)
MAX_TRANSLATION = 0.65
PARALLAX = 0.03


class BookendError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BookendSafetyError(BookendError):
    def __init__(self, message: str, violations: list[str]) -> None:
        super().__init__("SAFETY", message)
        self.violations = violations


@dataclass(frozen=True)
class BookendRequest:
    scene_id: str
    prompt_mode: str
    duration_sec: float
    out_dir: str
    pose: str = "idle"
    end_pose: str = "idle"
    walk_phase: float = 0.0
    end_walk_phase: float = 0.0
    actor_x: float = 0.5
    end_actor_x: float = 0.5
    width: int = 1280
    height: int = 720
    keyframe_props: tuple[dict[str, str], ...] = ()
    seed: int = 0


@dataclass(frozen=True)
class BookendPair:
    scene_id: str
    prompt_mode: str
    duration_sec: float
    start_frame: str | None
    end_frame: str | None
    meta_path: str
    safety_passed: bool
    start_sha256: str | None
    end_sha256: str | None
    warnings: tuple[dict[str, str], ...]


class BookendGenerator:
    def generate(self, request: BookendRequest) -> BookendPair:
        mode = _mode(request.prompt_mode)
        scene_id = _scene_id(request.scene_id)
        width, height = _size(request.width, request.height)
        duration, duration_warnings = _duration(mode, request.duration_sec)
        out_dir = Path(request.out_dir)
        if mode == TEXT_TO_VIDEO:
            meta = _write_meta(
                out_dir,
                scene_id,
                mode,
                duration,
                None,
                None,
                True,
                duration_warnings,
                translation_clamped=False,
                parallax_applied=False,
            )
            return BookendPair(scene_id, mode, duration, None, None, str(meta), True, None, None, tuple(duration_warnings))

        end_x, clamp_warnings = _clamp_translation(request.actor_x, request.end_actor_x)
        warnings = [*duration_warnings, *clamp_warnings]
        end_phase = request.end_walk_phase
        end_pose = request.end_pose
        parallax = False
        if mode == FIRST_AND_LAST_FRAME and _same_pose(request, end_x, end_phase, end_pose):
            end_phase = min(1.0, request.walk_phase + 0.2)
            end_pose = "walking" if request.pose == "idle" else request.pose
            end_x = min(1.0, end_x + PARALLAX)
            parallax = True
            warnings.append({"code": "PARALLAX", "from": "0", "to": f"{PARALLAX}"})

        stick = _load_sibling("stickman_pil")
        safety = _load_sibling("safety_validator")
        validator = safety.InputImageSafetyValidator()
        start_image = _compose(
            stick,
            request.pose,
            request.walk_phase,
            request.actor_x,
            width,
            height,
            request.keyframe_props,
            request.seed,
            shadow=1.0,
        )
        start_verdict = validator.validate(start_image)
        if not start_verdict.passed:
            raise BookendSafetyError("start frame failed the safety validator", list(start_verdict.violations))
        end_image = None
        end_verdict = None
        if mode == FIRST_AND_LAST_FRAME:
            end_image = _compose(
                stick,
                end_pose,
                end_phase,
                end_x,
                width,
                height,
                request.keyframe_props,
                request.seed,
                shadow=1.03,
            )
            end_verdict = validator.validate(end_image)
            if not end_verdict.passed:
                raise BookendSafetyError("end frame failed the safety validator", list(end_verdict.violations))

        out_dir.mkdir(parents=True, exist_ok=True)
        start_path = out_dir / f"{scene_id}_start.png"
        start_bytes = _png(start_image)
        start_path.write_bytes(start_bytes)
        end_path = None
        end_bytes = None
        if end_image is not None:
            end_path = out_dir / f"{scene_id}_end.png"
            end_bytes = _png(end_image)
            end_path.write_bytes(end_bytes)
        start_hash = hashlib.sha256(start_bytes).hexdigest()
        end_hash = None if end_bytes is None else hashlib.sha256(end_bytes).hexdigest()
        meta = _write_meta(
            out_dir,
            scene_id,
            mode,
            duration,
            start_hash,
            end_hash,
            True,
            warnings,
            translation_clamped=any(item["code"] == "TRANSLATION_CLAMP" for item in warnings),
            parallax_applied=parallax,
        )
        return BookendPair(
            scene_id,
            mode,
            duration,
            str(start_path),
            None if end_path is None else str(end_path),
            str(meta),
            True,
            start_hash,
            end_hash,
            tuple(warnings),
        )


def _compose(stick, pose: str, phase: float, actor_x: float, width: int, height: int, props, seed: int, shadow: float) -> Image.Image:
    frame = stick.StickmanRenderer().render(
        stick.StickmanRenderRequest(
            pose=pose,
            width=width,
            height=height,
            for_flow_keyframe=True,
            walk_phase=phase,
            keyframe_props=tuple(props),
            seed=seed,
        )
    )
    image = frame.image.convert("RGB")
    shift = int(round((actor_x - 0.5) * width))
    moved = Image.new("RGB", image.size, (0xE9, 0xE2, 0xD2))
    moved.paste(image, (shift, 0))
    draw_shadow(moved, shift, shadow)
    return moved


def draw_shadow(image: Image.Image, shift: int, scale: float) -> None:
    width, height = image.size
    cx = width // 2 + shift
    cy = int(height * 0.86)
    rx = int(70 * scale)
    ry = int(14 * scale)
    pixels = image.load()
    slate = (0x3A, 0x4F, 0x66)
    for y in range(max(0, cy - ry), min(height, cy + ry)):
        for x in range(max(0, cx - rx), min(width, cx + rx)):
            nx = (x - cx) / rx
            ny = (y - cy) / ry
            if nx * nx + ny * ny <= 1.0:
                pixels[x, y] = slate


def _write_meta(out_dir, scene_id, mode, duration, start_hash, end_hash, safety_passed, warnings, translation_clamped, parallax_applied) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{scene_id}_bookend_meta.json"
    body = {
        "scene_id": scene_id,
        "prompt_mode": mode,
        "duration_sec": duration,
        "start_sha256": start_hash,
        "end_sha256": end_hash,
        "safety_passed": safety_passed,
        "translation_clamped": translation_clamped,
        "parallax_applied": parallax_applied,
        "warnings": warnings,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return path


def _duration(mode: str, duration: float) -> tuple[float, list[dict[str, str]]]:
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        raise BookendError("DURATION", "duration_sec must be a number")
    low, high = (3.0, 15.0) if mode == FIRST_FRAME else (3.0, 10.0)
    if mode == TEXT_TO_VIDEO:
        low, high = (0.0, 3600.0)
    value = float(duration)
    if low <= value <= high:
        return value, []
    clamped = min(high, max(low, value))
    return clamped, [{"code": "DURATION_CLAMP", "from": str(value), "to": str(clamped)}]


def _clamp_translation(start: float, end: float) -> tuple[float, list[dict[str, str]]]:
    if abs(end - start) <= MAX_TRANSLATION:
        return end, []
    direction = 1.0 if end > start else -1.0
    clamped = start + direction * MAX_TRANSLATION
    return clamped, [{"code": "TRANSLATION_CLAMP", "from": str(end), "to": str(clamped)}]


def _same_pose(request: BookendRequest, end_x: float, end_phase: float, end_pose: str) -> bool:
    return (
        request.pose == end_pose
        and request.walk_phase == end_phase
        and abs(request.actor_x - end_x) < 1e-6
    )


def _mode(value: str) -> str:
    if value not in PROMPT_MODES:
        raise BookendError("PROMPT_MODE", f"unknown prompt mode {value}")
    return value


def _scene_id(value: str) -> str:
    if not value or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for char in value):
        raise BookendError("SCENE_ID", "scene_id must be a file-safe token")
    return value


def _size(width: int, height: int) -> tuple[int, int]:
    if (width, height) not in {(1280, 720), (1920, 1080)}:
        raise BookendError("SIZE", "frames must be 1280x720 or 1920x1080")
    return width, height


def _png(image: Image.Image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=9)
    return buffer.getvalue()


def _load_sibling(stem: str):
    path = Path(__file__).with_name(f"{stem}.py")
    spec = importlib.util.spec_from_file_location(f"tc_bookend_{stem}", path)
    if spec is None or spec.loader is None:
        raise BookendError("IMPORT", f"missing sibling {stem}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
