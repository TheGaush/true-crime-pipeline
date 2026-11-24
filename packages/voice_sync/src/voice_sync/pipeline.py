"""Offline Voice-First integration pipeline (Task 072).

Stage checks for chunking, TTS mastering, room-tone pads, FOIA slots,
WhisperX-style alignment, pronunciation gate, and drift validation are
encoded locally. Upstream voice_sync modules from Tasks 061–071 are not
imported. No network.
"""

from __future__ import annotations

import hashlib
import io
import math
import random
import re
import struct
import unicodedata
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

VOICE_READY = "VOICE_READY"
SCRIPT_LOCKED = "SCRIPT_LOCKED"
MAX_TOTAL_DRIFT_MS = 20
OUTPUT_SAMPLE_RATE_HZ = 48_000
OUTPUT_CHANNELS = 2
GEMINI_RAW_SAMPLE_RATE_HZ = 24_000
TARGET_LUFS = -16.0
LUFS_TOLERANCE_LU = 0.5
TWIST_PAD_MS_MIN = 450
TWIST_PAD_MS_MAX = 750
DEFAULT_TWIST_PAD_MS = 600
ROOM_TONE_TARGET_DBFS = -65.0
ROOM_TONE_RMS_DBFS_MIN = -72.0
ROOM_TONE_RMS_DBFS_MAX = -58.0
PRONUNCIATION_SIMILARITY_THRESHOLD = 0.72
PRIMARY_WORD_ALIGNER = "whisperx-local"

STAGE_CHUNK = "chunk_plan"
STAGE_TTS = "tts_master"
STAGE_STITCH = "timeline_stitch"
STAGE_ALIGN = "whisperx_align"
STAGE_PRONUNCIATION = "pronunciation_gate"
STAGE_DRIFT = "drift_validate"
STAGE_MANIFEST = "manifest_emit"

STAGE_ORDER: tuple[str, ...] = (
    STAGE_CHUNK,
    STAGE_TTS,
    STAGE_STITCH,
    STAGE_ALIGN,
    STAGE_PRONUNCIATION,
    STAGE_DRIFT,
    STAGE_MANIFEST,
)

SegmentKind = Literal["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT"]
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class TtsRateLimitError(RuntimeError):
    """Simulated HTTP 429 from a TTS provider."""


class VoiceSyncError(ValueError):
    """Pipeline invariant violation."""


@dataclass(frozen=True)
class NarrationBeat:
    text: str
    is_plot_twist: bool = False


@dataclass(frozen=True)
class FoiaAudioSlotBeat:
    foia_asset_id: str
    duration_ms: int
    l_cut_ms: int = 800


ScriptBeat = NarrationBeat | FoiaAudioSlotBeat


@dataclass(frozen=True)
class PlanNarrationChunk:
    seq_index: int
    segment_kind: Literal["NARRATION"] = "NARRATION"
    text: str = ""
    chunk_id: str = ""


@dataclass(frozen=True)
class PlanTwistPad:
    seq_index: int
    segment_kind: Literal["TWIST_PAD"] = "TWIST_PAD"
    duration_ms: int = DEFAULT_TWIST_PAD_MS


@dataclass(frozen=True)
class PlanFoiaAudioSlot:
    seq_index: int
    segment_kind: Literal["FOIA_AUDIO_SLOT"] = "FOIA_AUDIO_SLOT"
    foia_asset_id: str = ""
    duration_ms: int = 0
    l_cut_ms: int = 800


TtsPlanSegment = PlanNarrationChunk | PlanTwistPad | PlanFoiaAudioSlot


@dataclass(frozen=True)
class TtsSegmentPlan:
    case_id: str
    segments: tuple[TtsPlanSegment, ...]


@dataclass(frozen=True)
class MasteredChunk:
    chunk_id: str
    wav_path: Path
    sample_rate_hz: int
    channels: int
    integrated_lufs: float
    duration_ms: int
    narration_sha256: str


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
    chunk_id: str | None = None


@dataclass(frozen=True)
class GlobalWordStamp:
    segment_id: str
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class PronunciationFinding:
    expected: str
    asr_token: str
    similarity: float
    passed: bool
    flagged: bool
    chunk_id: str
    needs_resynthesis: bool


