"""Segmented narration / FOIA / twist-pad chunker tests (offline, stdlib only)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from voice_sync.chunker import (
    DEFAULT_TWIST_PAD_MS,
    MAX_NARRATION_WORDS,
    MIN_NARRATION_WORDS,
    FoiaAudioSlotBeat,
    NarrationBeat,
    build_tts_segment_plan,
    chunk_narration_text,
    count_words,
    narration_chunk_word_counts,
    split_sentences,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "voice_sync" / "chunker.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _words(n: int, *, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def _sentence(words: int, punct: str = ".") -> str:
    return f"{_words(words)}{punct}"


def test_stdlib_only() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _BANNED_IMPORTS
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in _BANNED_IMPORTS


def test_split_sentences_preserves_boundaries() -> None:
    text = "First beat here. Second beat follows! Third ends?"
    assert split_sentences(text) == [
        "First beat here.",
        "Second beat follows!",
        "Third ends?",
    ]


def test_chunk_narration_never_splits_mid_sentence() -> None:
    body = " ".join(_sentence(200) for _ in range(4))
    chunks = chunk_narration_text(body)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.rstrip()[-1] in ".!?"
        wc = count_words(chunk)
        assert wc <= MAX_NARRATION_WORDS
    assert sum(count_words(c) for c in chunks) == count_words(body)


def test_long_narration_chunks_stay_in_word_band() -> None:
    sentences = [_sentence(40) for _ in range(30)]
    text = " ".join(sentences)
    counts = [count_words(c) for c in chunk_narration_text(text)]
    assert len(counts) >= 2
    for wc in counts[:-1]:
        assert wc >= MIN_NARRATION_WORDS
        assert wc <= MAX_NARRATION_WORDS
    assert counts[-1] <= MAX_NARRATION_WORDS


def test_twist_pad_and_foia_slot_emitted() -> None:
    plan = build_tts_segment_plan(
        "case_7",
        [
            NarrationBeat("According to records, the affidavit was filed.", is_plot_twist=True),
            FoiaAudioSlotBeat(foia_asset_id="foia_911_a", duration_ms=12_000),
        ],
        twist_pad_duration_ms=520,
    )
    kinds = [s.segment_kind for s in plan.segments]
    assert kinds == ["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT"]
    twist = plan.segments[1]
    assert twist.duration_ms == 520
    foia = plan.segments[2]
    assert foia.foia_asset_id == "foia_911_a"
    assert foia.duration_ms == 12_000


def test_short_narration_between_two_foia_slots_stays_single_chunk() -> None:
    beats = [
        FoiaAudioSlotBeat("foia_open", duration_ms=8_000),
        NarrationBeat("Records show the call was logged. The timeline was later confirmed."),
        FoiaAudioSlotBeat("foia_close", duration_ms=5_500),
    ]
    plan = build_tts_segment_plan("case_sandwich", beats)
    kinds = [s.segment_kind for s in plan.segments]
    assert kinds == [
        "FOIA_AUDIO_SLOT",
        "NARRATION",
        "FOIA_AUDIO_SLOT",
    ]
    narration = plan.segments[1]
    assert narration.word_count < MIN_NARRATION_WORDS
    assert count_words(narration.text) == narration.word_count


def test_narration_never_crosses_foia_boundary() -> None:
    left = NarrationBeat(_words(80))
    bridge = NarrationBeat("Alpha sentence one. Beta sentence two.")
    right = NarrationBeat(_words(90))
    beats = [
        left,
        FoiaAudioSlotBeat("foia_mid", duration_ms=3_000),
        bridge,
        FoiaAudioSlotBeat("foia_tail", duration_ms=2_000),
        right,
    ]
    plan = build_tts_segment_plan("case_split", beats)
    narration_texts = [s.text for s in plan.segments if s.segment_kind == "NARRATION"]
    assert len(narration_texts) == 3
    assert bridge.text in narration_texts
    assert left.text in narration_texts
    assert right.text in narration_texts
    foia_indexes = [i for i, s in enumerate(plan.segments) if s.segment_kind == "FOIA_AUDIO_SLOT"]
    assert foia_indexes == [1, 3]


def test_seq_index_is_contiguous_from_one() -> None:
    plan = build_tts_segment_plan(
        "case_seq",
        [
            NarrationBeat(" ".join(_sentence(20) for _ in range(20))),
            FoiaAudioSlotBeat("foia_0", duration_ms=1_000),
        ],
    )
    indexes = [segment.seq_index for segment in plan.segments]
    assert indexes == list(range(1, len(plan.segments) + 1))


def test_narration_chunk_word_counts_helper() -> None:
    plan = build_tts_segment_plan(
        "case_counts",
        [NarrationBeat(f"{_sentence(5)} {_sentence(5)}")],
    )
    assert narration_chunk_word_counts(plan) == [count_words(plan.segments[0].text)]


@pytest.mark.parametrize("duration_ms", [449, 751])
def test_twist_pad_duration_enforced(duration_ms: int) -> None:
    with pytest.raises(ValueError, match="twist_pad_duration_ms"):
        build_tts_segment_plan(
            "case_bad_pad",
            [NarrationBeat("Twist incoming.", is_plot_twist=True)],
            twist_pad_duration_ms=duration_ms,
        )


def test_invalid_foia_slot_rejected() -> None:
    with pytest.raises(ValueError, match="foia_asset_id"):
        build_tts_segment_plan("case_x", [FoiaAudioSlotBeat("", duration_ms=100)])
    with pytest.raises(ValueError, match="duration_ms"):
        build_tts_segment_plan("case_x", [FoiaAudioSlotBeat("foia_x", duration_ms=0)])


def test_default_twist_pad_duration() -> None:
    plan = build_tts_segment_plan(
        "case_default",
        [NarrationBeat("Reveal beat.", is_plot_twist=True)],
    )
    assert plan.segments[1].duration_ms == DEFAULT_TWIST_PAD_MS