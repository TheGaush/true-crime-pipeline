"""Offline budget guardrail tests against a temp pipeline.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from orchestrator.budget_guardrails import (
    BudgetCapExceeded,
    BudgetGuardrails,
    GeminiOmniQuotaExceeded,
    deepseek_conservative_reservation_micro_usd,
    init_pipeline_db,
    load_provider_budget_caps,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SQL = REPO_ROOT / "schema" / "pipeline.sql"
PROVIDERS_YAML = REPO_ROOT / "providers.yaml"
YEAR_MONTH = "2026-11"
ALL_PROVIDERS_CAP = 135_000_000
DEEPSEEK_CAP = 38_000_000
EPISODE_VIDEO_CAP = 10_400_000

_CHARGED_SQL = """
SELECT COALESCE(SUM(
  CASE
    WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
    WHEN status IN ('RESERVED', 'UNKNOWN_HOLD') THEN estimated_micro_usd
    ELSE 0
  END
), 0)
FROM provider_spend_reservations
WHERE year_month = ?
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_case(conn: sqlite3.Connection, case_id: str = "case_1") -> None:
    conn.execute(
        """
        INSERT INTO cases (
          case_id, defendant_name, incident_year, jurisdiction,
          verification_source, disposition_status, conviction_confirmed,
          created_at, updated_at
        ) VALUES (?, 'John Doe', 2023, 'Mercer, NJ', 'courtlistener', 'AFFIRMED', 1, 1000, 1000)
        """,
        (case_id,),
    )


