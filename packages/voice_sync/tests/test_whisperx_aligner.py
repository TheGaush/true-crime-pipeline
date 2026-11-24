"""Offline tests for WhisperX global offset mapping (Task 066)."""

from __future__ import annotations

import pytest

from voice_sync.whisperx_aligner import (
    PRIMARY_WORD_ALIGNER,
    LocalWordOffset,
    VoiceSegmentRef,
    align_narration_segments,
)

FOIA_SLOT_MS = 25_000


def _stub_aligner(responses: dict[str, list[LocalWordOffset]]):
    def align(audio_path: str, narration_text: str) -> list[LocalWordOffset]:
        del narration_text
        return list(responses[audio_path])

    return align


def test_aligner_id_is_whisperx_local():
    segments = [
        VoiceSegmentRef(
            segment_id="seg_1",
            segment_kind="NARRATION",
            start_ms=0,
            end_ms=2000,
            audio_path="narr_a.wav",
        ),
    ]
    result = align_narration_segments(
        segments,
        {"seg_1": "hello"},
        _stub_aligner({"narr_a.wav": [LocalWordOffset("hello", 0, 400)]}),
    )
    assert result.aligner_id == PRIMARY_WORD_ALIGNER
    assert result.aligner_id == "whisperx-local"


def test_three_segments_one_foia_gap_global_offsets():
    """NARRATION, 25s FOIA slot, then NARRATION — segment-3 words shift by prior timeline."""
    narr_one_end = 4000
    foia_end = narr_one_end + FOIA_SLOT_MS
    narr_two_end = foia_end + 3000

    segments = [
        VoiceSegmentRef(
            segment_id="seg_narr_1",
            segment_kind="NARRATION",
            start_ms=0,
            end_ms=narr_one_end,
            audio_path="narr_1.wav",
        ),
        VoiceSegmentRef(
            segment_id="seg_foia",
            segment_kind="FOIA_AUDIO_SLOT",
            start_ms=narr_one_end,
            end_ms=foia_end,
        ),
        VoiceSegmentRef(
            segment_id="seg_narr_2",
            segment_kind="NARRATION",
            start_ms=foia_end,
            end_ms=narr_two_end,
            audio_path="narr_2.wav",
        ),
    ]

    aligner = _stub_aligner(
        {
            "narr_1.wav": [
                LocalWordOffset("According", 100, 500),
                LocalWordOffset("to", 520, 700),
            ],
            "narr_2.wav": [
                LocalWordOffset("records", 80, 420),
            ],
        }
    )

    result = align_narration_segments(
        segments,
        {
            "seg_narr_1": "According to the filing",
            "seg_narr_2": "records show",
        },
        aligner,
    )

    assert len(result.word_timestamps) == 3
    first, second, third = result.word_timestamps
    assert first.word == "According"
    assert first.start_ms == 100
    assert first.end_ms == 500
    assert second.start_ms == 520

    assert third.segment_id == "seg_narr_2"
    assert third.word == "records"
    assert third.start_ms == foia_end + 80
    assert third.end_ms == foia_end + 420
    assert third.start_ms == narr_one_end + FOIA_SLOT_MS + 80


def test_foia_slot_is_never_passed_to_aligner():
    calls: list[tuple[str, str]] = []

    def spy_align(audio_path: str, narration_text: str) -> list[LocalWordOffset]:
        calls.append((audio_path, narration_text))
        return [LocalWordOffset("only", 0, 200)]

    segments = [
        VoiceSegmentRef(
            segment_id="seg_a",
            segment_kind="NARRATION",
            start_ms=0,
            end_ms=1000,
            audio_path="a.wav",
        ),
        VoiceSegmentRef(
            segment_id="seg_foia",
            segment_kind="FOIA_AUDIO_SLOT",
            start_ms=1000,
            end_ms=1000 + FOIA_SLOT_MS,
        ),
    ]

    align_narration_segments(segments, {"seg_a": "only narration"}, spy_align)
    assert calls == [("a.wav", "only narration")]


def test_local_word_beyond_segment_duration_rejected():
    segments = [
        VoiceSegmentRef(
            segment_id="seg_1",
            segment_kind="NARRATION",
            start_ms=0,
            end_ms=500,
            audio_path="short.wav",
        ),
    ]
    with pytest.raises(ValueError, match="exceeds narration segment duration"):
        align_narration_segments(
            segments,
            {"seg_1": "overflow"},
            _stub_aligner({"short.wav": [LocalWordOffset("late", 0, 501)]}),
        )