"""RULE_08: cold-open rotation, >=3 turning points, thumbnail brand novelty."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent4_director.rules.rule_08_entropy import (
    CHANNEL_FRAMING,
    CHANNEL_TYPOGRAPHY,
    Rule08EntropyContext,
    Rule08Proposal,
    ThumbnailBrandSpec,
    load_entropy_context_from_db,
    validate_rule_08,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIPELINE_SQL = _REPO_ROOT / "schema" / "pipeline.sql"
_QUERIES_SQL = _REPO_ROOT / "schema" / "queries.sql"

T0 = 1_700_000_000_000


def brand_thumb(
    *,
    focal: str = "witness_silhouette_left",
    composition: str = "doorway_silhouette",
    accent: str = "muted_amber",
) -> ThumbnailBrandSpec:
    return ThumbnailBrandSpec(
        typography=CHANNEL_TYPOGRAPHY,
        framing=CHANNEL_FRAMING,
        focal_subject=focal,
        composition=composition,
        accent_mood=accent,
    )


def proposal(
    archetype: str = "SINGLE_FORENSIC_ANOMALY",
    turning_points: int = 4,
    thumb: ThumbnailBrandSpec | None = None,
    episode_id: str = "ep_next",
) -> Rule08Proposal:
    return Rule08Proposal(
        episode_id=episode_id,
        cold_open_archetype=archetype,
        turning_point_count=turning_points,
        thumbnail=thumb or brand_thumb(),
    )


def test_empty_history_passes_valid_proposal() -> None:
    result = validate_rule_08(proposal(), Rule08EntropyContext())
    assert result.ok


def test_turning_point_below_three_fails() -> None:
    result = validate_rule_08(proposal(turning_points=2))
    assert not result.ok
    assert any(v.code == "TURNING_POINT_MIN" for v in result.violations)


def test_back_to_back_archetype_fails_even_with_high_ctr() -> None:
    ctx = Rule08EntropyContext(
        recent_cold_open_archetypes=("ALIBI_THAT_CRACKED",),
        archetype_ctr_pct={"ALIBI_THAT_CRACKED": 12.4},
    )
    result = validate_rule_08(proposal(archetype="ALIBI_THAT_CRACKED"), ctx)
    assert not result.ok
    assert any(v.code == "COLD_OPEN_REPEAT" for v in result.violations)
    repeat = next(v for v in result.violations if v.code == "COLD_OPEN_REPEAT")
    assert "12.4" in repeat.message


def test_alibi_back_to_back_fails() -> None:
    ctx = Rule08EntropyContext(recent_cold_open_archetypes=("SINGLE_FORENSIC_ANOMALY",))
    dup = validate_rule_08(
        proposal(archetype="ALIBI_THAT_CRACKED"),
        ctx,
    )
    assert dup.ok
    ctx_after = Rule08EntropyContext(recent_cold_open_archetypes=("ALIBI_THAT_CRACKED",))
    again = validate_rule_08(proposal(archetype="ALIBI_THAT_CRACKED"), ctx_after)
    assert not again.ok
    assert any(v.code == "COLD_OPEN_REPEAT" for v in again.violations)


def test_rotated_archetype_passes() -> None:
    ctx = Rule08EntropyContext(recent_cold_open_archetypes=("911_CALL_IN_MEDIA_RES",))
    result = validate_rule_08(proposal(archetype="CHRONOLOGICAL_COUNTDOWN"), ctx)
    assert result.ok


def test_thumbnail_must_change_novelty_axis() -> None:
    prior = brand_thumb()
    ctx = Rule08EntropyContext(recent_thumbnail_specs=(prior,))
    same = validate_rule_08(proposal(thumb=prior), ctx)
    assert not same.ok
    assert any(v.code == "THUMBNAIL_NO_NOVELTY" for v in same.violations)

    rotated = validate_rule_08(
        proposal(thumb=brand_thumb(accent="slate_blue")),
        ctx,
    )
    assert rotated.ok


def test_thumbnail_typography_and_framing_locked() -> None:
    bad = ThumbnailBrandSpec(
        typography="clickbait_sans",
        framing=CHANNEL_FRAMING,
        focal_subject="x",
        composition="doorway_silhouette",
        accent_mood="muted_amber",
    )
    result = validate_rule_08(proposal(thumb=bad))
    assert any(v.code == "BRAND_TYPOGRAPHY" for v in result.violations)


@pytest.fixture
def conn() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("PRAGMA foreign_keys = ON;")
    db.executescript(_PIPELINE_SQL.read_text(encoding="utf-8"))
    return db


def _seed_episode(
    conn: sqlite3.Connection,
    episode_id: str,
    *,
    archetype: str,
    thumb_json: str,
    published_at: int,
) -> None:
    case_id = f"case_{episode_id}"
    conn.execute(
        """
        INSERT INTO cases (
          case_id, candidate_id, defendant_name, incident_year, jurisdiction, docket_id,
          primary_record_verified, verification_source, disposition_status,
          conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
          anonymization_artifact_sha256, created_at, updated_at
        ) VALUES (
          ?, NULL, 'Jane Doe', 2022, 'Cook, IL', 'DK-99', 1, 'courtlistener',
          'AFFIRMED', 1, 'APPROVED', 'rev_a', ?, 'sha_anon', ?, ?
        )
        """,
        (case_id, T0, T0, T0),
    )
    conn.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, flow_backend_mode, cold_open_archetype,
          turning_point_count, total_master_ms, timeline_validated_sha256,
          ready_bundle_sha256, thumbnail_mood_vec, updated_at, created_at
        ) VALUES (
          ?, ?, 'PUBLISHED', 'GEMINI_OMNI_INTERACTIONS', ?, 4, 1200000,
          ?, 'sha_bundle', ?, ?, ?
        )
        """,
        (
            episode_id,
            case_id,
            archetype,
            f"sha_tl_{episode_id}",
            thumb_json,
            T0,
            T0,
        ),
    )
    conn.execute(
        """
        INSERT INTO published_entropy_history (
          episode_id, cold_open_archetype, turning_point_count,
          thumbnail_mood_vec, published_at
        ) VALUES (?, ?, 4, ?, ?)
        """,
        (episode_id, archetype, thumb_json, published_at),
    )


def test_sqlite_context_loads_recent_archetype(conn: sqlite3.Connection) -> None:
    thumb_a = brand_thumb().to_mood_vec_json()
    thumb_b = brand_thumb(composition="desk_evidence_closeup", accent="slate_blue").to_mood_vec_json()
    _seed_episode(conn, "ep_a", archetype="911_CALL_IN_MEDIA_RES", thumb_json=thumb_a, published_at=T0)
    _seed_episode(
        conn,
        "ep_b",
        archetype="ALIBI_THAT_CRACKED",
        thumb_json=thumb_b,
        published_at=T0 + 1,
    )

    ctx = load_entropy_context_from_db(conn, queries_path=_QUERIES_SQL)
    assert ctx.recent_cold_open_archetypes[0] == "ALIBI_THAT_CRACKED"

    blocked = validate_rule_08(
        proposal(archetype="ALIBI_THAT_CRACKED", thumb=brand_thumb(accent="deep_crimson_stamp")),
        ctx,
    )
    assert any(v.code == "COLD_OPEN_REPEAT" for v in blocked.violations)

    allowed = validate_rule_08(
        proposal(
            archetype="CHRONOLOGICAL_COUNTDOWN",
            thumb=brand_thumb(composition="map_trajectory_split", accent="deep_crimson_stamp"),
        ),
        ctx,
    )
    assert allowed.ok