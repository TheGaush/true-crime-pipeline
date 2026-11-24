"""Segmented voice timeline builder (Task 065).

Assembles ordered NARRATION, TWIST_PAD room-tone pads, and silent-track FOIA
audio slots into a contiguous master timeline.
"""

from __future__ import annotations

import math
import random
import sqlite3
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence


SegmentKind = Literal["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT"]

TWIST_PAD_MS_MIN = 450
TWIST_PAD_MS_MAX = 750
L_CUT_MS_MIN = 600
L_CUT_MS_MAX = 1000
ROOM_TONE_TARGET_DBFS = -65.0
ROOM_TONE_RMS_DBFS_MIN = -72.0
ROOM_TONE_RMS_DBFS_MAX = -58.0
DEFAULT_SAMPLE_RATE = 48_000


class StitcherError(ValueError):
    """Invalid stitch inputs or timeline assembly failure."""


@dataclass(frozen=True)
class NarrationBeat:
    segment_id: str
    audio_path: str
    duration_ms: int
    narration_version_sha256: str
    plot_twist: bool = False


@dataclass(frozen=True)
class FoiaBeat:
    segment_id: str
    foia_asset_id: str
    clip_duration_ms: int
    l_cut_ms: int = 800


TimelineBeat = NarrationBeat | FoiaBeat


@dataclass(frozen=True)
class BuiltSegment:
    segment_id: str
    episode_id: str
    seq_index: int
    segment_kind: SegmentKind
    start_ms: int
    end_ms: int
    audio_path: str | None = None
    foia_asset_id: str | None = None
    narration_version_sha256: str | None = None
    twist_pad_wav_path: str | None = None


@dataclass(frozen=True)
class StitchResult:
    episode_id: str
    total_master_ms: int
    segments: tuple[BuiltSegment, ...]


def _validate_ms_range(value: int, low: int, high: int, label: str) -> None:
    if not low <= value <= high:
        raise StitcherError(f"{label} must be {low}–{high} ms, got {value}")


def rms_dbfs(samples: Sequence[float]) -> float:
    """Full-scale RMS in dBFS for samples nominally in [-1, 1]."""
    if not samples:
        return float("-inf")
    mean_sq = sum(s * s for s in samples) / len(samples)
    rms = math.sqrt(mean_sq)
    if rms <= 0.0:
        return float("-inf")
    return 20.0 * math.log10(rms)


def _pink_noise_samples(count: int, rng: random.Random) -> list[float]:
    """Lightweight pink-ish noise (Paul Kellet economy filter), mono."""
    b0 = b1 = b2 = 0.0
    out: list[float] = []
    for _ in range(count):
        white = rng.uniform(-1.0, 1.0)
        b0 = 0.99886 * b0 + white * 0.0555179
        b1 = 0.99332 * b1 + white * 0.0750759
        b2 = 0.96900 * b2 + white * 0.1538520
        pink = (b0 + b1 + b2 + white * 0.3104856) / 4.0
        out.append(pink)
    return out


def write_room_tone_wav(
    path: str | Path,
    duration_ms: int,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    target_dbfs: float = ROOM_TONE_TARGET_DBFS,
    seed: int | None = None,
) -> float:
    """Write stereo 16-bit PCM room tone; return measured RMS dBFS."""
    _validate_ms_range(duration_ms, TWIST_PAD_MS_MIN, TWIST_PAD_MS_MAX, "TWIST_PAD duration")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    frame_count = sample_rate * duration_ms // 1000
    mono = _pink_noise_samples(frame_count, rng)
    target_rms = 10 ** (target_dbfs / 20.0)
    rms_before = math.sqrt(sum(s * s for s in mono) / len(mono))
    scale = target_rms / rms_before if rms_before > 0 else 0.0
    mono = [max(-1.0, min(1.0, s * scale)) for s in mono]
    if all(abs(s) < 1e-12 for s in mono):
        raise StitcherError("room tone generation produced all-zero samples")

    stereo: list[float] = []
    for sample in mono:
        stereo.extend((sample, sample))

    measured = rms_dbfs(mono)
    if not ROOM_TONE_RMS_DBFS_MIN <= measured <= ROOM_TONE_RMS_DBFS_MAX:
        raise StitcherError(
            f"room tone RMS {measured:.2f} dBFS outside "
            f"[{ROOM_TONE_RMS_DBFS_MIN}, {ROOM_TONE_RMS_DBFS_MAX}]"
        )

    pcm = b"".join(struct.pack("<h", int(round(s * 32767.0))) for s in stereo)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return measured


