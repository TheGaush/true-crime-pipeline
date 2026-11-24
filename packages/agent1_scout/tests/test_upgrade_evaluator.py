"""Offline tests for the mandatory two-upgrade rule evaluator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent1_scout.upgrade_evaluator import (  # noqa: E402
    AXIS_CLEANER_SCRUBBED_FOIA_AUDIO,
    AXIS_MISSED_APPELLATE_FOIA_FACTS,
    AXIS_SPATIAL_2K_RECONSTRUCTION,
    AXIS_TOP3_COMMENT_QUESTION_ANSWERED,
    MIN_PASSED_AXES,
    REJECTED_NO_10X_UPGRADE,
    STATUS_PASSED,
    STATUS_REJECTED,
    TRACK_A_OUTLIER,
    TRACK_B_FOIA_RADAR,
    TwoUpgradeEvaluator,
    UpgradeAxisEvidence,
    decide_two_upgrade,
    evaluate_upgrade_axes,
    score_cleaner_scrubbed_foia_audio,
    score_missed_appellate_foia_facts,
    score_spatial_2k_reconstruction,
    score_top3_comment_question,
)


def _full_upgrade_evidence(**overrides: object) -> UpgradeAxisEvidence:
    base = dict(
        creator_cited_fact_ids=("fact_creator_1",),
        pipeline_appellate_or_foia_fact_ids=("fact_creator_1", "fact_foia_9"),
        top_comment_question_ids=("q1", "q2", "q3", "q4"),
        answered_comment_question_ids=("q2",),
        creator_has_spatial_2k=False,
        pipeline_has_locked_spatial_2k=True,
        creator_foia_audio_snr_db=12.0,
        pipeline_scrubbed_foia_audio_snr_db=18.0,
        pipeline_has_demucs_scrubbed_foia=True,
    )
    base.update(overrides)
    return UpgradeAxisEvidence(**base)  # type: ignore[arg-type]


def test_all_four_axes_score_independently():
    evidence = _full_upgrade_evidence()
    scores = evaluate_upgrade_axes(evidence)
    by_axis = {score.axis_id: score.passed for score in scores}
    assert by_axis[AXIS_MISSED_APPELLATE_FOIA_FACTS] is True
    assert by_axis[AXIS_TOP3_COMMENT_QUESTION_ANSWERED] is True
    assert by_axis[AXIS_SPATIAL_2K_RECONSTRUCTION] is True
    assert by_axis[AXIS_CLEANER_SCRUBBED_FOIA_AUDIO] is True


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        (
            UpgradeAxisEvidence(
                creator_cited_fact_ids=("a", "b"),
                pipeline_appellate_or_foia_fact_ids=("a",),
            ),
            False,
        ),
        (
            UpgradeAxisEvidence(
                creator_cited_fact_ids=("a",),
                pipeline_appellate_or_foia_fact_ids=("a", "foia_new"),
            ),
            True,
        ),
    ],
)
def test_missed_appellate_foia_axis(evidence: UpgradeAxisEvidence, expected: bool):
    assert score_missed_appellate_foia_facts(evidence).passed is expected


def test_top3_comment_axis_ignores_beyond_rank_three():
    evidence = UpgradeAxisEvidence(
        top_comment_question_ids=("q1", "q2", "q3", "q99"),
        answered_comment_question_ids=("q99",),
    )
    assert score_top3_comment_question(evidence).passed is False

    evidence_hit = UpgradeAxisEvidence(
        top_comment_question_ids=("q1", "q2", "q3"),
        answered_comment_question_ids=("q3",),
    )
    assert score_top3_comment_question(evidence_hit).passed is True


def test_spatial_2k_requires_pipeline_only_upgrade():
    assert (
        score_spatial_2k_reconstruction(
            UpgradeAxisEvidence(
                creator_has_spatial_2k=False,
                pipeline_has_locked_spatial_2k=True,
            )
        ).passed
        is True
    )
    assert (
        score_spatial_2k_reconstruction(
            UpgradeAxisEvidence(
                creator_has_spatial_2k=True,
                pipeline_has_locked_spatial_2k=True,
            )
        ).passed
        is False
    )


def test_cleaner_audio_requires_demucs_and_snr_delta():
    weak = UpgradeAxisEvidence(
        pipeline_has_demucs_scrubbed_foia=True,
        creator_foia_audio_snr_db=20.0,
        pipeline_scrubbed_foia_audio_snr_db=22.0,
    )
    assert score_cleaner_scrubbed_foia_audio(weak).passed is False

    strong = UpgradeAxisEvidence(
        pipeline_has_demucs_scrubbed_foia=True,
        creator_foia_audio_snr_db=10.0,
        pipeline_scrubbed_foia_audio_snr_db=15.0,
    )
    assert score_cleaner_scrubbed_foia_audio(strong).passed is True


@pytest.mark.parametrize("passed_count", [0, 1])
def test_reject_when_fewer_than_two_axes_pass(passed_count: int):
    flags = [
        passed_count >= 1,
        passed_count >= 2,
        False,
        False,
    ]
    scores = evaluate_upgrade_axes(
        UpgradeAxisEvidence(
            creator_cited_fact_ids=("x",),
            pipeline_appellate_or_foia_fact_ids=("x",) if not flags[0] else ("x", "y"),
            top_comment_question_ids=("q1",),
            answered_comment_question_ids=("q1",) if flags[1] else (),
            creator_has_spatial_2k=not flags[2],
            pipeline_has_locked_spatial_2k=flags[2],
            pipeline_has_demucs_scrubbed_foia=flags[3],
            creator_foia_audio_snr_db=30.0,
            pipeline_scrubbed_foia_audio_snr_db=40.0 if flags[3] else None,
        )
    )
    decision = decide_two_upgrade(scores, track=TRACK_A_OUTLIER)
    assert decision.status == STATUS_REJECTED
    assert decision.reject_reason == REJECTED_NO_10X_UPGRADE
    assert decision.passed_axis_count == passed_count


def test_pass_with_two_axes():
    decision = TwoUpgradeEvaluator().evaluate(_full_upgrade_evidence())
    assert decision.status == STATUS_PASSED
    assert decision.passed_axis_count >= MIN_PASSED_AXES
    assert decision.reject_reason is None
    axes = json.loads(decision.upgrade_axes_json)
    assert len(axes) >= MIN_PASSED_AXES


def test_track_b_bypasses_rule():
    decision = TwoUpgradeEvaluator().evaluate(
        UpgradeAxisEvidence(),
        track=TRACK_B_FOIA_RADAR,
    )
    assert decision.status == STATUS_PASSED
    assert decision.upgrade_axes_json == "[]"


def test_evaluator_reads_nested_upgrade_evidence_mapping():
    decision = TwoUpgradeEvaluator().evaluate(
        {
            "track": TRACK_A_OUTLIER,
            "upgrade_evidence": {
                "creator_cited_fact_ids": ["c1"],
                "pipeline_appellate_or_foia_fact_ids": ["c1", "appeal_42"],
                "top_comment_question_ids": ["t1", "t2"],
                "answered_comment_question_ids": ["t2"],
                "pipeline_has_locked_spatial_2k": True,
            },
        }
    )
    assert decision.status == STATUS_PASSED
    assert decision.passed_axis_count >= 2


def test_upgrade_axes_json_preserves_canonical_order():
    decision = TwoUpgradeEvaluator().evaluate(_full_upgrade_evidence())
    ordered = json.loads(decision.upgrade_axes_json)
    assert ordered.index(AXIS_MISSED_APPELLATE_FOIA_FACTS) < ordered.index(
        AXIS_CLEANER_SCRUBBED_FOIA_AUDIO
    )