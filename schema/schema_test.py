"""Python mirror of schema/schema-test.js (pipeline.db v5 + telemetry.db).

Sixteen pytest scenarios, grouped exactly like the Node script. Named statements
come from schema/queries.sql `-- name:` blocks. The SQL files are the authority;
this module does not rewrite them.

Documented runtime is SQLite >= 3.51.3 (WAL-reset fix). Older stdlib builds still
load the DDL. A statement is skipped only when this interpreter is below that
version and the statement fails as a parse/feature gap. The guard stays in SQL.
"""

from __future__ import annotations

import re
import sqlite3
import warnings
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).resolve().parent
PIPELINE_SQL = (SCHEMA_DIR / "pipeline.sql").read_text(encoding="utf-8")
TELEMETRY_SQL = (SCHEMA_DIR / "telemetry.sql").read_text(encoding="utf-8")
QUERIES_SQL = (SCHEMA_DIR / "queries.sql").read_text(encoding="utf-8")

# F-22 pin. Python's bundled SQLite may be older; do not weaken the SQL for that.
DOCUMENTED_MIN_SQLITE = (3, 51, 3)
ILLUSTRATIVE_WATERMARK = "ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO"

# Populated only when a statement is skipped for an older SQLite library.
SKIPPED_FOR_SQLITE_VERSION: list[str] = []


def extract_query(name: str) -> str:
    match = re.search(
        rf"-- name: {re.escape(name)}\r?\n([\s\S]*?)(?=\r?\n-- name:|$)",
        QUERIES_SQL,
    )
    assert match, f"Query '{name}' not found in queries.sql"
    return match.group(1).strip()


def _connect() -> sqlite3.Connection:
    # Autocommit matches node:sqlite DatabaseSync (each statement stands alone).
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _split_statements(script: str) -> list[str]:
    """Split on SQLite's own complete-statement rule so trigger bodies stay intact."""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            text = buffer.strip()
            buffer = ""
            if text:
                statements.append(text)
    tail = buffer.strip()
    if tail:
        statements.append(tail)
    return statements


def _version_gap(exc: sqlite3.Error) -> bool:
    if sqlite3.sqlite_version_info >= DOCUMENTED_MIN_SQLITE:
        return False
    text = str(exc).lower()
    return (
        "syntax error" in text
        or "unrecognized token" in text
        or "not supported" in text
    )


def _load_script(conn: sqlite3.Connection, script: str, label: str) -> None:
    # `label` is part of the call site so a version-gap failure can name the file.
    # Skips themselves happen in _open_with_version_skips, on a fresh connection.
    _ = label
    conn.executescript(script)
    conn.execute("PRAGMA foreign_keys = ON")


def _open_with_version_skips(scripts: list[tuple[str, str]]) -> sqlite3.Connection:
    conn = _connect()
    for label, script in scripts:
        for statement in _split_statements(script):
            try:
                conn.execute(statement)
            except sqlite3.Error as exc:
                if _version_gap(exc):
                    reason = (
                        f"{label}: skipped on SQLite {sqlite3.sqlite_version} "
                        f"(documented minimum 3.51.3) because the statement is a "
                        f"version gap ({exc}). Guard left in the SQL file. "
                        f"Statement starts: {statement[:160]!r}"
                    )
                    SKIPPED_FOR_SQLITE_VERSION.append(reason)
                    warnings.warn(reason, RuntimeWarning, stacklevel=2)
                    continue
                conn.close()
                raise
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_db(*scripts: tuple[str, str]) -> sqlite3.Connection:
    conn = _connect()
    try:
        for label, script in scripts:
            _load_script(conn, script, label)
        return conn
    except sqlite3.Error as exc:
        conn.close()
        if not _version_gap(exc):
            raise
        return _open_with_version_skips(list(scripts))


def setup_db() -> sqlite3.Connection:
    return open_db(("pipeline.sql", PIPELINE_SQL))


def setup_telemetry() -> sqlite3.Connection:
    return open_db(("telemetry.sql", TELEMETRY_SQL))


def _bind(params: dict) -> dict:
    bound = {}
    for key, value in params.items():
        bound[key[1:] if key.startswith(":") else key] = value
    return bound


def query_get(conn: sqlite3.Connection, sql: str, params: dict | None = None):
    row = conn.execute(sql, _bind(params or {})).fetchone()
    return row


