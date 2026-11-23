"""Episode spend ledger. Holds count until they are released."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

EPISODE_CAP_MICRO_USD = 10_400_000
DAILY_LOCK_MS = 86_700_000


class BudgetCapError(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetSnapshot:
    reserved_micro_usd: int
    committed_micro_usd: int
    unknown_hold_micro_usd: int
    remaining_cap_micro_usd: int


def open_ledger(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS budget_reservations (
          id INTEGER PRIMARY KEY,
          episode_id TEXT NOT NULL,
          scene_id TEXT NOT NULL,
          micro_usd INTEGER NOT NULL,
          status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS google_accounts (
          account_id TEXT PRIMARY KEY,
          first_spend_ms INTEGER,
          next_reset_ms INTEGER
        );
        """
    )
    return connection


def reserve(connection: sqlite3.Connection, episode_id: str, scene_id: str, micro_usd: int) -> int:
    if _held(connection, episode_id) + micro_usd > EPISODE_CAP_MICRO_USD:
        raise BudgetCapError("episode cap")
    cursor = connection.execute(
        "INSERT INTO budget_reservations (episode_id, scene_id, micro_usd, status) VALUES (?, ?, ?, 'RESERVED')",
        (episode_id, scene_id, micro_usd),
    )
    connection.commit()
    return int(cursor.lastrowid)


def mark_unknown(connection: sqlite3.Connection, episode_id: str, scene_id: str) -> None:
    connection.execute(
        "UPDATE budget_reservations SET status = 'UNKNOWN_HOLD' WHERE episode_id = ? AND scene_id = ?",
        (episode_id, scene_id),
    )
    connection.commit()


def release(connection: sqlite3.Connection, episode_id: str, scene_id: str) -> None:
    connection.execute(
        "UPDATE budget_reservations SET status = 'RELEASED', micro_usd = 0 WHERE episode_id = ? AND scene_id = ?",
        (episode_id, scene_id),
    )
    connection.commit()


def commit_spend(connection: sqlite3.Connection, episode_id: str, scene_id: str) -> None:
    connection.execute(
        "UPDATE budget_reservations SET status = 'COMMITTED' WHERE episode_id = ? AND scene_id = ?",
        (episode_id, scene_id),
    )
    connection.commit()


def snapshot(connection: sqlite3.Connection, episode_id: str) -> BudgetSnapshot:
    def total(status: str) -> int:
        return int(
            connection.execute(
                "SELECT COALESCE(SUM(micro_usd), 0) FROM budget_reservations WHERE episode_id = ? AND status = ?",
                (episode_id, status),
            ).fetchone()[0]
        )

    reserved = total("RESERVED")
    committed = total("COMMITTED")
    unknown = total("UNKNOWN_HOLD")
    return BudgetSnapshot(reserved, committed, unknown, EPISODE_CAP_MICRO_USD - reserved - committed - unknown)


def refill_account(connection: sqlite3.Connection, account_id: str, now_ms: int) -> int:
    row = connection.execute("SELECT next_reset_ms FROM google_accounts WHERE account_id = ?", (account_id,)).fetchone()
    if row and row[0] is not None and now_ms < int(row[0]):
        raise BudgetCapError("account locked")
    reset = now_ms + DAILY_LOCK_MS
    connection.execute(
        "INSERT INTO google_accounts (account_id, first_spend_ms, next_reset_ms) VALUES (?, ?, ?) "
        "ON CONFLICT(account_id) DO UPDATE SET first_spend_ms = excluded.first_spend_ms, next_reset_ms = excluded.next_reset_ms",
        (account_id, now_ms, reset),
    )
    connection.commit()
    return reset


def _held(connection: sqlite3.Connection, episode_id: str) -> int:
    return int(
        connection.execute(
            "SELECT COALESCE(SUM(micro_usd), 0) FROM budget_reservations WHERE episode_id = ? AND status != 'RELEASED'",
            (episode_id,),
        ).fetchone()[0]
    )
