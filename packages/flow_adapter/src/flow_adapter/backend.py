"""Provider selection and the durable spend ledger.

Rates and the primary model id are read from providers.yaml. A dispatch
without a reservation row is refused.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


class MissingProviderCredentialsError(RuntimeError):
    pass


class BudgetCapError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    adapter: str
    model_id: str
    usd_per_sec: float
    max_hero_clips: int
    max_hero_duration_sec: int
    episode_cap_micro_usd: int
    prompt_modes: dict[str, dict[str, int]]


def load_primary(providers_path: str) -> ProviderConfig:
    lines = Path(providers_path).read_text(encoding="utf8").splitlines()
    block: list[str] = []
    capture = False
    for line in lines:
        if line.startswith("  primary:"):
            capture = True
            continue
        if capture and line.startswith("  adapters:"):
            break
        if capture:
            block.append(line)
    values = _flat(block)
    modes: dict[str, dict[str, int]] = {}
    current = None
    for raw in block:
        if raw.startswith("      ") and raw.strip().endswith(":") and not raw.strip().startswith("min_") and not raw.strip().startswith("max_") and not raw.strip().startswith("frames"):
            current = raw.strip()[:-1]
            modes[current] = {}
        elif current and ":" in raw:
            key, value = raw.strip().split(":", 1)
            if key in {"min_sec", "max_sec", "frames"}:
                modes[current][key] = int(value.strip())
    return ProviderConfig(
        adapter=values["adapter"],
        model_id=values["model_id"],
        usd_per_sec=float(values["usd_per_sec"]),
        max_hero_clips=int(values["max_hero_clips"]),
        max_hero_duration_sec=int(values["max_hero_duration_sec"]),
        episode_cap_micro_usd=int(values["episode_cap_micro_usd"]),
        prompt_modes=modes,
    )


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
        CREATE TABLE IF NOT EXISTS flow_jobs (
          episode_id TEXT NOT NULL,
          scene_id TEXT NOT NULL,
          state TEXT NOT NULL,
          provider_operation_id TEXT,
          idempotency_key TEXT NOT NULL,
          UNIQUE(episode_id, scene_id)
        );
        """
    )
    return connection


def reserve(connection: sqlite3.Connection, episode_id: str, scene_id: str, micro_usd: int, cap: int) -> int:
    held = connection.execute(
        "SELECT COALESCE(SUM(micro_usd), 0) FROM budget_reservations WHERE episode_id = ? AND status != 'RELEASED'",
        (episode_id,),
    ).fetchone()[0]
    if held + micro_usd > cap:
        raise BudgetCapError("episode cap would be exceeded")
    cursor = connection.execute(
        "INSERT INTO budget_reservations (episode_id, scene_id, micro_usd, status) VALUES (?, ?, ?, 'RESERVED')",
        (episode_id, scene_id, micro_usd),
    )
    connection.execute(
        "INSERT INTO flow_jobs (episode_id, scene_id, state, idempotency_key) VALUES (?, ?, 'SUBMITTING', ?)",
        (episode_id, scene_id, f"{episode_id}:{scene_id}"),
    )
    connection.commit()
    return int(cursor.lastrowid)


def mark_unknown(connection: sqlite3.Connection, episode_id: str, scene_id: str, operation_id: str) -> None:
    connection.execute(
        "UPDATE flow_jobs SET state = 'UNKNOWN_RECONCILE', provider_operation_id = ? WHERE episode_id = ? AND scene_id = ?",
        (operation_id, episode_id, scene_id),
    )
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


def _flat(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in lines:
        if raw.startswith("    ") and not raw.startswith("     ") and ":" in raw:
            key, value = raw.strip().split(":", 1)
            values[key] = value.strip()
    return values
