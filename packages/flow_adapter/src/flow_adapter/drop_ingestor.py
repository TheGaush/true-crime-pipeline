"""Validate a dropped hero clip and conform it without touching the source."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class DropRejectedError(RuntimeError):
    pass


class DuplicateClipDropError(RuntimeError):
    pass


@dataclass(frozen=True)
class DropReceipt:
    scene_id: str
    path: str
    sha256: str
    width: int
    height: int
    fps: str
    duration_sec: float


def ingest(path: str, scene_id: str, out_dir: str, expected_sec: float, ledger_path: str | None = None) -> DropReceipt:
    source = Path(path)
    _reject_incomplete(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ledger = Path(ledger_path) if ledger_path else Path(out_dir) / "drop_ledger.json"
    _reject_duplicate(ledger, digest, scene_id)
    probe = _probe(str(source))
    width = int(probe.get("width") or 0)
    duration = float(probe.get("duration") or 0)
    frames = int(probe.get("nb_frames") or 0)
    if width < 1280 or frames < 1 or duration < 0.85 * expected_sec:
        raise DropRejectedError(f"{scene_id} failed the duration or resolution gate")
    out = Path(out_dir) / f"{scene_id}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    command = [
        "ffmpeg", "-y", "-i", str(source),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest",
        "-vf", "fps=30,scale=1920:1080:flags=lanczos:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
        "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-ar", "48000", "-ac", "2",
        str(out),
    ]
    subprocess.run(command, check=True, capture_output=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise DropRejectedError("source file was modified")
    checked = _probe(str(out))
    if checked.get("width") != 1920 or checked.get("height") != 1080 or checked.get("r_frame_rate") != "30/1":
        raise DropRejectedError("conformed clip is not 1920x1080 CFR 30")
    _remember(ledger, digest, scene_id)
    return DropReceipt(scene_id, out.as_posix(), digest, 1920, 1080, "30/1", float(checked["duration"]))


def _reject_incomplete(path: Path) -> None:
    if path.suffix in {".crdownload", ".tmp"} or not path.is_file() or path.stat().st_size == 0:
        raise DropRejectedError("Download incomplete — wait for browser to finish saving .mp4")
    head = path.read_bytes()[:16]
    if b"ftyp" not in head and not head.startswith(b"\x1a\x45\xdf\xa3"):
        raise DropRejectedError("unrecognized container")


def _reject_duplicate(ledger: Path, digest: str, scene_id: str) -> None:
    known = json.loads(ledger.read_text(encoding="utf8")) if ledger.is_file() else {}
    owner = known.get(digest)
    if owner and owner != scene_id:
        raise DuplicateClipDropError(f"{digest} is already on {owner}")


def _remember(ledger: Path, digest: str, scene_id: str) -> None:
    known = json.loads(ledger.read_text(encoding="utf8")) if ledger.is_file() else {}
    known[digest] = scene_id
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps(known, indent=2) + "\n", encoding="utf8")


def _probe(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,r_frame_rate,nb_frames,codec_type", "-of", "json", path],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise DropRejectedError("corrupt media")
    payload = json.loads(result.stdout)
    video = next(stream for stream in payload["streams"] if stream.get("codec_type", "video") == "video")
    video["duration"] = payload["format"]["duration"]
    return video
