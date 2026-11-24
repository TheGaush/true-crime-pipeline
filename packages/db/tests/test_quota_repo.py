"""Offline fake-clock tests for YouTube quota buckets and the 30-day ToS purge."""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import quota_repo  # noqa: E402
from quota_repo import (  # noqa: E402
    MissingYouTubeTtlError,
    QuotaRejected,
    QuotaTracker,
    load_named_queries,
    pacific_window_start_ms,
    repo_root,
)

PT = ZoneInfo("America/Los_Angeles")
DAY_MS = 24 * 60 * 60 * 1000
THIRTY_DAYS_MS = 30 * DAY_MS


def _utc_ms(year: int, month: int, day: int, hour: int, minute: int, second: int) -> int:
    instant = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    return int(instant.timestamp()) * 1000


# 2026-01-14 18:00:00 UTC is 2026-01-14 10:00:00 PST.
# 2026-01-15 07:59:59 UTC is still 2026-01-14 23:59:59 PST: the UTC date has
# rolled, and the Pacific date has not.
# 2026-01-15 08:00:00 UTC is 2026-01-15 00:00:00 PST, the next Pacific midnight.
PT_SAME_DAY_EARLIER_MS = _utc_ms(2026, 1, 14, 18, 0, 0)
BEFORE_PT_MIDNIGHT_MS = _utc_ms(2026, 1, 15, 7, 59, 59)
AT_PT_MIDNIGHT_MS = _utc_ms(2026, 1, 15, 8, 0, 0)
# Later on the Pacific date that begins at AT_PT_MIDNIGHT_MS.
SAME_PT_DAY_LATER_MS = _utc_ms(2026, 1, 16, 7, 30, 0)


def _local_midnight_ms(now_ms: int) -> int:
    instant = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).astimezone(PT)
    midnight = datetime(instant.year, instant.month, instant.day, tzinfo=PT)
    return int(midnight.timestamp()) * 1000


@pytest.fixture
def tracker(tmp_path: Path):
    db = QuotaTracker(tmp_path / "pipeline.db")
    try:
        yield db
    finally:
        db.close()


def test_utc_instants_cross_pacific_midnight() -> None:
    earlier = datetime.fromtimestamp(PT_SAME_DAY_EARLIER_MS / 1000, tz=timezone.utc)
    before = datetime.fromtimestamp(BEFORE_PT_MIDNIGHT_MS / 1000, tz=timezone.utc)
    after = datetime.fromtimestamp(AT_PT_MIDNIGHT_MS / 1000, tz=timezone.utc)
    assert earlier.astimezone(PT).date().isoformat() == "2026-01-14"
    assert before.astimezone(PT).date().isoformat() == "2026-01-14"
    assert earlier.date() != before.date()
    assert after.astimezone(PT).date().isoformat() == "2026-01-15"
    assert (after.astimezone(PT).hour, after.astimezone(PT).minute, after.astimezone(PT).second) == (
        0,
        0,
        0,
    )
    later = datetime.fromtimestamp(SAME_PT_DAY_LATER_MS / 1000, tz=timezone.utc).astimezone(PT)
    assert later.date() == after.astimezone(PT).date()


