from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest

from courtlistener_repo import (
    CourtListenerRateLimiter,
    CourtListenerRepository,
    FetchResult,
    LIMIT_PER_DAY,
    LIMIT_PER_HOUR,
    LIMIT_PER_MINUTE,
    WINDOW_DAY_MS,
    WINDOW_HOUR_MS,
    WINDOW_MINUTE_MS,
    ensure_courtlistener_cache,
)


def _payload(opinion_id: str) -> dict[str, Any]:
    return {"id": opinion_id, "text": f"opinion-{opinion_id}"}


@pytest.fixture
def fallback_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ensure_courtlistener_cache(conn)
    return conn


@pytest.fixture
def pipeline_schema_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE courtlistener_cache (
          cache_key    TEXT PRIMARY KEY,
          docket_id    TEXT,
          payload_json TEXT NOT NULL,
          fetched_at   INTEGER NOT NULL,
          expires_at   INTEGER NOT NULL
        )
        """
    )
    return conn


def test_cache_hit_reuses_payload_without_api_calls() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_courtlistener_cache(conn)
    limiter = CourtListenerRateLimiter()
    calls: list[str] = []

    def fetcher(opinion_id: str) -> FetchResult:
        calls.append(opinion_id)
        return FetchResult(200, json.dumps(_payload(opinion_id)))

    repo = CourtListenerRepository(conn, limiter, fetcher)
    now_ms = 1_700_000_000_000

    first = repo.get_opinion("cl:op-1", "op-1", now_ms)
    second = repo.get_opinion("cl:op-1", "op-1", now_ms)

    assert first.ok and first.cache_hit is False and first.api_calls == 1
    assert second.ok and second.cache_hit is True and second.api_calls == 0
    assert calls == ["op-1"]
    assert limiter.request_count == 1


def test_minute_ceiling_blocks_sixth_request_in_same_minute() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_courtlistener_cache(conn)
    limiter = CourtListenerRateLimiter()
    fetch_calls = 0

    def fetcher(opinion_id: str) -> FetchResult:
        nonlocal fetch_calls
        fetch_calls += 1
        return FetchResult(200, json.dumps(_payload(opinion_id)))

    repo = CourtListenerRepository(conn, limiter, fetcher)
    base_ms = 1_700_000_000_000

    for i in range(LIMIT_PER_MINUTE):
        result = repo.get_opinion(f"cl:minute-{i}", f"minute-{i}", base_ms)
        assert result.ok and result.wait_ms == 0

    sixth = repo.get_opinion("cl:minute-5", "minute-5", base_ms)
    assert sixth.ok is False
    assert sixth.wait_ms == WINDOW_MINUTE_MS
    assert sixth.api_calls == 0
    assert fetch_calls == LIMIT_PER_MINUTE


def test_hour_ceiling_blocks_fifty_first_request_in_same_hour() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_courtlistener_cache(conn)
    limiter = CourtListenerRateLimiter()
    base_ms = 2_000_000_000_000

    def fetcher(opinion_id: str) -> FetchResult:
        return FetchResult(200, json.dumps(_payload(opinion_id)))

    repo = CourtListenerRepository(conn, limiter, fetcher)

    for i in range(LIMIT_PER_HOUR):
        ms = base_ms + (i // LIMIT_PER_MINUTE) * WINDOW_MINUTE_MS
        result = repo.get_opinion(f"cl:hr-{i}", f"hr-{i}", ms)
        assert result.ok, i

    blocked = repo.get_opinion("cl:hr-blocked", "hr-blocked", base_ms + WINDOW_HOUR_MS - 1)
    assert blocked.ok is False
    assert blocked.wait_ms > 0
    assert blocked.api_calls == 0


def test_day_ceiling_blocks_hundred_twenty_sixth_request() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_courtlistener_cache(conn)
    limiter = CourtListenerRateLimiter()
    base_ms = 3_000_000_000_000

    def fetcher(opinion_id: str) -> FetchResult:
        return FetchResult(200, json.dumps(_payload(opinion_id)))

    repo = CourtListenerRepository(conn, limiter, fetcher)

    for i in range(LIMIT_PER_DAY):
        hour_bucket = i // LIMIT_PER_HOUR
        minute_in_hour = (i % LIMIT_PER_HOUR) // LIMIT_PER_MINUTE
        ms = base_ms + hour_bucket * WINDOW_HOUR_MS + minute_in_hour * WINDOW_MINUTE_MS
        result = repo.get_opinion(f"cl:day-{i}", f"day-{i}", ms)
        assert result.ok, i

    blocked = repo.get_opinion(
        "cl:day-blocked",
        "day-blocked",
        base_ms + WINDOW_DAY_MS - 1,
    )
    assert blocked.ok is False
    assert blocked.wait_ms > 0


def test_retry_after_honors_429_backoff_without_further_calls() -> None:
    conn = sqlite3.connect(":memory:")
    ensure_courtlistener_cache(conn)
    limiter = CourtListenerRateLimiter()
    now_ms = 4_000_000_000_000
    attempts = 0

    def fetcher(opinion_id: str) -> FetchResult:
        nonlocal attempts
        attempts += 1
        return FetchResult(429, retry_after_seconds=30)

    repo = CourtListenerRepository(conn, limiter, fetcher)

    throttled = repo.get_opinion("cl:retry", "retry-op", now_ms)
    assert throttled.http_status == 429
    assert throttled.wait_ms == 30_000
    assert attempts == 1

    blocked = repo.get_opinion("cl:retry-2", "retry-op-2", now_ms + 10_000)
    assert blocked.ok is False
    assert blocked.wait_ms == 20_000
    assert blocked.api_calls == 0
    assert attempts == 1

    allowed = repo.get_opinion("cl:retry-3", "retry-op-3", now_ms + 30_000)
    assert allowed.ok is False
    assert allowed.http_status == 429
    assert allowed.api_calls == 1
    assert attempts == 2


def test_writes_pipeline_schema_cache_columns(pipeline_schema_conn: sqlite3.Connection) -> None:
    limiter = CourtListenerRateLimiter()

    def fetcher(opinion_id: str) -> FetchResult:
        return FetchResult(200, json.dumps(_payload(opinion_id)))

    repo = CourtListenerRepository(pipeline_schema_conn, limiter, fetcher)
    now_ms = 5_000_000_000_000
    result = repo.get_opinion("cl:pipeline", "dk-99", now_ms)
    assert result.ok

    row = pipeline_schema_conn.execute(
        "SELECT cache_key, docket_id, payload_json, fetched_at, expires_at "
        "FROM courtlistener_cache WHERE cache_key = ?",
        ("cl:pipeline",),
    ).fetchone()
    assert row is not None
    assert row[0] == "cl:pipeline"
    assert row[1] == "dk-99"
    assert json.loads(row[2]) == _payload("dk-99")
    assert row[3] == now_ms
    assert row[4] > now_ms


def test_limiter_peek_is_deterministic_from_now_ms_only() -> None:
    limiter = CourtListenerRateLimiter()
    now_ms = 6_000_000_000_000

    for i in range(LIMIT_PER_MINUTE):
        limiter.record_request(now_ms)

    assert limiter.peek_wait_ms(now_ms) == WINDOW_MINUTE_MS
    assert limiter.peek_wait_ms(now_ms + WINDOW_MINUTE_MS) == 0