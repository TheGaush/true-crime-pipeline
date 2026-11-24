"""Google Pro account daily/monthly credit ledger (Task 009)."""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TypeVar

DAILY_CREDITS_CAP = 50
MONTHLY_CREDITS_CAP = 1000
DAILY_RESET_OFFSET_MS = 86_400_000 + 300_000

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_QUERIES_PATH = _REPO_ROOT / "schema" / "queries.sql"

T = TypeVar("T")


class CreditPool(str, Enum):
    DAILY = "DAILY"
    MONTHLY_BASE = "MONTHLY_BASE"


@dataclass(frozen=True, slots=True)
class AccountCreditSnapshot:
    account_id: str
    monthly_credits_left: int
    daily_credits_left: int
    first_daily_spend_utc_ms: int
    next_daily_reset_utc_ms: int


@dataclass(frozen=True, slots=True)
class DailyLockStatus:
    locked: bool
    seconds_until_reset: int


@dataclass(frozen=True, slots=True)
class ReserveOutcome:
    ok: bool
    snapshot: AccountCreditSnapshot | None
    pool: CreditPool


class DailyCreditsLockedError(RuntimeError):
    """Daily pool is locked until the rolling 24h + 5m reset window elapses."""


class InsufficientCreditsError(RuntimeError):
    """Requested credits exceed the selected pool balance."""


def extract_named_query(queries_sql: str, name: str) -> str:
    pattern = rf"-- name: {re.escape(name)}\r?\n([\s\S]*?)(?=\r?\n-- name:|$)"
    match = re.search(pattern, queries_sql)
    if not match:
        raise KeyError(f"Query '{name}' not found in queries.sql")
    return match.group(1).strip()


def load_named_query(name: str, queries_path: Path | None = None) -> str:
    path = queries_path or _DEFAULT_QUERIES_PATH
    queries_sql = path.read_text(encoding="utf-8")
    return extract_named_query(queries_sql, name)


_RESERVE_MONTHLY_SQL = """
UPDATE google_accounts
SET monthly_credits_left = monthly_credits_left - :credits
WHERE account_id = :account_id
  AND :credits > 0
  AND monthly_credits_left >= :credits
RETURNING
  account_id,
  monthly_credits_left,
  daily_credits_left,
  first_daily_spend_utc_ms,
  next_daily_reset_utc_ms
"""

_SELECT_ACCOUNT_SQL = """
SELECT
  account_id,
  monthly_credits_left,
  daily_credits_left,
  first_daily_spend_utc_ms,
  next_daily_reset_utc_ms
FROM google_accounts
WHERE account_id = ?
"""


