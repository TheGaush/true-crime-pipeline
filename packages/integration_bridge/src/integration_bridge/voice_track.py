"""Build a 90-second spoken track. Flite when FFmpeg has it, otherwise the bundled take."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from integration_bridge.narration import LINES, script_text

DURATION = 90.0
ASSET = Path(__file__).with_name("assets") / "narration.wav"


def render_narration(out_path: str) -> dict:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.with_suffix(".txt").write_text(script_text() + "\n", encoding="utf8")
    engine = "flite" if _try_flite(path) else "bundled"
    if engine == "bundled":
        if not ASSET.is_file():
            raise RuntimeError("ffmpeg has no flite voice and the bundled narration is missing")
        shutil.copyfile(ASSET, path)
    return {"engine": engine, "path": str(path), "lines": [line.text for line in LINES]}


def _try_flite(path: Path) -> bool:
    if not _flite_available():
        return False
    with tempfile.TemporaryDirectory(prefix="narration-") as raw:
        folder = Path(raw)
        command = ["ffmpeg", "-y", "-loglevel", "error"]
        filters: list[str] = []
        labels: list[str] = []
        for index, line in enumerate(LINES):
            text_file = folder / f"{index}.txt"
            text_file.write_text(line.text, encoding="utf8")
            command.extend(["-f", "lavfi", "-i", f"flite=textfile={text_file}:voice=kal"])
            delay_ms = int(round(line.start * 1000))
            label = f"a{index}"
            filters.append(f"[{index}]adelay={delay_ms}:all=1,apad=whole_dur={DURATION:.0f}[{label}]")
            labels.append(f"[{label}]")
        mix = (
            "".join(labels)
            + f"amix=inputs={len(LINES)}:duration=longest:dropout_transition=0:normalize=0,"
            + f"atrim=0:{DURATION:.0f},asetpts=N/SR/TB[a]"
        )
        command.extend(
            [
                "-filter_complex",
                ";".join(filters) + ";" + mix,
                "-map",
                "[a]",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(path),
            ]
        )
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return False
    return True


def _flite_available() -> bool:
    result = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return " flite " in result.stdout
