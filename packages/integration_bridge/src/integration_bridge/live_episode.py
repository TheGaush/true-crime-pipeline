"""Opt-in episode that calls DeepSeek and Gemini. The default runner never imports the network."""

from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from integration_bridge.mvp_slice import REPO, screen_narration

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SCENE_COUNT = 6
VOICE = "Kore"
VOICE_STYLE = "calm documentary narrator, measured pace, clear American English"
IMAGE_MODEL = "gemini-3.1-flash-lite-image"
TTS_MODEL = "gemini-3.8-flash-tts"
DISCLOSURE = "The pictures and the voice in this film are synthetic."


class LiveError(RuntimeError):
    pass


def load_env(directory: Path) -> None:
    """Fill empty variables from a local .env. Existing variables stay as they are."""
    file = directory / ".env"
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and not os.environ.get(name, "").strip():
            os.environ[name] = value


def run_live(out_dir: Path, topic: str, *, post=None, env_dir: Path | None = None) -> dict:
    """Write a 1080p illustrated episode. The caller uploads it in YouTube Studio."""
    if env_dir is not None:
        load_env(env_dir)
    else:
        load_env(Path.cwd())
        load_env(REPO)
    topic = " ".join(topic.split())
    if len(topic) < 8:
        raise LiveError("Pass a topic of at least a few words with --topic.")
    deepseek = _key("DEEPSEEK_API_KEY")
    gemini = _key("GEMINI_API_KEY")
    transport = post or http_post
    out_dir.mkdir(parents=True, exist_ok=True)
    print("Writing the script with DeepSeek.", flush=True)
    scenes = plan_scenes(transport, deepseek, topic)
    (out_dir / "script.json").write_text(json.dumps({"topic": topic, "scenes": scenes}, indent=2), encoding="utf8")
    clips: list[Path] = []
    for index, scene in enumerate(scenes, start=1):
        print(f"Scene {index} of {SCENE_COUNT}: picture and voice.", flush=True)
        image = out_dir / f"scene-{index}.png"
        voice = out_dir / f"scene-{index}.wav"
        image.write_bytes(illustrate(transport, gemini, scene["image_prompt"]))
        voice.write_bytes(narrate(transport, gemini, scene["narration"]))
        clip = out_dir / f"scene-{index}.mp4"
        render_scene(image, voice, clip, scene["heading"])
        clips.append(clip)
    master = out_dir / "master.mp4"
    print("Mixing the episode.", flush=True)
    concat_scenes(clips, master)
    return {
        "mode": "live",
        "title": scenes[0]["heading"],
        "topic": topic,
        "scenes": [scene["heading"] for scene in scenes],
        "calls": {"deepseek": 1, "gemini_image": SCENE_COUNT, "gemini_tts": SCENE_COUNT},
        "master": str(master),
        "upload": "Upload master.mp4 yourself in YouTube Studio and mark the film as altered or synthetic.",
    }


def plan_scenes(post, api_key: str, topic: str) -> list[dict]:
    payload = post(
        DEEPSEEK_URL,
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        {
            "model": "deepseek-flash",
            "thinking": {"type": "disabled"},
            "max_tokens": 1800,
            "messages": [
                {"role": "system", "content": _script_rules()},
                {"role": "user", "content": topic},
            ],
        },
        120,
    )
    content = _message_text(payload)
    try:
        parsed = json.loads(_json_object(content))
    except json.JSONDecodeError as exc:
        raise LiveError("DeepSeek did not return a script as JSON.") from exc
    scenes = parsed.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != SCENE_COUNT:
        raise LiveError(f"The script must contain exactly {SCENE_COUNT} scenes.")
    cleaned: list[dict] = []
    for index, scene in enumerate(scenes):
        narration = " ".join(str(scene.get("narration", "")).split())
        heading = _heading(str(scene.get("heading", "")), index)
        image_prompt = " ".join(str(scene.get("image_prompt", "")).split())
        if index == 0 and "synthetic" not in narration.lower():
            narration = f"{DISCLOSURE} {narration}"
        if len(narration.split()) < 8 or len(narration.split()) > 90:
            raise LiveError(f"Scene {index + 1} narration must be between 8 and 90 words.")
        screen_narration(narration)
        if len(image_prompt) < 12:
            raise LiveError(f"Scene {index + 1} is missing an image prompt.")
        cleaned.append(
            {
                "heading": heading,
                "narration": narration,
                "image_prompt": (
                    "Editorial infographic illustration, 16:9, clear shapes, no photorealistic face, "
                    "no gore, no logo, no brand name. "
                    + image_prompt[:500]
                ),
            }
        )
    return cleaned


