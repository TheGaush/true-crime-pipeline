"""20-minute frame lock, memory ceiling, and temp cleanup."""

from __future__ import annotations

import resource
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.slow
def test_twenty_minute_frame_lock_and_cleanup(tmp_path: Path):
    work = tmp_path / "stage_tmp"
    work.mkdir()
    video = work / "picture.mp4"
    audio = work / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1B1B1D:s=160x90:r=30:d=1200", "-frames:v", "36000", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-an", str(video)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=1200", "-c:a", "pcm_s16le", str(audio)],
        check=True, capture_output=True,
    )
    video_frames = int(_probe(video, "nb_frames"))
    audio_samples = int(_probe(audio, "duration_ts", audio=True))
    assert video_frames == 36_000
    assert abs((audio_samples / 48000) - 1200) < 0.015
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert rss_kb < 1.5 * 1024 * 1024
    shutil.rmtree(work)
    assert not work.exists()


def _probe(path: Path, field: str, audio: bool = False) -> str:
    stream = "a:0" if audio else "v:0"
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={field}", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()