class AccountPoolLedger:
    """Tracks optional Pro account daily (50) and monthly (1,000) credit pools."""

    def __init__(
        self,
        db: sqlite3.Connection | Any,
        *,
        queries_path: Path | None = None,
    ) -> None:
        self._db = db
        self._queries_path = queries_path
        queries_sql = (queries_path or _DEFAULT_QUERIES_PATH).read_text(encoding="utf-8")
        self._reserve_daily_sql = extract_named_query(
            queries_sql, "atomic_refill_and_reserve_daily_account_credits"
        )
        self._refund_daily_sql = extract_named_query(
            queries_sql, "refund_daily_account_credits"
        )

    def get_account(self, account_id: str) -> AccountCreditSnapshot:
        row = self._connection().execute(_SELECT_ACCOUNT_SQL, (account_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown account_id={account_id!r}")
        return _row_to_snapshot(row)

    def is_account_daily_locked(
        self,
        account_id: str,
        now_ms: int,
        *,
        credits: int = 1,
    ) -> DailyLockStatus:
        account = self.get_account(account_id)
        in_reset_window = (
            account.next_daily_reset_utc_ms > 0 and now_ms < account.next_daily_reset_utc_ms
        )
        daily_exhausted = account.daily_credits_left < credits
        locked = in_reset_window and daily_exhausted
        seconds_until_reset = 0
        if in_reset_window:
            seconds_until_reset = max(
                0,
                int(math.ceil((account.next_daily_reset_utc_ms - now_ms) / 1000)),
            )
        return DailyLockStatus(locked=locked, seconds_until_reset=seconds_until_reset)

    def reserve_credits(
        self,
        account_id: str,
        credits: int,
        now_ms: int,
        *,
        pool: CreditPool | str = CreditPool.DAILY,
    ) -> ReserveOutcome:
        if credits <= 0:
            raise ValueError("credits must be positive")
        pool = CreditPool(pool)

        def _reserve(conn: sqlite3.Connection) -> ReserveOutcome:
            monthly_before = conn.execute(
                "SELECT monthly_credits_left FROM google_accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
            if monthly_before is None:
                raise KeyError(f"Unknown account_id={account_id!r}")

            if pool is CreditPool.DAILY:
                lock = self.is_account_daily_locked(account_id, now_ms, credits=credits)
                if lock.locked:
                    snap = self.get_account(account_id)
                    return ReserveOutcome(ok=False, snapshot=snap, pool=pool)

                row = conn.execute(
                    self._reserve_daily_sql,
                    {
                        "account_id": account_id,
                        "credits": credits,
                        "now_ms": now_ms,
                    },
                ).fetchone()
                if row is None:
                    monthly_after = conn.execute(
                        "SELECT monthly_credits_left FROM google_accounts WHERE account_id = ?",
                        (account_id,),
                    ).fetchone()
                    if monthly_after and monthly_after[0] != monthly_before[0]:
                        raise RuntimeError(
                            "Zero early-click monthly drain invariant violated"
                        )
                    snap = self.get_account(account_id)
                    return ReserveOutcome(ok=False, snapshot=snap, pool=pool)
                return ReserveOutcome(
                    ok=True, snapshot=self.get_account(account_id), pool=pool
                )

            row = conn.execute(
                _RESERVE_MONTHLY_SQL,
                {"account_id": account_id, "credits": credits},
            ).fetchone()
            if row is None:
                snap = self.get_account(account_id)
                return ReserveOutcome(ok=False, snapshot=snap, pool=pool)
            return ReserveOutcome(
                ok=True, snapshot=self.get_account(account_id), pool=pool
            )

        outcome = self._run_write(_reserve)
        if pool is CreditPool.DAILY and not outcome.ok:
            raise DailyCreditsLockedError(
                f"Daily credits locked for {account_id!r} at now_ms={now_ms}"
            )
        if pool is CreditPool.MONTHLY_BASE and not outcome.ok:
            raise InsufficientCreditsError(
                f"Insufficient monthly credits for {account_id!r}"
            )
        return outcome

    def try_reserve_credits(
        self,
        account_id: str,
        credits: int,
        now_ms: int,
        *,
        pool: CreditPool | str = CreditPool.DAILY,
    ) -> ReserveOutcome:
        """Reserve without raising when the pool refuses the spend."""
        if credits <= 0:
            raise ValueError("credits must be positive")
        pool = CreditPool(pool)

        def _reserve(conn: sqlite3.Connection) -> ReserveOutcome:
            if pool is CreditPool.DAILY:
                row = conn.execute(
                    self._reserve_daily_sql,
                    {
                        "account_id": account_id,
                        "credits": credits,
                        "now_ms": now_ms,
                    },
                ).fetchone()
            else:
                row = conn.execute(
                    _RESERVE_MONTHLY_SQL,
                    {"account_id": account_id, "credits": credits},
                ).fetchone()
            if row is None:
                snap = self.get_account(account_id)
                return ReserveOutcome(ok=False, snapshot=snap, pool=pool)
            return ReserveOutcome(
                ok=True, snapshot=self.get_account(account_id), pool=pool
            )

        return self._run_write(_reserve)

    def refund_daily_credits(
        self,
        account_id: str,
        credits: int,
        now_ms: int,
    ) -> AccountCreditSnapshot | None:
        if credits <= 0:
            raise ValueError("credits must be positive")

        def _refund(conn: sqlite3.Connection) -> AccountCreditSnapshot | None:
            row = conn.execute(
                self._refund_daily_sql,
                {
                    "account_id": account_id,
                    "credits": credits,
                    "now_ms": now_ms,
                },
            ).fetchone()
            if row is None:
                return None
            return self.get_account(account_id)

        return self._run_write(_refund)

    def _connection(self) -> sqlite3.Connection:
        if isinstance(self._db, sqlite3.Connection):
            return self._db
        conn = getattr(self._db, "connection", None)
        if conn is None:
            raise TypeError("db must be sqlite3.Connection or expose .connection")
        return conn

    def _run_write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        db = self._db
        write_txn = getattr(db, "write_transaction", None)
        if callable(write_txn):
            with write_txn() as conn:
                return fn(conn)
        immediate = getattr(db, "write_immediate", None)
        if callable(immediate):
            return immediate(fn)

        conn = self._connection()
        in_txn = conn.in_transaction
        if in_txn:
            return fn(conn)
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = fn(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise


def _row_to_snapshot(row: sqlite3.Row | tuple[Any, ...]) -> AccountCreditSnapshot:
    if isinstance(row, sqlite3.Row):
        keys = set(row.keys())
        return AccountCreditSnapshot(
            account_id=row["account_id"],
            monthly_credits_left=int(row["monthly_credits_left"])
            if "monthly_credits_left" in keys
            else 0,
            daily_credits_left=int(row["daily_credits_left"]),
            first_daily_spend_utc_ms=int(
                row["first_daily_spend_utc_ms"]
                if "first_daily_spend_utc_ms" in keys
                else 0
            ),
            next_daily_reset_utc_ms=int(
                row["next_daily_reset_utc_ms"]
                if "next_daily_reset_utc_ms" in keys
                else 0
            ),
        )
    if len(row) >= 5:
        return AccountCreditSnapshot(
            account_id=str(row[0]),
            monthly_credits_left=int(row[1]),
            daily_credits_left=int(row[2]),
            first_daily_spend_utc_ms=int(row[3]),
            next_daily_reset_utc_ms=int(row[4]),
        )
    return AccountCreditSnapshot(
        account_id=str(row[0]),
        monthly_credits_left=0,
        daily_credits_left=int(row[1]),
        first_daily_spend_utc_ms=int(row[2]),
        next_daily_reset_utc_ms=int(row[3]),
    )