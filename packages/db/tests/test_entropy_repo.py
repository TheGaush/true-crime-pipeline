"""EntropyAndAnalyticsRepository — offline SQLite tests (schema/pipeline.sql)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from entropy_repo import (
    EpisodeAnalyticsSnapshot,
    EntropyAndAnalyticsRepository,
    ScoutingTrack,
    extract_named_query,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_SQL = _REPO_ROOT / "schema" / "pipeline.sql"
_QUERIES_SQL = _REPO_ROOT / "schema" / "queries.sql"

T0 = 1_700_000_000_000
TRACK_A = ScoutingTrack.TRACK_A.value
TRACK_B = ScoutingTrack.TRACK_B.value


@pytest.fixture
def conn() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("PRAGMA foreign_keys = ON;")
    db.executescript(_PIPELINE_SQL.read_text(encoding="utf-8"))
    return db


@pytest.fixture
def repo(conn: sqlite3.Connection) -> EntropyAndAnalyticsRepository:
    return EntropyAndAnalyticsRepository(conn, queries_path=_QUERIES_SQL)


def _seed_candidate(
    conn: sqlite3.Connection,
    candidate_id: str,
    *,
    track: str = TRACK_A,
) -> None:
    conn.execute(
        """
        INSERT INTO outlier_candidates (
          candidate_id, track, source_video_id, views_count, outlier_ratio,
          saturation_index, seed_packet_json, raw_yt_payload_json, yt_ttl_expires_at,
          status, created_at
        ) VALUES (?, ?, 'vid_1', 50000, 8.0, 25, '{}', '{"raw":1}', ?, 'GREENLIT', ?)
        """,
        (candidate_id, track, T0 + 86_400_000, T0),
    )


def _seed_case_and_episode(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    candidate_id: str | None = None,
    archetype: str = "911_CALL_IN_MEDIA_RES",
    ep_state: str = "PUBLISHED",
    thumb_vec: str | None = None,
    track: str = TRACK_A,
) -> None:
    case_id = f"case_{episode_id}"
    if candidate_id is not None:
        _seed_candidate(conn, candidate_id, track=track)
    conn.execute(
        """
        INSERT INTO cases (
          case_id, candidate_id, defendant_name, incident_year, jurisdiction, docket_id,
          primary_record_verified, verification_source, disposition_status,
          conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
          anonymization_artifact_sha256, created_at, updated_at
        ) VALUES (
          ?, ?, 'Jane Doe', 2022, 'Cook, IL', 'DK-99', 1, 'courtlistener',
          'AFFIRMED', 1, 'APPROVED', 'rev_a', ?, 'sha_anon', ?, ?
        )
        """,
        (case_id, candidate_id, T0, T0, T0),
    )
    conn.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
          turning_point_count, total_master_ms, timeline_validated_sha256,
          ready_bundle_sha256, thumbnail_mood_vec, updated_at, created_at
        ) VALUES (
          ?, ?, ?, 'GEMINI_OMNI_INTERACTIONS', ?, 4, 1200000,
          ?, 'sha_bundle', ?, ?, ?
        )
        """,
        (
            episode_id,
            case_id,
            ep_state,
            archetype,
            f"sha_tl_{episode_id}",
            thumb_vec,
            T0,
            T0,
        ),
    )


def test_recent_entropy_named_query_matches_schema() -> None:
    sql = _QUERIES_SQL.read_text(encoding="utf-8")
    recent = extract_named_query(sql, "recent_entropy_window")
    assert "published_entropy_history" in recent
    assert "ORDER BY published_at DESC" in recent
    assert "LIMIT 5" in recent


def test_archetype_back_to_back_guard(repo: EntropyAndAnalyticsRepository, conn) -> None:
    _seed_case_and_episode(conn, "ep_1")
    _seed_case_and_episode(conn, "ep_2", archetype="SINGLE_FORENSIC_ANOMALY")

    repo.record_published_entropy(
        episode_id="ep_1",
        cold_open_archetype="911_CALL_IN_MEDIA_RES",
        turning_point_count=3,
        thumbnail_mood_vec='{"mood":"tense"}',
        published_at=T0,
    )
    assert repo.is_archetype_allowed("SINGLE_FORENSIC_ANOMALY") is True
    assert repo.is_archetype_allowed("911_CALL_IN_MEDIA_RES") is False

    with pytest.raises(ValueError, match="repeats the most recent"):
        repo.record_published_entropy(
            episode_id="ep_2",
            cold_open_archetype="911_CALL_IN_MEDIA_RES",
            turning_point_count=4,
            thumbnail_mood_vec='{"mood":"cool"}',
            published_at=T0 + 1,
        )