def seed_approved_case_and_episode(conn: sqlite3.Connection, ep_state: str = "MASTERED") -> None:
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
             total_master_ms, timeline_validated_sha256, ready_bundle_sha256,
             updated_at, created_at
           ) VALUES (
             'ep_1','case_1',?,'GEMINI_OMNI_INTERACTIONS','911_CALL_IN_MEDIA_RES',
             1200000,'sha_tl_1','sha_bundle_1',1000,1000
           )""",
        (ep_state,),
    )


def insert_approved_scene_plan_and_scene(
    conn: sqlite3.Connection,
    scene_id: str = "sc_1",
    seq: int = 1,
    engine: str = "FLOW_HERO_VIDEO",
    motif: str = "HeroVideoBridge",
    start_ms: int = 0,
    end_ms: int = 8000,
) -> str:
    scene_plan_id = f"sp_{scene_id}_v1"
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
             ?, 'ep_1', ?, 1, ?, 'Establish arrival timeline', 'Curiosity hook',
             'At 10:14 PM a silhouette crossed the porch.', 'sha_nar_1', '["fact_1"]',
             'Monochrome doorway pan', ?, ?, 'TEXT_TO_VIDEO',
             'Slow charcoal camera push toward porch door', '[]', 'Crisp silhouette door entry',
             ?, ?, '{"type":"l_cut","ms":800}', '[{"cue":"door_creak"}]',
             'Hold title 2.8s then cut on dialogue', '["Fact cited","Safe-Zone clear"]',
             'sha_asset_1', 'EDITED_APPROVED', 'editor_jane', 1500, 1000, 1500
           )""",
        (scene_plan_id, scene_id, seq, engine, motif, start_ms, end_ms),
    )
    conn.execute(
        """INSERT INTO scenes (
             scene_id, episode_id, scene_plan_id, seq_index, act_number, visual_engine,
             motif_component, start_ms, end_ms, timeline_spec_json
           ) VALUES (?, 'ep_1', ?, ?, 1, ?, ?, ?, ?, '{}')""",
        (scene_id, scene_plan_id, seq, engine, motif, start_ms, end_ms),
    )
    return scene_plan_id


def test_01_telemetry_cached_input_tokens_strict() -> None:
    """1. cached_input_tokens <= total_input_tokens, STRICT telemetry."""
    tdb = setup_telemetry()
    try:
        with pytest.raises(sqlite3.Error):
            tdb.execute(
                """INSERT INTO api_token_usage (
                     episode_id, agent_name, model_id, is_off_peak, total_input_tokens,
                     cached_input_tokens, output_tokens, cost_micro_usd, created_at
                   ) VALUES (
                     'ep_01','agent4','DeepSeek-V4.1-Flash-1017',1,10000,25000,12000,15000,1700000000000
                   )"""
            )
        tdb.execute(
            """INSERT INTO api_token_usage (
                 episode_id, agent_name, model_id, is_off_peak, total_input_tokens,
                 cached_input_tokens, output_tokens, cost_micro_usd, created_at
               ) VALUES (
                 'ep_01','agent4','DeepSeek-V4.1-Flash-1017',1,35000,25000,12000,15000,1700000000000
               )"""
        )
        assert tdb.execute("SELECT COUNT(*) AS c FROM api_token_usage").fetchone()["c"] == 1
    finally:
        tdb.close()


def test_02_lookup_tables_seed_v5_metadata() -> None:
    """2. schema v5, gemini-omni-1.2-flash, whisperx-local, $0 offline cap, 4 MVP motifs."""
    db = setup_db()
    try:
        assert db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()["value"] == "5"
        assert (
            db.execute(
                "SELECT value FROM meta WHERE key='live_sandbox_lifetime_cap_micro_usd'"
            ).fetchone()["value"]
            == "2000000"
        )
        assert (
            db.execute("SELECT value FROM meta WHERE key='primary_video_model'").fetchone()["value"]
            == "gemini-omni-1.2-flash"
        )
        assert (
            db.execute("SELECT value FROM meta WHERE key='primary_word_aligner'").fetchone()["value"]
            == "whisperx-local"
        )
        assert (
            db.execute(
                "SELECT value FROM meta WHERE key='offline_test_spend_cap_micro_usd'"
            ).fetchone()["value"]
            == "0"
        )
        assert db.execute("SELECT COUNT(*) AS c FROM motif_registry WHERE is_mvp_4 = 1").fetchone()["c"] == 4
    finally:
        db.close()


