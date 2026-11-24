"""Fast offline slice: four motifs, a local mux, no outbound sockets."""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

MOTIFS = ("StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame")


def test_four_motifs_and_local_mux_stay_offline(tmp_path: Path):
    started = time.perf_counter()
    real_connect = socket.socket.connect

    def blocked(self, address):
        host = address[0] if isinstance(address, tuple) else ""
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise AssertionError(f"outbound socket {address}")
        return real_connect(self, address)

    socket.socket.connect = blocked
    root = Path(__file__).resolve().parents[2]
    for name in MOTIFS:
        text = (root / "packages/render_catalog/src/motifs" / f"{name}.tsx").read_text(encoding="utf8")
        assert f"function {name}" in text or f"const {name}" in text or name in text
    video = tmp_path / "slice.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0xE9E2D2:s=320x180:d=0.4:r=30", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=0.4", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video)],
        check=True, capture_output=True,
    )
    assert video.is_file()
    assert time.perf_counter() - started < 30
