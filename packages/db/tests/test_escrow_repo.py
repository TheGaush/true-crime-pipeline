"""Offline escrow tests. Schema comes from schema/pipeline.sql; no network."""

from __future__ import annotations

import sqlite3
import sys
import threading
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from escrow_repo import (  # noqa: E402
    BudgetCapExceeded,
    GlobalBudgetLedgerRepository,
    ReservationNotOpen,
    act1_hero_cap_micro_usd,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SQL = REPO_ROOT / "schema" / "pipeline.sql"
YEAR_MONTH = "2026-11"
ALL_PROVIDERS_CAP = 135_000_000
DEEPSEEK_CAP = 38_000_000
GEMINI_OMNI_MONTHLY_CAP = 104_000_000
EPISODE_VIDEO_CAP = 10_400_000
ACT1_CAP = 4_160_000

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


def seed_episode(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    case_id: str = "case_1",
    flow_backend_mode: str = "GEMINI_OMNI_INTERACTIONS",
) -> None:
    conn.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
          updated_at, created_at
        ) VALUES (?, ?, 'AWAITING_FLOW_BATCH', ?, '911_CALL_IN_MEDIA_RES', 1000, 1000)
        """,
        (episode_id, case_id, flow_backend_mode),
    )


def charged(conn: sqlite3.Connection, year_month: str = YEAR_MONTH) -> int:
    return int(conn.execute(_CHARGED_SQL, (year_month,)).fetchone()[0])


def repo_for(path: Path) -> GlobalBudgetLedgerRepository:
    return GlobalBudgetLedgerRepository(path)


def reserve(repo: GlobalBudgetLedgerRepository, **overrides):
    params = {
        "reservation_id": "res_1",
        "episode_id": "ep_1",
        "job_id": "job_1",
        "attempt_number": 1,
        "provider_id": "deepseek_chat",
        "purpose": "PRODUCTION",
        "year_month": YEAR_MONTH,
        "estimated_micro_usd": 1_000,
        "now_ms": 1_000,
        "flow_backend_mode": "GEMINI_OMNI_INTERACTIONS",
        "act_number": None,
    }
    params.update(overrides)
    return repo.reserve_provider_budget(**params)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "pipeline.db"
    init_pipeline(path)
    conn = connect(path)
    try:
        seed_case(conn)
        seed_episode(conn, "ep_1")
        conn.commit()
    finally:
        conn.close()
    return path


def test_schema_seed_caps_and_trigger_names(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        rows = {
            row["provider_id"]: row["hard_cap_micro_usd"]
            for row in conn.execute(
                """
                SELECT provider_id, hard_cap_micro_usd
                FROM monthly_budget_ledger
                WHERE year_month = ?
                """,
                (YEAR_MONTH,),
            )
        }
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
        default_cap = conn.execute(
            "SELECT video_budget_cap_micro_usd FROM episodes WHERE episode_id = 'ep_1'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert rows == {
        "ALL_PROVIDERS": ALL_PROVIDERS_CAP,
        "gemini_omni": GEMINI_OMNI_MONTHLY_CAP,
        "gemini_image": 5_000_000,
        "deepseek_chat": DEEPSEEK_CAP,
        "tts": 5_000_000,
        "vision_qa": 2_000_000,
    }
    assert "vertex_veo" not in rows
    assert default_cap == EPISODE_VIDEO_CAP
    assert triggers == {
        "trg_offline_test_zero_spend_guard",
        "trg_provider_global_budget_cap_guard",
    }
    assert act1_hero_cap_micro_usd(EPISODE_VIDEO_CAP) == ACT1_CAP


def test_named_sql_is_loaded_from_queries_file(db_path: Path) -> None:
    repo = repo_for(db_path)
    reserve_sql = repo.queries["reserve_provider_budget"]
    settle_sql = repo.queries["settle_provider_budget"]
    assert "INSERT INTO provider_spend_reservations" in reserve_sql
    assert "RETURNING reservation_id, estimated_micro_usd, status" in reserve_sql
    assert "SET actual_micro_usd = :actual_micro_usd" in settle_sql
    assert "status = :final_status" in settle_sql
    assert "status IN ('RESERVED', 'UNKNOWN_HOLD')" in settle_sql


def test_offline_test_positive_spend_fails_on_zero_spend_trigger(db_path: Path) -> None:
    repo = repo_for(db_path)
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            reservation_id="res_offline_bad",
            job_id="job_offline_bad",
            purpose="OFFLINE_TEST",
            estimated_micro_usd=1,
            provider_id="deepseek_chat",
            episode_id=None,
        )
    assert raised.value.code == "OFFLINE_TEST_ZERO_SPEND"
    assert isinstance(raised.value.__cause__, sqlite3.Error)
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM provider_spend_reservations").fetchone()[0] == 0
    finally:
        conn.close()


def test_offline_test_zero_succeeds(db_path: Path) -> None:
    repo = repo_for(db_path)
    row = reserve(
        repo,
        reservation_id="res_offline_ok",
        job_id="job_offline_ok",
        purpose="OFFLINE_TEST",
        estimated_micro_usd=0,
        provider_id="vertex_veo",
        episode_id=None,
        flow_backend_mode="VERTEX_VEO_ENTERPRISE",
    )
    assert row.status == "RESERVED"
    assert row.estimated_micro_usd == 0
    assert row.flow_backend_mode == "VERTEX_VEO_ENTERPRISE"
    conn = connect(db_path)
    try:
        assert charged(conn) == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("provider_id", "cap"),
    [
        ("deepseek_chat", DEEPSEEK_CAP),
        ("gemini_image", 5_000_000),
        ("tts", 5_000_000),
        ("vision_qa", 2_000_000),
    ],
)
def test_provider_subcap_from_seed(db_path: Path, provider_id: str, cap: int) -> None:
    repo = repo_for(db_path)
    ok = reserve(
        repo,
        reservation_id=f"res_{provider_id}",
        job_id=f"job_{provider_id}",
        provider_id=provider_id,
        episode_id=None,
        estimated_micro_usd=cap,
    )
    assert ok.status == "RESERVED"
    assert ok.estimated_micro_usd == cap
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            reservation_id=f"res_{provider_id}_over",
            job_id=f"job_{provider_id}_over",
            provider_id=provider_id,
            episode_id=None,
            estimated_micro_usd=1,
            now_ms=2_000,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"
    conn = connect(db_path)
    try:
        assert charged(conn) == cap
    finally:
        conn.close()


def test_episode_video_cap_is_trigger_enforced(db_path: Path) -> None:
    repo = repo_for(db_path)
    reserve(
        repo,
        reservation_id="res_ep_full",
        job_id="job_ep_full",
        provider_id="gemini_omni",
        estimated_micro_usd=EPISODE_VIDEO_CAP,
        act_number=2,
        flow_backend_mode="GEMINI_OMNI_INTERACTIONS",
    )
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            reservation_id="res_ep_over",
            job_id="job_ep_over",
            provider_id="gemini_omni",
            estimated_micro_usd=1,
            act_number=3,
            now_ms=2_000,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"


def test_gemini_omni_monthly_cap_across_episodes(db_path: Path) -> None:
    repo = repo_for(db_path)
    conn = connect(db_path)
    try:
        for index in range(10):
            seed_episode(conn, f"ep_g_{index}")
        conn.commit()
    finally:
        conn.close()

    for index in range(10):
        reserve(
            repo,
            reservation_id=f"res_g_{index}",
            episode_id=f"ep_g_{index}",
            job_id=f"job_g_{index}",
            provider_id="gemini_omni",
            estimated_micro_usd=EPISODE_VIDEO_CAP,
            act_number=2,
            now_ms=1_000 + index,
        )
    conn = connect(db_path)
    try:
        assert charged(conn) == GEMINI_OMNI_MONTHLY_CAP
    finally:
        conn.close()

    conn = connect(db_path)
    try:
        seed_episode(conn, "ep_g_over")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            reservation_id="res_g_over",
            episode_id="ep_g_over",
            job_id="job_g_over",
            provider_id="gemini_omni",
            estimated_micro_usd=1,
            act_number=2,
            now_ms=5_000,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"


def test_all_providers_monthly_cap(db_path: Path) -> None:
    repo = repo_for(db_path)
    conn = connect(db_path)
    try:
        for index in range(10):
            seed_episode(conn, f"ep_all_{index}")
        conn.commit()
    finally:
        conn.close()
    for index in range(10):
        reserve(
            repo,
            reservation_id=f"res_all_g_{index}",
            episode_id=f"ep_all_{index}",
            job_id=f"job_all_g_{index}",
            provider_id="gemini_omni",
            estimated_micro_usd=EPISODE_VIDEO_CAP,
            act_number=2,
            now_ms=1_000 + index,
        )
    deepseek_room = ALL_PROVIDERS_CAP - GEMINI_OMNI_MONTHLY_CAP
    assert deepseek_room == 31_000_000
    reserve(
        repo,
        reservation_id="res_all_ds",
        episode_id=None,
        job_id="job_all_ds",
        provider_id="deepseek_chat",
        estimated_micro_usd=deepseek_room,
        now_ms=2_000,
    )
    conn = connect(db_path)
    try:
        assert charged(conn) == ALL_PROVIDERS_CAP
    finally:
        conn.close()
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            reservation_id="res_all_over",
            episode_id=None,
            job_id="job_all_over",
            provider_id="deepseek_chat",
            estimated_micro_usd=1,
            now_ms=3_000,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"
    conn = connect(db_path)
    try:
        assert charged(conn) == ALL_PROVIDERS_CAP
    finally:
        conn.close()


def test_unconfigured_month_fails_closed(db_path: Path) -> None:
    repo = repo_for(db_path)
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            year_month="2026-12",
            provider_id="tts",
            episode_id=None,
            estimated_micro_usd=1,
        )
    assert raised.value.code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"


def test_act1_hero_allocation_rejects_above_forty_percent(db_path: Path) -> None:
    repo = repo_for(db_path)
    with pytest.raises(BudgetCapExceeded) as raised:
        reserve(
            repo,
            reservation_id="res_act1_over",
            job_id="job_act1_over",
            provider_id="gemini_omni",
            estimated_micro_usd=ACT1_CAP + 1,
            act_number=1,
            flow_backend_mode="HUMAN_BATCH_DESK",
        )
    assert raised.value.code == "ACT1_HERO_ALLOCATION_EXCEEDED"
    assert raised.value.__cause__ is None
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM provider_spend_reservations").fetchone()[0] == 0
    finally:
        conn.close()

    ok = reserve(
        repo,
        reservation_id="res_act1_ok",
        job_id="job_act1_ok",
        provider_id="gemini_omni",
        estimated_micro_usd=ACT1_CAP,
        act_number=1,
        flow_backend_mode="HUMAN_BATCH_DESK",
    )
    assert ok.flow_backend_mode == "HUMAN_BATCH_DESK"
    assert ok.status == "RESERVED"
    with pytest.raises(BudgetCapExceeded) as second:
        reserve(
            repo,
            reservation_id="res_act1_more",
            job_id="job_act1_more",
            provider_id="vertex_veo",
            estimated_micro_usd=1,
            act_number=1,
            now_ms=2_000,
            flow_backend_mode="VERTEX_VEO_ENTERPRISE",
        )
    assert second.value.code == "ACT1_HERO_ALLOCATION_EXCEEDED"


def test_act2_can_use_remaining_episode_video_cap(db_path: Path) -> None:
    repo = repo_for(db_path)
    reserve(
        repo,
        reservation_id="res_act1",
        job_id="job_act1",
        provider_id="gemini_omni",
        estimated_micro_usd=ACT1_CAP,
        act_number=1,
    )
    rest = EPISODE_VIDEO_CAP - ACT1_CAP
    row = reserve(
        repo,
        reservation_id="res_act2",
        job_id="job_act2",
        provider_id="gemini_omni",
        estimated_micro_usd=rest,
        act_number=2,
        now_ms=2_000,
        flow_backend_mode="VERTEX_VEO_ENTERPRISE",
    )
    assert row.status == "RESERVED"
    assert row.flow_backend_mode == "VERTEX_VEO_ENTERPRISE"
    conn = connect(db_path)
    try:
        assert charged(conn) == EPISODE_VIDEO_CAP
    finally:
        conn.close()


def test_flow_backend_modes_all_hit_the_usd_ledger(db_path: Path) -> None:
    repo = repo_for(db_path)
    modes = (
        "GEMINI_OMNI_INTERACTIONS",
        "VERTEX_VEO_ENTERPRISE",
        "HUMAN_BATCH_DESK",
    )
    for index, mode in enumerate(modes):
        row = reserve(
            repo,
            reservation_id=f"res_mode_{index}",
            job_id=f"job_mode_{index}",
            provider_id="deepseek_chat",
            episode_id=None,
            estimated_micro_usd=1_000,
            now_ms=1_000 + index,
            flow_backend_mode=mode,
        )
        assert row.flow_backend_mode == mode
        assert row.estimated_micro_usd == 1_000
    conn = connect(db_path)
    try:
        assert charged(conn) == 3_000
    finally:
        conn.close()


def test_invalid_flow_backend_mode_inserts_nothing(db_path: Path) -> None:
    repo = repo_for(db_path)
    with pytest.raises(ValueError):
        reserve(repo, flow_backend_mode="SKIP_THE_LEDGER")
    conn = connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM provider_spend_reservations").fetchone()[0] == 0
    finally:
        conn.close()


def test_settle_sets_actual_and_final_status(db_path: Path) -> None:
    repo = repo_for(db_path)
    reserve(
        repo,
        reservation_id="res_settle",
        job_id="job_settle",
        provider_id="deepseek_chat",
        episode_id=None,
        estimated_micro_usd=DEEPSEEK_CAP,
    )
    settled = repo.settle_provider_budget(
        reservation_id="res_settle",
        actual_micro_usd=1_000_000,
        final_status="COMMITTED",
        now_ms=5_000,
    )
    assert settled.reservation_id == "res_settle"
    assert settled.actual_micro_usd == 1_000_000
    assert settled.status == "COMMITTED"
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT actual_micro_usd, status, settled_at FROM provider_spend_reservations WHERE reservation_id = 'res_settle'"
        ).fetchone()
        assert row["actual_micro_usd"] == 1_000_000
        assert row["status"] == "COMMITTED"
        assert row["settled_at"] == 5_000
        assert charged(conn) == 1_000_000
    finally:
        conn.close()

    reserve(
        repo,
        reservation_id="res_after_settle",
        job_id="job_after_settle",
        provider_id="deepseek_chat",
        episode_id=None,
        estimated_micro_usd=DEEPSEEK_CAP - 1_000_000,
        now_ms=6_000,
    )
    with pytest.raises(BudgetCapExceeded):
        reserve(
            repo,
            reservation_id="res_after_settle_over",
            job_id="job_after_settle_over",
            provider_id="deepseek_chat",
            episode_id=None,
            estimated_micro_usd=1,
            now_ms=7_000,
        )
    with pytest.raises(ReservationNotOpen):
        repo.settle_provider_budget(
            reservation_id="res_settle",
            actual_micro_usd=1,
            final_status="COMMITTED",
            now_ms=8_000,
        )


def test_settle_released_frees_headroom(db_path: Path) -> None:
    repo = repo_for(db_path)
    reserve(
        repo,
        reservation_id="res_release",
        job_id="job_release",
        provider_id="vision_qa",
        episode_id=None,
        estimated_micro_usd=2_000_000,
    )
    with pytest.raises(BudgetCapExceeded):
        reserve(
            repo,
            reservation_id="res_release_blocked",
            job_id="job_release_blocked",
            provider_id="vision_qa",
            episode_id=None,
            estimated_micro_usd=1,
            now_ms=2_000,
        )
    released = repo.settle_provider_budget(
        reservation_id="res_release",
        actual_micro_usd=0,
        final_status="RELEASED",
        now_ms=3_000,
    )
    assert released.status == "RELEASED"
    assert released.actual_micro_usd == 0
    again = reserve(
        repo,
        reservation_id="res_release_retry",
        job_id="job_release_retry",
        provider_id="vision_qa",
        episode_id=None,
        estimated_micro_usd=2_000_000,
        now_ms=4_000,
    )
    assert again.status == "RESERVED"


def test_settle_unknown_hold(db_path: Path) -> None:
    repo = repo_for(db_path)
    reserve(
        repo,
        reservation_id="res_hold",
        job_id="job_hold",
        provider_id="tts",
        episode_id=None,
        estimated_micro_usd=10,
    )
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE provider_spend_reservations SET status = 'UNKNOWN_HOLD' WHERE reservation_id = 'res_hold'"
        )
        conn.commit()
    finally:
        conn.close()
    settled = repo.settle_provider_budget(
        reservation_id="res_hold",
        actual_micro_usd=4,
        final_status="COMMITTED",
        now_ms=9_000,
    )
    assert settled.status == "COMMITTED"
    assert settled.actual_micro_usd == 4


def test_concurrent_reservations_cannot_exceed_monthly_cap(db_path: Path) -> None:
    repo = repo_for(db_path)
    conn = connect(db_path)
    try:
        for index in range(10):
            seed_episode(conn, f"ep_race_{index}")
        conn.commit()
    finally:
        conn.close()
    for index in range(10):
        reserve(
            repo,
            reservation_id=f"res_race_g_{index}",
            episode_id=f"ep_race_{index}",
            job_id=f"job_race_g_{index}",
            provider_id="gemini_omni",
            estimated_micro_usd=EPISODE_VIDEO_CAP,
            act_number=2,
            now_ms=1_000 + index,
        )
    prefill_deepseek = 27_000_000
    reserve(
        repo,
        reservation_id="res_race_ds",
        episode_id=None,
        job_id="job_race_ds",
        provider_id="deepseek_chat",
        estimated_micro_usd=prefill_deepseek,
        now_ms=2_000,
    )
    conn = connect(db_path)
    try:
        prefill = charged(conn)
    finally:
        conn.close()
    assert prefill == GEMINI_OMNI_MONTHLY_CAP + prefill_deepseek
    headroom = ALL_PROVIDERS_CAP - prefill
    assert headroom == 4_000_000
    each = 3_000_000
    assert each <= headroom
    assert each * 2 > headroom
    assert prefill_deepseek + each * 2 <= DEEPSEEK_CAP

    barrier = threading.Barrier(2)
    ok: list[str] = []
    errors: list[BudgetCapExceeded] = []
    unexpected: list[BaseException] = []

    def attempt(reservation_id: str) -> None:
        barrier.wait(timeout=10)
        try:
            reserve(
                repo,
                reservation_id=reservation_id,
                episode_id=None,
                job_id=reservation_id,
                provider_id="deepseek_chat",
                estimated_micro_usd=each,
                now_ms=3_000,
            )
        except BudgetCapExceeded as exc:
            errors.append(exc)
        except BaseException as exc:  # noqa: BLE001 — surface lock errors in the assertion
            unexpected.append(exc)
        else:
            ok.append(reservation_id)

    threads = [
        threading.Thread(target=attempt, args=("race_a",)),
        threading.Thread(target=attempt, args=("race_b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert unexpected == []
    assert len(ok) == 1
    assert len(errors) == 1
    assert errors[0].code == "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED"
    conn = connect(db_path)
    try:
        total = charged(conn)
    finally:
        conn.close()
    assert total == prefill + each
    assert total <= ALL_PROVIDERS_CAP


def test_concurrent_act1_reservations_stay_within_forty_percent(db_path: Path) -> None:
    repo = repo_for(db_path)
    each = 3_000_000
    assert each <= ACT1_CAP
    assert each * 2 > ACT1_CAP
    assert each * 2 < EPISODE_VIDEO_CAP

    barrier = threading.Barrier(2)
    ok: list[str] = []
    errors: list[BudgetCapExceeded] = []
    unexpected: list[BaseException] = []

    def attempt(reservation_id: str) -> None:
        barrier.wait(timeout=10)
        try:
            reserve(
                repo,
                reservation_id=reservation_id,
                episode_id="ep_1",
                job_id=reservation_id,
                provider_id="gemini_omni",
                estimated_micro_usd=each,
                act_number=1,
                now_ms=4_000,
                flow_backend_mode="GEMINI_OMNI_INTERACTIONS",
            )
        except BudgetCapExceeded as exc:
            errors.append(exc)
        except BaseException as exc:  # noqa: BLE001
            unexpected.append(exc)
        else:
            ok.append(reservation_id)

    threads = [
        threading.Thread(target=attempt, args=("act_race_a",)),
        threading.Thread(target=attempt, args=("act_race_b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()

    assert unexpected == []
    assert len(ok) == 1
    assert len(errors) == 1
    assert errors[0].code == "ACT1_HERO_ALLOCATION_EXCEEDED"
    conn = connect(db_path)
    try:
        assert charged(conn) == each
        assert charged(conn) <= ACT1_CAP
    finally:
        conn.close()