def test_empty_history_allows_any_archetype(repo: EntropyAndAnalyticsRepository) -> None:
    assert repo.list_recent_cold_open_archetypes() == []
    for archetype in (
        "911_CALL_IN_MEDIA_RES",
        "SINGLE_FORENSIC_ANOMALY",
        "ALIBI_THAT_CRACKED",
        "CHRONOLOGICAL_COUNTDOWN",
    ):
        assert repo.is_archetype_allowed(archetype) is True


def test_recent_thumbnail_mood_vecs_last_three(
    repo: EntropyAndAnalyticsRepository, conn
) -> None:
    for idx, (ep, archetype, mood) in enumerate(
        [
            ("ep_a", "911_CALL_IN_MEDIA_RES", '{"v":1}'),
            ("ep_b", "SINGLE_FORENSIC_ANOMALY", '{"v":2}'),
            ("ep_c", "ALIBI_THAT_CRACKED", '{"v":3}'),
            ("ep_d", "CHRONOLOGICAL_COUNTDOWN", '{"v":4}'),
        ]
    ):
        _seed_case_and_episode(conn, ep, archetype=archetype)
        repo.record_published_entropy(
            episode_id=ep,
            cold_open_archetype=archetype,
            turning_point_count=3,
            thumbnail_mood_vec=mood,
            published_at=T0 + idx,
        )

    moods = repo.list_recent_thumbnail_mood_vecs()
    assert moods == ['{"v":4}', '{"v":3}', '{"v":2}']
    archetypes = repo.list_recent_cold_open_archetypes()
    assert archetypes[:5] == [
        "CHRONOLOGICAL_COUNTDOWN",
        "ALIBI_THAT_CRACKED",
        "SINGLE_FORENSIC_ANOMALY",
        "911_CALL_IN_MEDIA_RES",
    ]


def test_analytics_insert_defaults_adsense_unknown(
    repo: EntropyAndAnalyticsRepository, conn
) -> None:
    _seed_case_and_episode(conn, "ep_1", candidate_id="cand_a")
    snapshot = EpisodeAnalyticsSnapshot(
        snapshot_id="an_1",
        episode_id="ep_1",
        days_since_publish=2,
        captured_at=T0 + 50_000,
        watch_hours_total=120.5,
    )
    repo.record_analytics_snapshot(snapshot)

    row = conn.execute(
        "SELECT adsense_status, adsense_source, ctr_pct FROM episode_analytics WHERE snapshot_id='an_1'"
    ).fetchone()
    assert row["adsense_status"] == "UNKNOWN"
    assert row["adsense_source"] == "UNAVAILABLE"
    assert row["ctr_pct"] is None


def test_analytics_snapshot_does_not_mutate_episode_facts(
    repo: EntropyAndAnalyticsRepository, conn
) -> None:
    _seed_case_and_episode(conn, "ep_1", candidate_id="cand_a")
    before = conn.execute(
        "SELECT cold_open_archetype, timeline_validated_sha256 FROM episodes WHERE episode_id='ep_1'"
    ).fetchone()

    repo.record_analytics_snapshot(
        EpisodeAnalyticsSnapshot(
            snapshot_id="an_2",
            episode_id="ep_1",
            days_since_publish=3,
            captured_at=T0 + 60_000,
            ctr_pct=5.2,
            retention_30s_pct=62.0,
            watch_hours_total=80.0,
        )
    )

    after = conn.execute(
        "SELECT cold_open_archetype, timeline_validated_sha256 FROM episodes WHERE episode_id='ep_1'"
    ).fetchone()
    assert after == before