def illustrate(post, api_key: str, prompt: str) -> bytes:
    payload = _gemini(
        post,
        api_key,
        {
            "model": IMAGE_MODEL,
            "input": prompt,
            "response_format": {
                "type": "image",
                "mime_type": "image/png",
                "aspect_ratio": "16:9",
                "image_size": "1K",
            },
        },
    )
    kind, mime, data = _first_media(payload, "image")
    if "png" not in mime and not data.startswith(b"\x89PNG") and "jpeg" not in mime and not data.startswith(b"\xff\xd8"):
        raise LiveError(f"Gemini returned {kind or mime or 'an empty body'} instead of a picture.")
    return data


def narrate(post, api_key: str, text: str) -> bytes:
    payload = _gemini(
        post,
        api_key,
        {
            "model": TTS_MODEL,
            "input": [
                {
                    "type": "user_input",
                    "content": [
                        {
                            "type": "text",
                            "text": text,
                            "annotations": [{"type": "speech_metadata", "style": VOICE_STYLE}],
                        }
                    ],
                }
            ],
            "response_format": {"type": "audio", "mime_type": "audio/wav"},
            "generation_config": {"speech_config": [{"voice": VOICE}]},
        },
    )
    _kind, mime, data = _first_media(payload, "audio")
    if data.startswith(b"RIFF"):
        return data
    if "l16" in mime or "pcm" in mime or not mime:
        return _pcm_wav(data, 24000)
    return data


def render_scene(image: Path, voice: Path, clip: Path, heading: str) -> None:
    duration = _duration(voice)
    if duration < 0.4:
        raise LiveError(f"{voice.name} is too short to be a scene.")
    video_filter = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
    font = _font()
    if font is not None:
        label = _filter_text(heading)
        disclosure = _filter_text("Illustrative reconstruction. Synthetic voice and pictures.")
        video_filter += (
            f",drawtext=fontfile={font}:text='{label}':fontsize=42:fontcolor=white:"
            "x=48:y=h-140:box=1:boxcolor=black@0.55:boxborderw=12"
            f",drawtext=fontfile={font}:text='{disclosure}':fontsize=24:fontcolor=white:"
            "x=48:y=h-78:box=1:boxcolor=black@0.55:boxborderw=10"
        )
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-framerate", "30", "-i", str(image),
        "-i", str(voice),
        "-t", f"{duration:.3f}",
        "-vf", video_filter,
        "-r", "30",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k",
        "-shortest",
        str(clip),
    ]
    _ffmpeg(command)


def concat_scenes(clips: list[Path], master: Path) -> None:
    listing = master.with_name("scenes.txt")
    lines = []
    for clip in clips:
        escaped = str(clip.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    listing.write_text("\n".join(lines) + "\n", encoding="utf8")
    joined = master.with_name("joined.mp4")
    _ffmpeg(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", str(joined),
        ]
    )
    _ffmpeg(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(joined),
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            str(master),
        ]
    )