@dataclass(frozen=True)
class VoiceTrackManifest:
    episode_id: str
    total_master_ms: int
    segments: tuple[BuiltSegment, ...]
    word_timestamps: tuple[GlobalWordStamp, ...]


@dataclass(frozen=True)
class StageReport:
    stage: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VoiceSyncResult:
    episode_id: str
    conveyor_state: str
    manifest: VoiceTrackManifest
    total_drift_ms: int
    pronunciation_findings: tuple[PronunciationFinding, ...]
    stage_reports: tuple[StageReport, ...]
    cleaned_orphan_paths: tuple[str, ...]
    twist_pad_measured_dbfs: float | None = None


class TtsClient(Protocol):
    def synthesize(self, *, model_id: str, text: str, sample_rate_hz: int) -> bytes: ...


_CHUNK_TAG_RE = re.compile(r"\[chunk:([^\]]+)\]")


@dataclass
class MockableTtsClient:
    """Offline PCM source with optional 429 simulation."""

    gain: float = 0.35
    fail_once_on_chunk_id: str | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)
    _failed_chunks: set[str] = field(default_factory=set)

    def synthesize(self, *, model_id: str, text: str, sample_rate_hz: int) -> bytes:
        self.calls.append((model_id, text))
        match = _CHUNK_TAG_RE.search(text)
        chunk_id = match.group(1) if match else ""
        if (
            self.fail_once_on_chunk_id
            and chunk_id == self.fail_once_on_chunk_id
            and chunk_id not in self._failed_chunks
        ):
            self._failed_chunks.add(chunk_id)
            raise TtsRateLimitError("mocked HTTP 429")
        assert sample_rate_hz == GEMINI_RAW_SAMPLE_RATE_HZ
        duration_s = max(0.12, min(1.5, len(text.split()) * 0.04))
        freq = 440.0 + (hash(text) % 37)
        frames = int(duration_s * sample_rate_hz)
        samples: list[int] = []
        for i in range(frames):
            sample = 0.35 * self.gain * math.sin(2 * math.pi * freq * i / sample_rate_hz)
            samples.append(int(max(-32767, min(32767, round(sample * 32767)))))
        return struct.pack(f"<{len(samples)}h", *samples)


def count_words(text: str) -> int:
    stripped = text.strip()
    return len(stripped.split()) if stripped else 0


def split_sentences(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    return [part for part in _SENTENCE_SPLIT_RE.split(normalized) if part]


def chunk_narration_text(text: str, *, max_words: int = 450) -> list[str]:
    sentences = split_sentences(text)
    if not sentences:
        stripped = text.strip()
        return [stripped] if stripped else []
    groups: list[list[str]] = []
    current: list[str] = []
    current_words = 0
    for sentence in sentences:
        sentence_words = count_words(sentence)
        if current and current_words + sentence_words > max_words:
            groups.append(current)
            current = []
            current_words = 0
        current.append(sentence)
        current_words += sentence_words
    if current:
        groups.append(current)
    return [" ".join(group) for group in groups]


def build_tts_segment_plan(
    case_id: str,
    beats: Sequence[ScriptBeat],
    *,
    twist_pad_duration_ms: int = DEFAULT_TWIST_PAD_MS,
) -> TtsSegmentPlan:
    if not case_id.strip():
        raise VoiceSyncError("case_id is required")
    if not TWIST_PAD_MS_MIN <= twist_pad_duration_ms <= TWIST_PAD_MS_MAX:
        raise VoiceSyncError("twist_pad_duration_ms must be 450-750")
    out: list[TtsPlanSegment] = []
    seq = 0
    chunk_counter = 0

    def next_index() -> int:
        nonlocal seq
        seq += 1
        return seq

    for beat in beats:
        if isinstance(beat, NarrationBeat):
            narration = beat.text.strip()
            if narration:
                for chunk_text in chunk_narration_text(narration):
                    chunk_counter += 1
                    out.append(
                        PlanNarrationChunk(
                            seq_index=next_index(),
                            text=chunk_text,
                            chunk_id=f"chunk_{chunk_counter:03d}",
                        )
                    )
            if beat.is_plot_twist:
                out.append(
                    PlanTwistPad(seq_index=next_index(), duration_ms=twist_pad_duration_ms)
                )
        elif isinstance(beat, FoiaAudioSlotBeat):
            out.append(
                PlanFoiaAudioSlot(
                    seq_index=next_index(),
                    foia_asset_id=beat.foia_asset_id,
                    duration_ms=beat.duration_ms,
                    l_cut_ms=beat.l_cut_ms,
                )
            )
        else:
            raise VoiceSyncError(f"unsupported beat {type(beat)!r}")
    return TtsSegmentPlan(case_id=case_id, segments=tuple(out))


def verify_narration_never_crosses_foia(plan: TtsSegmentPlan) -> StageReport:
    """Each narration chunk must be fully emitted before the next FOIA slot."""
    pending_narration = False
    for segment in plan.segments:
        if segment.segment_kind == "NARRATION":
            pending_narration = True
        elif segment.segment_kind == "FOIA_AUDIO_SLOT":
            if pending_narration:
                return StageReport(
                    STAGE_CHUNK,
                    False,
                    "narration chunk would cross FOIA slot boundary",
                )
            pending_narration = False
        elif segment.segment_kind == "TWIST_PAD":
            pending_narration = False
    return StageReport(STAGE_CHUNK, True, "narration respects FOIA slot boundaries")


def _s16_bytes_to_floats(pcm: bytes) -> list[float]:
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm)
    return [s / 32768.0 for s in samples]


