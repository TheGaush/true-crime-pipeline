"""480p pre-flight animatic cards.

One PNG is drawn per scene. FFmpeg's concat demuxer holds each card for the
scene's exact frame count. No remote render call is made.
"""

from __future__ import annotations

import json
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

WIDTH = 854
HEIGHT = 480
FPS = 30
BADGES = {
    "CODE_STICKMAN": "CODE",
    "STILL_2K_PANZOOM": "2K",
    "FLOW_HERO_VIDEO": "FLOW_HERO",
    "FOIA_REAL_FOOTAGE": "FOIA",
}


class AnimaticError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AnimaticResult:
    mp4_path: str
    telemetry_path: str
    total_duration_sec: float
    hero_clip_count: int
    max_code_streak_sec: float
    nb_frames: int


def render_card(scene: dict, foia_missing: bool) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (0xE9, 0xE2, 0xD2))
    draw = ImageDraw.Draw(image)
    engine = str(scene.get("visual_engine", "CODE_STICKMAN"))
    badge = BADGES.get(engine, "CODE")
    scene_id = str(scene.get("scene_id", "scene"))
    draw.rectangle([24, 24, WIDTH - 24, 92], outline=(0x1B, 0x1B, 0x1D), width=3)
    draw.text((40, 40), scene_id, fill=(0x1B, 0x1B, 0x1D))
    draw.text((40, 64), badge, fill=(0x3A, 0x4F, 0x66))
    words = int(scene.get("word_count", 0))
    bar = min(WIDTH - 80, 40 + words * 8)
    draw.rectangle([40, 120, bar, 148], fill=(0x3A, 0x4F, 0x66))
    if engine == "STILL_2K_PANZOOM":
        for index in range(11):
            x = 40 + int(round(index * 200 / 10))
            y = 180 + int(round(index * 120 / 10))
            draw.line([(x, 180), (x, 300)], fill=(0xC9, 0x2A, 0x2A))
            draw.line([(40, y), (240, y)], fill=(0xC9, 0x2A, 0x2A))
    if foia_missing and engine == "FOIA_REAL_FOOTAGE":
        draw.rectangle([40, 310, 260, 348], fill=(0x1B, 0x1B, 0x1D))
        draw.text((48, 320), "[FOIA STUB]", fill=(0xE9, 0xE2, 0xD2))
    for step in range(80):
        x = 280 + step * 6
        y = 360 + int(12 * ((step * 3 + len(scene_id)) % 7) - 36)
        draw.point((x, y), fill=(0x1B, 0x1B, 0x1D))
    return image


def build_animatic(manifest: dict, out_dir: str, voice_wav: str | None = None, foia_wav: str | None = None) -> AnimaticResult:
    scenes = manifest.get("scenes") or manifest.get("scene_plans")
    if not isinstance(scenes, list) or not scenes:
        raise AnimaticError("MANIFEST", "manifest needs scenes")
    episode = str(manifest.get("episode_id", "episode"))
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    cards: list[tuple[Path, int, str]] = []
    durations: list[float] = []
    engines: list[str] = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise AnimaticError("MANIFEST", f"scene {index} must be an object")
        frames = _frames(scene)
        engine = str(scene.get("visual_engine", "CODE_STICKMAN"))
        missing = foia_wav is None or not Path(foia_wav).is_file()
        card = render_card(scene, missing)
        path = root / f"card_{index:03d}.png"
        card.save(path, format="PNG")
        cards.append((path, frames, engine))
        durations.append(frames / FPS)
        engines.append(engine)
    total_frames = sum(item[1] for item in cards)
    total = total_frames / FPS
    script = root / "concat.txt"
    lines = ["ffconcat version 1.0"]
    for path, frames, _engine in cards:
        lines.append(f"file '{path.as_posix()}'")
        lines.append(f"duration {frames / FPS:.6f}")
    lines.append(f"file '{cards[-1][0].as_posix()}'")
    script.write_text("\n".join(lines) + "\n", encoding="utf8")
    audio = _audio(root, total, voice_wav, foia_wav)
    mp4 = root / f"{episode}_preflight_480p.mp4"
    _encode(script, audio, mp4)
    telemetry = {
        "episode_id": episode,
        "total_duration_sec": total,
        "hero_clip_count": sum(1 for engine in engines if engine == "FLOW_HERO_VIDEO"),
        "max_code_streak_sec": _code_streak(engines, durations),
        "nb_frames": total_frames,
        "remote_calls": 0,
    }
    telemetry_path = root / f"{episode}_pacing.json"
    telemetry_path.write_text(json.dumps(telemetry, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return AnimaticResult(str(mp4), str(telemetry_path), total, telemetry["hero_clip_count"], telemetry["max_code_streak_sec"], total_frames)


def _frames(scene: dict) -> int:
    if "duration_ms" in scene:
        ms = int(scene["duration_ms"])
        if ms <= 0:
            raise AnimaticError("DURATION", "duration_ms must be positive")
        return max(1, int(round(ms * FPS / 1000)))
    if "duration_sec" in scene:
        return max(1, int(round(float(scene["duration_sec"]) * FPS)))
    raise AnimaticError("DURATION", "scene needs duration_ms or duration_sec")


def _code_streak(engines: list[str], durations: list[float]) -> float:
    best = 0.0
    current = 0.0
    for engine, duration in zip(engines, durations, strict=True):
        if engine == "CODE_STICKMAN":
            current += duration
            best = max(best, current)
        else:
            current = 0.0
    return best


def _audio(root: Path, total: float, voice_wav: str | None, foia_wav: str | None) -> Path:
    if voice_wav and Path(voice_wav).is_file():
        return Path(voice_wav)
    path = root / "silence.wav"
    frames = int(round(total * 48_000))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * frames)
    del foia_wav
    return path


def _encode(script: Path, audio: Path, mp4: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(script),
        "-i",
        str(audio),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-shortest",
        str(mp4),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise AnimaticError("FFMPEG", result.stderr[-500:])
