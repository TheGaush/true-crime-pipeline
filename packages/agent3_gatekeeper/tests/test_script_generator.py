"""Tests for fact-grounded script generator (Task 052)."""

from __future__ import annotations

import pytest

from agent3_gatekeeper.script_generator import (
    EPISODE_STATUS_SCENE_PLAN_APPROVED,
    ScriptCompileResult,
    REJECTED_UNLOCKED_ANCHORS,
    REJECTED_UNKNOWN_FACT_CITE,
    AnchorInput,
    BeatInput,
    CompiledScenePlan,
    FactInput,
    GroundedScriptGenerator,
    compute_target_narration_words,
    count_words,
    extract_asserted_fact_ids,
    narration_version_sha256,
    scene_plan_stage1_approved,
    topology_safe_clause,
)

LOCKED_ANCHOR = AnchorInput(
    anchor_id="anc_1",
    lock_status="LOCKED",
    clue_name="overturned table",
    cited_fact_id="fact_1",
    grid_cell="C4",
)

DRAFT_ANCHOR = AnchorInput(
    anchor_id="anc_2",
    lock_status="DRAFT",
    clue_name="latent print lift",
    cited_fact_id="fact_2",
    grid_cell="B2",
)

FACT_ONE = FactInput(
    fact_id="fact_1",
    event_summary="an overturned table was noted near the entryway",
    source_type="police_affidavit",
    citation_locator="Affidavit p.4",
)

FACT_TWO = FactInput(
    fact_id="fact_2",
    event_summary="a latent print matched the defendant",
    source_type="court_ruling",
    citation_locator="State v. Doe, slip op. at 12",
)

BEAT_ONE = BeatInput(
    beat_id="beat_1",
    fact_id="fact_1",
    datetime_iso="2019-03-02T14:10:00-05:00",
    citation_locator="Affidavit p.4",
    source_type="police_affidavit",
    record_anchor="Establish the physical scene from the affidavit",
    editorial_analysis="Viewer should understand the record places debris by the door",
)

BEAT_TWO = BeatInput(
    beat_id="beat_2",
    fact_id="fact_2",
    datetime_iso="2020-11-01T10:00:00-05:00",
    citation_locator="State v. Doe, slip op. at 12",
    source_type="court_ruling",
    record_anchor="Introduce the appellate forensic finding",
    editorial_analysis="Raise stakes without implying guilt",
)


def test_target_narration_words_foia_aware() -> None:
    assert compute_target_narration_words(210) == pytest.approx(2392.5)
    assert compute_target_narration_words(0) == pytest.approx(2900.0)


def test_rejects_when_spatial_anchors_not_locked() -> None:
    gen = GroundedScriptGenerator()
    result = gen.compile(
        episode_id="ep_1",
        foia_total_sec=210,
        facts=[FACT_ONE, FACT_TWO],
        beats=[BEAT_ONE, BEAT_TWO],
        spatial_anchors=[LOCKED_ANCHOR, DRAFT_ANCHOR],
    )
    assert not result.accepted
    assert result.reason == REJECTED_UNLOCKED_ANCHORS
    assert result.episode_status is None


def test_compiles_with_locked_anchors_and_scene_plan_fields() -> None:
    gen = GroundedScriptGenerator()
    result = gen.compile(
        episode_id="ep_1",
        foia_total_sec=210,
        facts=[FACT_ONE, FACT_TWO],
        beats=[BEAT_ONE, BEAT_TWO],
        spatial_anchors=[
            LOCKED_ANCHOR,
            AnchorInput(
                anchor_id="anc_2",
                lock_status="LOCKED",
                clue_name="latent print lift",
                cited_fact_id="fact_2",
            ),
        ],
    )
    assert result.accepted
    assert result.episode_status == EPISODE_STATUS_SCENE_PLAN_APPROVED
    assert len(result.scene_plans) == 2
    for plan in result.scene_plans:
        assert scene_plan_stage1_approved(plan)
        assert plan.story_purpose
        assert plan.intended_audience_effect
        assert plan.cited_fact_ids
        assert plan.narration_version_sha256 == narration_version_sha256(
            plan.approved_narration_text
        )


def test_topology_safe_narration_does_not_claim_measured_geometry() -> None:
    text = topology_safe_clause(
        event_summary="a bloodstain pattern was photographed",
        source_type="police_affidavit",
        citation_locator="Affidavit p.2",
        clue_name="bloodstain A",
    )
    assert "According to the affidavit" in text
    assert "illustrative" in text.lower()
    assert "measured layout" in text


def test_rejects_narration_citing_missing_fact_id() -> None:
    gen = GroundedScriptGenerator()
    bad = gen.apply_external_narration(
        scene_plan_id="plan_x",
        scene_id="scene_x",
        seq_index=1,
        story_purpose="Hook",
        intended_audience_effect="Curiosity",
        approved_narration_text="The record shows fact_9 was filed overnight.",
        cited_fact_ids=["fact_1"],
        allowed_fact_ids=frozenset({"fact_1"}),
    )
    assert isinstance(bad, ScriptCompileResult)
    assert bad.status == "REJECTED"
    assert bad.reason == REJECTED_UNKNOWN_FACT_CITE


def test_rejects_cited_fact_not_in_supplied_ledger() -> None:
    gen = GroundedScriptGenerator()
    bad = gen.apply_external_narration(
        scene_plan_id="plan_x",
        scene_id="scene_x",
        seq_index=1,
        story_purpose="Hook",
        intended_audience_effect="Curiosity",
        approved_narration_text="Per the affidavit, an item was logged.",
        cited_fact_ids=["fact_missing"],
        allowed_fact_ids=frozenset({"fact_1"}),
    )
    assert isinstance(bad, ScriptCompileResult)
    assert bad.reason == REJECTED_UNKNOWN_FACT_CITE


def test_extract_asserted_fact_ids_from_brackets() -> None:
    text = "The ledger notes fact_1 and also [fact_2] in bracket form."
    assert extract_asserted_fact_ids(text) == frozenset({"fact_1", "fact_2"})


def test_accepted_mocked_narration_scene_plan() -> None:
    gen = GroundedScriptGenerator()
    narration = "According to the affidavit (p. 1), the porch light was on."
    plan = gen.apply_external_narration(
        scene_plan_id="plan_1",
        scene_id="scene_1",
        seq_index=1,
        story_purpose="Open with a verifiable domestic detail",
        intended_audience_effect="Ground the viewer in time and place",
        approved_narration_text=narration,
        cited_fact_ids=["fact_1"],
        allowed_fact_ids=frozenset({"fact_1"}),
        anchor_id="anc_1",
    )
    assert isinstance(plan, CompiledScenePlan)
    assert scene_plan_stage1_approved(plan)
    assert plan.narration_version_sha256 == narration_version_sha256(narration)


def test_word_count_tracks_compiled_scenes() -> None:
    gen = GroundedScriptGenerator()
    result = gen.compile(
        episode_id="ep_1",
        foia_total_sec=0,
        facts=[FACT_ONE],
        beats=[BEAT_ONE],
        spatial_anchors=[LOCKED_ANCHOR],
    )
    manual = sum(count_words(p.approved_narration_text) for p in result.scene_plans)
    assert result.narration_word_count == manual