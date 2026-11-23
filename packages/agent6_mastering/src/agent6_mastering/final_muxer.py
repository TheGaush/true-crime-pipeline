"""Mux the silent master and the loudness master, with escaped chapter titles."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def mux(video: str, audio: str, chapters: list[dict], out_path: str) -> dict:
    root = Path(out_path).parent
    root.mkdir(parents=True, exist_ok=True)
    meta = root / "chapters.ffmeta"
    text = root / "chapters.txt"
    meta.write_text(_metadata(chapters), encoding="utf8")
    text.write_text("\n".join(f"{_stamp(item['start_ms'])} {item['title']}" for item in chapters) + "\n", encoding="utf8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video, "-i", audio, "-i", str(meta),
            "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "2",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest",
            out_path,
        ],
        check=True, capture_output=True,
    )
    return _probe(out_path)


def _metadata(chapters: list[dict]) -> str:
    lines = [";FFMETADATA1"]
    for item in chapters:
        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={int(item['start_ms'])}",
                f"END={int(item['end_ms'])}",
                f"title={_escape(item['title'])}",
            ]
        )
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    out = []
    for char in value:
        if char in "=;#\\\n":
            out.append("\\")
        out.append(" " if char == "\n" else char)
    return "".join(out)


def _stamp(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _probe(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,r_frame_rate,sample_rate,color_space:format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in payload["streams"] if stream["codec_type"] == "audio")
    return {
        "r_frame_rate": video["r_frame_rate"],
        "color_space": video.get("color_space"),
        "sample_rate": audio["sample_rate"],
        "duration": float(payload["format"]["duration"]),
    }
