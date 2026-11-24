"""Script beat chunker for segmented Voice-First TTS (voice-segmented-chunker@1).

Partitions approved narration into ordered ``NARRATION`` chunks (150–450 words,
sentence boundaries only), inserts ``TWIST_PAD`` markers after plot-twist beats,
and preserves ``FOIA_AUDIO_SLOT`` intervals. Narration never crosses a FOIA slot.
Pure stdlib; no network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal, Sequence, TypeAlias

MIN_NARRATION_WORDS: Final[int] = 150
MAX_NARRATION_WORDS: Final[int] = 450
TWIST_PAD_MIN_MS: Final[int] = 450
TWIST_PAD_MAX_MS: Final[int] = 750
DEFAULT_TWIST_PAD_MS: Final[int] = 600

_SENTENCE_SPLIT_RE: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")

SegmentKind: TypeAlias = Literal["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT"]


@dataclass(frozen=True)
class NarrationBeat:
    text: str
    is_plot_twist: bool = False


@dataclass(frozen=True)
class FoiaAudioSlotBeat:
    foia_asset_id: str
    duration_ms: int


ScriptBeat: TypeAlias = NarrationBeat | FoiaAudioSlotBeat


@dataclass(frozen=True)
class PlanNarrationChunk:
    seq_index: int
    segment_kind: Literal["NARRATION"] = "NARRATION"
    text: str = ""
    word_count: int = 0


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


TtsPlanSegment: TypeAlias = PlanNarrationChunk | PlanTwistPad | PlanFoiaAudioSlot


@dataclass(frozen=True)
class TtsSegmentPlan:
    case_id: str
    segments: tuple[TtsPlanSegment, ...]


def count_words(text: str) -> int:
    """Count whitespace-delimited words."""
    stripped = text.strip()
    if not stripped:
        return 0
    return len(stripped.split())


def split_sentences(text: str) -> list[str]:
    """Split narration on sentence boundaries without breaking mid-sentence."""
    normalized = " ".join(text.split())
    if not normalized:
        return []
    parts = _SENTENCE_SPLIT_RE.split(normalized)
    return [part for part in parts if part]


def chunk_narration_text(
    text: str,
    *,
    min_words: int = MIN_NARRATION_WORDS,
    max_words: int = MAX_NARRATION_WORDS,
) -> list[str]:
    """Pack sentences into narration chunks respecting word caps."""
    if min_words < 1 or max_words < min_words:
        raise ValueError("invalid narration word bounds")
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

    chunks = [" ".join(group) for group in groups]

    if len(chunks) >= 2 and count_words(chunks[-1]) < min_words:
        combined = count_words(chunks[-2]) + count_words(chunks[-1])
        if combined <= max_words:
            chunks[-2] = f"{chunks[-2]} {chunks[-1]}"
            chunks.pop()

    return chunks


def build_tts_segment_plan(
    case_id: str,
    beats: Sequence[ScriptBeat],
    *,
    twist_pad_duration_ms: int = DEFAULT_TWIST_PAD_MS,
) -> TtsSegmentPlan:
    """Partition script beats into a ordered ``TtsSegmentPlan``."""
    if not case_id.strip():
        raise ValueError("case_id is required")
    if not TWIST_PAD_MIN_MS <= twist_pad_duration_ms <= TWIST_PAD_MAX_MS:
        raise ValueError("twist_pad_duration_ms must be 450-750")

    out: list[TtsPlanSegment] = []
    seq = 0

    def _next_index() -> int:
        nonlocal seq
        seq += 1
        return seq

    for beat in beats:
        if isinstance(beat, NarrationBeat):
            narration = beat.text.strip()
            if narration:
                for chunk_text in chunk_narration_text(narration):
                    out.append(
                        PlanNarrationChunk(
                            seq_index=_next_index(),
                            text=chunk_text,
                            word_count=count_words(chunk_text),
                        )
                    )
            if beat.is_plot_twist:
                out.append(
                    PlanTwistPad(seq_index=_next_index(), duration_ms=twist_pad_duration_ms)
                )
        elif isinstance(beat, FoiaAudioSlotBeat):
            if not beat.foia_asset_id.strip():
                raise ValueError("FOIA_AUDIO_SLOT requires foia_asset_id")
            if beat.duration_ms <= 0:
                raise ValueError("FOIA_AUDIO_SLOT duration_ms must be positive")
            out.append(
                PlanFoiaAudioSlot(
                    seq_index=_next_index(),
                    foia_asset_id=beat.foia_asset_id,
                    duration_ms=beat.duration_ms,
                )
            )
        else:
            raise TypeError(f"unsupported beat type: {type(beat)!r}")

    return TtsSegmentPlan(case_id=case_id, segments=tuple(out))


def narration_chunk_word_counts(plan: TtsSegmentPlan) -> list[int]:
    """Return word counts for each NARRATION segment in order."""
    return [
        segment.word_count
        for segment in plan.segments
        if segment.segment_kind == "NARRATION"
    ]