def test_03_offline_test_zero_spend_and_global_cap() -> None:
    """3. OFFLINE_TEST must be $0, and ALL_PROVIDERS $135/mo blocks cross-provider overage."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "AWAITING_FLOW_BATCH")
        reserve_sql = extract_query("reserve_provider_budget")

        with pytest.raises(sqlite3.Error, match="OFFLINE_TEST_ZERO_SPEND"):
            query_get(
                db,
                reserve_sql,
                {
                    ":reservation_id": "r_test_bad",
                    ":episode_id": "ep_1",
                    ":job_id": "job_t",
                    ":attempt_number": 1,
                    ":provider_id": "deepseek_chat",
                    ":purpose": "OFFLINE_TEST",
                    ":year_month": "2026-11",
                    ":estimated_micro_usd": 1000,
                    ":now_ms": 1000,
                },
            )

        query_get(
            db,
            reserve_sql,
            {
                ":reservation_id": "r_ds_1",
                ":episode_id": "ep_1",
                ":job_id": "job_ds_1",
                ":attempt_number": 1,
                ":provider_id": "deepseek_chat",
                ":purpose": "PRODUCTION",
                ":year_month": "2026-11",
                ":estimated_micro_usd": 38_000_000,
                ":now_ms": 1000,
            },
        )

        db.execute(
            """UPDATE monthly_budget_ledger
               SET hard_cap_micro_usd = 120000000
               WHERE year_month='2026-11' AND provider_id='gemini_omni'"""
        )
        db.execute(
            "UPDATE episodes SET video_budget_cap_micro_usd = 120000000 WHERE episode_id='ep_1'"
        )
        with pytest.raises(sqlite3.Error, match="GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"):
            query_get(
                db,
                reserve_sql,
                {
                    ":reservation_id": "r_omni_over",
                    ":episode_id": "ep_1",
                    ":job_id": "job_omni_1",
                    ":attempt_number": 1,
                    ":provider_id": "gemini_omni",
                    ":purpose": "PRODUCTION",
                    ":year_month": "2026-11",
                    ":estimated_micro_usd": 98_000_000,
                    ":now_ms": 1001,
                },
            )
    finally:
        db.close()


def test_04_scene_plan_stale_on_edit_and_five_gate_release() -> None:
    """4. Narration edit marks the ScenePlan stale and the 5-gate release stays blocked."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "MASTERED")
        scene_plan_id = insert_approved_scene_plan_and_scene(db, "sc_1", 1)
        gates = [
            "FACTUAL_ACCURACY",
            "PRIVACY_PII",
            "SOURCE_RIGHTS",
            "SYNTHETIC_DISCLOSURE",
            "ILLUSTRATIVE_LABELING",
        ]
        for idx, gate in enumerate(gates):
            db.execute(
                """INSERT INTO release_approvals
                   VALUES (?, 'ep_1', ?, 'sha_bundle_1', 'APPROVED', 'editor_jane', 2000, 'verified')""",
                (f"ap_{idx}", gate),
            )

        db.execute(
            """UPDATE scene_plans
               SET approved_narration_text = 'Revised 10:19 PM narration.',
                   narration_version_sha256 = 'sha_nar_2',
                   updated_at = 3000
               WHERE scene_plan_id = ?""",
            (scene_plan_id,),
        )
        assert (
            db.execute(
                "SELECT plan_status FROM scene_plans WHERE scene_plan_id = ?",
                (scene_plan_id,),
            ).fetchone()["plan_status"]
            == "STALE_NEEDS_REAPPROVAL"
        )
        assert (
            db.execute(
                "SELECT timeline_validated_sha256 FROM episodes WHERE episode_id = 'ep_1'"
            ).fetchone()["timeline_validated_sha256"]
            is None
        )

        with pytest.raises(sqlite3.Error, match="RELEASE_GATE_BLOCKED"):
            db.execute("UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'")

        db.execute(
            """UPDATE scene_plans
               SET asset_version_sha256 = 'sha_asset_2',
                   plan_status = 'EDITED_APPROVED',
                   reviewed_by = 'editor_jane',
                   reviewed_at = 3500
               WHERE scene_plan_id = ?""",
            (scene_plan_id,),
        )
        db.execute(
            "UPDATE episodes SET timeline_validated_sha256 = 'sha_tl_2' WHERE episode_id = 'ep_1'"
        )
        db.execute(
            """INSERT INTO qa_reports VALUES
               ('qa_1','ep_1',-14.0,-1.5,1,1,'PASSED',1,'final.mp4','sha_mp4',4000)"""
        )
        db.execute(
            """INSERT INTO compliance_audits VALUES
               ('aud_1','case_1',1,1,1,1,1,1,4000)"""
        )
        db.execute("UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'")
        assert (
            db.execute("SELECT state FROM episodes WHERE episode_id = 'ep_1'").fetchone()["state"]
            == "READY_TO_UPLOAD"
        )
    finally:
        db.close()


def test_05_disposition_guard_and_quarantine_on_update() -> None:
    """5. Disposition guard covers INSERT and UPDATE, then quarantines downstream episodes."""
    db = setup_db()
    try:
        with pytest.raises(sqlite3.Error, match="LEGAL_DISPOSITION"):
            db.execute(
                """INSERT INTO cases (
                     case_id, defendant_name, incident_year, jurisdiction, verification_source,
                     disposition_status, conviction_confirmed, created_at, updated_at
                   ) VALUES (
                     'case_rev','Jane Doe',2023,'Mercer, NJ','courtlistener','REVERSED',1,1000,1000
                   )"""
            )

        seed_approved_case_and_episode(db, "PENDING_HUMAN_SIGNOFF")
        db.execute(
            """INSERT INTO release_approvals
               VALUES ('ap_1','ep_1','FACTUAL_ACCURACY','sha_bundle_1','APPROVED','rev_1',1001,'ok')"""
        )

        with pytest.raises(sqlite3.Error, match="LEGAL_DISPOSITION"):
            db.execute(
                """UPDATE cases
                   SET disposition_status = 'REVERSED', updated_at = 2000
                   WHERE case_id = 'case_1'"""
            )

        db.execute(
            """UPDATE cases
               SET disposition_status = 'REVERSED', conviction_confirmed = 0, updated_at = 2000
               WHERE case_id = 'case_1'"""
        )
        assert (
            db.execute("SELECT state FROM episodes WHERE episode_id = 'ep_1'").fetchone()["state"]
            == "QUARANTINED_LEGAL_HOLD"
        )
        assert (
            db.execute(
                "SELECT status FROM release_approvals WHERE approval_id = 'ap_1'"
            ).fetchone()["status"]
            == "REVOKED"
        )
    finally:
        db.close()