def test_schema_seed_is_loaded_once_and_not_duplicated(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    first = QuotaTracker(db_path)
    first.close()
    second = QuotaTracker(db_path)
    try:
        rows = second.connection.execute(
            """
            SELECT bucket_name, daily_limit, used_today, COUNT(*) AS n
            FROM quota_buckets
            GROUP BY bucket_name, daily_limit, used_today
            ORDER BY bucket_name
            """
        ).fetchall()
    finally:
        second.close()
    observed = {
        row["bucket_name"]: (row["daily_limit"], row["used_today"], row["n"])
        for row in rows
    }
    assert observed["yt_search"] == (100, 0, 1)
    assert observed["yt_general"] == (10000, 0, 1)
    assert observed["yt_insert"] == (100, 0, 1)
    assert observed["courtlistener"] == (125, 0, 1)


def test_missing_youtube_seeds_are_inserted_without_touching_existing_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "pipeline.db"
    seeded = QuotaTracker(db_path)
    seeded.connection.execute("DELETE FROM quota_buckets WHERE bucket_name = 'yt_search'")
    seeded.connection.execute(
        """
        UPDATE quota_buckets
        SET daily_limit = 125, used_today = 4, window_reset_at = 0
        WHERE bucket_name = 'courtlistener'
        """
    )
    seeded.close()

    restored = QuotaTracker(db_path)
    try:
        search = restored.get_bucket("yt_search")
        court = restored.get_bucket("courtlistener")
        assert search is not None and court is not None
        assert (search["daily_limit"], search["used_today"]) == (100, 0)
        assert (court["daily_limit"], court["used_today"], court["window_reset_at"]) == (
            125,
            4,
            0,
        )
        names = restored.connection.execute(
            "SELECT bucket_name FROM quota_buckets"
        ).fetchall()
    finally:
        restored.close()
    assert sorted(row["bucket_name"] for row in names) == [
        "courtlistener",
        "yt_general",
        "yt_insert",
        "yt_search",
    ]


def test_named_sql_matches_queries_file() -> None:
    queries = load_named_queries(repo_root() / "schema" / "queries.sql")
    consume = queries["consume_quota_bucket"]
    purge = queries["purge_expired_yt_api_records"]
    assert consume == (
        "UPDATE quota_buckets\n"
        "SET used_today = used_today + :units\n"
        "WHERE bucket_name = :bucket_name\n"
        "  AND used_today + :units <= daily_limit\n"
        "RETURNING bucket_name, used_today, daily_limit;"
    )
    assert purge == (
        "UPDATE outlier_candidates\n"
        "SET raw_yt_payload_json = NULL,\n"
        "    views_count = NULL,\n"
        "    outlier_ratio = NULL,\n"
        "    seed_packet_json = '{}',\n"
        "    yt_data_purged_at = :now_ms,\n"
        "    status = CASE WHEN status = 'CONSUMED' THEN 'CONSUMED' ELSE 'EXPIRED_TOS_PURGED' END\n"
        "WHERE track = 'TRACK_A_OUTLIER'\n"
        "  AND yt_ttl_expires_at <= :now_ms\n"
        "  AND yt_data_purged_at IS NULL;"
    )


def test_yt_search_reserve_blocks_ordinary_calls_and_allows_fifteen_rechecks(
    tracker: QuotaTracker,
) -> None:
    now_ms = BEFORE_PT_MIDNIGHT_MS
    for call in range(1, 86):
        result = tracker.consume_quota("yt_search", 1, now_ms)
        assert result.used_today == call
        assert result.daily_limit == 100

    with pytest.raises(QuotaRejected) as ordinary:
        tracker.consume_quota("yt_search", 1, now_ms)
    assert ordinary.value.reason == "search_reserve"
    assert tracker.get_bucket("yt_search")["used_today"] == 85

    with pytest.raises(QuotaRejected) as other_tag:
        tracker.consume_quota("yt_search", 1, now_ms, tag="scout")
    assert other_tag.value.reason == "search_reserve"

    for call in range(1, 16):
        result = tracker.consume_quota(
            "yt_search", 1, now_ms, tag="pre_render_recheck"
        )
        assert result.used_today == 85 + call

    with pytest.raises(QuotaRejected) as past_cap:
        tracker.consume_quota("yt_search", 1, now_ms, tag="pre_render_recheck")
    assert past_cap.value.reason == "daily_limit"
    assert tracker.get_bucket("yt_search")["used_today"] == 100


def test_ordinary_bulk_consume_cannot_enter_the_reserved_fifteen(
    tracker: QuotaTracker,
) -> None:
    now_ms = BEFORE_PT_MIDNIGHT_MS
    accepted = tracker.consume_quota("yt_search", 85, now_ms)
    assert accepted.used_today == 85
    with pytest.raises(QuotaRejected) as rejected:
        tracker.consume_quota("yt_search", 1, now_ms)
    assert rejected.value.reason == "search_reserve"
    assert tracker.get_bucket("yt_search")["used_today"] == 85


def test_single_ordinary_call_cannot_spend_into_the_reserved_fifteen(
    tmp_path: Path,
) -> None:
    with QuotaTracker(tmp_path / "fresh.db") as fresh:
        with pytest.raises(QuotaRejected) as over:
            fresh.consume_quota("yt_search", 86, BEFORE_PT_MIDNIGHT_MS)
        assert over.value.reason == "search_reserve"
        assert fresh.get_bucket("yt_search")["used_today"] == 0


def test_pre_render_recheck_can_spend_the_full_daily_limit(tracker: QuotaTracker) -> None:
    result = tracker.consume_quota(
        "yt_search", 100, BEFORE_PT_MIDNIGHT_MS, tag="pre_render_recheck"
    )
    assert result.used_today == 100
    with pytest.raises(QuotaRejected) as rejected:
        tracker.consume_quota(
            "yt_search", 1, BEFORE_PT_MIDNIGHT_MS, tag="pre_render_recheck"
        )
    assert rejected.value.reason == "daily_limit"


def test_nightly_poll_is_rejected_on_yt_search_only(tracker: QuotaTracker) -> None:
    now_ms = BEFORE_PT_MIDNIGHT_MS
    with pytest.raises(QuotaRejected) as rejected:
        tracker.consume_quota("yt_search", 1, now_ms, tag="nightly_poll")
    assert rejected.value.reason == "nightly_poll_forbidden"
    assert tracker.get_bucket("yt_search")["used_today"] == 0

    general = tracker.consume_quota("yt_general", 450, now_ms, tag="nightly_poll")
    assert general.used_today == 450
    assert tracker.get_bucket("yt_general")["daily_limit"] == 10000


def test_other_buckets_use_their_full_daily_limit(tracker: QuotaTracker) -> None:
    now_ms = BEFORE_PT_MIDNIGHT_MS
    assert tracker.consume_quota("yt_insert", 100, now_ms).used_today == 100
    with pytest.raises(QuotaRejected) as insert_rejected:
        tracker.consume_quota("yt_insert", 1, now_ms)
    assert insert_rejected.value.reason == "daily_limit"
    assert tracker.consume_quota("yt_general", 10000, now_ms).used_today == 10000
    with pytest.raises(QuotaRejected) as general_rejected:
        tracker.consume_quota("yt_general", 1, now_ms)
    assert general_rejected.value.reason == "daily_limit"


def test_pacific_midnight_resets_used_today_from_now_ms_only(
    tracker: QuotaTracker,
) -> None:
    source = Path(quota_repo.__file__).read_text(encoding="utf-8")
    assert "datetime.now" not in source
    assert "time.time" not in source

    tracker.connection.execute(
        """
        UPDATE quota_buckets
        SET used_today = 9, window_reset_at = 0
        WHERE bucket_name = 'courtlistener'
        """
    )
    first = tracker.consume_quota("yt_search", 40, PT_SAME_DAY_EARLIER_MS)
    assert first.used_today == 40
    assert first.window_reset_at == _local_midnight_ms(PT_SAME_DAY_EARLIER_MS)
    assert first.window_reset_at == pacific_window_start_ms(PT_SAME_DAY_EARLIER_MS)

    same_day = tracker.consume_quota("yt_search", 5, BEFORE_PT_MIDNIGHT_MS)
    assert same_day.used_today == 45
    assert same_day.window_reset_at == first.window_reset_at

    reset = tracker.consume_quota("yt_search", 1, AT_PT_MIDNIGHT_MS)
    assert reset.used_today == 1
    assert reset.window_reset_at == _local_midnight_ms(AT_PT_MIDNIGHT_MS)
    assert reset.window_reset_at != first.window_reset_at

    court = tracker.get_bucket("courtlistener")
    assert court is not None
    assert (court["used_today"], court["window_reset_at"]) == (9, 0)


def test_rejected_consume_still_rolls_the_pacific_window(tracker: QuotaTracker) -> None:
    tracker.consume_quota("yt_search", 10, BEFORE_PT_MIDNIGHT_MS)
    with pytest.raises(QuotaRejected) as rejected:
        tracker.consume_quota("yt_search", 1, AT_PT_MIDNIGHT_MS, tag="nightly_poll")
    assert rejected.value.reason == "nightly_poll_forbidden"
    assert rejected.value.used_today == 0
    bucket = tracker.get_bucket("yt_search")
    assert bucket is not None
    assert bucket["used_today"] == 0
    assert bucket["window_reset_at"] == _local_midnight_ms(AT_PT_MIDNIGHT_MS)


def test_track_a_insert_requires_ttl_and_purge_clears_youtube_fields(
    tracker: QuotaTracker,
) -> None:
    created_at = BEFORE_PT_MIDNIGHT_MS
    expired_at = created_at + THIRTY_DAYS_MS
    still_live_at = expired_at + 1
    payload = '{"items":[{"id":"vid"}]}'
    seed = '{"yt_title":"Night Watch","video_id":"vid","comment":"lead only"}'

    with pytest.raises(MissingYouTubeTtlError):
        tracker.insert_track_a_outlier(
            candidate_id="missing-ttl",
            saturation_index=10,
            seed_packet_json=seed,
            created_at=created_at,
            yt_ttl_expires_at=None,
        )
    assert (
        tracker.connection.execute(
            "SELECT COUNT(*) FROM outlier_candidates"
        ).fetchone()[0]
        == 0
    )
    with pytest.raises(sqlite3.IntegrityError):
        tracker.connection.execute(
            """
            INSERT INTO outlier_candidates (
                candidate_id, track, saturation_index, seed_packet_json,
                status, created_at
            ) VALUES ('raw-missing-ttl', 'TRACK_A_OUTLIER', 10, '{}', 'CANDIDATE', ?)
            """,
            (created_at,),
        )

    tracker.insert_track_a_outlier(
        candidate_id="cand-open",
        saturation_index=22,
        seed_packet_json=seed,
        created_at=created_at,
        yt_ttl_expires_at=expired_at,
        raw_yt_payload_json=payload,
        views_count=28000,
        outlier_ratio=4.5,
        source_video_id="vid-open",
        status="CANDIDATE",
    )
    tracker.insert_track_a_outlier(
        candidate_id="cand-consumed",
        saturation_index=30,
        seed_packet_json=seed,
        created_at=created_at,
        yt_ttl_expires_at=expired_at,
        raw_yt_payload_json=payload,
        views_count=41000,
        outlier_ratio=6.0,
        source_video_id="vid-consumed",
        status="CONSUMED",
    )
    tracker.insert_track_a_outlier(
        candidate_id="cand-live",
        saturation_index=12,
        seed_packet_json=seed,
        created_at=created_at,
        yt_ttl_expires_at=still_live_at,
        raw_yt_payload_json=payload,
        views_count=21000,
        outlier_ratio=3.6,
        source_video_id="vid-live",
        status="GREENLIT",
    )
    tracker.connection.execute(
        """
        INSERT INTO outlier_candidates (
            candidate_id, track, saturation_index, seed_packet_json,
            raw_yt_payload_json, views_count, outlier_ratio, status, created_at
        ) VALUES (
            'foia-1', 'TRACK_B_FOIA_RADAR', 5, '{"docket":"keep"}',
            '{"not":"youtube-policy-target"}', 9, 1.2, 'CANDIDATE', ?
        )
        """,
        (created_at,),
    )
    tracker.connection.execute(
        """
        INSERT INTO cases (
            case_id, candidate_id, defendant_name, incident_year, jurisdiction,
            verification_source, disposition_status, created_at, updated_at
        ) VALUES (
            'case-1', 'cand-open', 'Alex Rivera', 2019, 'Clark County, NV',
            'FOIA', 'AFFIRMED', ?, ?
        )
        """,
        (created_at, created_at),
    )

    assert tracker.purge_expired_yt_api_records(expired_at - 1) == 0
    open_before = _candidate(tracker, "cand-open")
    assert open_before["raw_yt_payload_json"] == payload
    assert open_before["views_count"] == 28000
    assert open_before["status"] == "CANDIDATE"

    purged = tracker.purge_expired_yt_api_records(expired_at)
    assert purged == 2
    assert tracker.purge_expired_yt_api_records(expired_at) == 0

    opened = _candidate(tracker, "cand-open")
    consumed = _candidate(tracker, "cand-consumed")
    live = _candidate(tracker, "cand-live")
    foia = _candidate(tracker, "foia-1")
    case = tracker.connection.execute(
        "SELECT case_id, candidate_id, defendant_name, disposition_status FROM cases"
    ).fetchone()

    assert opened["raw_yt_payload_json"] is None
    assert opened["views_count"] is None
    assert opened["outlier_ratio"] is None
    assert opened["seed_packet_json"] == "{}"
    assert opened["yt_data_purged_at"] == expired_at
    assert opened["status"] == "EXPIRED_TOS_PURGED"

    assert consumed["raw_yt_payload_json"] is None
    assert consumed["views_count"] is None
    assert consumed["outlier_ratio"] is None
    assert consumed["seed_packet_json"] == "{}"
    assert consumed["status"] == "CONSUMED"

    assert live["status"] == "GREENLIT"
    assert live["raw_yt_payload_json"] == payload
    assert live["views_count"] == 21000
    assert live["seed_packet_json"] == seed
    assert live["yt_data_purged_at"] is None

    assert foia["seed_packet_json"] == '{"docket":"keep"}'
    assert foia["raw_yt_payload_json"] == '{"not":"youtube-policy-target"}'
    assert foia["views_count"] == 9
    assert foia["status"] == "CANDIDATE"

    assert case["case_id"] == "case-1"
    assert case["candidate_id"] == "cand-open"
    assert case["defendant_name"] == "Alex Rivera"
    assert case["disposition_status"] == "AFFIRMED"
    assert (
        tracker.connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
    )
    assert (
        tracker.connection.execute(
            "SELECT COUNT(*) FROM outlier_candidates"
        ).fetchone()[0]
        == 4
    )


def _candidate(tracker: QuotaTracker, candidate_id: str) -> sqlite3.Row:
    row = tracker.connection.execute(
        "SELECT * FROM outlier_candidates WHERE candidate_id = ?",
        (candidate_id,),
    ).fetchone()
    assert row is not None
    return row
