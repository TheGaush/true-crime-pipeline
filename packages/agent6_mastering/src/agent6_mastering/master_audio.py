"""Mix stems through a script file, then lock the master at -14 LUFS."""

from __future__ import annotations

import subprocess
from pathlib import Path

BUS = 32


def build_script(cue_count: int, duration_sec: float = 2.0) -> str:
    if cue_count < 1:
        cue_count = 1
    labels = []
    lines = [f"sine=frequency=220:sample_rate=48000,atrim=0:{duration_sec:.3f},asetpts=PTS-STARTPTS[narr]"]
    for index in range(cue_count):
        delay = int(index * 10)
        label = f"s{index}"
        lines.append(
            f"sine=frequency=880:sample_rate=48000,atrim=0:0.020,adelay={delay}|{delay},apad=whole_dur={duration_sec:.3f}[{label}]"
        )
        labels.append(f"[{label}]")
    buses = []
    for offset in range(0, len(labels), BUS):
        chunk = labels[offset : offset + BUS]
        name = f"submix_{offset // BUS}"
        lines.append("".join(chunk) + f"amix=inputs={len(chunk)}:normalize=0[{name}]")
        buses.append(f"[{name}]")
    lines.append("[narr]" + "".join(buses) + f"amix=inputs={1 + len(buses)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[out]")
    return ";\n".join(lines)


def master(out_path: str, cue_count: int = 8, duration_sec: float = 2.0) -> dict:
    root = Path(out_path).parent
    root.mkdir(parents=True, exist_ok=True)
    script = root / "audio_graph.ffscript"
    script.write_text(build_script(cue_count, duration_sec) + "\n", encoding="utf8")
    command = [
        "ffmpeg", "-y", "-filter_complex_script", str(script), "-map", "[out]",
        "-ar", "48000", "-c:a", "pcm_s16le", out_path,
    ]
    if "-filter_complex" in command:
        raise RuntimeError("the graph must not be passed on argv")
    subprocess.run(command, check=True, capture_output=True)
    return {"path": out_path, "script": str(script), "integrated_lufs": measure(out_path), "cue_count": cue_count}


def measure(path: str) -> float:
    result = subprocess.run(["ffmpeg", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, check=False)
    found = None
    for line in result.stderr.splitlines():
        if "I:" in line and "LUFS" in line:
            found = float(line.split("I:", 1)[1].split("LUFS", 1)[0].strip())
    if found is None:
        raise RuntimeError("no integrated loudness")
    return found