def test_06_anonymization_anchor_defaults_and_illustrative_watermark() -> None:
    """6. Anonymization and anchor locks default unapproved; 2K plates stay illustrative."""
    db = setup_db()
    try:
        db.execute(
            """INSERT INTO cases (
                 case_id, defendant_name, incident_year, jurisdiction, verification_source,
                 disposition_status, conviction_confirmed, created_at, updated_at
               ) VALUES (
                 'case_raw','John Doe',2023,'Mercer, NJ','courtlistener','AFFIRMED',1,1000,1000
               )"""
        )
        assert (
            db.execute(
                "SELECT anonymization_status FROM cases WHERE case_id = 'case_raw'"
            ).fetchone()["anonymization_status"]
            == "NOT_STARTED"
        )

        db.execute(
            """INSERT INTO episodes (
                 episode_id, case_id, state, cold_open_archetype, updated_at, created_at
               ) VALUES (
                 'ep_raw','case_raw','EVIDENCE_AND_2K_LOCKED','ALIBI_THAT_CRACKED',1000,1000
               )"""
        )
        db.execute(
            """INSERT INTO still_assets (
                 still_2k_id, episode_id, asset_path, asset_sha256, width_px, height_px, created_at
               ) VALUES ('st_1','ep_raw','room.png','sha_room',2560,1440,1000)"""
        )
        plate = db.execute(
            """SELECT is_illustrative_reconstruction, disclaimer_label_text
               FROM still_assets WHERE still_2k_id = 'st_1'"""
        ).fetchone()
        assert plate["is_illustrative_reconstruction"] == 1
        assert plate["disclaimer_label_text"] == ILLUSTRATIVE_WATERMARK
        with pytest.raises(sqlite3.Error):
            db.execute(
                "UPDATE still_assets SET is_illustrative_reconstruction = 0 WHERE still_2k_id = 'st_1'"
            )

        db.execute(
            """INSERT INTO spatial_anchors (
                 anchor_id, episode_id, still_2k_id, clue_name, grid_cell, x_px, y_px
               ) VALUES ('anc_1','ep_raw','st_1','broken_chair','E5',1280,720)"""
        )
        assert (
            db.execute(
                "SELECT lock_status FROM spatial_anchors WHERE anchor_id = 'anc_1'"
            ).fetchone()["lock_status"]
            == "DRAFT"
        )

        with pytest.raises(sqlite3.Error):
            db.execute("UPDATE spatial_anchors SET lock_status = 'LOCKED' WHERE anchor_id = 'anc_1'")
        with pytest.raises(sqlite3.Error):
            db.execute(
                """INSERT INTO spatial_anchors (
                     anchor_id, episode_id, still_2k_id, clue_name, grid_cell, x_px, y_px
                   ) VALUES ('anc_bad','ep_raw','st_1','x','Z99',100,100)"""
            )
    finally:
        db.close()