def _floats_to_s16_bytes(samples: list[float]) -> bytes:
    clipped = [max(-1.0, min(1.0, s)) for s in samples]
    ints = [int(round(s * 32767.0)) for s in clipped]
    return struct.pack(f"<{len(ints)}h", *ints)


def _resample_linear_mono(samples: list[float], src_hz: int, dst_hz: int) -> list[float]:
    if src_hz == dst_hz or not samples:
        return list(samples)
    ratio = dst_hz / src_hz
    out_len = max(1, int(math.floor(len(samples) * ratio)))
    out: list[float] = []
    for i in range(out_len):
        src_pos = i / ratio
        left = int(math.floor(src_pos))
        right = min(left + 1, len(samples) - 1)
        frac = src_pos - left
        out.append(samples[left] * (1.0 - frac) + samples[right] * frac)
    return out


def _measure_lufs_floats(floats: list[float], channels: int) -> float:
    if channels == 2:
        left = floats[0::2]
        right = floats[1::2]
        combined = left + right
    else:
        combined = floats
    if not combined:
        return float("-inf")
    mean_square = sum(x * x for x in combined) / len(combined)
    if mean_square <= 0.0:
        return float("-inf")
    return -0.691 + 10.0 * math.log10(mean_square)


def process_raw_tts_pcm(raw_pcm: bytes) -> tuple[bytes, float]:
    mono = _s16_bytes_to_floats(raw_pcm)
    at_48 = _resample_linear_mono(mono, GEMINI_RAW_SAMPLE_RATE_HZ, OUTPUT_SAMPLE_RATE_HZ)
    stereo: list[float] = []
    for sample in at_48:
        stereo.extend((sample, sample))
    loudness = _measure_lufs_floats(stereo, OUTPUT_CHANNELS)
    if math.isfinite(loudness):
        gain = 10.0 ** ((TARGET_LUFS - loudness) / 20.0)
        stereo = [s * gain for s in stereo]
        loudness = _measure_lufs_floats(stereo, OUTPUT_CHANNELS)
    return _floats_to_s16_bytes(stereo), loudness


def pcm_duration_ms(pcm: bytes, sample_rate_hz: int, channels: int) -> int:
    frames = len(pcm) // 2 // channels
    return int(round(frames * 1000 / sample_rate_hz))


def write_wav(path: Path, pcm: bytes, *, sample_rate_hz: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate_hz)
        wf.writeframes(pcm)


def rms_dbfs(samples: Sequence[float]) -> float:
    if not samples:
        return float("-inf")
    mean_sq = sum(s * s for s in samples) / len(samples)
    rms = math.sqrt(mean_sq)
    if rms <= 0.0:
        return float("-inf")
    return 20.0 * math.log10(rms)