def read_wav_mono_float(path: str | Path) -> tuple[list[float], int]:
    """Read a WAV file into normalized mono floats (stereo averaged)."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise StitcherError(f"unsupported sample width {width} in {path}")
    count = len(raw) // 2
    ints = struct.unpack(f"<{count}h", raw)
    if channels == 1:
        samples = [v / 32768.0 for v in ints]
    else:
        samples = []
        for i in range(0, len(ints), channels):
            frame = ints[i : i + channels]
            samples.append(sum(v / 32768.0 for v in frame) / len(frame))
    return samples, rate


def stitch_timeline(
    episode_id: str,
    beats: Sequence[TimelineBeat],
    *,
    twist_pad_ms: int = 600,
    output_dir: str | Path | None = None,
    twist_pad_seed: int | None = None,
    connection: sqlite3.Connection | None = None,
) -> StitchResult:
    """Build contiguous voice segments; persist when ``connection`` is given."""
    _validate_ms_range(twist_pad_ms, TWIST_PAD_MS_MIN, TWIST_PAD_MS_MAX, "twist_pad_ms")
    if not beats:
        raise StitcherError("at least one timeline beat is required")

    out_root = Path(output_dir) if output_dir is not None else None
    if out_root is not None:
        out_root.mkdir(parents=True, exist_ok=True)

    cursor = 0
    built: list[BuiltSegment] = []
    seq = 0
    twist_index = 0

    def append_segment(
        segment_id: str,
        kind: SegmentKind,
        start_ms: int,
        end_ms: int,
        *,
        audio_path: str | None = None,
        foia_asset_id: str | None = None,
        narration_sha: str | None = None,
        twist_wav: str | None = None,
    ) -> None:
        nonlocal seq
        seq += 1
        built.append(
            BuiltSegment(
                segment_id=segment_id,
                episode_id=episode_id,
                seq_index=seq,
                segment_kind=kind,
                start_ms=start_ms,
                end_ms=end_ms,
                audio_path=audio_path,
                foia_asset_id=foia_asset_id,
                narration_version_sha256=narration_sha,
                twist_pad_wav_path=twist_wav,
            )
        )

    for beat in beats:
        if isinstance(beat, NarrationBeat):
            if beat.duration_ms <= 0:
                raise StitcherError(f"narration {beat.segment_id} duration must be positive")
            start = cursor
            end = cursor + beat.duration_ms
            append_segment(
                beat.segment_id,
                "NARRATION",
                start,
                end,
                audio_path=beat.audio_path,
                narration_sha=beat.narration_version_sha256,
            )
            cursor = end
            if beat.plot_twist:
                twist_start = cursor
                twist_end = cursor + twist_pad_ms
                twist_id = f"{beat.segment_id}_twist"
                twist_wav: str | None = None
                if out_root is not None:
                    twist_path = out_root / f"twist_pad_{twist_index:03d}.wav"
                    seed = None if twist_pad_seed is None else twist_pad_seed + twist_index
                    write_room_tone_wav(twist_path, twist_pad_ms, seed=seed)
                    twist_wav = str(twist_path)
                    twist_index += 1
                append_segment(twist_id, "TWIST_PAD", twist_start, twist_end, twist_wav=twist_wav)
                cursor = twist_end
        elif isinstance(beat, FoiaBeat):
            _validate_ms_range(beat.l_cut_ms, L_CUT_MS_MIN, L_CUT_MS_MAX, "l_cut_ms")
            if beat.clip_duration_ms <= 0:
                raise StitcherError(f"FOIA clip {beat.foia_asset_id} duration must be positive")
            slot_ms = beat.clip_duration_ms + beat.l_cut_ms
            start = cursor
            end = cursor + slot_ms
            append_segment(
                beat.segment_id,
                "FOIA_AUDIO_SLOT",
                start,
                end,
                foia_asset_id=beat.foia_asset_id,
            )
            cursor = end
        else:
            raise StitcherError(f"unsupported beat type {type(beat)!r}")

    total_master_ms = cursor
    result = StitchResult(episode_id=episode_id, total_master_ms=total_master_ms, segments=tuple(built))
    if connection is not None:
        persist_timeline(connection, result)
    return result


def persist_timeline(connection: sqlite3.Connection, result: StitchResult) -> None:
    """Insert voice_segments rows and update episodes.total_master_ms."""
    for segment in result.segments:
        connection.execute(
            """
            INSERT INTO voice_segments (
              segment_id, episode_id, seq_index, segment_kind,
              start_ms, end_ms, audio_path, foia_asset_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                segment.segment_id,
                segment.episode_id,
                segment.seq_index,
                segment.segment_kind,
                segment.start_ms,
                segment.end_ms,
                segment.audio_path,
                segment.foia_asset_id,
            ),
        )
    connection.execute(
        "UPDATE episodes SET total_master_ms = ? WHERE episode_id = ?",
        (result.total_master_ms, result.episode_id),
    )
    connection.commit()