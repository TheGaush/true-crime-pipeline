import socket
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "packages" / "integration_bridge" / "src"
sys.path.insert(0, str(SRC))
from integration_bridge.mvp_slice import MOTIFS, run_slice


def test_ninety_second_slice_stays_offline(tmp_path: Path):
    real = socket.socket.connect

    def blocked(self, address):
        host = address[0] if isinstance(address, tuple) else ""
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise AssertionError(f"outbound socket {address}")
        return real(self, address)

    socket.socket.connect = blocked
    root = Path(__file__).resolve().parents[2]
    for name in MOTIFS:
        assert name in (root / "packages/render_catalog/src/motifs" / f"{name}.tsx").read_text(encoding="utf8")
    result = run_slice(str(tmp_path / "pipeline.db"), str(tmp_path / "final_1080p30.mp4"))
    assert result["released_without_gates"] is False
    assert result["state"] == "READY_TO_UPLOAD"
    assert result["transport"]["spend_usd"] == 0.0
    assert result["master"]["nb_frames"] == 2700
    assert abs(result["master"]["integrated_lufs"] - (-14.0)) <= 1.0
    sample = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", "20", "-i", result["master"]["path"], "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        check=True,
        capture_output=True,
    )
    colors = {sample.stdout[index : index + 3] for index in range(0, len(sample.stdout), 900)}
    assert len(colors) > 8