def seed_episode(conn: sqlite3.Connection, episode_id: str, *, case_id: str = "case_1") -> None:
    conn.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
          updated_at, created_at
        ) VALUES (?, ?, 'AWAITING_FLOW_BATCH', 'GEMINI_OMNI_INTERACTIONS', '911_CALL_IN_MEDIA_RES', 1000, 1000)
        """,
        (episode_id, case_id),
    )


def charged(conn: sqlite3.Connection, year_month: str = YEAR_MONTH) -> int:
    return int(conn.execute(_CHARGED_SQL, (year_month,)).fetchone()[0])


def guard_for(path: Path) -> BudgetGuardrails:
    return BudgetGuardrails(path, providers_yaml=PROVIDERS_YAML)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.db"
    init_pipeline_db(path, pipeline_sql=PIPELINE_SQL)
    conn = connect(path)
    try:
        seed_case(conn)
        seed_episode(conn, "ep_1")
        conn.commit()
    finally:
        conn.close()
    return path


def test_providers_yaml_caps_match_economics() -> None:
    caps = load_provider_budget_caps(PROVIDERS_YAML)
    assert caps.all_providers_monthly_cap_micro_usd == ALL_PROVIDERS_CAP
    assert caps.deepseek_monthly_cap_micro_usd == DEEPSEEK_CAP
    assert caps.per_episode_video_cap_micro_usd == EPISODE_VIDEO_CAP
    assert caps.max_hero_clips == 10
    assert caps.max_hero_duration_sec == 80
    assert caps.offline_test_cap_micro_usd == 0
    assert deepseek_conservative_reservation_micro_usd(caps) == DEEPSEEK_CAP


def test_pipeline_triggers_present(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        triggers = {
            row[0]
            for row in conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'trigger'
                  AND name IN (
                    'trg_offline_test_zero_spend_guard',
                    'trg_provider_global_budget_cap_guard'
                  )
                """
            )
        }
        global_cap = conn.execute(
            """
            SELECT hard_cap_micro_usd FROM monthly_budget_ledger
            WHERE year_month = ? AND provider_id = 'ALL_PROVIDERS'
            """,
            (YEAR_MONTH,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert triggers == {
        "trg_offline_test_zero_spend_guard",
        "trg_provider_global_budget_cap_guard",
    }
    assert global_cap == ALL_PROVIDERS_CAP


def test_offline_test_positive_spend_rejected(db_path: Path) -> None:
    guard = guard_for(db_path)
    with pytest.raises(BudgetCapExceeded) as raised:
        guard.reserve_provider_budget(
            reservation_id="res_offline_bad",
            episode_id=None,
            job_id="job_offline_bad",
            attempt_number=1,
            provider_id="deepseek_chat",
            purpose="OFFLINE_TEST",
            year_month=YEAR_MONTH,
            estimated_micro_usd=1,
            now_ms=1_000,
        )
    assert raised.value.code == "OFFLINE_TEST_ZERO_SPEND"
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM provider_spend_reservations").fetchone()[0] == 0
    finally:
        conn.close()


def test_offline_test_zero_allowed(db_path: Path) -> None:
    guard = guard_for(db_path)
    row = guard.reserve_provider_budget(
        reservation_id="res_offline_ok",
        episode_id=None,
        job_id="job_offline_ok",
        attempt_number=1,
        provider_id="gemini_omni",
        purpose="OFFLINE_TEST",
        year_month=YEAR_MONTH,
        estimated_micro_usd=0,
        now_ms=1_000,
    )
    assert row.status == "RESERVED"
    assert row.estimated_micro_usd == 0


def test_deepseek_conservative_cap_from_providers_yaml(db_path: Path) -> None:
    guard = guard_for(db_path)
    row = guard.reserve_deepseek_conservative(
        reservation_id="res_ds",
        episode_id=None,
        job_id="job_ds",
        attempt_number=1,
        year_month=YEAR_MONTH,
        now_ms=1_000,
    )
    assert row.estimated_micro_usd == DEEPSEEK_CAP
    assert row.status == "RESERVED"
    with pytest.raises(BudgetCapExceeded) as raised:
        guard.reserve_provider_budget(
            reservation_id="res_ds_over",
            episode_id=None,
            job_id="job_ds_over",
            attempt_number=1,
            provider_id="deepseek_chat",
            purpose="PRODUCTION",
            year_month=YEAR_MONTH,
            estimated_micro_usd=1,
            now_ms=2_000,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"


def test_two_reservations_exceeding_135_rejects_second(db_path: Path) -> None:
    guard = guard_for(db_path)
    first_amount = 104_000_000
    second_amount = ALL_PROVIDERS_CAP - first_amount + 1
    guard.reserve_provider_budget(
        reservation_id="res_global_a",
        episode_id=None,
        job_id="job_global_a",
        attempt_number=1,
        provider_id="gemini_omni",
        purpose="PRODUCTION",
        year_month=YEAR_MONTH,
        estimated_micro_usd=first_amount,
        now_ms=1_000,
    )
    with pytest.raises(BudgetCapExceeded) as raised:
        guard.reserve_provider_budget(
            reservation_id="res_global_b",
            episode_id=None,
            job_id="job_global_b",
            attempt_number=1,
            provider_id="deepseek_chat",
            purpose="PRODUCTION",
            year_month=YEAR_MONTH,
            estimated_micro_usd=second_amount,
            now_ms=2_000,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"
    conn = connect(db_path)
    try:
        assert charged(conn) == first_amount
        assert conn.execute("SELECT COUNT(*) FROM provider_spend_reservations").fetchone()[0] == 1
    finally:
        conn.close()


def test_gemini_omni_episode_video_cap(db_path: Path) -> None:
    guard = guard_for(db_path)
    guard.reserve_provider_budget(
        reservation_id="res_ep_full",
        episode_id="ep_1",
        job_id="job_ep_full",
        attempt_number=1,
        provider_id="gemini_omni",
        purpose="PRODUCTION",
        year_month=YEAR_MONTH,
        estimated_micro_usd=EPISODE_VIDEO_CAP,
        now_ms=1_000,
        gemini_clip_count=10,
        gemini_duration_sec=80,
    )
    with pytest.raises(BudgetCapExceeded) as cap:
        guard.reserve_provider_budget(
            reservation_id="res_ep_over",
            episode_id="ep_1",
            job_id="job_ep_over",
            attempt_number=1,
            provider_id="gemini_omni",
            purpose="PRODUCTION",
            year_month=YEAR_MONTH,
            estimated_micro_usd=1,
            now_ms=2_000,
            gemini_clip_count=1,
            gemini_duration_sec=3,
        )
    assert cap.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"


def test_gemini_omni_clip_and_duration_quota_from_providers_yaml(db_path: Path) -> None:
    guard = guard_for(db_path)
    with pytest.raises(GeminiOmniQuotaExceeded):
        guard.reserve_provider_budget(
            reservation_id="res_clips",
            episode_id="ep_1",
            job_id="job_clips",
            attempt_number=1,
            provider_id="gemini_omni",
            purpose="PRODUCTION",
            year_month=YEAR_MONTH,
            estimated_micro_usd=1_000_000,
            now_ms=1_000,
            gemini_clip_count=11,
            gemini_duration_sec=10,
        )
    with pytest.raises(GeminiOmniQuotaExceeded):
        guard.reserve_provider_budget(
            reservation_id="res_dur",
            episode_id="ep_1",
            job_id="job_dur",
            attempt_number=1,
            provider_id="gemini_omni",
            purpose="PRODUCTION",
            year_month=YEAR_MONTH,
            estimated_micro_usd=1_000_000,
            now_ms=1_000,
            gemini_clip_count=1,
            gemini_duration_sec=81,
        )


def test_telemetry_db_rejected_for_admission(tmp_path: Path) -> None:
    path = tmp_path / "telemetry.db"
    sqlite3.connect(path).close()
    guard = BudgetGuardrails(path, providers_yaml=PROVIDERS_YAML)
    with pytest.raises(ValueError, match="telemetry.db"):
        guard.reserve_provider_budget(
            reservation_id="res_tel",
            episode_id=None,
            job_id="job_tel",
            attempt_number=1,
            provider_id="tts",
            purpose="PRODUCTION",
            year_month=YEAR_MONTH,
            estimated_micro_usd=1,
            now_ms=1,
        )