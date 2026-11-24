"""Local WhisperX forced-alignment wrapper with global master-timeline offsets (Task 066)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

PRIMARY_WORD_ALIGNER = "whisperx-local"

SegmentKind = Literal["NARRATION", "FOIA_AUDIO_SLOT", "TWIST_PAD"]

SegmentForcedAligner = Callable[[str, str], Sequence["LocalWordOffset"]]


@dataclass(frozen=True, slots=True)
class LocalWordOffset:
    """Word timing relative to the start of one narration audio clip (0 ms = segment audio t=0)."""

    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class VoiceSegmentRef:
    segment_id: str
    segment_kind: SegmentKind
    start_ms: int
    end_ms: int
    audio_path: str | None = None


@dataclass(frozen=True, slots=True)
class GlobalWordStamp:
    segment_id: str
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True, slots=True)
class WhisperXAlignResult:
    aligner_id: str
    word_timestamps: tuple[GlobalWordStamp, ...]


def _segment_duration_ms(segment: VoiceSegmentRef) -> int:
    if segment.end_ms <= segment.start_ms:
        raise ValueError(f"segment {segment.segment_id} has non-positive duration")
    return segment.end_ms - segment.start_ms


def _map_local_offsets(
    segment: VoiceSegmentRef,
    local_words: Sequence[LocalWordOffset],
) -> list[GlobalWordStamp]:
    duration = _segment_duration_ms(segment)
    global_stamps: list[GlobalWordStamp] = []
    for offset in local_words:
        if offset.end_ms <= offset.start_ms:
            raise ValueError(
                f"local word {offset.word!r} in {segment.segment_id} "
                "must have end_ms > start_ms"
            )
        if offset.end_ms > duration:
            raise ValueError(
                f"local word {offset.word!r} exceeds narration segment duration "
                f"({offset.end_ms} ms > {duration} ms)"
            )
        global_stamps.append(
            GlobalWordStamp(
                segment_id=segment.segment_id,
                word=offset.word,
                start_ms=segment.start_ms + offset.start_ms,
                end_ms=segment.start_ms + offset.end_ms,
            )
        )
    global_stamps.sort(key=lambda stamp: (stamp.start_ms, stamp.end_ms, stamp.word))
    for previous, nxt in zip(global_stamps, global_stamps[1:]):
        if nxt.start_ms < previous.end_ms:
            raise ValueError("mapped word timestamps must not overlap")
    return global_stamps


def align_narration_segments(
    segments: Sequence[VoiceSegmentRef],
    narration_text_by_segment: Mapping[str, str],
    aligner: SegmentForcedAligner,
    *,
    aligner_id: str = PRIMARY_WORD_ALIGNER,
) -> WhisperXAlignResult:
    """Run injected forced alignment per NARRATION segment and map to global master time."""
    if aligner_id != PRIMARY_WORD_ALIGNER:
        raise ValueError(f"aligner_id must be {PRIMARY_WORD_ALIGNER!r}")

    ordered = sorted(segments, key=lambda seg: seg.start_ms)
    all_words: list[GlobalWordStamp] = []

    for segment in ordered:
        if segment.segment_kind != "NARRATION":
            continue
        if not segment.audio_path:
            raise ValueError(f"NARRATION {segment.segment_id} requires audio_path")
        text = narration_text_by_segment.get(segment.segment_id, "")
        if not text.strip():
            raise ValueError(f"NARRATION {segment.segment_id} requires narration text")
        local = tuple(aligner(segment.audio_path, text))
        all_words.extend(_map_local_offsets(segment, local))

    all_words.sort(key=lambda stamp: (stamp.start_ms, stamp.end_ms, stamp.segment_id))
    return WhisperXAlignResult(
        aligner_id=aligner_id,
        word_timestamps=tuple(all_words),
    )