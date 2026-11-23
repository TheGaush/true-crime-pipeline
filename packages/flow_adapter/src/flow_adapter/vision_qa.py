"""Three-frame vision check. A dead judge fails closed."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ClipVisionVerdict:
    passed: bool
    failure_codes: tuple[str, ...]
    confidence: float
    retry_hint: str
    state: str
    frames: tuple[str, ...]


def review(path: str, scene_id: str, out_dir: str, judge) -> ClipVisionVerdict:
    duration = _duration(path)
    stamps = (0.2, max(0.2, duration * 0.5), max(0.2, duration - 0.2))
    folder = Path(out_dir) / scene_id
    folder.mkdir(parents=True, exist_ok=True)
    frames = []
    for index, stamp in enumerate(stamps):
        frame = folder / f"frame_{index}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{stamp:.3f}", "-i", path, "-frames:v", "1", str(frame)],
            check=True, capture_output=True,
        )
        frames.append(str(frame))
    codes = _heuristics(frames)
    if codes:
        return ClipVisionVerdict(False, tuple(codes), 0.9, "heuristic", "qa_failed", tuple(frames))
    verdict = _ask(judge, frames)
    if verdict is None:
        return ClipVisionVerdict(False, ("PENDING_MANUAL_SPOT_CHECK",), 0.0, "judge_unreachable", "PENDING_MANUAL_SPOT_CHECK", tuple(frames))
    return ClipVisionVerdict(bool(verdict["passed"]), tuple(verdict.get("failure_codes", ())), float(verdict.get("confidence", 0.5)), str(verdict.get("retry_hint", "")), "qa_passed" if verdict["passed"] else "qa_failed", tuple(frames))


def _ask(judge, frames: list[str]):
    last = None
    for _ in range(2):
        try:
            return judge(frames)
        except RuntimeError as error:
            last = error
    return None if last is not None else None


def _heuristics(frames: list[str]) -> list[str]:
    codes = []
    lumas = []
    for frame in frames:
        rgb = np.asarray(Image.open(frame).convert("RGB"))
        luma = rgb.mean(axis=2)
        lumas.append(float(luma.mean()))
        if float(luma.std()) < 2.0 and float(luma.mean()) < 8.0:
            codes.append("BLANK_FRAME")
        red = rgb[..., 0].astype(np.int16)
        green = rgb[..., 1].astype(np.int16)
        blue = rgb[..., 2].astype(np.int16)
        if int(np.count_nonzero((red > 160) & (red > green * 1.8) & (red > blue * 1.8))) > 35:
            codes.append("CRIMSON_BURST")
    if lumas and max(lumas) - min(lumas) > 80:
        codes.append("FLASH_CUT")
    return codes


def _duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return max(0.4, float(result.stdout.strip() or "0.4"))
