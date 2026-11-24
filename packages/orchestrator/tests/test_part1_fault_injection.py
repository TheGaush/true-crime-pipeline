"""Task 099 · Part 1 fault-injection soak tests (offline, in-memory).

Recovery rules are encoded in ``RECOVERY_RULES`` and exercised without live APIs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from orchestrator.fault_recovery import (
    ABORTED_COPYCAT_WAVE,
    EVIDENCE_AND_2K_LOCKED,
    UNKNOWN_RECONCILE,
    InMemory429Dispatcher,
    Part1StillCheckpoint,
    count_flow_jobs_for_scene,
    evaluate_day2_wave_abort,
    extract_query,
    lock_early_2k_anchor,
    mark_unknown_reconcile_on_crash,
    open_pipeline_memory,
    purge_expired_youtube_fields,
    recover_after_anchor_lock_crash,
    settle_unknown_reconciled_job,
    startup_reconcile_inflight,
)

RECOVERY_RULES: tuple[dict[str, str], ...] = (
    {
        "id": "F-10-crash-reconcile",
        "rule": (
            "A crash in SUBMITTING or RUNNING marks the existing flow_jobs row "
            "UNKNOWN_RECONCILE, moves budget_reservations to UNKNOWN_HOLD, and "
            "forbids a second paid flow_jobs row for the same (episode_id, scene_id)."
        ),
    },
    {
        "id": "F-10-429-idempotency",
        "rule": (
            "HTTP 429 responses honor bounded Retry-After backoff and retry the "
            "same idempotency_key without creating a duplicate paid scene job."
        ),
    },
    {
        "id": "F-03-disposition-quarantine",
        "rule": (
            "An UPDATE that flips cases.disposition_status to REVERSED quarantines "
            "active downstream episodes to QUARANTINED_LEGAL_HOLD and revokes "
            "APPROVED release_approvals."
        ),
    },
    {
        "id": "F-08-day2-copycat-abort",
        "rule": (
            "On batch Day 2, when spent_credits_pct is 20% and N_14d_wave is large "
            "(> 5), the episode aborts as ABORTED_COPYCAT_WAVE without sunk-cost override."
        ),
    },
    {
        "id": "F-20-youtube-30d-purge",
        "rule": (
            "After 30 days, purge_expired_yt_api_records clears all YouTube API-derived "
            "fields on TRACK_A_OUTLIER rows while primary-record cases rows persist."
        ),
    },
    {
        "id": "checkpoint-2k-resume",
        "rule": (
            "A crash after the early 2K anchor is LOCKED resumes at "
            "EVIDENCE_AND_2K_LOCKED without incrementing still_generation_count."
        ),
    },
)

assert len(RECOVERY_RULES) == 6


def _seed_flow_scene(conn: sqlite3.Connection) -> None:
    conn.execute(
        """INSERT INTO cases (
             case_id, defendant_name, incident_year, jurisdiction, docket_id,
             primary_record_verified, verification_source, disposition_status,
             conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
             anonymization_artifact_sha256, created_at, updated_at
           ) VALUES (
             'case_1','John Doe',2023,'Mercer, NJ','DK-1',1,'courtlistener','AFFIRMED',1,
             'APPROVED','reviewer_a',1000,'sha_anon_1',1000,1000
           )"""
    )
    conn.execute(
        """INSERT INTO episodes (
             episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
             updated_at, created_at
           ) VALUES (
             'ep_1','case_1','AWAITING_FLOW_BATCH','GEMINI_OMNI_INTERACTIONS',
             '911_CALL_IN_MEDIA_RES',1000,1000
           )"""
    )
    conn.execute(
        """INSERT INTO scene_plans (
             scene_plan_id, episode_id, scene_id, plan_version, seq_index, story_purpose,
             intended_audience_effect, approved_narration_text, narration_version_sha256,
             cited_fact_ids_json, visual_concept, visual_engine, motif_component, prompt_mode,
             visual_prompt, keyframe_refs_json, expected_output_summary, timing_start_ms,
             timing_end_ms, transition_spec_json, sound_cues_json, edit_instructions,
             acceptance_criteria_json, asset_version_sha256, plan_status, reviewed_by,
             reviewed_at, created_at, updated_at
           ) VALUES (
             'sp_s1','ep_1','s1',1,1,'Establish arrival timeline','Curiosity hook',
             'At 10:14 PM a silhouette crossed the porch.','sha_nar_1','["fact_1"]',
             'Monochrome doorway pan','FLOW_HERO_VIDEO','HeroVideoBridge','TEXT_TO_VIDEO',
             'Slow charcoal camera push toward porch door','[]','Crisp silhouette door entry',
             0,12000,'{"type":"l_cut","ms":800}','[{"cue":"door_creak"}]',
             'Hold title 2.8s then cut on dialogue','["Fact cited","Safe-Zone clear"]',
             'sha_asset_1','EDITED_APPROVED','editor_jane',1500,1000,1500
           )"""
    )
    conn.execute(
        """INSERT INTO scenes (
             scene_id, episode_id, scene_plan_id, seq_index, act_number, visual_engine,
             motif_component, start_ms, end_ms, timeline_spec_json
           ) VALUES (
             's1','ep_1','sp_s1',1,1,'FLOW_HERO_VIDEO','HeroVideoBridge',0,12000,'{}'
           )"""
    )


def _insert_flow_job(
    conn: sqlite3.Connection,
    *,
    flow_job_id: str,
    state: str,
    idempotency_key: str = "idem-crash-1",
) -> None:
    conn.execute(
        """INSERT INTO flow_jobs (
             flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
             duration_bucket_sec, prompt_v1, prompt_v2_safe, fallback_spec_json,
             provider_operation_id, state, updated_at
           ) VALUES (
             ?, 'ep_1', 's1', ?, 'TEXT_TO_VIDEO', 12, 'p1', 'p2', '{}', 'op_1', ?, 1000
           )""",
        (flow_job_id, idempotency_key, state),
    )


def _reserve_budget(conn: sqlite3.Connection, *, job_id: str) -> str:
    reservation_id = f"res_{job_id}"
    conn.execute(
        extract_query("reserve_provider_budget"),
        {
            "reservation_id": reservation_id,
            "episode_id": "ep_1",
            "job_id": job_id,
            "attempt_number": 1,
            "provider_id": "gemini_omni",
            "purpose": "OFFLINE_TEST",
            "year_month": "2026-11",
            "estimated_micro_usd": 0,
            "now_ms": 1000,
        },
    )
    return reservation_id


@pytest.mark.parametrize("crash_state", ["SUBMITTING", "RUNNING"])
def test_crash_mid_dispatch_unknown_reconcile_no_duplicate_job(crash_state: str) -> None:
    """RECOVERY_RULES F-10-crash-reconcile."""

    conn = open_pipeline_memory()
    try:
        _seed_flow_scene(conn)
        job_id = f"fj_{crash_state.lower()}"
        _insert_flow_job(conn, flow_job_id=job_id, state=crash_state)
        _reserve_budget(conn, job_id=job_id)

        mark_unknown_reconcile_on_crash(conn, flow_job_id=job_id, now_ms=2000)

        job = conn.execute(
            "SELECT state FROM flow_jobs WHERE flow_job_id = ?", (job_id,)
        ).fetchone()
        hold = conn.execute(
            "SELECT status FROM provider_spend_reservations WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        assert job["state"] == UNKNOWN_RECONCILE
        assert hold["status"] == "UNKNOWN_HOLD"
        assert count_flow_jobs_for_scene(conn, episode_id="ep_1", scene_id="s1") == 1

        with pytest.raises(sqlite3.Error):
            conn.execute(
                """INSERT INTO flow_jobs (
                     flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
                     duration_bucket_sec, prompt_v1, prompt_v2_safe, fallback_spec_json,
                     state, updated_at
                   ) VALUES (
                     'fj_dup','ep_1','s1','idem-dup','TEXT_TO_VIDEO',8,'p1','p2','{}',
                     'PENDING',2001
                   )"""
            )
    finally:
        conn.close()


def test_startup_reconcile_marks_all_inflight_jobs() -> None:
    conn = open_pipeline_memory()
    try:
        _seed_flow_scene(conn)
        _insert_flow_job(conn, flow_job_id="fj_sub", state="SUBMITTING", idempotency_key="idem-a")
        conn.execute(
            """INSERT INTO scenes (
                 scene_id, episode_id, scene_plan_id, seq_index, act_number, visual_engine,
                 motif_component, start_ms, end_ms, timeline_spec_json
               ) VALUES (
                 's2','ep_1','sp_s1',2,1,'FLOW_HERO_VIDEO','HeroVideoBridge',12000,20000,'{}'
               )"""
        )
        conn.execute(
            """INSERT INTO flow_jobs (
                 flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
                 duration_bucket_sec, prompt_v1, prompt_v2_safe, fallback_spec_json,
                 state, updated_at
               ) VALUES (
                 'fj_run2','ep_1','s2','idem-c','TEXT_TO_VIDEO',8,'p1','p2','{}','RUNNING',1000
               )"""
        )

        reconciled = startup_reconcile_inflight(conn, now_ms=3000)
        assert set(reconciled) == {"fj_sub", "fj_run2"}
        states = {
            row["flow_job_id"]: row["state"]
            for row in conn.execute("SELECT flow_job_id, state FROM flow_jobs").fetchall()
        }
        assert all(state == UNKNOWN_RECONCILE for state in states.values())
    finally:
        conn.close()


def test_settle_reconciled_job_before_retry_preserves_single_row() -> None:
    conn = open_pipeline_memory()
    try:
        _seed_flow_scene(conn)
        job_id = "fj_rec"
        _insert_flow_job(conn, flow_job_id=job_id, state="RUNNING")
        reservation_id = _reserve_budget(conn, job_id=job_id)
        mark_unknown_reconcile_on_crash(conn, flow_job_id=job_id, now_ms=1500)
        settle_unknown_reconciled_job(
            conn,
            flow_job_id=job_id,
            reservation_id=reservation_id,
            final_status="RELEASED",
            actual_micro_usd=0,
            now_ms=1600,
        )
        assert count_flow_jobs_for_scene(conn, episode_id="ep_1", scene_id="s1") == 1
        assert (
            conn.execute(
                "SELECT state FROM flow_jobs WHERE flow_job_id = ?", (job_id,)
            ).fetchone()["state"]
            == "ACCEPTED"
        )
    finally:
        conn.close()


def test_429_backoff_retries_same_idempotency_key() -> None:
    """RECOVERY_RULES F-10-429-idempotency."""

    dispatcher = InMemory429Dispatcher(retry_after_ms=500, fail_before_success=2)
    key = "sha256:ep_1:s1:prompt:v1"
    trace = dispatcher.dispatch_with_backoff(idempotency_key=key, http_statuses=(429, 429, 200))

    assert trace.idempotency_key == key
    assert trace.retry_count == 2
    assert trace.backoff_ms == (500, 500)
    assert dispatcher.paid_dispatches == 1
    assert all(used == key for used in dispatcher.idempotency_keys_used)
    assert len(set(dispatcher.idempotency_keys_used)) == 1


def test_reversed_disposition_quarantines_and_revokes_approvals() -> None:
    """RECOVERY_RULES F-03-disposition-quarantine."""

    conn = open_pipeline_memory()
    try:
        conn.execute(
            """INSERT INTO cases (
                 case_id, defendant_name, incident_year, jurisdiction, docket_id,
                 primary_record_verified, verification_source, disposition_status,
                 conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
                 anonymization_artifact_sha256, created_at, updated_at
               ) VALUES (
                 'case_1','John Doe',2023,'Mercer, NJ','DK-1',1,'courtlistener','AFFIRMED',1,
                 'APPROVED','reviewer_a',1000,'sha_anon_1',1000,1000
               )"""
        )
        conn.execute(
            """INSERT INTO episodes (
                 episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
                 updated_at, created_at
               ) VALUES (
                 'ep_1','case_1','PENDING_HUMAN_SIGNOFF','GEMINI_OMNI_INTERACTIONS',
                 '911_CALL_IN_MEDIA_RES',1000,1000
               )"""
        )
        conn.execute(
            """INSERT INTO release_approvals
               VALUES ('ap_1','ep_1','FACTUAL_ACCURACY','sha_bundle_1','APPROVED','rev_1',1001,'ok')"""
        )

        with pytest.raises(sqlite3.Error, match="LEGAL_DISPOSITION"):
            conn.execute(
                "UPDATE cases SET disposition_status = 'REVERSED', updated_at = 2000 "
                "WHERE case_id = 'case_1'"
            )

        conn.execute(
            """UPDATE cases
               SET disposition_status = 'REVERSED', conviction_confirmed = 0, updated_at = 2000
               WHERE case_id = 'case_1'"""
        )
        assert (
            conn.execute("SELECT state FROM episodes WHERE episode_id = 'ep_1'").fetchone()["state"]
            == "QUARANTINED_LEGAL_HOLD"
        )
        assert (
            conn.execute(
                "SELECT status FROM release_approvals WHERE approval_id = 'ap_1'"
            ).fetchone()["status"]
            == "REVOKED"
        )
    finally:
        conn.close()


def test_day2_twenty_percent_large_14d_wave_aborts() -> None:
    """RECOVERY_RULES F-08-day2-copycat-abort."""

    decision, aborted = evaluate_day2_wave_abort(
        batch_day=2,
        n_14d_wave=6,
        spent_credits_pct=0.20,
    )
    assert decision == ABORTED_COPYCAT_WAVE
    assert aborted == 1


def test_youtube_30d_purge_clears_api_fields_case_row_remains() -> None:
    """RECOVERY_RULES F-20-youtube-30d-purge."""

    conn = open_pipeline_memory()
    try:
        conn.execute(
            """INSERT INTO cases (
                 case_id, defendant_name, incident_year, jurisdiction,
                 verification_source, disposition_status, conviction_confirmed,
                 created_at, updated_at
               ) VALUES (
                 'case_yt','Jane Doe',2022,'Ocean, NJ','courtlistener','AFFIRMED',1,1000,1000
               )"""
        )
        conn.execute(
            """INSERT INTO outlier_candidates (
                 candidate_id, track, source_video_id, views_count, outlier_ratio,
                 saturation_index, seed_packet_json, raw_yt_payload_json, yt_ttl_expires_at,
                 status, created_at
               ) VALUES (
                 'c_ok','TRACK_A_OUTLIER','v1',50000,10.0,20,'{"yt_title":"x"}','{"raw":1}',
                 2000,'GREENLIT',1000
               )"""
        )
        touched = purge_expired_youtube_fields(conn, now_ms=2500)
        assert touched >= 1
        purged = conn.execute(
            """SELECT views_count, raw_yt_payload_json, status
               FROM outlier_candidates WHERE candidate_id='c_ok'"""
        ).fetchone()
        assert purged["views_count"] is None
        assert purged["raw_yt_payload_json"] is None
        assert purged["status"] == "EXPIRED_TOS_PURGED"
        case = conn.execute(
            "SELECT case_id FROM cases WHERE case_id = 'case_yt'"
        ).fetchone()
        assert case is not None
    finally:
        conn.close()


def test_crash_after_2k_anchor_lock_resumes_without_regenerating_still() -> None:
    """RECOVERY_RULES checkpoint-2k-resume."""

    before = Part1StillCheckpoint(
        episode_id="ep_2k",
        pipeline_state="SCOUTED",
        anchor_lock_status="DRAFT",
        still_2k_id=None,
        still_sha256=None,
        still_generation_count=0,
    )
    locked = lock_early_2k_anchor(
        before,
        still_2k_id="st_anc",
        still_sha256="9c31da772cc099b3248d697cd1f65572d7cbb0bd66416b9dc66adccd56218d02",
    )
    assert locked.pipeline_state == EVIDENCE_AND_2K_LOCKED
    assert locked.anchor_lock_status == "LOCKED"

    resumed = recover_after_anchor_lock_crash(locked)
    assert resumed.pipeline_state == EVIDENCE_AND_2K_LOCKED
    assert resumed.still_sha256 == locked.still_sha256
    assert resumed.still_generation_count == 0
    assert resumed.still_2k_id == "st_anc"


def test_recovery_rules_registry_complete() -> None:
    ids = {rule["id"] for rule in RECOVERY_RULES}
    assert ids == {
        "F-10-crash-reconcile",
        "F-10-429-idempotency",
        "F-03-disposition-quarantine",
        "F-08-day2-copycat-abort",
        "F-20-youtube-30d-purge",
        "checkpoint-2k-resume",
    }