def test_07_unique_flow_jobs_prompt_mode_and_two_strike() -> None:
    """7. One flow job per scene, T2V/2F frame rules, and the 2-strike breaker."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "AWAITING_FLOW_BATCH")
        insert_approved_scene_plan_and_scene(db, "s1", 1, "FLOW_HERO_VIDEO", "HeroVideoBridge", 0, 12000)
        insert_approved_scene_plan_and_scene(db, "s2", 2, "FLOW_HERO_VIDEO", "HeroVideoBridge", 12000, 20000)

        db.execute(
            """INSERT INTO flow_jobs (
                 flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
                 duration_bucket_sec, start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe,
                 fallback_spec_json, provider_operation_id, state, updated_at
               ) VALUES (
                 'fj_t2v','ep_1','s1','idem_1','TEXT_TO_VIDEO',12,NULL,NULL,'p1','p2','{}','op_1',
                 'UNKNOWN_RECONCILE',1000
               )"""
        )
        with pytest.raises(sqlite3.Error):
            db.execute(
                """INSERT INTO flow_jobs (
                     flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
                     duration_bucket_sec, start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe,
                     fallback_spec_json, updated_at
                   ) VALUES (
                     'fj_dup','ep_1','s1','idem_dup','TEXT_TO_VIDEO',8,NULL,NULL,'p1','p2','{}',1001
                   )"""
            )
        with pytest.raises(sqlite3.Error):
            db.execute(
                """INSERT INTO flow_jobs (
                     flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
                     duration_bucket_sec, start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe,
                     fallback_spec_json, updated_at
                   ) VALUES (
                     'fj_bad2f','ep_1','s2','idem_2','FIRST_AND_LAST_FRAME',12,'a.png','b.png','p1','p2','{}',1001
                   )"""
            )
        db.execute(
            """INSERT INTO flow_jobs (
                 flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode,
                 duration_bucket_sec, start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe,
                 fallback_spec_json, updated_at
               ) VALUES (
                 'fj_2f','ep_1','s2','idem_3','FIRST_AND_LAST_FRAME',8,'a.png','b.png','p1','p2','{}',1001
               )"""
        )
        assert db.execute("SELECT COUNT(*) AS c FROM flow_jobs").fetchone()["c"] == 2

        db.execute(
            """INSERT INTO flow_job_attempts (
                 attempt_id, flow_job_id, attempt_number, prompt_used, pool_source, qa_verdict, created_at
               ) VALUES ('att_1','fj_t2v',1,'p1','GEMINI_API_USD','PASS',1002)"""
        )
        db.execute(
            "UPDATE flow_jobs SET attempts_used = 2, updated_at = 1003 WHERE flow_job_id = 'fj_t2v'"
        )
        with pytest.raises(sqlite3.Error, match="LAW_3_BREAKER"):
            db.execute(
                """INSERT INTO flow_job_attempts (
                     attempt_id, flow_job_id, attempt_number, prompt_used, pool_source,
                     qa_verdict, created_at
                   ) VALUES (
                     'att_2','fj_t2v',2,'p2','GEMINI_API_USD','FAIL_MORPH',1004
                   )"""
            )
    finally:
        db.close()


def test_08_daily_credit_reset_is_24h_plus_5m() -> None:
    """8. Daily credits lock until 24h+5m, then refill on the reset instant."""
    db = setup_db()
    try:
        statement = extract_query("atomic_refill_and_reserve_daily_account_credits")
        t0 = 1_700_000_000_000
        expected_reset = t0 + 86_400_000 + 300_000

        row = query_get(db, statement, {":account_id": "acct_1", ":credits": 50, ":now_ms": t0})
        assert row["daily_credits_left"] == 0
        assert (
            query_get(
                db,
                statement,
                {":account_id": "acct_1", ":credits": 10, ":now_ms": expected_reset - 1},
            )
            is None
        )
        row = query_get(
            db,
            statement,
            {":account_id": "acct_1", ":credits": 10, ":now_ms": expected_reset},
        )
        assert row["daily_credits_left"] == 40
    finally:
        db.close()


def test_09_voice_segment_non_overlap() -> None:
    """9. Voice segments reject kind violations and overlapping intervals."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "VOICE_READY")
        with pytest.raises(sqlite3.Error):
            db.execute(
                "INSERT INTO voice_segments VALUES ('vs_bad','ep_1',1,'NARRATION',0,5000,NULL,NULL)"
            )
        db.execute(
            "INSERT INTO voice_segments VALUES ('vs_1','ep_1',1,'NARRATION',0,10000,'s1.wav',NULL)"
        )
        with pytest.raises(sqlite3.Error, match="TIMELINE_OVERLAP"):
            db.execute(
                "INSERT INTO voice_segments VALUES ('vs_ov','ep_1',2,'NARRATION',9500,15000,'s2.wav',NULL)"
            )
        db.execute(
            "INSERT INTO voice_segments VALUES ('vs_2','ep_1',2,'TWIST_PAD',10000,10600,NULL,NULL)"
        )
        assert db.execute("SELECT COUNT(*) AS c FROM voice_segments").fetchone()["c"] == 2
    finally:
        db.close()


def test_10_youtube_purge_and_adsense_unknown() -> None:
    """10. YouTube rows require a 30-day TTL and purge; AdSense defaults to UNKNOWN."""
    db = setup_db()
    try:
        with pytest.raises(sqlite3.Error):
            db.execute(
                """INSERT INTO outlier_candidates (
                     candidate_id, track, source_video_id, views_count, outlier_ratio,
                     saturation_index, seed_packet_json, raw_yt_payload_json, yt_ttl_expires_at,
                     status, created_at
                   ) VALUES (
                     'c_bad','TRACK_A_OUTLIER','v1',50000,10.0,20,'{}','{"raw":1}',NULL,'CANDIDATE',1000
                   )"""
            )
        db.execute(
            """INSERT INTO channels_watchlist (
                 channel_id, uploads_playlist_id, channel_name, subscriber_count,
                 median_20_views, yt_ttl_expires_at
               ) VALUES ('UCkeep','UUkeep','Crime Channel',50000,10000,2000)"""
        )
        db.execute(
            """INSERT INTO outlier_candidates (
                 candidate_id, track, source_video_id, source_channel_id, views_count, outlier_ratio,
                 saturation_index, seed_packet_json, raw_yt_payload_json, yt_ttl_expires_at,
                 status, created_at
               ) VALUES (
                 'c_ok','TRACK_A_OUTLIER','v1','UCkeep',50000,10.0,20,'{"yt_title":"x"}','{"raw":1}',2000,
                 'GREENLIT',1000
               )"""
        )
        db.execute(
            """INSERT INTO saturation_checks (
                 check_id, candidate_id, phase, aliases_json, n_mega_excl, n_recent_excl,
                 n_14d_wave, si_score, checked_at
               ) VALUES ('chk_1','c_ok','SCOUTING','["alias"]',2,3,1,40,1500)"""
        )
        db.execute(extract_query("purge_expired_yt_api_records"), _bind({":now_ms": 2500}))
        purged = db.execute(
            """SELECT views_count, outlier_ratio, raw_yt_payload_json, status
               FROM outlier_candidates WHERE candidate_id='c_ok'"""
        ).fetchone()
        assert purged["views_count"] is None
        assert purged["raw_yt_payload_json"] is None
        assert purged["status"] == "EXPIRED_TOS_PURGED"
        assert (
            db.execute("SELECT aliases_json FROM saturation_checks WHERE check_id='chk_1'").fetchone()[
                "aliases_json"
            ]
            == "[]"
        )
        channel = db.execute(
            "SELECT channel_name, subscriber_count FROM channels_watchlist WHERE channel_id='UCkeep'"
        ).fetchone()
        assert channel["channel_name"] == ""
        assert channel["subscriber_count"] == 0

        seed_approved_case_and_episode(db, "MASTERED")
        db.execute(
            """INSERT INTO episode_analytics (
                 snapshot_id, episode_id, days_since_publish, watch_hours_total, captured_at
               ) VALUES ('an_1','ep_1',2,180.5,5000)"""
        )
        analytics = db.execute(
            """SELECT adsense_status, adsense_source, ctr_pct
               FROM episode_analytics WHERE snapshot_id='an_1'"""
        ).fetchone()
        assert analytics["adsense_status"] == "UNKNOWN"
        assert analytics["adsense_source"] == "UNAVAILABLE"
        assert analytics["ctr_pct"] is None
    finally:
        db.close()


