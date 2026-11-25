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
from integration_bridge.blender_scene import choose_kit, find_blender
from integration_bridge.live_episode import (
    LiveError,
    _picture_file,
    _reach_error,
    _ssl_context,
    format_image_request,
    load_env,
    run_live,
    take_picture,
    _has_filter,
)

TOPIC = "How a public record becomes an illustrated explainer"


def test_env_file_does_not_replace_a_variable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "already")
    (tmp_path / ".env").write_text('DEEPSEEK_API_KEY="from-file"\nGEMINI_API_KEY=studio\n', encoding="utf8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    load_env(tmp_path)
    assert os.environ["DEEPSEEK_API_KEY"] == "already"
    assert os.environ["GEMINI_API_KEY"] == "studio"


def test_mac_certificate_error_names_the_fix():
    message = _reach_error("api.deepseek.com", Exception("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"))
    assert "python3 -m pip install certifi" in message
    assert "Install Certificates.command" in message
    assert _ssl_context() is not None


def test_live_refuses_before_any_call_when_a_key_is_missing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def post(*_args, **_kwargs):
        raise AssertionError("network")

    with pytest.raises(LiveError, match="DEEPSEEK_API_KEY"):
        run_live(tmp_path, TOPIC, post=post, env_dir=tmp_path)


def test_image_request_names_the_kind_of_picture_and_the_prompt():
    scene = _scenes()[0]
    brief = format_image_request(1, scene)
    assert "Kind of image needed" in brief
    assert "16:9" in brief
    assert "not a photo of a real person" in brief
    assert "Prompt to paste into your image tool" in brief
    assert "parchment desk" in brief
    assert scene["narration"] in brief


def test_picture_file_rejects_a_missing_path_and_accepts_a_quoted_png(tmp_path: Path):
    picture = tmp_path / "My still.png"
    picture.write_bytes(_png())
    with pytest.raises(LiveError, match="No file"):
        _picture_file(str(tmp_path / "missing.png"))
    found = _picture_file(f'"{picture}"')
    assert found == picture


def test_ffmpeg_filter_list_names_scale_and_ignores_an_unknown_filter():
    assert _has_filter("scale") is True
    assert _has_filter("not-a-real-filter") is False


def test_scene_renders_when_ffmpeg_has_no_drawtext(tmp_path: Path, monkeypatch, capsys):
    import integration_bridge.live_episode as live

    monkeypatch.setattr(live, "_has_filter", lambda _name: False)
    monkeypatch.setattr(live, "_drawtext_note_sent", False)
    image = tmp_path / "plate.png"
    image.write_bytes(_png())
    voice = tmp_path / "line.wav"
    voice.write_bytes(_wav())
    clip = tmp_path / "scene.mp4"
    live.render_scene(image, voice, clip, "Synthetic Media Warning")
    assert clip.is_file() and clip.stat().st_size > 1000
    assert "drawtext" not in live._scene_filter("Synthetic Media Warning")
    assert "without the drawtext filter" in capsys.readouterr().out


def test_caption_is_drawn_when_drawtext_is_available(monkeypatch):
    import integration_bridge.live_episode as live

    monkeypatch.setattr(live, "_has_filter", lambda _name: True)
    monkeypatch.setattr(live, "_font", lambda: "/Library/Fonts/Arial.ttf")
    text = live._scene_filter("Porch camera")
    assert "drawtext" in text
    assert "Porch camera" in text
    assert "Synthetic voice and pictures" in text


def test_choose_kit_follows_the_scene_heading():
    assert choose_kit({"heading": "Synthetic Media Warning", "image_prompt": "a porch camera and a case file"}) == "overview"
    assert choose_kit({"heading": "The Porch Camera", "image_prompt": "a timeline"}) == "porch"
    assert choose_kit({"heading": "The Redacted Statement", "image_prompt": "a page"}) == "document"
    assert choose_kit({"heading": "Combining Evidence", "image_prompt": "arrows"}) == "merge"
    assert choose_kit({"heading": "Building the Case File", "image_prompt": "tabs"}) == "desk"
    assert choose_kit({"heading": "Ethical Considerations", "image_prompt": "a shield"}) == "scale"


def test_find_blender_uses_the_BLENDER_variable(tmp_path: Path, monkeypatch):
    binary = tmp_path / "Blender"
    binary.write_text("binary", encoding="utf8")
    monkeypatch.setenv("BLENDER", str(binary))
    assert find_blender() == str(binary)


def test_live_episode_draws_a_moving_illustrated_scene(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    spoken = _wav()

    def post(url, headers, body, timeout):
        if "deepseek.com" in url:
            scenes = _scenes()
            scenes[0]["heading"] = "Synthetic Media Warning"
            scenes[1]["heading"] = "The Porch Camera"
            return {"choices": [{"message": {"content": json.dumps({"scenes": scenes})}}]}
        encoded = base64.b64encode(spoken).decode("ascii")
        return {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav", "data": encoded}]}]}

    def ask(_message: str) -> str:
        raise AssertionError("picture prompt")

    receipt = run_live(tmp_path, TOPIC, post=post, env_dir=tmp_path, ask_image=ask)
    frame = tmp_path / "frame.raw"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp_path / "scene-2-picture.mp4"), "-vf", "select=eq(n\\,12)", "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", str(frame)],
        check=True,
    )
    pixels = frame.read_bytes()
    assert max(pixels) - min(pixels) > 40
    assert receipt["renderer"] == "infographic"
    assert receipt["calls"]["infographic_scenes"] == 6
    assert receipt["calls"]["user_images"] == 0
    assert Path(receipt["master"]).is_file()


def test_enter_keeps_a_picture_already_saved(tmp_path: Path):
    saved = tmp_path / "scene-1.png"
    saved.write_bytes(_png())
    asked: list[str] = []

    def ask(message: str) -> str:
        asked.append(message)
        return ""

    kept = take_picture(tmp_path, 1, _scenes()[0], ask)
    assert kept == saved
    assert "Kind of image needed" in asked[0]
    assert "already saved as scene-1.png" in asked[0]


def test_live_episode_asks_for_each_picture_and_speaks_the_lines(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    picture = tmp_path / "provided.png"
    picture.write_bytes(_png())
    note = tmp_path / "notes.txt"
    note.write_text("not a picture", encoding="utf8")
    spoken = _wav()
    calls: list[str] = []
    asked: list[str] = []
    answers = iter([str(note), str(picture)] + [str(picture)] * 5)

    def post(url, headers, body, timeout):
        calls.append(body.get("model") or url)
        if "deepseek.com" in url:
            assert headers["Authorization"] == "Bearer deepseek"
            return {"choices": [{"message": {"content": json.dumps({"scenes": _scenes()})}}]}
        assert "tts" in body["model"]
        encoded = base64.b64encode(spoken).decode("ascii")
        return {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav", "data": encoded}]}]}

    def ask(message: str) -> str:
        asked.append(message)
        return next(answers)

    receipt = run_live(tmp_path, TOPIC, post=post, env_dir=tmp_path, ask_image=ask, blender_bin="")
    assert calls[0] == "deepseek-flash"
    assert calls.count("gemini-3.8-flash-tts") == 6
    assert "gemini-3.1-flash-lite-image" not in calls
    assert len(asked) == 7
    assert "Kind of image needed" in asked[0]
    assert "Prompt to paste into your image tool" in asked[0]
    assert "parchment desk" in (tmp_path / "image-briefs.txt").read_text(encoding="utf8")
    assert receipt["calls"]["user_images"] == 6
    assert receipt["calls"]["gemini_image"] == 0
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
