"""Offline tests for the composite evidence-density ranker."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent1_scout.ranker import (  # noqa: E402
    STATUS_CANDIDATE,
    STATUS_GREENLIT,
    WEIGHT_DOCS,
    WEIGHT_FOIA,
    WEIGHT_GAP,
    WEIGHT_TWIST,
    EvidenceAxisScores,
    EvidenceDensityRanker,
    RankableCandidate,
    composite_evidence_density_score,
    evidence_weight_sum,
    parse_evidence_density,
)


def _scores(
    docs: float,
    foia: float,
    twist: float,
    gap: float,
) -> EvidenceAxisScores:
    return EvidenceAxisScores(docs=docs, foia=foia, twist=twist, gap=gap)


def _candidate(
    cid: str,
    *,
    safe_title: int,
    docs: float,
    foia: float,
    twist: float,
    gap: float,
) -> RankableCandidate:
    return RankableCandidate(
        candidate_id=cid,
        safe_title_ctr_ok=safe_title,
        scores=_scores(docs, foia, twist, gap),
    )


def test_weights_sum_to_one():
    assert evidence_weight_sum() == pytest.approx(1.0)
    assert WEIGHT_DOCS + WEIGHT_FOIA + WEIGHT_TWIST + WEIGHT_GAP == pytest.approx(1.0)


def test_composite_score_formula():
    scores = _scores(1.0, 0.8, 0.6, 0.4)
    expected = 0.30 * 1.0 + 0.25 * 0.8 + 0.25 * 0.6 + 0.20 * 0.4
    assert composite_evidence_density_score(scores) == pytest.approx(expected)


def test_parse_evidence_density_from_mapping():
    packet = {
        "evidence_density": {"docs": 0.9, "foia": 0.5, "twist": 0.7, "gap": 0.3},
    }
    parsed = parse_evidence_density(packet)
    assert parsed.docs == 0.9
    assert parsed.foia == 0.5


def test_parse_rejects_out_of_range_axis():
    packet = {"evidence_density": {"docs": 1.5, "foia": 0.5, "twist": 0.5, "gap": 0.5}}
    with pytest.raises(ValueError, match="docs"):
        parse_evidence_density(packet)


def test_ranks_descending_and_greenlits_winner():
    pool = [
        _candidate("c-low", safe_title=1, docs=0.4, foia=0.4, twist=0.4, gap=0.4),
        _candidate("c-high", safe_title=1, docs=0.95, foia=0.9, twist=0.85, gap=0.8),
        _candidate("c-mid", safe_title=1, docs=0.7, foia=0.6, twist=0.6, gap=0.6),
    ]
    result = EvidenceDensityRanker().rank(pool)

    assert [row.candidate_id for row in result.ranked] == ["c-high", "c-mid", "c-low"]
    assert result.winner_id == "c-high"
    assert result.ranked[0].greenlit is True
    assert all(not row.greenlit for row in result.ranked[1:])


def test_unsafe_title_rejected_despite_high_docs():
    pool = [
        _candidate("tabloid", safe_title=0, docs=1.0, foia=1.0, twist=1.0, gap=1.0),
        _candidate("safe", safe_title=1, docs=0.5, foia=0.5, twist=0.5, gap=0.5),
    ]
    result = EvidenceDensityRanker().rank(pool)

    assert result.rejected_unsafe_title == ("tabloid",)
    assert result.winner_id == "safe"
    assert len(result.ranked) == 1


def test_tie_breaker_uses_candidate_id():
    pool = [
        _candidate("b-same", safe_title=1, docs=0.8, foia=0.8, twist=0.8, gap=0.8),
        _candidate("a-same", safe_title=1, docs=0.8, foia=0.8, twist=0.8, gap=0.8),
    ]
    result = EvidenceDensityRanker().rank(pool)
    assert result.ranked[0].candidate_id == "a-same"
    assert result.ranked[0].greenlit is True


def test_no_eligible_candidates_yields_no_winner():
    pool = [
        _candidate("x", safe_title=0, docs=0.9, foia=0.9, twist=0.9, gap=0.9),
    ]
    result = EvidenceDensityRanker().rank(pool)
    assert result.winner_id is None
    assert result.ranked == ()


def _seed(docs: float, foia: float, twist: float, gap: float) -> str:
    return json.dumps(
        {
            "evidence_density": {
                "docs": docs,
                "foia": foia,
                "twist": twist,
                "gap": gap,
            }
        }
    )


def _memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE outlier_candidates (
            candidate_id TEXT PRIMARY KEY,
            track TEXT NOT NULL,
            saturation_index INTEGER NOT NULL,
            safe_title_ctr_ok INTEGER NOT NULL,
            composite_score REAL NOT NULL DEFAULT 0.0,
            seed_packet_json TEXT NOT NULL,
            status TEXT NOT NULL
        );
        """
    )
    return conn


def test_rank_and_persist_writes_greenlit_and_scores():
    conn = _memory_db()
    conn.execute(
        """
        INSERT INTO outlier_candidates VALUES
        ('winner', 'TRACK_A_OUTLIER', 10, 1, 0.0, ?, 'CANDIDATE'),
        ('runner', 'TRACK_A_OUTLIER', 10, 1, 0.0, ?, 'CANDIDATE'),
        ('blocked', 'TRACK_A_OUTLIER', 10, 0, 0.0, ?, 'CANDIDATE')
        """,
        (
            _seed(0.9, 0.9, 0.9, 0.9),
            _seed(0.5, 0.5, 0.5, 0.5),
            _seed(1.0, 1.0, 1.0, 1.0),
        ),
    )

    result = EvidenceDensityRanker().rank_and_persist(conn)
    assert result.winner_id == "winner"

    rows = {
        row[0]: row
        for row in conn.execute(
            "SELECT candidate_id, composite_score, status FROM outlier_candidates"
        ).fetchall()
    }
    assert rows["winner"][2] == STATUS_GREENLIT
    assert rows["runner"][2] == STATUS_CANDIDATE
    assert rows["blocked"][2] == STATUS_CANDIDATE
    assert rows["winner"][1] > rows["runner"][1]
    assert rows["blocked"][1] == pytest.approx(0.0)