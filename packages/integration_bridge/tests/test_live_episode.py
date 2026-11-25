import base64
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from integration_bridge.live_episode import LiveError, load_env, run_live

TOPIC = "How a public record becomes an illustrated explainer"


def test_env_file_does_not_replace_a_variable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "already")
    (tmp_path / ".env").write_text('DEEPSEEK_API_KEY="from-file"\nGEMINI_API_KEY=studio\n', encoding="utf8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    load_env(tmp_path)
    assert os.environ["DEEPSEEK_API_KEY"] == "already"
    assert os.environ["GEMINI_API_KEY"] == "studio"


def test_live_refuses_before_any_call_when_a_key_is_missing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def post(*_args, **_kwargs):
        raise AssertionError("network")

    with pytest.raises(LiveError, match="DEEPSEEK_API_KEY"):
        run_live(tmp_path, TOPIC, post=post, env_dir=tmp_path)


def test_live_episode_builds_a_picture_and_a_voice(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    picture = _png()
    spoken = _wav()
    calls: list[str] = []

    def post(url, headers, body, timeout):
        calls.append(body.get("model") or url)
        if "deepseek.com" in url:
            assert headers["Authorization"] == "Bearer deepseek"
            return {"choices": [{"message": {"content": json.dumps({"scenes": _scenes()})}}]}
        encoded = base64.b64encode(spoken if "tts" in body["model"] else picture).decode("ascii")
        kind = "audio" if "tts" in body["model"] else "image"
        mime = "audio/wav" if kind == "audio" else "image/png"
        return {"steps": [{"type": "model_output", "content": [{"type": kind, "mime_type": mime, "data": encoded}]}]}

    receipt = run_live(tmp_path, TOPIC, post=post, env_dir=tmp_path)
    assert calls[0] == "deepseek-flash"
    assert calls.count("gemini-3.8-flash-tts") == 6
    assert calls.count("gemini-3.1-flash-lite-image") == 6
    master = Path(receipt["master"])
    assert master.is_file()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(master)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(probe.stdout.strip()) > 2
    assert "YouTube Studio" in receipt["upload"]
    assert "synthetic" in (tmp_path / "script.json").read_text(encoding="utf8").lower()


def _scenes() -> list[dict]:
    scenes = []
    for index in range(6):
        narration = "A public file can be shown as a drawing while the narration stays with the record."
        if index == 0:
            narration = "The pictures and the voice in this film are synthetic. " + narration
        scenes.append(
            {
                "heading": f"Part {index + 1}",
                "narration": narration,
                "image_prompt": "A parchment desk with a sealed folder and a lamp, no people.",
            }
        )
    return scenes


def _png() -> bytes:
    path = Path("/tmp/live-episode-plate.png")
    if not path.is_file():
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x1B3A4B:s=640x360", "-frames:v", "1", str(path)],
            check=True,
        )
    return path.read_bytes()


def _wav() -> bytes:
    path = Path("/tmp/live-episode-line.wav")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x10\x00" * 16000)
    return path.read_bytes()
