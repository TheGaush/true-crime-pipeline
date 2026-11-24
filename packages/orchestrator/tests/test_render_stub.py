"""RenderBackendStub offline vertical-slice and ledger tests."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SQL = REPO_ROOT / "schema" / "pipeline.sql"
PROMPT_V1 = "slow charcoal push toward the porch door"
PROMPT_V2_SAFE = "flashlight beam crosses rain on an empty porch"

from orchestrator.render_stub import (  # noqa: E402
    AccountSnapshot,
    BatchDeskLockedError,
    FlowJobDispatch,
    OfflineTestSpendError,
    RenderBackendPort,
    RenderBackendStub,
    assert_offline_test_spend,
    batch_desk_may_spend,
    validate_render_bundle,
)
from vector_factory import (  # noqa: E402
    bible_valid,
    production_valid,
    scene_valid,
    timeline_valid,
    voice_valid,
)


def _payload(rows: list, model: str, index: int = 0) -> dict:
    for row in rows:
        if row["model"] == model and row["index"] == index:
            return row["payload"]
    raise KeyError(f"{model}[{index}]")


def _bundle_dicts(index: int = 0) -> tuple[dict, dict, dict, dict, dict]:
    return (
        _payload(production_valid(), "ProductionManifest", index),
        _payload(timeline_valid(), "TimelineSpec", index),
        _payload(bible_valid(), "CaseBible", index),
        _payload(scene_valid(), "ScenePlan", index),
        _payload(voice_valid(), "VoiceTrackManifest", index),
    )


def init_pipeline(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(PIPELINE_SQL.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_case_and_episode(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO cases (
          case_id, defendant_name, incident_year, jurisdiction,
          verification_source, disposition_status, conviction_confirmed,
          created_at, updated_at
        ) VALUES ('case_1', 'John Doe', 2023, 'Mercer, NJ', 'courtlistener', 'AFFIRMED', 1, 1000, 1000)
        """
    )
    conn.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
          updated_at, created_at
        ) VALUES ('ep_1', 'case_1', 'AWAITING_FLOW_BATCH', 'GEMINI_OMNI_INTERACTIONS',
                  '911_CALL_IN_MEDIA_RES', 1000, 1000)
        """
    )


def seed_flow_job(conn: sqlite3.Connection, *, flow_job_id: str = "fj_strike") -> None:
    scene_id = "sc_strike"
    plan_id = "sp_strike_v1"
    conn.execute(
        """
        INSERT INTO scene_plans (
          scene_plan_id, episode_id, scene_id, plan_version, seq_index,
          story_purpose, intended_audience_effect, approved_narration_text,
          narration_version_sha256, cited_fact_ids_json, visual_concept,
          visual_engine, motif_component, prompt_mode, visual_prompt,
          expected_output_summary, timing_start_ms, timing_end_ms,
          transition_spec_json, edit_instructions, acceptance_criteria_json,
          asset_version_sha256, plan_status, reviewed_by, reviewed_at,
          created_at, updated_at
        ) VALUES (
          ?, 'ep_1', ?, 1, 1,
          'Establish arrival timeline', 'Curiosity hook', 'At 10:14 PM a silhouette crossed the porch.',
          'sha_nar_1', '["fact_1"]', 'Monochrome doorway pan',
          'FLOW_HERO_VIDEO', 'HeroVideoBridge', 'TEXT_TO_VIDEO', 'Slow charcoal camera push',
          'Crisp silhouette door entry', 0, 8000,
          '{"type":"l_cut","ms":800}', 'Hold then cut', '["Fact cited","Safe-Zone clear"]',
          'sha_asset_1', 'EDITED_APPROVED', 'editor_jane', 1500,
          1000, 1500
        )
        """,
        (plan_id, scene_id),
    )
    conn.execute(
        """
        INSERT INTO scenes (
          scene_id, episode_id, scene_plan_id, seq_index, act_number,
          visual_engine, motif_component, start_ms, end_ms, timeline_spec_json,
          fallback_spec_json
        ) VALUES (?, 'ep_1', ?, 1, 1, 'FLOW_HERO_VIDEO', 'HeroVideoBridge', 0, 8000, '{}',
                  '{"engine":"STILL_2K_PANZOOM"}')
        """,
        (scene_id, plan_id),
    )
    conn.execute(
        """
        INSERT INTO flow_jobs (
          flow_job_id, episode_id, scene_id, idempotency_key, provider_route,
          engine_model, prompt_mode, resolution, duration_bucket_sec, variations,
          estimated_micro_usd, estimated_credits, prompt_v1, prompt_v2_safe,
          fallback_spec_json, state, attempts_used, updated_at
        ) VALUES (
          ?, 'ep_1', ?, 'idem-strike-1', 'GEMINI_OMNI_INTERACTIONS',
          'gemini-omni-1.2-flash', 'TEXT_TO_VIDEO', '720p', 8, 1,
          0, 0, ?, ?,
          '{"visual_engine":"STILL_2K_PANZOOM","motif_component":"Illustrative2KPanZoom","reason":"RULE_05"}',
          'PENDING', 0, 1000
        )
        """,
        (flow_job_id, scene_id, PROMPT_V1, PROMPT_V2_SAFE),
    )


def reserve(conn: sqlite3.Connection, *, reservation_id: str, attempt_number: int) -> None:
    conn.execute(
        """
        INSERT INTO provider_spend_reservations (
          reservation_id, episode_id, job_id, attempt_number, provider_id, purpose,
          year_month, estimated_micro_usd, status, created_at
        ) VALUES (?, 'ep_1', 'fj_strike', ?, 'gemini_omni', 'OFFLINE_TEST',
                  '2026-11', 0, 'RESERVED', 1000)
        """,
        (reservation_id, attempt_number),
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.db"
    init_pipeline(path)
    conn = connect(path)
    try:
        seed_case_and_episode(conn)
        seed_flow_job(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def test_validate_bundle_rejects_unknown_keys() -> None:
    manifest, timeline, bible, scene, voice = _bundle_dicts()
    bad = dict(manifest)
    bad["extra_field"] = True
    with pytest.raises(ValueError):
        validate_render_bundle(bad, timeline, bible, scene, voice)


def test_offline_test_spend_must_be_zero() -> None:
    assert_offline_test_spend("OFFLINE_TEST", 0)
    with pytest.raises(OfflineTestSpendError, match="OFFLINE_TEST_ZERO_SPEND"):
        assert_offline_test_spend("OFFLINE_TEST", 1)


def test_deterministic_vertical_slice_outputs() -> None:
    stub = RenderBackendStub()
    inputs = _bundle_dicts(1)
    first = stub.complete_vertical_slice(*inputs, now_ms=1_000)
    second = stub.complete_vertical_slice(*inputs, now_ms=9_999)
    assert first == second
    assert first.spend_micro_usd == 0
    assert first.bundle_sha256
    assert first.master_relpath.startswith("stub/masters/")


def test_stub_implements_render_backend_port() -> None:
    assert isinstance(RenderBackendStub(), RenderBackendPort)


def test_gemini_dispatch_ignores_batch_lock() -> None:
    stub = RenderBackendStub()
    locked = AccountSnapshot(
        account_id="acct_1",
        daily_credits_left=0,
        next_daily_reset_utc_ms=9_000,
        first_daily_spend_utc_ms=1_000,
    )
    receipts = stub.dispatch_flow_jobs(
        (
            FlowJobDispatch(
                flow_job_id="fj_headless",
                episode_id="ep_1",
                scene_id="sc_1",
                idempotency_key="idem-headless",
                provider_route="GEMINI_OMNI_INTERACTIONS",
                prompt_mode="TEXT_TO_VIDEO",
                prompt_v1=PROMPT_V1,
                prompt_v2_safe=PROMPT_V2_SAFE,
                duration_bucket_sec=8,
            ),
        ),
        now_ms=2_000,
        batch_account=locked,
    )
    assert receipts[0].state == "PENDING"


def test_human_batch_desk_refuses_before_daily_reset() -> None:
    stub = RenderBackendStub()
    locked = AccountSnapshot(
        account_id="desk_1",
        daily_credits_left=0,
        next_daily_reset_utc_ms=50_000,
        first_daily_spend_utc_ms=1_000,
    )
    assert not batch_desk_may_spend(locked, now_ms=5_000, credits=1)
    job = FlowJobDispatch(
        flow_job_id="fj_desk",
        episode_id="ep_1",
        scene_id="sc_1",
        idempotency_key="idem-desk",
        provider_route="HUMAN_BATCH_DESK",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1=PROMPT_V1,
        prompt_v2_safe=PROMPT_V2_SAFE,
        duration_bucket_sec=8,
        estimated_credits=1,
    )
    with pytest.raises(BatchDeskLockedError):
        stub.dispatch_flow_jobs((job,), now_ms=5_000, batch_account=locked)


def test_human_batch_desk_allows_after_daily_reset() -> None:
    stub = RenderBackendStub()
    account = AccountSnapshot(
        account_id="desk_2",
        daily_credits_left=0,
        next_daily_reset_utc_ms=50_000,
        first_daily_spend_utc_ms=1_000,
    )
    job = FlowJobDispatch(
        flow_job_id="fj_desk_ok",
        episode_id="ep_1",
        scene_id="sc_1",
        idempotency_key="idem-desk-ok",
        provider_route="HUMAN_BATCH_DESK",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1=PROMPT_V1,
        prompt_v2_safe=PROMPT_V2_SAFE,
        duration_bucket_sec=8,
        estimated_credits=1,
    )
    receipts = stub.dispatch_flow_jobs((job,), now_ms=60_000, batch_account=account)
    assert receipts[0].state == "QUEUED_BATCH_DESK"


def test_dispatch_rejects_nonzero_offline_estimate() -> None:
    stub = RenderBackendStub(spend_purpose="OFFLINE_TEST")
    job = FlowJobDispatch(
        flow_job_id="fj_bad_spend",
        episode_id="ep_1",
        scene_id="sc_1",
        idempotency_key="idem-spend",
        provider_route="GEMINI_OMNI_INTERACTIONS",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1=PROMPT_V1,
        prompt_v2_safe=PROMPT_V2_SAFE,
        duration_bucket_sec=8,
        estimated_micro_usd=500,
    )
    with pytest.raises(OfflineTestSpendError):
        stub.dispatch_flow_jobs((job,), now_ms=1_000)


def test_safety_block_two_strike_and_refuse_third(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        reserve(conn, reservation_id="res_a1", attempt_number=1)
        reserve(conn, reservation_id="res_a2", attempt_number=2)
        reserve(conn, reservation_id="res_a3", attempt_number=3)
        conn.commit()
    finally:
        conn.close()

    stub = RenderBackendStub(pipeline_db=db_path)
    first = stub.record_flow_attempt(
        flow_job_id="fj_strike",
        now_ms=7000,
        attempt_id="att_1",
        pool_source="GEMINI_API_USD",
        qa_verdict="PASS",
        total_output_tokens=0,
        cost_micro_usd=800_000,
        provider_operation_id="operations/strike-1",
        prompt_used="porch door, first take",
    )
    assert first.state == "STRIKE_1_RETRY_SAFE"
    assert first.reservation_status == "RELEASED"
    assert first.actual_micro_usd == 0
    assert first.retry_prompt == PROMPT_V2_SAFE

    second = stub.record_flow_attempt(
        flow_job_id="fj_strike",
        now_ms=8000,
        attempt_id="att_2",
        pool_source="GEMINI_API_USD",
        qa_verdict="FAIL_SAFETY_BLOCK",
        total_output_tokens=0,
        cost_micro_usd=800_000,
        provider_operation_id="operations/strike-2",
        prompt_used="caller text must not win",
    )
    assert second.state == "SWITCHED_TO_FALLBACK"
    assert second.prompt_used == PROMPT_V2_SAFE
    assert second.actual_micro_usd == 0

    with pytest.raises(sqlite3.IntegrityError, match="LAW_3_BREAKER"):
        stub.record_flow_attempt(
            flow_job_id="fj_strike",
            now_ms=9000,
            attempt_id="att_3",
            pool_source="GEMINI_API_USD",
            qa_verdict="FAIL_SAFETY_BLOCK",
            total_output_tokens=0,
            provider_operation_id="operations/strike-3",
        )