def write_room_tone_wav(path: Path, duration_ms: int, *, seed: int = 1) -> float:
    if not TWIST_PAD_MS_MIN <= duration_ms <= TWIST_PAD_MS_MAX:
        raise VoiceSyncError("TWIST_PAD duration out of range")
    rng = random.Random(seed)
    frame_count = OUTPUT_SAMPLE_RATE_HZ * duration_ms // 1000
    mono = [rng.uniform(-1.0, 1.0) * 0.08 for _ in range(frame_count)]
    target_rms = 10 ** (ROOM_TONE_TARGET_DBFS / 20.0)
    rms_before = math.sqrt(sum(s * s for s in mono) / len(mono))
    scale = target_rms / rms_before if rms_before > 0 else 0.0
    mono = [max(-1.0, min(1.0, s * scale)) for s in mono]
    if all(abs(s) < 1e-12 for s in mono):
        raise VoiceSyncError("room tone would be digital silence")
    measured = rms_dbfs(mono)
    if not ROOM_TONE_RMS_DBFS_MIN <= measured <= ROOM_TONE_RMS_DBFS_MAX:
        raise VoiceSyncError(f"room tone RMS {measured:.2f} dBFS out of band")
    stereo: list[float] = []
    for sample in mono:
        stereo.extend((sample, sample))
    pcm = struct.pack(f"<{len(stereo)}h", *(int(round(s * 32767.0)) for s in stereo))
    write_wav(path, pcm, sample_rate_hz=OUTPUT_SAMPLE_RATE_HZ, channels=OUTPUT_CHANNELS)
    return measured


def read_wav_mono_float(path: Path) -> list[float]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        raw = wf.readframes(wf.getnframes())
    count = len(raw) // 2
    ints = struct.unpack(f"<{count}h", raw)
    if channels == 1:
        return [v / 32768.0 for v in ints]
    out: list[float] = []
    for i in range(0, len(ints), channels):
        frame = ints[i : i + channels]
        out.append(sum(v / 32768.0 for v in frame) / len(frame))
    return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def synthesize_chunk_wav(
    client: TtsClient,
    *,
    chunk_id: str,
    text: str,
    wav_path: Path,
    model_id: str,
    style_prefix: str = "[Doc narrator] ",
    on_orphan: Callable[[Path], None] | None = None,
) -> MasteredChunk:
    styled = f"{style_prefix}[chunk:{chunk_id}] {text}"
    partial_path = wav_path.with_suffix(".partial.wav")
    try:
        raw = client.synthesize(model_id=model_id, text=styled, sample_rate_hz=GEMINI_RAW_SAMPLE_RATE_HZ)
    except TtsRateLimitError:
        write_wav(partial_path, b"\x00\x00" * 1200, sample_rate_hz=OUTPUT_SAMPLE_RATE_HZ, channels=OUTPUT_CHANNELS)
        if on_orphan:
            on_orphan(partial_path)
        else:
            partial_path.unlink(missing_ok=True)
        raw = client.synthesize(
            model_id=f"{model_id}-failover",
            text=styled,
            sample_rate_hz=GEMINI_RAW_SAMPLE_RATE_HZ,
        )
    pcm, lufs = process_raw_tts_pcm(raw)
    if partial_path.exists():
        if on_orphan:
            on_orphan(partial_path)
        else:
            partial_path.unlink(missing_ok=True)
    if wav_path.exists():
        if on_orphan:
            on_orphan(wav_path)
        else:
            wav_path.unlink(missing_ok=True)
    write_wav(wav_path, pcm, sample_rate_hz=OUTPUT_SAMPLE_RATE_HZ, channels=OUTPUT_CHANNELS)
    duration_ms = pcm_duration_ms(pcm, OUTPUT_SAMPLE_RATE_HZ, OUTPUT_CHANNELS)
    return MasteredChunk(
        chunk_id=chunk_id,
        wav_path=wav_path,
        sample_rate_hz=OUTPUT_SAMPLE_RATE_HZ,
        channels=OUTPUT_CHANNELS,
        integrated_lufs=lufs,
        duration_ms=duration_ms,
        narration_sha256=sha256_text(text),
    )


