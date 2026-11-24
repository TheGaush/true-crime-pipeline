"""CourtListener three-window rate limiter and persistent opinion cache."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

LIMIT_PER_MINUTE = 5
LIMIT_PER_HOUR = 50
LIMIT_PER_DAY = 125

WINDOW_MINUTE_MS = 60_000
WINDOW_HOUR_MS = 3_600_000
WINDOW_DAY_MS = 86_400_000

COURTLISTENER_CACHE_FALLBACK_DDL = """
CREATE TABLE IF NOT EXISTS courtlistener_cache (
  cache_key    TEXT PRIMARY KEY,
  opinion_id   TEXT,
  payload_json TEXT NOT NULL,
  fetched_at_ms INTEGER NOT NULL
);
"""

DEFAULT_CACHE_TTL_MS = 7 * 86_400_000


@dataclass(frozen=True, slots=True)
class FetchResult:
    status_code: int
    body: str = ""
    retry_after_seconds: int | None = None


@dataclass(frozen=True, slots=True)
class OpinionResult:
    ok: bool
    cache_hit: bool
    payload: dict[str, Any] | None
    api_calls: int
    wait_ms: int = 0
    http_status: int | None = None


def ensure_courtlistener_cache(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'courtlistener_cache'"
    ).fetchone()
    if row is None:
        conn.execute(COURTLISTENER_CACHE_FALLBACK_DDL)
        conn.commit()


def _column_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(courtlistener_cache)").fetchall()
    return {str(r[1]) for r in rows}


class CourtListenerRateLimiter:
    """Sliding-window limiter for 5/min, 50/hr, and 125/day API ceilings."""

    _windows: tuple[tuple[int, int], ...] = (
        (WINDOW_MINUTE_MS, LIMIT_PER_MINUTE),
        (WINDOW_HOUR_MS, LIMIT_PER_HOUR),
        (WINDOW_DAY_MS, LIMIT_PER_DAY),
    )

    def __init__(self) -> None:
        self._request_times_ms: list[int] = []
        self._retry_until_ms: int | None = None

    @property
    def request_count(self) -> int:
        return len(self._request_times_ms)

    def peek_wait_ms(self, now_ms: int) -> int:
        if self._retry_until_ms is not None and now_ms < self._retry_until_ms:
            return self._retry_until_ms - now_ms
        return self._sliding_wait_ms(now_ms)

    def record_request(self, now_ms: int) -> None:
        self._prune(now_ms)
        self._request_times_ms.append(now_ms)

    def record_429(self, now_ms: int, retry_after_seconds: int) -> None:
        block_until = now_ms + retry_after_seconds * 1000
        if self._retry_until_ms is None or block_until > self._retry_until_ms:
            self._retry_until_ms = block_until

    def _prune(self, now_ms: int) -> None:
        cutoff = now_ms - WINDOW_DAY_MS
        self._request_times_ms = [t for t in self._request_times_ms if t > cutoff]

    def _count_in_window(self, now_ms: int, window_ms: int) -> int:
        cutoff = now_ms - window_ms
        return sum(1 for t in self._request_times_ms if t > cutoff)

    def _sliding_wait_ms(self, now_ms: int) -> int:
        self._prune(now_ms)
        wait_ms = 0
        for window_ms, limit in self._windows:
            times_in_window = sorted(t for t in self._request_times_ms if t > now_ms - window_ms)
            if len(times_in_window) >= limit:
                oldest = times_in_window[0]
                window_wait = oldest + window_ms - now_ms
                if window_wait > wait_ms:
                    wait_ms = window_wait
        return max(wait_ms, 0)


class CourtListenerRepository:
    """SQLite-backed CourtListener opinions with rate-paced HTTP fetch."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        limiter: CourtListenerRateLimiter,
        fetch_fn: Callable[[str], FetchResult],
    ) -> None:
        ensure_courtlistener_cache(conn)
        self._conn = conn
        self._limiter = limiter
        self._fetch_fn = fetch_fn
        self._columns = _column_names(conn)

    def get_opinion(self, cache_key: str, opinion_id: str, now_ms: int) -> OpinionResult:
        cached = self._read_cache(cache_key)
        if cached is not None:
            return OpinionResult(
                ok=True,
                cache_hit=True,
                payload=cached,
                api_calls=0,
            )

        wait_ms = self._limiter.peek_wait_ms(now_ms)
        if wait_ms > 0:
            return OpinionResult(
                ok=False,
                cache_hit=False,
                payload=None,
                api_calls=0,
                wait_ms=wait_ms,
            )

        self._limiter.record_request(now_ms)
        response = self._fetch_fn(opinion_id)

        if response.status_code == 429:
            retry_after = response.retry_after_seconds or 60
            self._limiter.record_429(now_ms, retry_after)
            return OpinionResult(
                ok=False,
                cache_hit=False,
                payload=None,
                api_calls=1,
                wait_ms=retry_after * 1000,
                http_status=429,
            )

        if response.status_code != 200:
            return OpinionResult(
                ok=False,
                cache_hit=False,
                payload=None,
                api_calls=1,
                http_status=response.status_code,
            )

        payload = json.loads(response.body) if response.body else {}
        self._write_cache(cache_key, opinion_id, payload, now_ms)
        return OpinionResult(
            ok=True,
            cache_hit=False,
            payload=payload,
            api_calls=1,
            http_status=200,
        )

    def _read_cache(self, cache_key: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload_json FROM courtlistener_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def _write_cache(
        self,
        cache_key: str,
        opinion_id: str,
        payload: dict[str, Any],
        now_ms: int,
    ) -> None:
        payload_json = json.dumps(payload, separators=(",", ":"))
        cols = self._columns
        if "fetched_at_ms" in cols:
            self._conn.execute(
                """
                INSERT INTO courtlistener_cache (cache_key, opinion_id, payload_json, fetched_at_ms)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  opinion_id = excluded.opinion_id,
                  payload_json = excluded.payload_json,
                  fetched_at_ms = excluded.fetched_at_ms
                """,
                (cache_key, opinion_id, payload_json, now_ms),
            )
        elif "fetched_at" in cols and "expires_at" in cols:
            expires_at = now_ms + DEFAULT_CACHE_TTL_MS
            id_col = "docket_id" if "docket_id" in cols else "opinion_id"
            self._conn.execute(
                f"""
                INSERT INTO courtlistener_cache (cache_key, {id_col}, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                  {id_col} = excluded.{id_col},
                  payload_json = excluded.payload_json,
                  fetched_at = excluded.fetched_at,
                  expires_at = excluded.expires_at
                """,
                (cache_key, opinion_id, payload_json, now_ms, expires_at),
            )
        else:
            raise RuntimeError("courtlistener_cache has an unsupported column layout")
        self._conn.commit()