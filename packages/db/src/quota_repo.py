"""YouTube Data API quota buckets and 30-day ToS payload purge.

`consume_quota` applies a Pacific-midnight window reset, then the named
`consume_quota_bucket` statement from `schema/queries.sql`. The 15-unit
`yt_search` reserve for pre-render re-checks is enforced in Python because
that statement only compares `used_today + units` to `daily_limit`.

`purge_expired_yt_api_records` runs the named statement of the same name.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")

YT_SEARCH = "yt_search"
YT_GENERAL = "yt_general"
YT_INSERT = "yt_insert"
PRE_RENDER_RECHECK_TAG = "pre_render_recheck"
NIGHTLY_POLL_TAG = "nightly_poll"
YT_SEARCH_RESERVE_UNITS = 15

# Used only when schema/pipeline.sql did not already insert these rows.
YOUTUBE_BUCKET_LIMITS: dict[str, int] = {
    YT_SEARCH: 100,
    YT_GENERAL: 10000,
    YT_INSERT: 100,
}

_QUERY_NAMES = ("consume_quota_bucket", "purge_expired_yt_api_records")


class QuotaRejected(Exception):
    """A consume was refused. The Pacific window reset, if any, is kept."""

    def __init__(
        self,
        bucket: str,
        reason: str,
        used_today: int,
        daily_limit: int,
        window_reset_at: int,
    ) -> None:
        self.bucket = bucket
        self.reason = reason
        self.used_today = used_today
        self.daily_limit = daily_limit
        self.window_reset_at = window_reset_at
        super().__init__(
            f"quota rejected for {bucket}: {reason} "
            f"(used_today={used_today}, daily_limit={daily_limit})"
        )


class MissingYouTubeTtlError(ValueError):
    """TRACK_A_OUTLIER rows require a non-null yt_ttl_expires_at."""


@dataclass(frozen=True)
class QuotaConsumeResult:
    bucket_name: str
    used_today: int
    daily_limit: int
    window_reset_at: int


def repo_root() -> Path:
    """Return the repository root that contains schema/pipeline.sql."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        pipeline = parent / "schema" / "pipeline.sql"
        queries = parent / "schema" / "queries.sql"
        if pipeline.is_file() and queries.is_file():
            return parent
    raise FileNotFoundError(
        "Could not locate schema/pipeline.sql and schema/queries.sql"
    )


def load_named_queries(path: Path) -> dict[str, str]:
    """Parse `-- name:` blocks from schema/queries.sql without rewriting them."""
    queries: dict[str, str] = {}
    name: str | None = None
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("-- name:"):
            if name is not None:
                queries[name] = "\n".join(lines).strip()
            name = line.split(":", 1)[1].strip()
            lines = []
            continue
        if name is not None:
            lines.append(line)
    if name is not None:
        queries[name] = "\n".join(lines).strip()
    missing = [query_name for query_name in _QUERY_NAMES if query_name not in queries]
    if missing:
        raise FileNotFoundError(
            f"{path} is missing named queries: {', '.join(missing)}"
        )
    return queries


def pacific_window_start_ms(now_ms: int) -> int:
    """Epoch milliseconds of America/Los_Angeles midnight containing `now_ms`.

    Derived only from `now_ms`. This function does not read the system clock.
    """
    _require_int("now_ms", now_ms)
    seconds, millis = divmod(now_ms, 1000)
    instant = datetime.fromtimestamp(seconds, tz=timezone.utc).replace(
        microsecond=millis * 1000
    )
    local = instant.astimezone(PACIFIC)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp()) * 1000