def http_post(url: str, headers: dict, body: dict, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf8"),
        headers=headers,
        method="POST",
    )
    host = url.split("/")[2]
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=_ssl_context()) as response:
            return json.loads(response.read().decode("utf8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        raise LiveError(f"{host} returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LiveError(_reach_error(host, exc.reason)) from exc


def _ssl_context() -> ssl.SSLContext:
    """Use a real CA bundle. The python.org Mac installer ships without one."""
    cafile = _ca_file()
    if cafile is None:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=cafile)


def _ca_file() -> str | None:
    try:
        import certifi
    except ImportError:
        certifi = None
    else:
        bundle = certifi.where()
        if Path(bundle).is_file():
            return bundle
    env_file = os.environ.get("SSL_CERT_FILE", "").strip()
    candidates = [env_file, "/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _reach_error(host: str, reason: object) -> str:
    text = str(reason)
    if "CERTIFICATE_VERIFY_FAILED" in text:
        return (
            f"Python could not verify the certificate for {host}. "
            "The API key was not sent. On the Mac, run this once, then run the live command again:\n"
            "  python3 -m pip install certifi\n"
            "If Python came from python.org, this also works:\n"
            "  open \"/Applications/Python 3.12/Install Certificates.command\""
        )
    return f"Could not reach {host}: {reason}"


def _gemini(post, api_key: str, body: dict) -> dict:
    return post(
        GEMINI_URL,
        {"x-goog-api-key": api_key, "Content-Type": "application/json"},
        body,
        180,
    )


def _first_media(payload: dict, wanted: str) -> tuple[str, str, bytes]:
    if isinstance(payload.get("error"), dict):
        raise LiveError(str(payload["error"].get("message") or "Gemini refused the request."))
    blocks = []
    audio = payload.get("output_audio") or payload.get("outputAudio")
    if isinstance(audio, dict):
        blocks.append({"type": "audio", **audio})
    for step in payload.get("steps") or []:
        content = step.get("content") if isinstance(step, dict) else None
        if isinstance(content, dict):
            blocks.append(content)
        elif isinstance(content, list):
            blocks.extend(item for item in content if isinstance(item, dict))
    for candidate in payload.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        blocks.extend(part for part in parts if isinstance(part, dict))
    for block in blocks:
        inline = block.get("inlineData") or block.get("inline_data") or {}
        encoded = block.get("data") or inline.get("data")
        if not encoded or not isinstance(encoded, str):
            continue
        mime = str(block.get("mime_type") or block.get("mimeType") or inline.get("mimeType") or inline.get("mime_type") or "")
        kind = str(block.get("type") or "")
        if wanted == "image" and "audio" in kind:
            continue
        if wanted == "audio" and "image" in kind:
            continue
        try:
            data = base64.b64decode(encoded)
        except ValueError as exc:
            raise LiveError("Gemini returned media that was not base64.") from exc
        if data:
            return kind, mime.lower(), data
    raise LiveError(f"Gemini returned no {wanted}.")


def _message_text(payload: dict) -> str:
    if isinstance(payload.get("error"), dict):
        raise LiveError(str(payload["error"].get("message") or "DeepSeek refused the request."))
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LiveError("DeepSeek returned no script.") from exc
    if isinstance(content, list):
        content = " ".join(str(part.get("text", part)) if isinstance(part, dict) else str(part) for part in content)
    return str(content)


def _json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        stripped = stripped.rsplit("```", 1)[0]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise LiveError("DeepSeek did not return a script as JSON.")
    return stripped[start : end + 1]


def _script_rules() -> str:
    return (
        "Write a six-scene illustrated YouTube explainer. Return one JSON object and nothing else. "
        "The object has a scenes array of exactly 6 items. Each item has heading, narration, and image_prompt. "
        "heading is at most 32 characters. narration is 2 or 3 spoken sentences, 20 to 60 words, with no stage directions. "
        f"The first narration begins with this sentence: {DISCLOSURE} "
        "Do not accuse a real private person of a crime. Do not explain how to commit a crime. "
        "Do not mention a minor. image_prompt describes an editorial infographic with no photorealistic face, no gore, and no logo."
    )


def _heading(value: str, index: int) -> str:
    cleaned = "".join(character if character.isalnum() or character == " " else " " for character in value)
    cleaned = " ".join(cleaned.split())[:32]
    return cleaned or f"Scene {index + 1}"


def _filter_text(value: str) -> str:
    return value.replace("\\", " ").replace(":", " ").replace("'", "")


def _font() -> str | None:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _pcm_wav(pcm: bytes, rate: int) -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def _ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise LiveError(result.stderr[-500:] or "ffmpeg failed")


def _key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise LiveError(f"Add {name} to the .env file in the project folder, then run this command again.")
    return value