def test_11_rights_provenance_blocks_restricted_reuse() -> None:
    """11. RESTRICTED_NO_REUSE cannot be approved; ASR disagreement is stored honestly."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "EVIDENCE_AND_2K_LOCKED")
        with pytest.raises(sqlite3.Error):
            db.execute(
                """INSERT INTO foia_media_assets (
                     asset_id, case_id, source_domain, source_url, creator_entity, rights_holder,
                     license_basis, rights_review_status, rights_reviewed_by, rights_reviewed_at,
                     media_kind, raw_path
                   ) VALUES (
                     'fa_bad','case_1','muckrock.com','https://muckrock.com/1','Bystander',
                     'Private Citizen','RESTRICTED_NO_REUSE','APPROVED','rev_1',1000,
                     'bodycam_mp4','raw.mp4'
                   )"""
            )
        db.execute(
            """INSERT INTO foia_media_assets (
                 asset_id, case_id, source_domain, source_url, creator_entity, rights_holder,
                 license_basis, rights_review_status, rights_reviewed_by, rights_reviewed_at,
                 media_kind, raw_path, asr_hypothesis_disagreement, human_audio_review_required
               ) VALUES (
                 'fa_ok','case_1','fbi.gov','https://fbi.gov/1','US Federal Employee',
                 'Public Domain (17 USC 105)','US_FED_EMPLOYEE_17USC105','APPROVED','rev_1',1000,
                 'call_911_wav','911.wav',0.14,1
               )"""
        )
        assert (
            db.execute(
                """SELECT human_audio_review_required
                   FROM foia_media_assets WHERE asset_id='fa_ok'"""
            ).fetchone()["human_audio_review_required"]
            == 1
        )
    finally:
        db.close()


def test_12_quota_daily_limit_and_news_hedging() -> None:
    """12. Quota RETURNING stops at daily_limit; news_report facts must stay hedged.

    The frozen v4 seed is yt_search daily_limit = 100. The Node scenario accepts
    +60 and rejects +45 (105 > 100). A separate 15-call yt_search floor is Task 007
    application logic, not a column or CHECK in this schema, so it is not invented here.
    """
    db = setup_db()
    try:
        statement = extract_query("consume_quota_bucket")
        assert query_get(db, statement, {":bucket_name": "yt_search", ":units": 60})["used_today"] == 60
        assert query_get(db, statement, {":bucket_name": "yt_search", ":units": 45}) is None

        seed_approved_case_and_episode(db, "SCOUTED")
        db.execute(
            """INSERT INTO primary_documents
               VALUES ('doc_1','case_1','example.com','https://example.com/1','news_text_only','abc','/tmp/1.txt',1000)"""
        )
        with pytest.raises(sqlite3.Error, match="RULE_09"):
            db.execute(
                """INSERT INTO fact_ledger
                   VALUES ('f1','case_1','2023-11-04T22:00:00Z','Suspect seen','[]','Route 9','news_report','doc_1','p.1',0,'[]')"""
            )
    finally:
        db.close()


def test_13_settlement_and_live_sandbox_caps() -> None:
    """13. Positive spend cannot be released, offline actuals stay $0, sandbox retries share a $2 cap."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "AWAITING_FLOW_BATCH")
        reserve = extract_query("reserve_provider_budget")
        settle = extract_query("settle_provider_budget")
        query_get(
            db,
            reserve,
            {
                ":reservation_id": "r_rel",
                ":episode_id": "ep_1",
                ":job_id": "job_rel",
                ":attempt_number": 1,
                ":provider_id": "tts",
                ":purpose": "PRODUCTION",
                ":year_month": "2026-11",
                ":estimated_micro_usd": 1000,
                ":now_ms": 1000,
            },
        )
        with pytest.raises(sqlite3.Error, match="BUDGET_SETTLEMENT_BLOCKED"):
            query_get(
                db,
                settle,
                {
                    ":reservation_id": "r_rel",
                    ":actual_micro_usd": 1000,
                    ":final_status": "RELEASED",
                    ":now_ms": 1100,
                },
            )
        query_get(
            db,
            settle,
            {
                ":reservation_id": "r_rel",
                ":actual_micro_usd": 1000,
                ":final_status": "COMMITTED",
                ":now_ms": 1100,
            },
        )
        query_get(
            db,
            reserve,
            {
                ":reservation_id": "r_off",
                ":episode_id": "ep_1",
                ":job_id": "job_off",
                ":attempt_number": 1,
                ":provider_id": "tts",
                ":purpose": "OFFLINE_TEST",
                ":year_month": "2026-11",
                ":estimated_micro_usd": 0,
                ":now_ms": 1200,
            },
        )
        with pytest.raises(sqlite3.Error, match="BUDGET_SETTLEMENT_BLOCKED"):
            query_get(
                db,
                settle,
                {
                    ":reservation_id": "r_off",
                    ":actual_micro_usd": 1,
                    ":final_status": "COMMITTED",
                    ":now_ms": 1300,
                },
            )
        query_get(
            db,
            reserve,
            {
                ":reservation_id": "r_sb1",
                ":episode_id": "ep_1",
                ":job_id": "job_sb",
                ":attempt_number": 1,
                ":provider_id": "gemini_omni",
                ":purpose": "LIVE_SANDBOX",
                ":year_month": "2026-11",
                ":estimated_micro_usd": 1_500_000,
                ":now_ms": 1400,
            },
        )
        with pytest.raises(sqlite3.Error, match="LIVE_SANDBOX_CAP_EXCEEDED"):
            query_get(
                db,
                reserve,
                {
                    ":reservation_id": "r_sb2",
                    ":episode_id": "ep_1",
                    ":job_id": "job_sb",
                    ":attempt_number": 2,
                    ":provider_id": "gemini_omni",
                    ":purpose": "LIVE_SANDBOX",
                    ":year_month": "2026-11",
                    ":estimated_micro_usd": 600_000,
                    ":now_ms": 1500,
                },
            )
    finally:
        db.close()