def _require_int(label: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int")


class QuotaTracker:
    """Atomic YouTube quota consumer and Track A payload TTL purge."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if connection is not None and db_path is not None:
            raise TypeError("Pass db_path or connection, not both")
        if connection is None:
            target = ":memory:" if db_path is None else str(db_path)
            connection = sqlite3.connect(target)
            self._owns_connection = True
        else:
            self._owns_connection = False
        connection.row_factory = sqlite3.Row
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys = ON")
        self._conn = connection
        root = repo_root()
        self._queries = load_named_queries(root / "schema" / "queries.sql")
        self._ensure_schema(root / "schema" / "pipeline.sql")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        if self._owns_connection:
            self._conn.close()
            self._owns_connection = False

    def __enter__(self) -> QuotaTracker:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_bucket(self, bucket: str) -> sqlite3.Row | None:
        return self._conn.execute(
            """
            SELECT bucket_name, daily_limit, used_today, window_reset_at
            FROM quota_buckets
            WHERE bucket_name = ?
            """,
            (bucket,),
        ).fetchone()

    def consume_quota(
        self,
        bucket: str,
        units: int,
        now_ms: int,
        tag: str | None = None,
    ) -> QuotaConsumeResult:
        """Spend `units` from `bucket` at the Pacific day containing `now_ms`.

        Ordinary `yt_search` consumption stops at `daily_limit - 15`. A call
        tagged `pre_render_recheck` may use those reserved units, up to
        `daily_limit`. A call tagged `nightly_poll` is always rejected on
        `yt_search`. `now_ms` is the only clock input.
        """
        if not isinstance(bucket, str) or bucket == "":
            raise TypeError("bucket must be a non-empty str")
        if tag is not None and not isinstance(tag, str):
            raise TypeError("tag must be a str or None")
        _require_int("units", units)
        _require_int("now_ms", now_ms)

        window_id = pacific_window_start_ms(now_ms)
        rejected: QuotaRejected | None = None
        result: QuotaConsumeResult | None = None
        self._begin()
        try:
            self._reset_bucket_window(bucket, window_id)
            row = self.get_bucket(bucket)
            if row is None:
                rejected = QuotaRejected(
                    bucket,
                    "unknown_bucket",
                    used_today=0,
                    daily_limit=0,
                    window_reset_at=window_id,
                )
            else:
                used = int(row["used_today"])
                limit = int(row["daily_limit"])
                stored_window = int(row["window_reset_at"])
                reason = _rejection_reason(bucket, units, used, limit, tag)
                if reason is not None:
                    rejected = QuotaRejected(
                        bucket, reason, used, limit, stored_window
                    )
                else:
                    updated = self._conn.execute(
                        self._queries["consume_quota_bucket"],
                        {"bucket_name": bucket, "units": units},
                    ).fetchone()
                    if updated is None:
                        rejected = QuotaRejected(
                            bucket, "daily_limit", used, limit, stored_window
                        )
                    else:
                        result = QuotaConsumeResult(
                            bucket_name=str(updated["bucket_name"]),
                            used_today=int(updated["used_today"]),
                            daily_limit=int(updated["daily_limit"]),
                            window_reset_at=stored_window,
                        )
            self._conn.execute("COMMIT")
        except Exception:
            self._rollback_if_open()
            raise
        if rejected is not None:
            raise rejected
        assert result is not None
        return result

    def insert_track_a_outlier(
        self,
        *,
        candidate_id: str,
        saturation_index: int,
        seed_packet_json: str,
        created_at: int,
        yt_ttl_expires_at: int | None,
        status: str = "CANDIDATE",
        raw_yt_payload_json: str | None = None,
        views_count: int | None = None,
        outlier_ratio: float | None = None,
        source_video_id: str | None = None,
        source_channel_id: str | None = None,
        composite_score: float = 0.0,
    ) -> None:
        """Insert one TRACK_A_OUTLIER row. A null TTL is refused."""
        if yt_ttl_expires_at is None:
            raise MissingYouTubeTtlError(
                "TRACK_A_OUTLIER requires non-null yt_ttl_expires_at"
            )
        _require_int("yt_ttl_expires_at", yt_ttl_expires_at)
        _require_int("created_at", created_at)
        _require_int("saturation_index", saturation_index)
        self._conn.execute(
            """
            INSERT INTO outlier_candidates (
                candidate_id,
                track,
                source_video_id,
                source_channel_id,
                views_count,
                outlier_ratio,
                saturation_index,
                seed_packet_json,
                raw_yt_payload_json,
                yt_ttl_expires_at,
                status,
                created_at,
                composite_score
            ) VALUES (
                :candidate_id,
                'TRACK_A_OUTLIER',
                :source_video_id,
                :source_channel_id,
                :views_count,
                :outlier_ratio,
                :saturation_index,
                :seed_packet_json,
                :raw_yt_payload_json,
                :yt_ttl_expires_at,
                :status,
                :created_at,
                :composite_score
            )
            """,
            {
                "candidate_id": candidate_id,
                "source_video_id": source_video_id,
                "source_channel_id": source_channel_id,
                "views_count": views_count,
                "outlier_ratio": outlier_ratio,
                "saturation_index": saturation_index,
                "seed_packet_json": seed_packet_json,
                "raw_yt_payload_json": raw_yt_payload_json,
                "yt_ttl_expires_at": yt_ttl_expires_at,
                "status": status,
                "created_at": created_at,
                "composite_score": composite_score,
            },
        )

    def purge_expired_yt_api_records(self, now_ms: int) -> int:
        """Run named SQL `purge_expired_yt_api_records`. Returns rows changed."""
        _require_int("now_ms", now_ms)
        self._begin()
        try:
            self._conn.execute(
                self._queries["purge_expired_yt_api_records"],
                {"now_ms": now_ms},
            )
            purged = int(self._conn.execute("SELECT changes()").fetchone()[0])
            self._conn.execute("COMMIT")
            return purged
        except Exception:
            self._rollback_if_open()
            raise

    def _ensure_schema(self, pipeline_sql: Path) -> None:
        exists = self._conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'quota_buckets'
            """
        ).fetchone()
        if exists is None:
            self._conn.executescript(pipeline_sql.read_text(encoding="utf-8"))
        self._seed_youtube_buckets_if_missing()

    def _seed_youtube_buckets_if_missing(self) -> None:
        present = {
            str(row["bucket_name"])
            for row in self._conn.execute("SELECT bucket_name FROM quota_buckets")
        }
        missing = [name for name in YOUTUBE_BUCKET_LIMITS if name not in present]
        if not missing:
            return
        self._begin()
        try:
            for name in missing:
                already = self._conn.execute(
                    "SELECT 1 FROM quota_buckets WHERE bucket_name = ?",
                    (name,),
                ).fetchone()
                if already is None:
                    self._conn.execute(
                        """
                        INSERT INTO quota_buckets (
                            bucket_name, daily_limit, used_today, window_reset_at
                        ) VALUES (?, ?, 0, 0)
                        """,
                        (name, YOUTUBE_BUCKET_LIMITS[name]),
                    )
            self._conn.execute("COMMIT")
        except Exception:
            self._rollback_if_open()
            raise

    def _reset_bucket_window(self, bucket: str, window_id: int) -> None:
        self._conn.execute(
            """
            UPDATE quota_buckets
            SET used_today = 0,
                window_reset_at = :window_id
            WHERE bucket_name = :bucket_name
              AND window_reset_at != :window_id
            """,
            {"bucket_name": bucket, "window_id": window_id},
        )

    def _begin(self) -> None:
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK")
        self._conn.execute("BEGIN IMMEDIATE")

    def _rollback_if_open(self) -> None:
        if self._conn.in_transaction:
            self._conn.execute("ROLLBACK")


def _rejection_reason(
    bucket: str,
    units: int,
    used_today: int,
    daily_limit: int,
    tag: str | None,
) -> str | None:
    if units <= 0:
        return "invalid_units"
    if bucket == YT_SEARCH and tag == NIGHTLY_POLL_TAG:
        return "nightly_poll_forbidden"
    effective_limit = daily_limit
    if bucket == YT_SEARCH and tag != PRE_RENDER_RECHECK_TAG:
        effective_limit = daily_limit - YT_SEARCH_RESERVE_UNITS
    projected = used_today + units
    if projected > daily_limit:
        return "daily_limit"
    if projected > effective_limit:
        return "search_reserve"
    return None
