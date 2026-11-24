import sqlite3
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "packages" / "integration_bridge" / "src"
sys.path.insert(0, str(SRC))
from integration_bridge.mvp_slice import connect, seed


def test_ten_episode_month_stays_inside_the_global_cap(tmp_path: Path):
    connection = connect(str(tmp_path / "pipeline.db"))
    seed(connection)
    connection.commit()
    try:
        connection.execute(
            """
            INSERT INTO provider_spend_reservations (
              reservation_id, episode_id, job_id, attempt_number, provider_id, purpose,
              year_month, estimated_micro_usd, status, created_at
            ) VALUES ('r_bad','ep_slice','job_bad',1,'deepseek_chat','OFFLINE_TEST','2026-11',1000,'RESERVED',1000)
            """
        )
        assert False
    except sqlite3.IntegrityError as error:
        assert "OFFLINE_TEST_ZERO_SPEND" in str(error)
        connection.rollback()
    connection.execute(
        "UPDATE monthly_budget_ledger SET hard_cap_micro_usd = 120000000 WHERE year_month='2026-11' AND provider_id='gemini_omni'"
    )
    connection.execute("UPDATE episodes SET video_budget_cap_micro_usd = 120000000 WHERE episode_id='ep_slice'")
    _reserve(connection, "r_ds", "job_ds", "deepseek_chat", 38_000_000)
    try:
        _reserve(connection, "r_over", "job_over", "gemini_omni", 98_000_000)
        assert False
    except sqlite3.IntegrityError as error:
        assert "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED" in str(error)
        connection.rollback()
    connection.execute("DELETE FROM provider_spend_reservations")
    connection.execute("UPDATE episodes SET video_budget_cap_micro_usd = 104000000 WHERE episode_id='ep_slice'")
    video = 10 * 9_600_000
    _reserve(connection, "r_video", "job_video", "gemini_omni", video)
    _reserve(connection, "r_ds_ok", "job_ds_ok", "deepseek_chat", 38_000_000)
    held = connection.execute(
        """
        SELECT COALESCE(SUM(estimated_micro_usd),0) FROM provider_spend_reservations
        WHERE year_month='2026-11' AND status='RESERVED'
        """
    ).fetchone()[0]
    assert held == video + 38_000_000
    assert held <= 135_000_000
    try:
        _reserve(connection, "r_extra", "job_extra", "gemini_omni", 2_000_000, attempt=2)
        assert False
    except sqlite3.IntegrityError as error:
        assert "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED" in str(error)
    clips = connection.execute("SELECT max_hero_clips FROM episodes WHERE episode_id='ep_slice'").fetchone()[0]
    assert clips == 10
    assert 780 + 340 + 80 == 1200


def _reserve(connection, reservation_id, job_id, provider, micro, attempt=1):
    connection.execute(
        """
        INSERT INTO provider_spend_reservations (
          reservation_id, episode_id, job_id, attempt_number, provider_id, purpose,
          year_month, estimated_micro_usd, status, created_at
        ) VALUES (?,?,?,?,?,'PRODUCTION','2026-11',?,'RESERVED',1000)
        """,
        (reservation_id, "ep_slice", job_id, attempt, provider, micro),
    )