def test_14_hero_clip_count_and_duration_are_cumulative() -> None:
    """14. Hero clip count and duration are enforced across inserts and updates."""
    db = setup_db()
    try:
        seed_approved_case_and_episode(db, "AWAITING_FLOW_BATCH")
        db.execute(
            "UPDATE episodes SET max_hero_clips = 1, max_hero_duration_sec = 10 WHERE episode_id = 'ep_1'"
        )
        insert_approved_scene_plan_and_scene(db, "s1", 1, "FLOW_HERO_VIDEO", "HeroVideoBridge", 0, 8000)
        insert_approved_scene_plan_and_scene(db, "s2", 2, "FLOW_HERO_VIDEO", "HeroVideoBridge", 8000, 16000)
        db.execute(
            """INSERT INTO flow_jobs (
                 flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode, duration_bucket_sec,
                 start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe, fallback_spec_json, state, updated_at
               ) VALUES (
                 'fj1','ep_1','s1','idem_h1','TEXT_TO_VIDEO',8,NULL,NULL,'p','p2','{}','PENDING',1000
               )"""
        )
        with pytest.raises(sqlite3.Error, match="HERO_CAP_EXCEEDED"):
            db.execute(
                """INSERT INTO flow_jobs (
                     flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode, duration_bucket_sec,
                     start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe, fallback_spec_json, state, updated_at
                   ) VALUES (
                     'fj2','ep_1','s2','idem_h2','TEXT_TO_VIDEO',4,NULL,NULL,'p','p2','{}','PENDING',1001
                   )"""
            )
        db.execute(
            "UPDATE episodes SET max_hero_clips = 2, max_hero_duration_sec = 12 WHERE episode_id = 'ep_1'"
        )
        db.execute(
            """INSERT INTO flow_jobs (
                 flow_job_id, episode_id, scene_id, idempotency_key, prompt_mode, duration_bucket_sec,
                 start_frame_png, end_frame_png, prompt_v1, prompt_v2_safe, fallback_spec_json, state, updated_at
               ) VALUES (
                 'fj2','ep_1','s2','idem_h2','TEXT_TO_VIDEO',4,NULL,NULL,'p','p2','{}','PENDING',1001
               )"""
        )
        with pytest.raises(sqlite3.Error, match="HERO_CAP_EXCEEDED"):
            db.execute("UPDATE flow_jobs SET duration_bucket_sec = 8 WHERE flow_job_id = 'fj2'")
    finally:
        db.close()


