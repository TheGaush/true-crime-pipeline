"""VoiceTrackManifest serializer with per-chunk SHA-256 synthesis cache (Task 071)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from shared_contracts.models import (
    CuePoint,
    VoiceSegment,
    VoiceTrackManifest,
    WordTimestamp,
)

ENVELOPE_STEP_MS = 100
TWIST_PAD_MIN_MS = 450
TWIST_PAD_MAX_MS = 750

SegmentKind: TypeAlias = Literal["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT"]
NarrationSynthesizer = Callable[[str, str], "CachedNarrationChunk"]


def narration_text_sha256(text: str) -> str:
    """Stable SHA-256 hex digest for narration chunk text (UTF-8)."""
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _envelope_length(duration_ms: int) -> int:
    return max(1, (duration_ms + ENVELOPE_STEP_MS - 1) // ENVELOPE_STEP_MS)


def _silent_envelope(duration_ms: int) -> tuple[float, ...]:
    return tuple(0.0 for _ in range(_envelope_length(duration_ms)))


@dataclass(frozen=True, slots=True)
class LocalWordStamp:
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class LocalCuePoint:
    cue_id: str
    at_ms: int
    label: str


@dataclass(frozen=True, slots=True)
class CachedNarrationChunk:
    text_sha256: str
    duration_ms: int
    audio_path: str
    word_timestamps: tuple[LocalWordStamp, ...] = ()
    cue_points: tuple[LocalCuePoint, ...] = ()
    amplitude_envelope: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        for stamp in self.word_timestamps:
            if stamp.end_ms <= stamp.start_ms or stamp.end_ms > self.duration_ms:
                raise ValueError("word timestamps must sit inside chunk duration")
        for cue in self.cue_points:
            if cue.at_ms < 0 or cue.at_ms > self.duration_ms:
                raise ValueError("cue points must sit inside chunk duration")
        for sample in self.amplitude_envelope:
            if not 0.0 <= sample <= 1.0:
                raise ValueError("amplitude_envelope samples must be within 0..1")


@dataclass
class ChunkManifestCache:
    """In-memory store keyed by narration text SHA-256."""

    _by_sha: dict[str, CachedNarrationChunk] = field(default_factory=dict)

    def get(self, text_sha256: str) -> CachedNarrationChunk | None:
        return self._by_sha.get(text_sha256)

    def put(self, chunk: CachedNarrationChunk) -> None:
        self._by_sha[chunk.text_sha256] = chunk

    def invalidate(self, text_sha256: str) -> bool:
        return self._by_sha.pop(text_sha256, None) is not None

    def __len__(self) -> int:
        return len(self._by_sha)


@dataclass(frozen=True, slots=True)
class NarrationSegmentSpec:
    segment_id: str
    text: str
    segment_kind: Literal["NARRATION"] = "NARRATION"


@dataclass(frozen=True, slots=True)
class TwistPadSegmentSpec:
    segment_id: str
    duration_ms: int
    segment_kind: Literal["TWIST_PAD"] = "TWIST_PAD"


@dataclass(frozen=True, slots=True)
class FoiaSegmentSpec:
    segment_id: str
    foia_asset_id: str
    duration_ms: int
    segment_kind: Literal["FOIA_AUDIO_SLOT"] = "FOIA_AUDIO_SLOT"


ManifestSegmentSpec: TypeAlias = (
    NarrationSegmentSpec | TwistPadSegmentSpec | FoiaSegmentSpec
)


@dataclass(slots=True)
class ManifestBuildStats:
    """Observability for cache hits and synthesis work."""

    cache_hits: int = 0
    synthesized: int = 0
    invalidated_sha256: tuple[str, ...] = ()


def serialize_manifest_payload(manifest: VoiceTrackManifest) -> dict[str, Any]:
    """Deterministic JSON-ready dict for the frozen segmented manifest."""
    return json.loads(
        manifest.model_dump_json(
            exclude_none=False,
        )
    )


def serialize_manifest_json(manifest: VoiceTrackManifest, *, indent: int | None = 2) -> str:
    payload = serialize_manifest_payload(manifest)
    return json.dumps(payload, indent=indent, sort_keys=True)


def _resolve_narration(
    cache: ChunkManifestCache,
    spec: NarrationSegmentSpec,
    synthesize: NarrationSynthesizer,
    stats: ManifestBuildStats,
) -> CachedNarrationChunk:
    text_hash = narration_text_sha256(spec.text)
    cached = cache.get(text_hash)
    if cached is not None:
        stats.cache_hits += 1
        return cached
    chunk = synthesize(spec.segment_id, spec.text)
    if chunk.text_sha256 != text_hash:
        raise ValueError(
            "synthesizer text_sha256 must match narration_text_sha256(text)"
        )
    cache.put(chunk)
    stats.synthesized += 1
    return chunk


def _validate_twist_duration(duration_ms: int) -> None:
    if not TWIST_PAD_MIN_MS <= duration_ms <= TWIST_PAD_MAX_MS:
        raise ValueError("TWIST_PAD duration_ms must be 450-750")


def build_voice_track_manifest(
    episode_id: str,
    segments: Sequence[ManifestSegmentSpec],
    *,
    cache: ChunkManifestCache | None = None,
    synthesize: NarrationSynthesizer,
) -> tuple[VoiceTrackManifest, ManifestBuildStats]:
    """Assemble a validated ``VoiceTrackManifest`` with chunk-granular caching."""
    if not episode_id.strip():
        raise ValueError("episode_id is required")
    if not segments:
        raise ValueError("segments must not be empty")

    store = cache if cache is not None else ChunkManifestCache()
    stats = ManifestBuildStats()

    voice_segments: list[VoiceSegment] = []
    word_timestamps: list[WordTimestamp] = []
    cue_points: list[CuePoint] = []
    amplitude_envelope: list[float] = []
    cursor = 0

    for seq_index, spec in enumerate(segments, start=1):
        if isinstance(spec, NarrationSegmentSpec):
            if not spec.text.strip():
                raise ValueError(f"NARRATION {spec.segment_id} requires text")
            chunk = _resolve_narration(store, spec, synthesize, stats)
            start_ms = cursor
            end_ms = cursor + chunk.duration_ms
            voice_segments.append(
                VoiceSegment(
                    segment_id=spec.segment_id,
                    episode_id=episode_id,
                    seq_index=seq_index,
                    segment_kind="NARRATION",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    audio_path=chunk.audio_path,
                    narration_version_sha256=chunk.text_sha256,
                )
            )
            for stamp in chunk.word_timestamps:
                word_timestamps.append(
                    WordTimestamp(
                        segment_id=spec.segment_id,
                        word=stamp.word,
                        start_ms=start_ms + stamp.start_ms,
                        end_ms=start_ms + stamp.end_ms,
                    )
                )
            for cue in chunk.cue_points:
                cue_points.append(
                    CuePoint(
                        cue_id=cue.cue_id,
                        at_ms=start_ms + cue.at_ms,
                        label=cue.label,
                    )
                )
            amplitude_envelope.extend(chunk.amplitude_envelope or _silent_envelope(chunk.duration_ms))
            cursor = end_ms
        elif isinstance(spec, TwistPadSegmentSpec):
            _validate_twist_duration(spec.duration_ms)
            start_ms = cursor
            end_ms = cursor + spec.duration_ms
            voice_segments.append(
                VoiceSegment(
                    segment_id=spec.segment_id,
                    episode_id=episode_id,
                    seq_index=seq_index,
                    segment_kind="TWIST_PAD",
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
            amplitude_envelope.extend(_silent_envelope(spec.duration_ms))
            cursor = end_ms
        elif isinstance(spec, FoiaSegmentSpec):
            if not spec.foia_asset_id.strip():
                raise ValueError("FOIA_AUDIO_SLOT requires foia_asset_id")
            if spec.duration_ms <= 0:
                raise ValueError("FOIA_AUDIO_SLOT duration_ms must be positive")
            start_ms = cursor
            end_ms = cursor + spec.duration_ms
            voice_segments.append(
                VoiceSegment(
                    segment_id=spec.segment_id,
                    episode_id=episode_id,
                    seq_index=seq_index,
                    segment_kind="FOIA_AUDIO_SLOT",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    foia_asset_id=spec.foia_asset_id,
                )
            )
            amplitude_envelope.extend(_silent_envelope(spec.duration_ms))
            cursor = end_ms
        else:
            raise TypeError(f"unsupported segment spec: {type(spec)!r}")

    manifest = VoiceTrackManifest(
        episode_id=episode_id,
        total_master_ms=cursor,
        segments=voice_segments,
        word_timestamps=word_timestamps,
        cue_points=cue_points,
        amplitude_envelope=amplitude_envelope,
    )
    return manifest, stats


def replace_narration_chunk(
    episode_id: str,
    segments: Sequence[ManifestSegmentSpec],
    *,
    segment_id: str,
    new_text: str,
    cache: ChunkManifestCache,
    synthesize: NarrationSynthesizer,
) -> tuple[VoiceTrackManifest, ManifestBuildStats]:
    """Invalidate one edited narration chunk and rebuild global offsets."""
    if not new_text.strip():
        raise ValueError("new_text must be non-empty")

    updated: list[ManifestSegmentSpec] = []
    invalidated: list[str] = []
    found = False

    for spec in segments:
        if isinstance(spec, NarrationSegmentSpec) and spec.segment_id == segment_id:
            old_hash = narration_text_sha256(spec.text)
            cache.invalidate(old_hash)
            invalidated.append(old_hash)
            updated.append(
                NarrationSegmentSpec(segment_id=spec.segment_id, text=new_text)
            )
            found = True
        else:
            updated.append(spec)

    if not found:
        raise ValueError(f"unknown NARRATION segment_id: {segment_id}")

    manifest, stats = build_voice_track_manifest(
        episode_id,
        updated,
        cache=cache,
        synthesize=synthesize,
    )
    return manifest, ManifestBuildStats(
        cache_hits=stats.cache_hits,
        synthesized=stats.synthesized,
        invalidated_sha256=tuple(invalidated),
    )


def manifest_from_cached_chunks(
    episode_id: str,
    segments: Sequence[ManifestSegmentSpec],
    cache: ChunkManifestCache,
) -> VoiceTrackManifest:
    """Rebuild manifest using only cached narration entries (no synthesizer)."""

    def _forbid_synth(_segment_id: str, text: str) -> CachedNarrationChunk:
        raise KeyError(
            f"missing cached chunk for narration_text_sha256={narration_text_sha256(text)!r}"
        )

    manifest, _ = build_voice_track_manifest(
        episode_id,
        segments,
        cache=cache,
        synthesize=_forbid_synth,
    )
    return manifest