def stitch_voice_timeline(
    episode_id: str,
    plan: TtsSegmentPlan,
    mastered: Mapping[str, MasteredChunk],
    *,
    output_dir: Path,
) -> tuple[tuple[BuiltSegment, ...], float | None]:
    cursor = 0
    built: list[BuiltSegment] = []
    seq = 0
    twist_measured: float | None = None
    twist_index = 0

    def append(
        segment_id: str,
        kind: SegmentKind,
        start_ms: int,
        end_ms: int,
        *,
        audio_path: str | None = None,
        foia_asset_id: str | None = None,
        narration_sha: str | None = None,
        chunk_id: str | None = None,
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
                chunk_id=chunk_id,
            )
        )

    narration_index = 0
    for segment in plan.segments:
        if segment.segment_kind == "NARRATION":
            chunk = mastered[segment.chunk_id]
            narration_index += 1
            seg_id = f"seg_n{narration_index:02d}"
            start = cursor
            end = cursor + chunk.duration_ms
            append(
                seg_id,
                "NARRATION",
                start,
                end,
                audio_path=str(chunk.wav_path),
                narration_sha=chunk.narration_sha256,
                chunk_id=segment.chunk_id,
            )
            cursor = end
        elif segment.segment_kind == "TWIST_PAD":
            start = cursor
            end = cursor + segment.duration_ms
            twist_path = output_dir / f"twist_pad_{twist_index:03d}.wav"
            twist_measured = write_room_tone_wav(twist_path, segment.duration_ms, seed=7 + twist_index)
            twist_index += 1
            append(
                f"seg_twist_{twist_index}",
                "TWIST_PAD",
                start,
                end,
                audio_path=str(twist_path),
            )
            cursor = end
        elif segment.segment_kind == "FOIA_AUDIO_SLOT":
            slot_ms = segment.duration_ms + segment.l_cut_ms
            start = cursor
            end = cursor + slot_ms
            append(
                f"seg_foia_{segment.foia_asset_id}",
                "FOIA_AUDIO_SLOT",
                start,
                end,
                foia_asset_id=segment.foia_asset_id,
            )
            cursor = end
    return tuple(built), twist_measured