def test_15_release_insert_and_qa_demotion() -> None:
    """15. A releasable state cannot be inserted, and a failing QA demotes a ready episode."""
    db = setup_db()
    try:
        db.execute(
            """INSERT INTO cases (
                 case_id, defendant_name, incident_year, jurisdiction, docket_id,
                 primary_record_verified, verification_source, disposition_status,
                 conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
                 anonymization_artifact_sha256, created_at, updated_at
               ) VALUES (
                 'case_pub','John Doe',2023,'Mercer, NJ','DK-9',1,'courtlistener','AFFIRMED',1,
                 'APPROVED','reviewer_a',1000,'sha_anon_1',1000,1000
               )"""
        )
        with pytest.raises(sqlite3.Error, match="RELEASE_GATE_BLOCKED"):
            db.execute(
                """INSERT INTO episodes (
                     episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
                     total_master_ms, timeline_validated_sha256, ready_bundle_sha256,
                     updated_at, created_at
                   ) VALUES (
                     'ep_pub','case_pub','PUBLISHED','GEMINI_OMNI_INTERACTIONS','911_CALL_IN_MEDIA_RES',
                     1200000,'sha_tl_1','sha_bundle_1',1000,1000
                   )"""
            )
        seed_approved_case_and_episode(db, "MASTERED")
        insert_approved_scene_plan_and_scene(db)
        gates = [
            "FACTUAL_ACCURACY",
            "PRIVACY_PII",
            "SOURCE_RIGHTS",
            "SYNTHETIC_DISCLOSURE",
            "ILLUSTRATIVE_LABELING",
        ]
        for idx, gate in enumerate(gates):
            db.execute(
                """INSERT INTO release_approvals
                   VALUES (?, 'ep_1', ?, 'sha_bundle_1', 'APPROVED', 'editor_jane', 2000, 'verified')""",
                (f"rel_{idx}", gate),
            )
        db.execute(
            """INSERT INTO qa_reports VALUES
               ('qa_rel','ep_1',-14.0,-1.5,1,1,'PASSED',1,'final.mp4','sha_mp4',4000)"""
        )
        db.execute(
            """INSERT INTO compliance_audits VALUES
               ('aud_rel','case_1',1,1,1,1,1,1,4000)"""
        )
        db.execute("UPDATE cases SET primary_record_verified = 0 WHERE case_id = 'case_1'")
        with pytest.raises(sqlite3.Error, match="RELEASE_GATE_BLOCKED"):
            db.execute("UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'")
        db.execute("UPDATE cases SET primary_record_verified = 1 WHERE case_id = 'case_1'")
        db.execute("UPDATE episodes SET state = 'READY_TO_UPLOAD' WHERE episode_id = 'ep_1'")
        db.execute(
            """UPDATE qa_reports
               SET vision_frame_qa_status = 'PENDING_MANUAL_SPOT_CHECK'
               WHERE qa_id = 'qa_rel'"""
        )
        assert (
            db.execute("SELECT state FROM episodes WHERE episode_id = 'ep_1'").fetchone()["state"]
            == "PENDING_HUMAN_SIGNOFF"
        )
    finally:
        db.close()


def test_16_quota_reset_and_idempotent_refund() -> None:
    """16. Negative quota units do nothing, reset is explicit, and a refund id cannot be reused."""
    db = setup_db()
    try:
        consume = extract_query("consume_quota_bucket")
        assert query_get(db, consume, {":bucket_name": "yt_search", ":units": -5}) is None
        assert (
            db.execute(
                "SELECT used_today FROM quota_buckets WHERE bucket_name = 'yt_search'"
            ).fetchone()["used_today"]
            == 0
        )
        query_get(db, consume, {":bucket_name": "yt_search", ":units": 10})
        reset = extract_query("reset_quota_window")
        assert query_get(db, reset, {":bucket_name": "yt_search", ":now_ms": 86_400_000})["used_today"] == 0
        db.execute(
            """UPDATE google_accounts
               SET next_daily_reset_utc_ms = 9000000000, daily_credits_left = 10
               WHERE account_id = 'acct_1'"""
        )
        refund = extract_query("refund_daily_account_credits")
        query_get(
            db,
            refund,
            {
                ":refund_id": "rf_1",
                ":account_id": "acct_1",
                ":reservation_id": "res_1",
                ":credits": 5,
                ":now_ms": 1000,
            },
        )
        after = db.execute(
            "SELECT daily_credits_left FROM google_accounts WHERE account_id = 'acct_1'"
        ).fetchone()["daily_credits_left"]
        with pytest.raises(sqlite3.Error):
            query_get(
                db,
                refund,
                {
                    ":refund_id": "rf_1",
                    ":account_id": "acct_1",
                    ":reservation_id": "res_1",
                    ":credits": 5,
                    ":now_ms": 1001,
                },
            )
        assert (
            db.execute(
                "SELECT daily_credits_left FROM google_accounts WHERE account_id = 'acct_1'"
            ).fetchone()["daily_credits_left"]
            == after
        )
    finally:
        db.close()
