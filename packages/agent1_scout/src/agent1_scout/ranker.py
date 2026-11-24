"""Composite evidence-density ranker for post-upgrade scout survivors.

``EvidenceDensityRanker`` scores eligible ``outlier_candidates`` with the fixed
0.30/0.25/0.25/0.20 Docs/FOIA/Twist/Gap blend, ranks survivors descending, and
writes ``GREENLIT`` for the top row after the ``safe_title_ctr_ok`` gate.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

WEIGHT_DOCS = 0.30
WEIGHT_FOIA = 0.25
WEIGHT_TWIST = 0.25
WEIGHT_GAP = 0.20

EVIDENCE_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("docs", WEIGHT_DOCS),
    ("foia", WEIGHT_FOIA),
    ("twist", WEIGHT_TWIST),
    ("gap", WEIGHT_GAP),
)

STATUS_CANDIDATE = "CANDIDATE"
STATUS_GREENLIT = "GREENLIT"

_AXIS_KEYS = ("docs", "foia", "twist", "gap")


def evidence_weight_sum() -> float:
    """Return the fixed composite weight total (must equal ``1.00``)."""

    return sum(weight for _, weight in EVIDENCE_WEIGHTS)


@dataclass(frozen=True, slots=True)
class EvidenceAxisScores:
    """Normalized 0..1 density scores for the four ranking axes."""

    docs: float
    foia: float
    twist: float
    gap: float

    def __post_init__(self) -> None:
        for name in _AXIS_KEYS:
            value = getattr(self, name)
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")

    def as_mapping(self) -> dict[str, float]:
        return {key: float(getattr(self, key)) for key in _AXIS_KEYS}


def composite_evidence_density_score(scores: EvidenceAxisScores) -> float:
    """Weighted composite score using the fixed 0.30/0.25/0.25/0.20 blend."""

    total = (
        WEIGHT_DOCS * scores.docs
        + WEIGHT_FOIA * scores.foia
        + WEIGHT_TWIST * scores.twist
        + WEIGHT_GAP * scores.gap
    )
    return round(total, 6)


@dataclass(frozen=True, slots=True)
class RankableCandidate:
    """One scout survivor entering the evidence-density ranker."""

    candidate_id: str
    safe_title_ctr_ok: int
    scores: EvidenceAxisScores
    status: str = STATUS_CANDIDATE

    def __post_init__(self) -> None:
        if self.safe_title_ctr_ok not in (0, 1):
            raise ValueError("safe_title_ctr_ok must be 0 or 1")


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One eligible survivor with computed composite score and ordinal rank."""

    candidate_id: str
    composite_score: float
    rank: int
    scores: EvidenceAxisScores
    greenlit: bool = False


@dataclass(frozen=True, slots=True)
class RankingResult:
    """Full ranker output including gated rejects and the single winner."""

    ranked: tuple[RankedCandidate, ...]
    rejected_unsafe_title: tuple[str, ...]
    winner_id: str | None

    @property
    def greenlit_id(self) -> str | None:
        return self.winner_id


def parse_evidence_density(seed_packet: Mapping[str, Any] | str | None) -> EvidenceAxisScores:
    """Read ``evidence_density`` from a seed packet JSON object or string."""

    payload: Mapping[str, Any]
    if seed_packet is None:
        payload = {}
    elif isinstance(seed_packet, str):
        try:
            decoded = json.loads(seed_packet)
        except json.JSONDecodeError as exc:
            raise ValueError("seed_packet_json is not valid JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ValueError("seed_packet_json must decode to an object")
        payload = decoded
    elif isinstance(seed_packet, Mapping):
        payload = seed_packet
    else:
        raise TypeError("seed_packet must be a mapping or JSON string")

    block = payload.get("evidence_density")
    if block is None:
        raise ValueError("seed_packet_json.evidence_density is required")
    if not isinstance(block, Mapping):
        raise ValueError("evidence_density must be an object")

    values: dict[str, float] = {}
    for key in _AXIS_KEYS:
        if key not in block:
            raise ValueError(f"evidence_density.{key} is required")
        raw = block[key]
        if not isinstance(raw, (int, float)):
            raise TypeError(f"evidence_density.{key} must be numeric")
        values[key] = float(raw)

    return EvidenceAxisScores(**values)


def _sort_key(row: RankedCandidate) -> tuple[float, str]:
    return (-row.composite_score, row.candidate_id)


class EvidenceDensityRanker:
    """Rank survivors by composite evidence density and elect one GREENLIT winner."""

    def rank(self, candidates: Sequence[RankableCandidate]) -> RankingResult:
        eligible: list[RankedCandidate] = []
        rejected: list[str] = []

        for candidate in candidates:
            if candidate.safe_title_ctr_ok != 1:
                rejected.append(candidate.candidate_id)
                continue
            composite = composite_evidence_density_score(candidate.scores)
            eligible.append(
                RankedCandidate(
                    candidate_id=candidate.candidate_id,
                    composite_score=composite,
                    rank=0,
                    scores=candidate.scores,
                )
            )

        eligible.sort(key=_sort_key)
        ranked: list[RankedCandidate] = []
        winner_id: str | None = None
        for index, row in enumerate(eligible, start=1):
            greenlit = index == 1 and len(eligible) > 0
            if greenlit:
                winner_id = row.candidate_id
            ranked.append(
                RankedCandidate(
                    candidate_id=row.candidate_id,
                    composite_score=row.composite_score,
                    rank=index,
                    scores=row.scores,
                    greenlit=greenlit,
                )
            )

        return RankingResult(
            ranked=tuple(ranked),
            rejected_unsafe_title=tuple(rejected),
            winner_id=winner_id,
        )

    def rank_and_persist(
        self,
        conn: sqlite3.Connection,
        *,
        status_filter: str = STATUS_CANDIDATE,
    ) -> RankingResult:
        """Load ``outlier_candidates``, rank eligible rows, and write scores/status."""

        rows = conn.execute(
            """
            SELECT candidate_id, safe_title_ctr_ok, seed_packet_json, status
            FROM outlier_candidates
            WHERE status = ?
            ORDER BY candidate_id ASC
            """,
            (status_filter,),
        ).fetchall()

        candidates = [
            RankableCandidate(
                candidate_id=str(row[0]),
                safe_title_ctr_ok=int(row[1]),
                scores=parse_evidence_density(row[2]),
                status=str(row[3]),
            )
            for row in rows
        ]

        result = self.rank(candidates)
        for ranked in result.ranked:
            conn.execute(
                """
                UPDATE outlier_candidates
                SET composite_score = ?, status = ?
                WHERE candidate_id = ?
                """,
                (
                    ranked.composite_score,
                    STATUS_GREENLIT if ranked.greenlit else status_filter,
                    ranked.candidate_id,
                ),
            )
        conn.commit()
        return result


__all__ = [
    "EVIDENCE_WEIGHTS",
    "EvidenceAxisScores",
    "EvidenceDensityRanker",
    "RankableCandidate",
    "RankedCandidate",
    "RankingResult",
    "STATUS_CANDIDATE",
    "STATUS_GREENLIT",
    "WEIGHT_DOCS",
    "WEIGHT_FOIA",
    "WEIGHT_GAP",
    "WEIGHT_TWIST",
    "composite_evidence_density_score",
    "evidence_weight_sum",
    "parse_evidence_density",
]