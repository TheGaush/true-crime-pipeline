"""Offline flow-job repository tests. Schema comes from schema/pipeline.sql; no network."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from flow_jobs_repo import (  # noqa: E402
    POOL_SOURCES,
    FlowJobRepository,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SQL = REPO_ROOT / "schema" / "pipeline.sql"
YEAR_MONTH = "2026-11"
PROMPT_V1 = "slow charcoal push toward the porch door"
PROMPT_V2_SAFE = "flashlight beam crosses rain on an empty porch"


def init_pipeline(path: Path) -> None:
    script = PIPELINE_SQL.read_text(encoding="utf-8")
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_case_and_episode(
    conn: sqlite3.Connection,
    *,
    episode_id: str = "ep_1",
    flow_backend_mode: str = "GEMINI_OMNI_INTERACTIONS",
) -> None:
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
        ) VALUES (?, 'case_1', 'AWAITING_FLOW_BATCH', ?, '911_CALL_IN_MEDIA_RES', 1000, 1000)
        """,
        (episode_id, flow_backend_mode),
    )


def seed_flow_job(
    conn: sqlite3.Connection,
    *,
    flow_job_id: str,
    scene_id: str,
    seq_index: int,
    start_ms: int,
    end_ms: int,
    provider_route: str = "GEMINI_OMNI_INTERACTIONS",
    engine_model: str = "gemini-omni-1.2-flash",
    prompt_v1: str = PROMPT_V1,
    prompt_v2_safe: str = PROMPT_V2_SAFE,
    episode_id: str = "ep_1",
) -> None:
    plan_id = f"sp_{scene_id}_v1"
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
          ?, ?, ?, 1, ?,
          'Establish arrival timeline', 'Curiosity hook', 'At 10:14 PM a silhouette crossed the porch.',
          'sha_nar_1', '["fact_1"]', 'Monochrome doorway pan',
          'FLOW_HERO_VIDEO', 'HeroVideoBridge', 'TEXT_TO_VIDEO', 'Slow charcoal camera push',
          'Crisp silhouette door entry', ?, ?,
          '{"type":"l_cut","ms":800}', 'Hold then cut', '["Fact cited","Safe-Zone clear"]',
          'sha_asset_1', 'EDITED_APPROVED', 'editor_jane', 1500,
          1000, 1500
        )
        """,
        (plan_id, episode_id, scene_id, seq_index, start_ms, end_ms),
    )
    conn.execute(
        """
        INSERT INTO scenes (
          scene_id, episode_id, scene_plan_id, seq_index, act_number,
          visual_engine, motif_component, start_ms, end_ms, timeline_spec_json,
          fallback_spec_json
        ) VALUES (?, ?, ?, ?, 1, 'FLOW_HERO_VIDEO', 'HeroVideoBridge', ?, ?, '{}', '{"engine":"STILL_2K_PANZOOM"}')
        """,
        (scene_id, episode_id, plan_id, seq_index, start_ms, end_ms),
    )
    conn.execute(
        """
        INSERT INTO flow_jobs (
          flow_job_id, episode_id, scene_id, idempotency_key, provider_route,
          engine_model, prompt_mode, duration_bucket_sec, prompt_v1, prompt_v2_safe,
          fallback_spec_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'TEXT_TO_VIDEO', 8, ?, ?, '{"engine":"STILL_2K_PANZOOM"}', 1000)
        """,
        (
            flow_job_id,
            episode_id,
            scene_id,
            f"idem-{flow_job_id}",
            provider_route,
            engine_model,
            prompt_v1,
            prompt_v2_safe,
        ),
    )


def reserve(
    conn: sqlite3.Connection,
    *,
    reservation_id: str,
    flow_job_id: str,
    attempt_number: int,
    estimated_micro_usd: int = 800_000,
    episode_id: str = "ep_1",
    provider_id: str = "gemini_omni",
) -> None:
    conn.execute(
        """
        INSERT INTO provider_spend_reservations (
          reservation_id, episode_id, job_id, attempt_number, provider_id,
          purpose, year_month, estimated_micro_usd, status, created_at
        ) VALUES (?, ?, ?, ?, ?, 'PRODUCTION', ?, ?, 'RESERVED', 1000)
        """,
        (
            reservation_id,
            episode_id,
            flow_job_id,
            attempt_number,
            provider_id,
            YEAR_MONTH,
            estimated_micro_usd,
        ),
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.db"
    init_pipeline(path)
    conn = connect(path)
    try:
        seed_case_and_episode(conn)
        conn.commit()
    finally:
        conn.close()
    return path


def test_schema_has_two_strike_trigger(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'trigger' AND name = 'trg_flow_two_strike_breaker'
            """
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert "attempts_used" in row["sql"]
    assert "LAW_3_BREAKER" in row["sql"]


