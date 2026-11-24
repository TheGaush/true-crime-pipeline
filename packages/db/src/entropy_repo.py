"""Published entropy history and post-publish episode analytics (Task 013)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

_COLD_START_MIN_PUBLISHED_ANALYTICS = 3
_RECENT_ARCHETYPES_LIMIT = 5
_RECENT_MOOD_VEC_LIMIT = 3

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_QUERIES_PATH = _REPO_ROOT / "schema" / "queries.sql"

T = TypeVar("T")

# Task docs say TRACK_A / TRACK_B; pipeline.sql uses full enum literals (F-12).
_TRACK_ALIASES: dict[str, str] = {
    "TRACK_A": "TRACK_A_OUTLIER",
    "TRACK_B": "TRACK_B_FOIA_RADAR",
    "TRACK_A_OUTLIER": "TRACK_A_OUTLIER",
    "TRACK_B_FOIA_RADAR": "TRACK_B_FOIA_RADAR",
}

FeedbackMetric = Literal["ctr_pct", "retention_30s_pct"]


class ScoutingTrack(str, Enum):
    """Scouting track labels.

    Task shorthand ``TRACK_A`` / ``TRACK_B`` map to ``outlier_candidates.track`` values
    ``TRACK_A_OUTLIER`` and ``TRACK_B_FOIA_RADAR`` in ``schema/pipeline.sql``.
    """

    TRACK_A = "TRACK_A_OUTLIER"
    TRACK_B = "TRACK_B_FOIA_RADAR"


@dataclass(frozen=True, slots=True)
class PublishedEntropyRecord:
    episode_id: str
    cold_open_archetype: str
    thumbnail_mood_vec: str
    published_at: int
    turning_point_count: int | None = None


@dataclass(frozen=True, slots=True)
class EpisodeAnalyticsSnapshot:
    snapshot_id: str
    episode_id: str
    days_since_publish: int
    captured_at: int
    ctr_pct: float | None = None
    retention_30s_pct: float | None = None
    retention_min6_14_pct: float | None = None
    avd_pct: float | None = None
    watch_hours_total: float = 0.0
    rpm_micro_usd: int | None = None
    adsense_status: str = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ArchetypePerformanceAggregate:
    cold_open_archetype: str
    track: str
    episode_count: int
    avg_ctr_pct: float | None
    avg_retention_30s_pct: float | None
    avg_retention_min6_14_pct: float | None
    avg_avd_pct: float | None
    avg_watch_hours_total: float | None
    avg_rpm_micro_usd: float | None


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


def normalize_scouting_track(track: str | ScoutingTrack) -> str:
    if isinstance(track, ScoutingTrack):
        return track.value
    key = str(track).strip().upper()
    try:
        return _TRACK_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"Unknown scouting track: {track!r}") from exc


_LATEST_ANALYTICS_PER_EPISODE = """
SELECT a.*
FROM episode_analytics a
INNER JOIN (
  SELECT episode_id, MAX(captured_at) AS max_captured
  FROM episode_analytics
  GROUP BY episode_id
) latest ON latest.episode_id = a.episode_id AND a.captured_at = latest.max_captured
"""

_AGGREGATE_BY_ARCHETYPE_TRACK = f"""
SELECT
  e.cold_open_archetype,
  oc.track,
  COUNT(DISTINCT e.episode_id) AS episode_count,
  AVG(a.ctr_pct) AS avg_ctr_pct,
  AVG(a.retention_30s_pct) AS avg_retention_30s_pct,
  AVG(a.retention_min6_14_pct) AS avg_retention_min6_14_pct,
  AVG(a.avd_pct) AS avg_avd_pct,
  AVG(a.watch_hours_total) AS avg_watch_hours_total,
  AVG(a.rpm_micro_usd) AS avg_rpm_micro_usd
