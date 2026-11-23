"""SQLite access for the desk. Transactions stay short."""

from __future__ import annotations

import sqlite3
from pathlib import Path

REQUIRED_SQLITE = (3, 51, 3)


class SqliteTooOldError(RuntimeError):
    pass


def require_sqlite(version: tuple[int, int, int] | None = None) -> None:
    found = version or sqlite3.sqlite_version_info
    if found < REQUIRED_SQLITE:
        raise SqliteTooOldError(f"sqlite {found} is older than {REQUIRED_SQLITE}")


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS cards (
          episode_id TEXT NOT NULL,
          scene_id TEXT NOT NULL,
          status TEXT NOT NULL,
          PRIMARY KEY (episode_id, scene_id)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY,
          action TEXT NOT NULL,
          detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
          episode_id TEXT NOT NULL,
          gate TEXT NOT NULL,
          reviewer_id TEXT NOT NULL,
          PRIMARY KEY (episode_id, gate)
        );
        """
    )
    return connection


def audit(connection: sqlite3.Connection, action: str, detail: str) -> None:
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO audit_log (action, detail) VALUES (?, ?)", (action, detail))
    connection.execute("COMMIT")


def claim(connection: sqlite3.Connection, episode_id: str, scene_id: str) -> bool:
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute(
        "SELECT status FROM cards WHERE episode_id = ? AND scene_id = ?",
        (episode_id, scene_id),
    ).fetchone()
    if row and row["status"] == "CLAIMED":
        connection.execute("COMMIT")
        return False
    connection.execute(
        "INSERT INTO cards (episode_id, scene_id, status) VALUES (?, ?, 'CLAIMED') "
        "ON CONFLICT(episode_id, scene_id) DO UPDATE SET status = 'CLAIMED'",
        (episode_id, scene_id),
    )
    connection.execute("INSERT INTO audit_log (action, detail) VALUES ('CLAIM', ?)", (f"{episode_id}:{scene_id}",))
    connection.execute("COMMIT")
    return True


def contained(root: str, candidate: str) -> bool:
    base = Path(root).resolve()
    try:
        return Path(candidate).resolve().is_relative_to(base)
    except ValueError:
        return False