def test_aggregate_by_archetype_and_track(repo: EntropyAndAnalyticsRepository, conn) -> None:
    _seed_case_and_episode(
        conn, "ep_a", candidate_id="cand_a", archetype="911_CALL_IN_MEDIA_RES"
    )
    _seed_case_and_episode(
        conn, "ep_b", candidate_id="cand_b", archetype="SINGLE_FORENSIC_ANOMALY"
    )
    _seed_case_and_episode(
        conn,
        "ep_c",
        candidate_id="cand_c",
        archetype="911_CALL_IN_MEDIA_RES",
        track=TRACK_B,
    )

    repo.record_analytics_snapshot(
        EpisodeAnalyticsSnapshot(
            snapshot_id="an_a",
            episode_id="ep_a",
            days_since_publish=2,
            captured_at=T0,
            ctr_pct=4.0,
            retention_30s_pct=50.0,
            retention_min6_14_pct=30.0,
            avd_pct=40.0,
            watch_hours_total=100.0,
            rpm_micro_usd=500,
        )
    )
    repo.record_analytics_snapshot(
        EpisodeAnalyticsSnapshot(
            snapshot_id="an_b",
            episode_id="ep_b",
            days_since_publish=2,
            captured_at=T0,
            ctr_pct=6.0,
            retention_30s_pct=70.0,
            watch_hours_total=80.0,
        )
    )
    repo.record_analytics_snapshot(
        EpisodeAnalyticsSnapshot(
            snapshot_id="an_c",
            episode_id="ep_c",
            days_since_publish=2,
            captured_at=T0,
            ctr_pct=3.0,
            retention_30s_pct=45.0,
            watch_hours_total=60.0,
        )
    )

    track_a_rows = repo.aggregate_analytics_by_archetype_and_track("TRACK_A")
    by_arch = {row.cold_open_archetype: row for row in track_a_rows}
    assert set(by_arch) == {"911_CALL_IN_MEDIA_RES", "SINGLE_FORENSIC_ANOMALY"}
    assert by_arch["911_CALL_IN_MEDIA_RES"].avg_ctr_pct == pytest.approx(4.0)
    assert by_arch["SINGLE_FORENSIC_ANOMALY"].avg_retention_30s_pct == pytest.approx(70.0)

    track_b_rows = repo.aggregate_analytics_by_archetype_and_track(ScoutingTrack.TRACK_B)
    assert len(track_b_rows) == 1
    assert track_b_rows[0].cold_open_archetype == "911_CALL_IN_MEDIA_RES"
    assert track_b_rows[0].track == TRACK_B


def test_cold_start_uniform_weights(repo: EntropyAndAnalyticsRepository, conn) -> None:
    known = conn.execute("SELECT COUNT(*) FROM cold_open_archetypes").fetchone()[0]
    assert known == 4

    _seed_case_and_episode(conn, "ep_1", candidate_id="cand_a")
    repo.record_analytics_snapshot(
        EpisodeAnalyticsSnapshot(
            snapshot_id="an_1",
            episode_id="ep_1",
            days_since_publish=2,
            captured_at=T0,
            retention_30s_pct=80.0,
            watch_hours_total=10.0,
        )
    )

    weights = repo.archetype_selection_weights("TRACK_A")
    assert len(weights) == 4
    assert all(pytest.approx(w) == 0.25 for w in weights.values())


def test_telemetry_weights_after_three_published_rows(
    repo: EntropyAndAnalyticsRepository, conn
) -> None:
    specs = [
        ("ep_1", "cand_1", "911_CALL_IN_MEDIA_RES", 50.0, 4.0),
        ("ep_2", "cand_2", "SINGLE_FORENSIC_ANOMALY", 80.0, 6.0),
        ("ep_3", "cand_3", "ALIBI_THAT_CRACKED", 20.0, 2.0),
    ]
    for ep, cand, archetype, retention, ctr in specs:
        _seed_case_and_episode(conn, ep, candidate_id=cand, archetype=archetype)
        repo.record_analytics_snapshot(
            EpisodeAnalyticsSnapshot(
                snapshot_id=f"an_{ep}",
                episode_id=ep,
                days_since_publish=2,
                captured_at=T0,
                retention_30s_pct=retention,
                ctr_pct=ctr,
                watch_hours_total=50.0,
            )
        )

    retention_weights = repo.archetype_selection_weights(
        ScoutingTrack.TRACK_A, metric="retention_30s_pct"
    )
    assert retention_weights["SINGLE_FORENSIC_ANOMALY"] > retention_weights[
        "911_CALL_IN_MEDIA_RES"
    ]
    assert retention_weights["ALIBI_THAT_CRACKED"] < retention_weights[
        "911_CALL_IN_MEDIA_RES"
    ]
    assert pytest.approx(sum(retention_weights.values())) == 1.0

    ctr_weights = repo.archetype_selection_weights("TRACK_A", metric="ctr_pct")
    assert ctr_weights["SINGLE_FORENSIC_ANOMALY"] > ctr_weights["911_CALL_IN_MEDIA_RES"]
    assert pytest.approx(sum(ctr_weights.values())) == 1.0