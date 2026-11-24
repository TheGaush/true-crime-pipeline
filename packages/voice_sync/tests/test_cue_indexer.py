"""Task 068 — keyword cue mapping and proper-noun pronunciation gate."""

from __future__ import annotations

import pytest

from voice_sync.cue_indexer import (
    PRONUNCIATION_SIMILARITY_THRESHOLD,
    WordStamp,
    check_proper_noun_pronunciation,
    map_keyword_cue_timestamp,
    phonetic_respelling_for,
    pronunciation_similarity,
    run_pronunciation_gate,
    verify_respelling_meets_threshold,
)


def _stamps(*rows: tuple[str, int, int]) -> list[WordStamp]:
    return [WordStamp(word=w, start_ms=s, end_ms=e, segment_id="seg_narr_1") for w, s, e in rows]


class TestBeatScopedKeywordCue:
    def test_maps_keyword_inside_beat(self) -> None:
        stamps = _stamps(("Earlier", 1000, 1200), ("suspect", 4520, 4780), ("suspect", 9000, 9300))
        assert map_keyword_cue_timestamp("suspect", stamps, beat_start_ms=4000, beat_end_ms=6000) == 4520

    def test_ignores_keyword_outside_beat(self) -> None:
        stamps = _stamps(("suspect", 9000, 9300))
        assert map_keyword_cue_timestamp("suspect", stamps, beat_start_ms=4000, beat_end_ms=6000) is None

    def test_boundary_inclusive(self) -> None:
        stamps = _stamps(("knife", 5000, 5200))
        assert map_keyword_cue_timestamp("knife", stamps, beat_start_ms=5000, beat_end_ms=8000) == 5000

    def test_normalizes_punctuation(self) -> None:
        stamps = _stamps(("County.", 3100, 3300))
        assert map_keyword_cue_timestamp("county", stamps, 3000, 4000) == 3100


class TestProperNounPronunciationGate:
    def test_close_pronunciation_passes(self) -> None:
        score = pronunciation_similarity("Krzysztof", "Krzystof")
        assert score >= PRONUNCIATION_SIMILARITY_THRESHOLD
        finding = check_proper_noun_pronunciation(
            "Krzysztof",
            ["Krzystof", "later"],
            chunk_id="chunk_a",
        )
        assert finding.passed
        assert not finding.needs_resynthesis
        assert finding.phonetic_respelling is None

    def test_unrelated_english_word_fails(self) -> None:
        score = pronunciation_similarity("Krzysztof", "crystal")
        assert score < PRONUNCIATION_SIMILARITY_THRESHOLD
        finding = check_proper_noun_pronunciation(
            "Krzysztof",
            ["crystal", "was", "charged"],
            chunk_id="chunk_b",
        )
        assert not finding.passed
        assert finding.needs_resynthesis
        assert finding.phonetic_respelling == "KRIH-stohf"

    def test_respelling_meets_threshold(self) -> None:
        respelling = phonetic_respelling_for("Krzysztof")
        assert respelling == "KRIH-stohf"
        assert verify_respelling_meets_threshold(respelling, "Krzysztof")

    def test_mangled_surname_triggers_single_chunk_resynth(self) -> None:
        gate = run_pronunciation_gate(
            [("Nguyen", "chunk_ok"), ("Krzysztof", "chunk_bad")],
            {
                "chunk_ok": ["Nguyen", "testified"],
                "chunk_bad": ["crystal", "fled"],
            },
        )
        assert "chunk_bad" in gate.chunks_needing_resynthesis
        assert "chunk_ok" not in gate.chunks_needing_resynthesis
        bad = next(f for f in gate.findings if f.chunk_id == "chunk_bad")
        assert bad.phonetic_respelling == "KRIH-stohf"


class TestMetaphoneEdgeCases:
    def test_win_vs_nguyen_fails(self) -> None:
        assert pronunciation_similarity("Nguyen", "win") < PRONUNCIATION_SIMILARITY_THRESHOLD

    def test_invalid_beat_raises(self) -> None:
        with pytest.raises(ValueError):
            map_keyword_cue_timestamp("a", [], beat_start_ms=5000, beat_end_ms=4000)