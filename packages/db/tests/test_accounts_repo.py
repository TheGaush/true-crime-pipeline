"""AccountPoolLedger tests — 24h + 5m rolling reset (offline, injected clock)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from accounts_repo import (
    DAILY_CREDITS_CAP,
    DAILY_RESET_OFFSET_MS,
    MONTHLY_CREDITS_CAP,
    AccountPoolLedger,
    CreditPool,
    DailyCreditsLockedError,
    extract_named_query,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_SQL = _REPO_ROOT / "schema" / "pipeline.sql"
_QUERIES_SQL = _REPO_ROOT / "schema" / "queries.sql"

T0 = 1_700_000_000_000
ACCOUNT_ID = "acct_1"


@pytest.fixture
def conn() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("PRAGMA foreign_keys = ON;")
    db.executescript(_PIPELINE_SQL.read_text(encoding="utf-8"))
    return db


@pytest.fixture
def ledger(conn: sqlite3.Connection) -> AccountPoolLedger:
    return AccountPoolLedger(conn, queries_path=_QUERIES_SQL)


def test_named_queries_match_schema_test_js() -> None:
    sql = _QUERIES_SQL.read_text(encoding="utf-8")
    atomic = extract_named_query(sql, "atomic_refill_and_reserve_daily_account_credits")
    refund = extract_named_query(sql, "refund_daily_account_credits")
    assert "86400000 + 300000" in atomic
    assert "daily_credits_cap - :credits" in atomic
    assert "MIN(daily_credits_cap" in refund


def test_f08_atomic_daily_lock_and_refill(ledger: AccountPoolLedger) -> None:
    """Mirrors schema-test.js #8 (F-08)."""
    expected_reset = T0 + DAILY_RESET_OFFSET_MS

    outcome = ledger.reserve_credits(ACCOUNT_ID, DAILY_CREDITS_CAP, T0)
    assert outcome.ok
    assert outcome.snapshot is not None
    assert outcome.snapshot.daily_credits_left == 0
    assert outcome.snapshot.first_daily_spend_utc_ms == T0
    assert outcome.snapshot.next_daily_reset_utc_ms == expected_reset

    with pytest.raises(DailyCreditsLockedError):
        ledger.reserve_credits(ACCOUNT_ID, 10, expected_reset - 1)

    outcome2 = ledger.reserve_credits(ACCOUNT_ID, 10, expected_reset)
    assert outcome2.snapshot is not None
    assert outcome2.snapshot.daily_credits_left == DAILY_CREDITS_CAP - 10
    assert outcome2.snapshot.next_daily_reset_utc_ms == expected_reset + DAILY_RESET_OFFSET_MS


def test_three_minutes_before_reset_does_not_touch_monthly(
    ledger: AccountPoolLedger,
) -> None:
    expected_reset = T0 + DAILY_RESET_OFFSET_MS
    ledger.reserve_credits(ACCOUNT_ID, DAILY_CREDITS_CAP, T0)
    before = ledger.get_account(ACCOUNT_ID)
    assert before.monthly_credits_left == MONTHLY_CREDITS_CAP

    early_ms = expected_reset - 180_000
    lock = ledger.is_account_daily_locked(ACCOUNT_ID, early_ms)
    assert lock.locked is True
    assert lock.seconds_until_reset == 180

    outcome = ledger.try_reserve_credits(ACCOUNT_ID, 1, early_ms)
    assert outcome.ok is False
    after = ledger.get_account(ACCOUNT_ID)
    assert after.monthly_credits_left == MONTHLY_CREDITS_CAP
    assert after.daily_credits_left == 0


def test_monthly_base_bypasses_daily_lock(ledger: AccountPoolLedger) -> None:
    expected_reset = T0 + DAILY_RESET_OFFSET_MS
    ledger.reserve_credits(ACCOUNT_ID, DAILY_CREDITS_CAP, T0)

    outcome = ledger.reserve_credits(
        ACCOUNT_ID,
        25,
        expected_reset - 60_000,
        pool=CreditPool.MONTHLY_BASE,
    )
    assert outcome.ok
    assert outcome.snapshot is not None
    assert outcome.snapshot.monthly_credits_left == MONTHLY_CREDITS_CAP - 25
    assert outcome.snapshot.daily_credits_left == 0


def test_refund_daily_only_inside_reset_window(ledger: AccountPoolLedger) -> None:
    expected_reset = T0 + DAILY_RESET_OFFSET_MS
    ledger.reserve_credits(ACCOUNT_ID, 10, T0)
    mid = T0 + 1_000
    refunded = ledger.refund_daily_credits(ACCOUNT_ID, 5, mid)
    assert refunded is not None
    assert refunded.daily_credits_left == DAILY_CREDITS_CAP - 5

    assert ledger.refund_daily_credits(ACCOUNT_ID, 1, expected_reset) is None


def test_fourteen_day_simulation_injected_clock(ledger: AccountPoolLedger) -> None:
    """Fourteen rolling windows: exhaust, block early click, refill at reset."""
    now_ms = T0

    for _ in range(14):
        assert ledger.get_account(ACCOUNT_ID).monthly_credits_left == MONTHLY_CREDITS_CAP

        snap = ledger.get_account(ACCOUNT_ID)
        in_window = (
            snap.next_daily_reset_utc_ms > 0 and now_ms < snap.next_daily_reset_utc_ms
        )
        if in_window and snap.daily_credits_left > 0:
            ledger.reserve_credits(ACCOUNT_ID, snap.daily_credits_left, now_ms)
        elif not in_window:
            ledger.reserve_credits(ACCOUNT_ID, DAILY_CREDITS_CAP, now_ms)

        snap = ledger.get_account(ACCOUNT_ID)
        assert snap.daily_credits_left == 0
        expected_reset = snap.next_daily_reset_utc_ms

        pre_reset = expected_reset - 180_000
        lock = ledger.is_account_daily_locked(ACCOUNT_ID, pre_reset)
        assert lock.locked is True
        assert lock.seconds_until_reset == 180
        assert ledger.try_reserve_credits(ACCOUNT_ID, 1, pre_reset).ok is False
        assert ledger.get_account(ACCOUNT_ID).monthly_credits_left == MONTHLY_CREDITS_CAP

        outcome = ledger.reserve_credits(ACCOUNT_ID, 10, expected_reset)
        assert outcome.snapshot is not None
        assert outcome.snapshot.daily_credits_left == DAILY_CREDITS_CAP - 10
        assert outcome.snapshot.first_daily_spend_utc_ms == expected_reset
        assert (
            outcome.snapshot.next_daily_reset_utc_ms
            == expected_reset + DAILY_RESET_OFFSET_MS
        )

        now_ms = expected_reset + 1