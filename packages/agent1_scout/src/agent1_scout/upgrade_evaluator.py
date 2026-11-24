"""Mandatory two-upgrade rule for Track A small-creator outliers.

``TwoUpgradeEvaluator`` requires a Track A candidate to beat the source creator on
at least two of four differentiation axes:

1. Missed appellate or FOIA primary-record facts
2. Answers at least one top-three viewer comment question
3. Illustrative 2K spatial crime-scene reconstruction
4. Cleaner Demucs-scrubbed FOIA audio

The module is offline-only: pure functions, no network or filesystem I/O.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

TRACK_A_OUTLIER = "TRACK_A_OUTLIER"
TRACK_B_FOIA_RADAR = "TRACK_B_FOIA_RADAR"
Track = Literal["TRACK_A_OUTLIER", "TRACK_B_FOIA_RADAR"]

AXIS_MISSED_APPELLATE_FOIA_FACTS = "MISSED_APPELLATE_FOIA_FACTS"
AXIS_TOP3_COMMENT_QUESTION_ANSWERED = "TOP3_COMMENT_QUESTION_ANSWERED"
AXIS_SPATIAL_2K_RECONSTRUCTION = "SPATIAL_2K_RECONSTRUCTION"
AXIS_CLEANER_SCRUBBED_FOIA_AUDIO = "CLEANER_SCRUBBED_FOIA_AUDIO"

UPGRADE_AXES: tuple[str, ...] = (
    AXIS_MISSED_APPELLATE_FOIA_FACTS,
    AXIS_TOP3_COMMENT_QUESTION_ANSWERED,
    AXIS_SPATIAL_2K_RECONSTRUCTION,
    AXIS_CLEANER_SCRUBBED_FOIA_AUDIO,
)

MIN_PASSED_AXES = 2
TOP_COMMENT_QUESTION_LIMIT = 3

STATUS_PASSED = "PASSED"
STATUS_REJECTED = "REJECTED"
REJECTED_NO_10X_UPGRADE = "REJECTED_NO_10X_UPGRADE"

AUDIO_SNR_IMPROVEMENT_DB = 3.0


@dataclass(frozen=True, slots=True)
class UpgradeAxisEvidence:
    """Inputs describing how our pipeline compares to the small-creator upload."""

    creator_cited_fact_ids: tuple[str, ...] = ()
    pipeline_primary_fact_ids: tuple[str, ...] = ()
    pipeline_appellate_or_foia_fact_ids: tuple[str, ...] = ()
    top_comment_question_ids: tuple[str, ...] = ()
    answered_comment_question_ids: tuple[str, ...] = ()
    creator_has_spatial_2k: bool = False
    pipeline_has_locked_spatial_2k: bool = False
    creator_foia_audio_snr_db: float | None = None
    pipeline_scrubbed_foia_audio_snr_db: float | None = None
    pipeline_has_demucs_scrubbed_foia: bool = False


@dataclass(frozen=True, slots=True)
class AxisScore:
    """Pass/fail for one differentiation axis."""

    axis_id: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class TwoUpgradeDecision:
    """Outcome of the mandatory two-upgrade gate."""

    status: str
    passed_axis_count: int
    passed_axes: tuple[str, ...]
    axis_scores: tuple[AxisScore, ...]
    reject_reason: str | None = None
    upgrade_axes_json: str = "[]"
    track: Track | None = None


def _normalize_ids(values: Sequence[str] | None) -> frozenset[str]:
    if not values:
        return frozenset()
    return frozenset(value.strip() for value in values if value and value.strip())


def score_missed_appellate_foia_facts(evidence: UpgradeAxisEvidence) -> AxisScore:
    """Pass when primary appellate/FOIA facts exist that the creator did not cite."""

    creator = _normalize_ids(evidence.creator_cited_fact_ids)
    pipeline_primary = _normalize_ids(evidence.pipeline_primary_fact_ids)
    appellate_foia = _normalize_ids(evidence.pipeline_appellate_or_foia_fact_ids)
    pool = appellate_foia if appellate_foia else pipeline_primary
    missed = pool - creator
    passed = bool(missed)
    detail = f"missed_count={len(missed)}"
    return AxisScore(AXIS_MISSED_APPELLATE_FOIA_FACTS, passed, detail)


def score_top3_comment_question(evidence: UpgradeAxisEvidence) -> AxisScore:
    """Pass when at least one ranked top-three comment question is answered."""

    top_three = tuple(
        question_id
        for question_id in evidence.top_comment_question_ids[:TOP_COMMENT_QUESTION_LIMIT]
        if question_id and question_id.strip()
    )
    answered = _normalize_ids(evidence.answered_comment_question_ids)
    hits = [question_id for question_id in top_three if question_id in answered]
    passed = bool(hits)
    detail = f"answered_top3={len(hits)}"
    return AxisScore(AXIS_TOP3_COMMENT_QUESTION_ANSWERED, passed, detail)


def score_spatial_2k_reconstruction(evidence: UpgradeAxisEvidence) -> AxisScore:
    """Pass when we add a locked 2K spatial reconstruction the creator lacked."""

    passed = evidence.pipeline_has_locked_spatial_2k and not evidence.creator_has_spatial_2k
    detail = (
        "pipeline_locked=1,creator_had_2k=0"
        if passed
        else f"pipeline_locked={int(evidence.pipeline_has_locked_spatial_2k)},"
        f"creator_had_2k={int(evidence.creator_has_spatial_2k)}"
    )
    return AxisScore(AXIS_SPATIAL_2K_RECONSTRUCTION, passed, detail)


def score_cleaner_scrubbed_foia_audio(evidence: UpgradeAxisEvidence) -> AxisScore:
    """Pass when Demucs-scrubbed FOIA audio measurably beats the creator source."""

    if not evidence.pipeline_has_demucs_scrubbed_foia:
        return AxisScore(
            AXIS_CLEANER_SCRUBBED_FOIA_AUDIO,
            False,
            "pipeline_demucs_scrubbed=0",
        )

    creator_snr = evidence.creator_foia_audio_snr_db
    pipeline_snr = evidence.pipeline_scrubbed_foia_audio_snr_db
    if pipeline_snr is None:
        return AxisScore(
            AXIS_CLEANER_SCRUBBED_FOIA_AUDIO,
            False,
            "pipeline_snr_missing",
        )
    if creator_snr is None:
        passed = True
        detail = "creator_snr_missing,pipeline_demucs_scrubbed=1"
    else:
        passed = pipeline_snr >= creator_snr + AUDIO_SNR_IMPROVEMENT_DB
        detail = (
            f"pipeline_snr_db={pipeline_snr:.1f},creator_snr_db={creator_snr:.1f},"
            f"delta_required_db={AUDIO_SNR_IMPROVEMENT_DB:.1f}"
        )
    return AxisScore(AXIS_CLEANER_SCRUBBED_FOIA_AUDIO, passed, detail)


def evaluate_upgrade_axes(evidence: UpgradeAxisEvidence) -> tuple[AxisScore, ...]:
    """Score all four mandatory upgrade axes."""

    return (
        score_missed_appellate_foia_facts(evidence),
        score_top3_comment_question(evidence),
        score_spatial_2k_reconstruction(evidence),
        score_cleaner_scrubbed_foia_audio(evidence),
    )


def _upgrade_axes_json(passed_axes: Sequence[str]) -> str:
    ordered = [axis for axis in UPGRADE_AXES if axis in passed_axes]
    return json.dumps(ordered, separators=(",", ":"))


def _tuple_field(candidate: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = candidate.get(key, ())
    if raw is None:
        return ()
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Mapping):
        return tuple(str(value) for value in raw.values())
    return tuple(str(value) for value in raw)


def _bool_field(candidate: Mapping[str, Any], key: str) -> bool:
    value = candidate.get(key, False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _float_or_none(candidate: Mapping[str, Any], key: str) -> float | None:
    value = candidate.get(key)
    if value is None or value == "":
        return None
    return float(value)


def evidence_from_mapping(candidate: Mapping[str, Any]) -> UpgradeAxisEvidence:
    """Build ``UpgradeAxisEvidence`` from a loose candidate mapping."""

    source: Mapping[str, Any] = candidate
    nested = candidate.get("upgrade_evidence")
    if isinstance(nested, Mapping):
        source = nested

    return UpgradeAxisEvidence(
        creator_cited_fact_ids=_tuple_field(source, "creator_cited_fact_ids"),
        pipeline_primary_fact_ids=_tuple_field(source, "pipeline_primary_fact_ids"),
        pipeline_appellate_or_foia_fact_ids=_tuple_field(
            source, "pipeline_appellate_or_foia_fact_ids"
        ),
        top_comment_question_ids=_tuple_field(source, "top_comment_question_ids"),
        answered_comment_question_ids=_tuple_field(
            source, "answered_comment_question_ids"
        ),
        creator_has_spatial_2k=_bool_field(source, "creator_has_spatial_2k"),
        pipeline_has_locked_spatial_2k=_bool_field(source, "pipeline_has_locked_spatial_2k"),
        creator_foia_audio_snr_db=_float_or_none(source, "creator_foia_audio_snr_db"),
        pipeline_scrubbed_foia_audio_snr_db=_float_or_none(
            source, "pipeline_scrubbed_foia_audio_snr_db"
        ),
        pipeline_has_demucs_scrubbed_foia=_bool_field(
            source, "pipeline_has_demucs_scrubbed_foia"
        ),
    )


def decide_two_upgrade(
    axis_scores: Sequence[AxisScore],
    *,
    track: Track = TRACK_A_OUTLIER,
) -> TwoUpgradeDecision:
    """Apply the ``>= 2`` passed-axis rule for Track A."""

    if track == TRACK_B_FOIA_RADAR:
        return TwoUpgradeDecision(
            status=STATUS_PASSED,
            passed_axis_count=0,
            passed_axes=(),
            axis_scores=tuple(axis_scores),
            reject_reason=None,
            upgrade_axes_json="[]",
            track=track,
        )

    passed_axes = tuple(score.axis_id for score in axis_scores if score.passed)
    passed_count = len(passed_axes)
    if passed_count >= MIN_PASSED_AXES:
        return TwoUpgradeDecision(
            status=STATUS_PASSED,
            passed_axis_count=passed_count,
            passed_axes=passed_axes,
            axis_scores=tuple(axis_scores),
            reject_reason=None,
            upgrade_axes_json=_upgrade_axes_json(passed_axes),
            track=track,
        )

    return TwoUpgradeDecision(
        status=STATUS_REJECTED,
        passed_axis_count=passed_count,
        passed_axes=passed_axes,
        axis_scores=tuple(axis_scores),
        reject_reason=REJECTED_NO_10X_UPGRADE,
        upgrade_axes_json=_upgrade_axes_json(passed_axes),
        track=track,
    )


class TwoUpgradeEvaluator:
    """Gate Track A outliers on the mandatory two-upgrade rule."""

    def evaluate(
        self,
        candidate: Mapping[str, Any] | UpgradeAxisEvidence,
        *,
        track: Track | None = None,
    ) -> TwoUpgradeDecision:
        if isinstance(candidate, UpgradeAxisEvidence):
            evidence = candidate
            effective_track = track or TRACK_A_OUTLIER
        else:
            evidence = evidence_from_mapping(candidate)
            raw_track = track or candidate.get("track", TRACK_A_OUTLIER)
            effective_track = (
                raw_track
                if raw_track in (TRACK_A_OUTLIER, TRACK_B_FOIA_RADAR)
                else TRACK_A_OUTLIER
            )

        scores = evaluate_upgrade_axes(evidence)
        return decide_two_upgrade(scores, track=effective_track)


__all__ = [
    "AUDIO_SNR_IMPROVEMENT_DB",
    "AXIS_CLEANER_SCRUBBED_FOIA_AUDIO",
    "AXIS_MISSED_APPELLATE_FOIA_FACTS",
    "AXIS_SPATIAL_2K_RECONSTRUCTION",
    "AXIS_TOP3_COMMENT_QUESTION_ANSWERED",
    "MIN_PASSED_AXES",
    "REJECTED_NO_10X_UPGRADE",
    "STATUS_PASSED",
    "STATUS_REJECTED",
    "TOP_COMMENT_QUESTION_LIMIT",
    "TRACK_A_OUTLIER",
    "TRACK_B_FOIA_RADAR",
    "AxisScore",
    "TwoUpgradeDecision",
    "TwoUpgradeEvaluator",
    "UPGRADE_AXES",
    "UpgradeAxisEvidence",
    "decide_two_upgrade",
    "evaluate_upgrade_axes",
    "evidence_from_mapping",
    "score_cleaner_scrubbed_foia_audio",
    "score_missed_appellate_foia_facts",
    "score_spatial_2k_reconstruction",
    "score_top3_comment_question",
]