def test_crash_states_and_operation_id_survive_reopen(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        seed_flow_job(conn, flow_job_id="fj_crash", scene_id="sc_crash", seq_index=1, start_ms=0, end_ms=8000)
        reserve(conn, reservation_id="res_crash", flow_job_id="fj_crash", attempt_number=1)
        conn.commit()
    finally:
        conn.close()

    FlowJobRepository(db_path).record_attempt(
        flow_job_id="fj_crash",
        now_ms=2000,
        state="SUBMITTING",
    )
    _assert_job_file(db_path, state="SUBMITTING", provider_operation_id=None, attempts_used=0)
    _assert_reservation(db_path, "res_crash", status="RESERVED", actual_micro_usd=None)

    FlowJobRepository(db_path).record_attempt(
        flow_job_id="fj_crash",
        now_ms=3000,
        state="RUNNING",
        provider_operation_id="operations/omni-77",
    )
    _assert_job_file(
        db_path,
        state="RUNNING",
        provider_operation_id="operations/omni-77",
        attempts_used=0,
    )

    FlowJobRepository(db_path).record_attempt(
        flow_job_id="fj_crash",
        now_ms=4000,
        state="UNKNOWN_RECONCILE",
    )
    _assert_job_file(
        db_path,
        state="UNKNOWN_RECONCILE",
        provider_operation_id="operations/omni-77",
        attempts_used=0,
    )
    _assert_reservation(db_path, "res_crash", status="UNKNOWN_HOLD", actual_micro_usd=None)


def test_pool_sources_round_trip_and_reject_unknown(db_path: Path) -> None:
    routes = {
        "GEMINI_API_USD": ("GEMINI_OMNI_INTERACTIONS", "gemini-omni-1.2-flash"),
        "VERTEX_USD": ("VERTEX_VEO_ENTERPRISE", "vertex-veo-enterprise"),
        "DAILY_CREDITS": ("HUMAN_BATCH_DESK", "manual-desk-video"),
        "MONTHLY_CREDITS": ("HUMAN_BATCH_DESK", "manual-desk-video"),
    }
    conn = connect(db_path)
    try:
        for index, pool_source in enumerate(POOL_SOURCES, start=1):
            route, engine = routes[pool_source]
            seed_flow_job(
                conn,
                flow_job_id=f"fj_{pool_source}",
                scene_id=f"sc_{index}",
                seq_index=index,
                start_ms=(index - 1) * 10_000,
                end_ms=index * 10_000,
                provider_route=route,
                engine_model=engine,
            )
        conn.commit()
    finally:
        conn.close()

    for pool_source in POOL_SOURCES:
        result = FlowJobRepository(db_path).record_attempt(
            flow_job_id=f"fj_{pool_source}",
            now_ms=5000,
            attempt_id=f"att_{pool_source}",
            pool_source=pool_source,
            qa_verdict="PASS",
            total_output_tokens=120,
            provider_operation_id=f"op-{pool_source}",
        )
        assert result.state == "ACCEPTED"
        assert result.pool_source == pool_source
        assert result.provider_operation_id == f"op-{pool_source}"

    reopened = connect(db_path)
    try:
        stored = {
            row["pool_source"]
            for row in reopened.execute("SELECT pool_source FROM flow_job_attempts")
        }
    finally:
        reopened.close()
    assert stored == set(POOL_SOURCES)

    with pytest.raises(ValueError, match="pool_source"):
        FlowJobRepository(db_path).record_attempt(
            flow_job_id="fj_GEMINI_API_USD",
            now_ms=6000,
            attempt_id="att_bad_pool",
            pool_source="FREE_POOL",
            qa_verdict="PASS",
            total_output_tokens=10,
        )


def test_safety_block_releases_zero_and_trigger_rejects_attempt_three(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        seed_flow_job(conn, flow_job_id="fj_strike", scene_id="sc_strike", seq_index=1, start_ms=0, end_ms=8000)
        reserve(conn, reservation_id="res_a1", flow_job_id="fj_strike", attempt_number=1)
        reserve(conn, reservation_id="res_a2", flow_job_id="fj_strike", attempt_number=2)
        reserve(conn, reservation_id="res_a3", flow_job_id="fj_strike", attempt_number=3)
        conn.commit()
    finally:
        conn.close()

    first = FlowJobRepository(db_path).record_attempt(
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
    assert first.qa_verdict == "FAIL_SAFETY_BLOCK"
    assert first.attempt_number == 1
    assert first.prompt_used == "porch door, first take"
    assert first.retry_prompt == PROMPT_V2_SAFE
    assert first.reservation_status == "RELEASED"
    assert first.actual_micro_usd == 0
    _assert_job_file(
        db_path,
        state="STRIKE_1_RETRY_SAFE",
        provider_operation_id="operations/strike-1",
        attempts_used=1,
        flow_job_id="fj_strike",
    )
    _assert_reservation(db_path, "res_a1", status="RELEASED", actual_micro_usd=0)
    _assert_reservation(db_path, "res_a2", status="RESERVED", actual_micro_usd=None)

    second = FlowJobRepository(db_path).record_attempt(
        flow_job_id="fj_strike",
        now_ms=8000,
        attempt_id="att_2",
        pool_source="GEMINI_API_USD",
        qa_verdict="FAIL_SAFETY_BLOCK",
        total_output_tokens=0,
        cost_micro_usd=800_000,
        provider_operation_id="operations/strike-2",
        prompt_used="this caller prompt must be ignored",
    )
    assert second.state == "SWITCHED_TO_FALLBACK"
    assert second.attempt_number == 2
    assert second.prompt_used == PROMPT_V2_SAFE
    assert second.reservation_status == "RELEASED"
    assert second.actual_micro_usd == 0
    _assert_job_file(
        db_path,
        state="SWITCHED_TO_FALLBACK",
        provider_operation_id="operations/strike-2",
        attempts_used=2,
        flow_job_id="fj_strike",
    )

    with pytest.raises(sqlite3.IntegrityError, match="LAW_3_BREAKER") as exc_info:
        FlowJobRepository(db_path).record_attempt(
            flow_job_id="fj_strike",
            now_ms=9000,
            attempt_id="att_3",
            pool_source="GEMINI_API_USD",
            qa_verdict="FAIL_SAFETY_BLOCK",
            total_output_tokens=0,
            provider_operation_id="operations/strike-3",
        )
    assert "LAW_3_BREAKER" in str(exc_info.value)

    reopened = connect(db_path)
    try:
        attempts = reopened.execute(
            """
            SELECT attempt_number, prompt_used, qa_verdict, cost_micro_usd, pool_source,
                   provider_operation_id
            FROM flow_job_attempts
            WHERE flow_job_id = 'fj_strike'
            ORDER BY attempt_number
            """
        ).fetchall()
        job = reopened.execute(
            """
            SELECT state, attempts_used, provider_operation_id
            FROM flow_jobs WHERE flow_job_id = 'fj_strike'
            """
        ).fetchone()
    finally:
        reopened.close()

    assert [row["attempt_number"] for row in attempts] == [1, 2]
    assert attempts[0]["qa_verdict"] == "FAIL_SAFETY_BLOCK"
    assert attempts[0]["cost_micro_usd"] == 0
    assert attempts[0]["pool_source"] == "GEMINI_API_USD"
    assert attempts[1]["prompt_used"] == PROMPT_V2_SAFE
    assert attempts[1]["cost_micro_usd"] == 0
    assert job["state"] == "SWITCHED_TO_FALLBACK"
    assert job["attempts_used"] == 2
    assert job["provider_operation_id"] == "operations/strike-2"
    _assert_reservation(db_path, "res_a1", status="RELEASED", actual_micro_usd=0)
    _assert_reservation(db_path, "res_a2", status="RELEASED", actual_micro_usd=0)
    _assert_reservation(db_path, "res_a3", status="RESERVED", actual_micro_usd=None)


def test_paid_failure_strikes_without_releasing_reservation(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        seed_flow_job(
            conn,
            flow_job_id="fj_morph",
            scene_id="sc_morph",
            seq_index=1,
            start_ms=0,
            end_ms=8000,
            provider_route="HUMAN_BATCH_DESK",
            engine_model="manual-desk-video",
        )
        reserve(conn, reservation_id="res_morph", flow_job_id="fj_morph", attempt_number=1)
        conn.commit()
    finally:
        conn.close()

    result = FlowJobRepository(db_path).record_attempt(
        flow_job_id="fj_morph",
        now_ms=6500,
        attempt_id="att_morph",
        pool_source="DAILY_CREDITS",
        qa_verdict="FAIL_MORPH",
        total_output_tokens=40,
        credits_charged=10,
    )
    assert result.state == "STRIKE_1_RETRY_SAFE"
    assert result.retry_prompt == PROMPT_V2_SAFE
    assert result.reservation_status is None
    _assert_reservation(db_path, "res_morph", status="RESERVED", actual_micro_usd=None)


def _assert_job_file(
    path: Path,
    *,
    state: str,
    provider_operation_id: str | None,
    attempts_used: int,
    flow_job_id: str = "fj_crash",
) -> None:
    conn = connect(path)
    try:
        row = conn.execute(
            """
            SELECT state, provider_operation_id, attempts_used
            FROM flow_jobs WHERE flow_job_id = ?
            """,
            (flow_job_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["state"] == state
    assert row["provider_operation_id"] == provider_operation_id
    assert row["attempts_used"] == attempts_used


def _assert_reservation(
    path: Path,
    reservation_id: str,
    *,
    status: str,
    actual_micro_usd: int | None,
) -> None:
    conn = connect(path)
    try:
        row = conn.execute(
            """
            SELECT status, actual_micro_usd, settled_at
            FROM provider_spend_reservations
            WHERE reservation_id = ?
            """,
            (reservation_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row["status"] == status
    assert row["actual_micro_usd"] == actual_micro_usd
    if status == "RELEASED":
        assert row["settled_at"] is not None
        assert row["actual_micro_usd"] == 0
    else:
        assert row["settled_at"] is None