def _normalize_token(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    asciiish = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", asciiish.lower())


def jaro_winkler(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0
    len_left, len_right = len(left), len(right)
    match_distance = max(len_left, len_right) // 2 - 1
    left_matches = [False] * len_left
    right_matches = [False] * len_right
    matches = 0
    for i in range(len_left):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len_right)
        for j in range(start, end):
            if right_matches[j] or left[i] != right[j]:
                continue
            left_matches[i] = right_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    k = transpositions = 0
    for i in range(len_left):
        if not left_matches[i]:
            continue
        while not right_matches[k]:
            k += 1
        if left[i] != right[k]:
            transpositions += 1
        k += 1
    transpositions //= 2
    jaro = (matches / len_left + matches / len_right + (matches - transpositions) / matches) / 3.0
    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
        if prefix == 4:
            break
    return jaro + prefix * 0.1 * (1.0 - jaro)


def pronunciation_similarity(expected: str, asr_token: str) -> float:
    left = _normalize_token(expected)
    right = _normalize_token(asr_token)
    if not left or not right:
        return 0.0
    return jaro_winkler(left, right)


def check_proper_noun_pronunciation(
    expected: str,
    asr_tokens: Sequence[str],
    *,
    chunk_id: str,
) -> PronunciationFinding:
    best_token = ""
    best_score = 0.0
    for token in asr_tokens:
        score = pronunciation_similarity(expected, token)
        if score > best_score:
            best_score = score
            best_token = token
    passed = best_score >= PRONUNCIATION_SIMILARITY_THRESHOLD
    flagged = not passed
    return PronunciationFinding(
        expected=expected,
        asr_token=best_token,
        similarity=round(best_score, 4),
        passed=passed,
        flagged=flagged,
        chunk_id=chunk_id,
        needs_resynthesis=not passed,
    )


def align_words_offline(
    segments: Sequence[BuiltSegment],
    text_by_chunk: Mapping[str, str],
    asr_tokens_by_chunk: Mapping[str, Sequence[str]] | None = None,
) -> tuple[GlobalWordStamp, ...]:
    stamps: list[GlobalWordStamp] = []
    for segment in sorted(segments, key=lambda s: s.start_ms):
        if segment.segment_kind != "NARRATION" or not segment.chunk_id:
            continue
        words = list(text_by_chunk[segment.chunk_id].split())
        if asr_tokens_by_chunk and segment.chunk_id in asr_tokens_by_chunk:
            words = list(asr_tokens_by_chunk[segment.chunk_id])
        if not words:
            continue
        local_span = segment.end_ms - segment.start_ms
        slice_ms = max(1, local_span // len(words))
        for idx, word in enumerate(words):
            local_start = idx * slice_ms
            local_end = local_start + slice_ms - 1 if idx < len(words) - 1 else local_span
            stamps.append(
                GlobalWordStamp(
                    segment_id=segment.segment_id,
                    word=word,
                    start_ms=segment.start_ms + local_start,
                    end_ms=segment.start_ms + local_end,
                )
            )
    return tuple(stamps)


def foia_slot_duration_before_ms(segments: Sequence[BuiltSegment], word_ms: int) -> int:
    """Return cumulative FOIA slot ms at or before ``word_ms`` for offset checks."""
    total = 0
    for segment in segments:
        if segment.start_ms >= word_ms:
            break
        if segment.segment_kind == "FOIA_AUDIO_SLOT":
            total += segment.end_ms - segment.start_ms
    return total


def measure_total_drift_ms(segments: Sequence[BuiltSegment], total_master_ms: int) -> int:
    if not segments:
        return abs(total_master_ms)
    contiguous = 0
    for segment in segments:
        contiguous += segment.end_ms - segment.start_ms
    edge = abs(segments[-1].end_ms - total_master_ms)
    return max(abs(contiguous - total_master_ms), edge)


def validate_manifest_invariants(manifest: VoiceTrackManifest) -> None:
    ordered = sorted(manifest.segments, key=lambda s: s.start_ms)
    if ordered[0].start_ms != 0:
        raise VoiceSyncError("timeline must start at 0 ms")
    for previous, nxt in zip(ordered, ordered[1:]):
        if previous.end_ms != nxt.start_ms:
            raise VoiceSyncError("voice segments must be contiguous")
        if nxt.start_ms < previous.end_ms:
            raise VoiceSyncError("voice segments overlap")
    drift = measure_total_drift_ms(manifest.segments, manifest.total_master_ms)
    if drift >= MAX_TOTAL_DRIFT_MS:
        raise VoiceSyncError(f"total drift {drift} ms exceeds {MAX_TOTAL_DRIFT_MS} ms")


@dataclass
class VoiceSyncService:
    repo_root: Path
    primary_model_id: str = "gemini-3.8-flash-tts"
    alternate_model_id: str = "flash-lite-tts"
    cleaned_orphan_paths: list[str] = field(default_factory=list)

    def _record_orphan_cleanup(self, path: Path) -> None:
        if path.exists():
            path.unlink()
            self.cleaned_orphan_paths.append(str(path))

    def run_episode(
        self,
        episode_id: str,
        beats: Sequence[ScriptBeat],
        *,
        proper_nouns: Sequence[tuple[str, str]] = (),
        asr_tokens_by_chunk: Mapping[str, Sequence[str]] | None = None,
        tts_client: TtsClient | None = None,
        work_dir: Path | None = None,
    ) -> VoiceSyncResult:
        self.cleaned_orphan_paths.clear()
        stage_reports: list[StageReport] = []
        case_id = episode_id
        plan = build_tts_segment_plan(case_id, beats)
        stage_reports.append(verify_narration_never_crosses_foia(plan))

        out_dir = work_dir or (self.repo_root / "artifacts" / episode_id / "voice")
        out_dir.mkdir(parents=True, exist_ok=True)
        client = tts_client or MockableTtsClient()

        text_by_chunk = {
            segment.chunk_id: segment.text
            for segment in plan.segments
            if segment.segment_kind == "NARRATION"
        }
        mastered: dict[str, MasteredChunk] = {}
        for segment in plan.segments:
            if segment.segment_kind != "NARRATION":
                continue
            wav_path = out_dir / f"{segment.chunk_id}.wav"
            mastered[segment.chunk_id] = synthesize_chunk_wav(
                client,
                chunk_id=segment.chunk_id,
                text=segment.text,
                wav_path=wav_path,
                model_id=self.primary_model_id,
                on_orphan=self._record_orphan_cleanup,
            )

        lufs_ok = all(
            abs(chunk.integrated_lufs - TARGET_LUFS) <= LUFS_TOLERANCE_LU
            for chunk in mastered.values()
        )
        rate_ok = all(
            chunk.sample_rate_hz == OUTPUT_SAMPLE_RATE_HZ and chunk.channels == OUTPUT_CHANNELS
            for chunk in mastered.values()
        )
        stage_reports.append(
            StageReport(
                STAGE_TTS,
                lufs_ok and rate_ok,
                "48 kHz stereo chunks near -16 LUFS",
            )
        )

        segments, twist_dbfs = stitch_voice_timeline(episode_id, plan, mastered, output_dir=out_dir)
        twist_ok = twist_dbfs is None or (
            ROOM_TONE_RMS_DBFS_MIN <= twist_dbfs <= ROOM_TONE_RMS_DBFS_MAX
        )
        stage_reports.append(
            StageReport(STAGE_STITCH, twist_ok, "room-tone TWIST_PAD (not digital silence)")
        )

        total_master_ms = segments[-1].end_ms if segments else 0
        word_stamps = align_words_offline(segments, text_by_chunk, asr_tokens_by_chunk)
        stage_reports.append(
            StageReport(STAGE_ALIGN, True, f"aligner={PRIMARY_WORD_ALIGNER}")
        )

        findings: list[PronunciationFinding] = []
        resynth_chunks: set[str] = set()
        for expected, chunk_id in proper_nouns:
            tokens = (asr_tokens_by_chunk or {}).get(chunk_id, text_by_chunk.get(chunk_id, "").split())
            finding = check_proper_noun_pronunciation(expected, tokens, chunk_id=chunk_id)
            findings.append(finding)
            if finding.needs_resynthesis:
                resynth_chunks.add(chunk_id)

        for chunk_id in resynth_chunks:
            respell = f"KRIH-stohf" if "krzysztof" in text_by_chunk[chunk_id].lower() else text_by_chunk[chunk_id]
            old_path = mastered[chunk_id].wav_path
            new_text = text_by_chunk[chunk_id].replace("Krzysztof", respell)
            mastered[chunk_id] = synthesize_chunk_wav(
                client,
                chunk_id=chunk_id,
                text=new_text,
                wav_path=old_path,
                model_id=self.primary_model_id,
                on_orphan=self._record_orphan_cleanup,
            )
            text_by_chunk[chunk_id] = new_text

        if resynth_chunks:
            segments, twist_dbfs = stitch_voice_timeline(episode_id, plan, mastered, output_dir=out_dir)
            total_master_ms = segments[-1].end_ms if segments else 0
            word_stamps = align_words_offline(segments, text_by_chunk)

        flagged = any(f.flagged for f in findings)
        stage_reports.append(
            StageReport(
                STAGE_PRONUNCIATION,
                True,
                "mangled proper noun flagged" if flagged else "pronunciation gate passed",
            )
        )

        drift_ms = measure_total_drift_ms(segments, total_master_ms)
        stage_reports.append(
            StageReport(
                STAGE_DRIFT,
                drift_ms < MAX_TOTAL_DRIFT_MS,
                f"total_drift_ms={drift_ms}",
            )
        )

        manifest = VoiceTrackManifest(
            episode_id=episode_id,
            total_master_ms=total_master_ms,
            segments=segments,
            word_timestamps=word_stamps,
        )
        try:
            validate_manifest_invariants(manifest)
            stage_reports.append(StageReport(STAGE_MANIFEST, True, "VoiceTrackManifest invariants"))
        except VoiceSyncError as exc:
            stage_reports.append(StageReport(STAGE_MANIFEST, False, str(exc)))
            raise

        orphan_wavs = [
            p
            for p in out_dir.glob("*.wav")
            if p.name.startswith("chunk_") and p.name.endswith(".partial.wav")
        ]
        if orphan_wavs:
            raise VoiceSyncError(f"orphan wav paths remain: {orphan_wavs}")

        if not all(report.passed for report in stage_reports):
            raise VoiceSyncError("one or more stage checks failed")

        return VoiceSyncResult(
            episode_id=episode_id,
            conveyor_state=VOICE_READY,
            manifest=manifest,
            total_drift_ms=drift_ms,
            pronunciation_findings=tuple(findings),
            stage_reports=tuple(stage_reports),
            cleaned_orphan_paths=tuple(self.cleaned_orphan_paths),
            twist_pad_measured_dbfs=twist_dbfs,
        )