FROM episodes e
INNER JOIN ({_LATEST_ANALYTICS_PER_EPISODE}) a ON a.episode_id = e.episode_id
INNER JOIN cases c ON c.case_id = e.case_id
INNER JOIN outlier_candidates oc ON oc.candidate_id = c.candidate_id
WHERE oc.track = :track
GROUP BY e.cold_open_archetype, oc.track
"""

_COUNT_PUBLISHED_ANALYTICS_ON_TRACK = f"""
SELECT COUNT(*) AS c
FROM ({_LATEST_ANALYTICS_PER_EPISODE}) a
INNER JOIN episodes e ON e.episode_id = a.episode_id
INNER JOIN cases c ON c.case_id = e.case_id
INNER JOIN outlier_candidates oc ON oc.candidate_id = c.candidate_id
WHERE oc.track = :track
"""

_INSERT_ENTROPY_HISTORY = """
INSERT INTO published_entropy_history (
  episode_id, cold_open_archetype, turning_point_count, thumbnail_mood_vec, published_at
) VALUES (?, ?, ?, ?, ?)
"""

_INSERT_ANALYTICS = """
INSERT INTO episode_analytics (
  snapshot_id,
  episode_id,
  days_since_publish,
  ctr_pct,
  retention_30s_pct,
  retention_min6_14_pct,
  avd_pct,
  watch_hours_total,
  rpm_micro_usd,
  adsense_status,
  captured_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_LIST_KNOWN_ARCHETYPES = """
SELECT archetype FROM cold_open_archetypes ORDER BY archetype
"""


class EntropyAndAnalyticsRepository:
    """Read/write ``published_entropy_history`` and ``episode_analytics`` feedback rows."""

    def __init__(
        self,
        db: sqlite3.Connection | Any,
        *,
        queries_path: Path | None = None,
    ) -> None:
        self._db = db
        path = queries_path or _DEFAULT_QUERIES_PATH
        queries_sql = path.read_text(encoding="utf-8")
        self._recent_entropy_sql = extract_named_query(queries_sql, "recent_entropy_window")

    def list_recent_cold_open_archetypes(
        self, *, limit: int = _RECENT_ARCHETYPES_LIMIT
    ) -> list[str]:
        sql = self._recent_entropy_sql
        if limit != _RECENT_ARCHETYPES_LIMIT:
            sql = re.sub(
                r"LIMIT\s+\d+",
                f"LIMIT {int(limit)}",
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
        rows = self._connection().execute(sql).fetchall()
        return [str(row["cold_open_archetype"]) for row in rows]

    def is_archetype_allowed(self, candidate: str) -> bool:
        """Reject back-to-back duplicate cold-open archetype (empty history allows all)."""
        recent = self.list_recent_cold_open_archetypes(limit=1)
        if not recent:
            return True
        return candidate != recent[0]

    def list_recent_thumbnail_mood_vecs(
        self, *, limit: int = _RECENT_MOOD_VEC_LIMIT
    ) -> list[str]:
        rows = self._connection().execute(
            """
            SELECT thumbnail_mood_vec
            FROM published_entropy_history
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def record_published_entropy(
        self,
        *,
        episode_id: str,
        cold_open_archetype: str,
        turning_point_count: int,
        thumbnail_mood_vec: str,
        published_at: int,
    ) -> None:
        if turning_point_count < 3:
            raise ValueError("turning_point_count must be >= 3")
        if not self.is_archetype_allowed(cold_open_archetype):
            raise ValueError(
                f"cold_open_archetype {cold_open_archetype!r} repeats the most recent publish"
            )

        def _write(conn: sqlite3.Connection) -> None:
            conn.execute(
                _INSERT_ENTROPY_HISTORY,
                (
                    episode_id,
                    cold_open_archetype,
                    turning_point_count,
                    thumbnail_mood_vec,
                    published_at,
                ),
            )

        self._run_write(_write)

    def record_analytics_snapshot(self, snapshot: EpisodeAnalyticsSnapshot) -> None:
        """Append analytics facts only (never mutates ``episodes`` / ``cases``)."""
        if snapshot.days_since_publish < 1:
            raise ValueError("days_since_publish must be >= 1")

        def _write(conn: sqlite3.Connection) -> None:
            episode_sha = conn.execute(
                "SELECT timeline_validated_sha256, cold_open_archetype FROM episodes WHERE episode_id = ?",
                (snapshot.episode_id,),
            ).fetchone()
            if episode_sha is None:
                raise KeyError(f"Unknown episode_id={snapshot.episode_id!r}")

            conn.execute(
                _INSERT_ANALYTICS,
                (
                    snapshot.snapshot_id,
                    snapshot.episode_id,
                    snapshot.days_since_publish,
                    snapshot.ctr_pct,
                    snapshot.retention_30s_pct,
                    snapshot.retention_min6_14_pct,
                    snapshot.avd_pct,
                    snapshot.watch_hours_total,
                    snapshot.rpm_micro_usd,
                    snapshot.adsense_status,
                    snapshot.captured_at,
                ),
            )

            after = conn.execute(
                "SELECT timeline_validated_sha256, cold_open_archetype FROM episodes WHERE episode_id = ?",
                (snapshot.episode_id,),
            ).fetchone()
            assert after is not None
            if after[0] != episode_sha[0] or after[1] != episode_sha[1]:
                raise RuntimeError(
                    "Closed-loop feedback invariant violated: episode facts mutated"
                )

        self._run_write(_write)

    def count_published_analytics_on_track(self, track: str | ScoutingTrack) -> int:
        track_sql = normalize_scouting_track(track)
        row = self._connection().execute(
            _COUNT_PUBLISHED_ANALYTICS_ON_TRACK, {"track": track_sql}
        ).fetchone()
        return int(row[0] if row else 0)

    def aggregate_analytics_by_archetype_and_track(
        self, track: str | ScoutingTrack
    ) -> list[ArchetypePerformanceAggregate]:
        track_sql = normalize_scouting_track(track)
        rows = self._connection().execute(
            _AGGREGATE_BY_ARCHETYPE_TRACK, {"track": track_sql}
        ).fetchall()
        return [_row_to_aggregate(row) for row in rows]

    def archetype_selection_weights(
        self,
        track: str | ScoutingTrack,
        *,
        metric: FeedbackMetric = "retention_30s_pct",
    ) -> dict[str, float]:
        known = self._list_known_archetypes()
        if not known:
            return {}

        published_count = self.count_published_analytics_on_track(track)
        uniform = 1.0 / len(known)
        if published_count < _COLD_START_MIN_PUBLISHED_ANALYTICS:
            return {name: uniform for name in known}

        aggregates = self.aggregate_analytics_by_archetype_and_track(track)
        scores = {name: 0.0 for name in known}
        for row in aggregates:
            value = _metric_value(row, metric)
            if value is not None:
                scores[row.cold_open_archetype] = max(0.0, float(value))

        total = sum(scores.values())
        if total <= 0.0:
            return {name: uniform for name in known}

        return {name: scores[name] / total for name in known}

    def _list_known_archetypes(self) -> list[str]:
        rows = self._connection().execute(_LIST_KNOWN_ARCHETYPES).fetchall()
        return [str(row[0]) for row in rows]

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


def _metric_value(
    row: ArchetypePerformanceAggregate, metric: FeedbackMetric
) -> float | None:
    if metric == "ctr_pct":
        return row.avg_ctr_pct
    return row.avg_retention_30s_pct


def _row_to_aggregate(row: sqlite3.Row | tuple[Any, ...]) -> ArchetypePerformanceAggregate:
    if isinstance(row, sqlite3.Row):
        return ArchetypePerformanceAggregate(
            cold_open_archetype=str(row["cold_open_archetype"]),
            track=str(row["track"]),
            episode_count=int(row["episode_count"]),
            avg_ctr_pct=_maybe_float(row["avg_ctr_pct"]),
            avg_retention_30s_pct=_maybe_float(row["avg_retention_30s_pct"]),
            avg_retention_min6_14_pct=_maybe_float(row["avg_retention_min6_14_pct"]),
            avg_avd_pct=_maybe_float(row["avg_avd_pct"]),
            avg_watch_hours_total=_maybe_float(row["avg_watch_hours_total"]),
            avg_rpm_micro_usd=_maybe_float(row["avg_rpm_micro_usd"]),
        )
    return ArchetypePerformanceAggregate(
        cold_open_archetype=str(row[0]),
        track=str(row[1]),
        episode_count=int(row[2]),
        avg_ctr_pct=_maybe_float(row[3]),
        avg_retention_30s_pct=_maybe_float(row[4]),
        avg_retention_min6_14_pct=_maybe_float(row[5]),
        avg_avd_pct=_maybe_float(row[6]),
        avg_watch_hours_total=_maybe_float(row[7]),
        avg_rpm_micro_usd=_maybe_float(row[8]),
    )


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)