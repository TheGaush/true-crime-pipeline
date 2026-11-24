"""Conveyor repository tests against schema/pipeline.sql. No network and no sleep."""

from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

import pytest

from db.conveyor_repo import (
    ADVANCED,
    BACKPRESSURE_QUEUE_FULL,
    FLOW_BATCH_SLOT_CAP,
    AwaitingFlowEpisode,
    ConveyorStateRepository,
    EpisodeNotFound,
    IllegalTransition,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_SQL = REPO_ROOT / "schema" / "pipeline.sql"

# F-22 pin lives in schema/pipeline.sql. This host may be older. Do not drop guards.
DOCUMENTED_MIN_SQLITE = (3, 51, 3)
SKIPPED_FOR_SQLITE_VERSION: list[str] = []

LEGAL_PATH = (
    "QUEUED",
    "SCOUTED",
    "EVIDENCE_AND_2K_LOCKED",
    "COMPLIANCE_PASSED",
    "SCENE_PLAN_APPROVED",
    "VOICE_READY",
    "MANIFEST_LINTED",
    "ANIMATIC_APPROVED",
    "CODE_RENDERED",
    "AWAITING_FLOW_BATCH",
    "POST_FLOW_PROCESSING",
    "MASTERED",
    "PENDING_HUMAN_SIGNOFF",
    "READY_TO_UPLOAD",
    "PUBLISHED",
)

GATES = (
    "FACTUAL_ACCURACY",
    "PRIVACY_PII",
    "SOURCE_RIGHTS",
    "SYNTHETIC_DISCLOSURE",
    "ILLUSTRATIVE_LABELING",
)


class Clock:
    """Injected millisecond clock. Each call advances by one millisecond."""

    def __init__(self, start: int = 5_000) -> None:
        self.now_ms = start

    def __call__(self) -> int:
        self.now_ms += 1
        return self.now_ms


def _split_statements(script: str) -> list[str]:
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            text = buffer.strip()
            buffer = ""
            if text:
                statements.append(text)
    tail = buffer.strip()
    if tail:
        statements.append(tail)
    return statements


def _version_gap(exc: sqlite3.Error) -> bool:
    if sqlite3.sqlite_version_info >= DOCUMENTED_MIN_SQLITE:
        return False
    text = str(exc).lower()
    return (
        "syntax error" in text
        or "unrecognized token" in text
        or "not supported" in text
    )


def open_pipeline() -> sqlite3.Connection:
    """Load schema/pipeline.sql. Skip a statement only when the host SQLite is too old."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    script = PIPELINE_SQL.read_text(encoding="utf-8")
    for statement in _split_statements(script):
        try:
            conn.execute(statement)
        except sqlite3.Error as exc:
            if _version_gap(exc):
                reason = (
                    f"pipeline.sql: skipped on SQLite {sqlite3.sqlite_version} "
                    f"(documented minimum 3.51.3) because the statement is a "
                    f"version gap ({exc}). Guard left in the SQL file. "
                    f"Statement starts: {statement[:160]!r}"
                )
                SKIPPED_FOR_SQLITE_VERSION.append(reason)
                warnings.warn(reason, RuntimeWarning, stacklevel=2)
                continue
            conn.close()
            raise
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def conn():
    connection = open_pipeline()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def repo(conn: sqlite3.Connection, clock: Clock) -> ConveyorStateRepository:
    return ConveyorStateRepository(conn, now=clock)


def insert_case(
    conn: sqlite3.Connection,
    case_id: str = "case-1",
    *,
    disposition_status: str = "AFFIRMED",
) -> None:
    conn.execute(
        """
        INSERT INTO cases (
          case_id, defendant_name, incident_year, jurisdiction, verification_source,
          disposition_status, conviction_confirmed, created_at, updated_at
        ) VALUES (?, 'Alex Rivera', 2018, 'Mercer, NJ', 'courtlistener', ?, 0, 1, 1)
        """,
        (case_id, disposition_status),
    )


def insert_episode(
    conn: sqlite3.Connection,
    episode_id: str,
    created_at: int,
    *,
    case_id: str = "case-1",
    state: str = "QUEUED",
) -> None:
    conn.execute(
        """
        INSERT INTO episodes (
          episode_id, case_id, state, cold_open_archetype, updated_at, created_at
        ) VALUES (?, ?, ?, '911_CALL_IN_MEDIA_RES', ?, ?)
        """,
        (episode_id, case_id, state, created_at, created_at),
    )


def advance(repo: ConveyorStateRepository, episode_id: str, to_state: str) -> None:
    path = repo.legal_path
    start = path.index(repo.get_state(episode_id))
    end = path.index(to_state)
    for step in path[start + 1 : end + 1]:
        result = repo.transition(episode_id, step)
        assert result.status == ADVANCED
        assert result.state == step


def arm_release_gate(conn: sqlite3.Connection, episode_id: str, case_id: str) -> None:
    """Satisfy trg_episode_release_gate. The trigger text stays in the schema."""
    bundle = "b" * 64
    conn.execute(
        """
        UPDATE cases
        SET anonymization_status = 'APPROVED',
            anonymized_by = 'gate-reviewer',
            anonymized_at = 40,
            anonymization_artifact_sha256 = ?,
            updated_at = 40
        WHERE case_id = ?
        """,
        ("c" * 64, case_id),
    )
    conn.execute(
        """
        UPDATE episodes
        SET timeline_validated_sha256 = ?,
            ready_bundle_sha256 = ?,
            updated_at = 41
        WHERE episode_id = ?
        """,
        ("a" * 64, bundle, episode_id),
    )
    conn.execute(
        """
        INSERT INTO scene_plans (
          scene_plan_id, episode_id, scene_id, plan_version, seq_index,
          story_purpose, intended_audience_effect, approved_narration_text,
          narration_version_sha256, cited_fact_ids_json, visual_concept,
          visual_engine, motif_component, prompt_mode, visual_prompt,
          keyframe_refs_json, expected_output_summary, timing_start_ms, timing_end_ms,
          transition_spec_json, sound_cues_json, edit_instructions,
          acceptance_criteria_json, asset_version_sha256, plan_status,
          reviewed_by, reviewed_at, created_at, updated_at
        ) VALUES (
          ?, ?, 'scene-1', 1, 1,
          'establish the record', 'orient the viewer', 'The docket was affirmed.',
          ?, '["fact-1"]', 'stickman at the counsel table',
          'CODE_STICKMAN', 'StickmanStage', 'NONE', 'no generative video',
          '[]', 'a still stickman frame', 0, 1000,
          '{}', '[]', 'hold',
          '["narration-matches-frame"]', ?, 'EDITED_APPROVED',
          'gate-reviewer', 42, 42, 42
        )
        """,
        (f"plan-{episode_id}", episode_id, "d" * 64, "e" * 64),
    )
    conn.execute(
        """
        INSERT INTO scenes (
          scene_id, episode_id, scene_plan_id, seq_index, act_number,
          visual_engine, motif_component, start_ms, end_ms, timeline_spec_json
        ) VALUES (?, ?, ?, 1, 1, 'CODE_STICKMAN', 'StickmanStage', 0, 1000, '{}')
        """,
        (f"scene-{episode_id}", episode_id, f"plan-{episode_id}"),
    )
    for gate in GATES:
        conn.execute(
            """
            INSERT INTO release_approvals (
              approval_id, episode_id, gate_name, artifact_bundle_sha256,
              status, reviewer_id, reviewed_at
            ) VALUES (?, ?, ?, ?, 'APPROVED', 'gate-reviewer', 43)
            """,
            (f"ap-{episode_id}-{gate}", episode_id, gate, bundle),
        )


def _updated_at(conn: sqlite3.Connection, episode_id: str) -> int:
    row = conn.execute(
        "SELECT updated_at FROM episodes WHERE episode_id = ?",
        (episode_id,),
    ).fetchone()
    assert row is not None
    return int(row["updated_at"])


def test_legal_path_follows_episode_states(repo: ConveyorStateRepository) -> None:
    assert repo.legal_path == LEGAL_PATH
    assert FLOW_BATCH_SLOT_CAP == 3


def test_host_sqlite_keeps_schema_guards(conn: sqlite3.Connection) -> None:
    version = conn.execute(
        "SELECT value FROM meta WHERE key = 'min_sqlite_version'"
    ).fetchone()
    assert version is not None
    assert version["value"] == "3.51.3"
    trigger = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'trg_episode_release_gate'"
    ).fetchone()
    assert trigger is not None
    assert "RELEASE_GATE_BLOCKED" in str(trigger["sql"])
    quarantine = conn.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'trigger' AND name = 'trg_case_disposition_quarantine'
        """
    ).fetchone()
    assert quarantine is not None
    assert "QUARANTINED_LEGAL_HOLD" in str(quarantine["sql"])
    for reason in SKIPPED_FOR_SQLITE_VERSION:
        assert "3.51.3" in reason
        assert "version gap" in reason
        assert "Guard left in the SQL file" in reason


def test_adjacent_walk_uses_injected_now(
    repo: ConveyorStateRepository, conn: sqlite3.Connection, clock: Clock
) -> None:
    insert_case(conn)
    insert_episode(conn, "ep-1", created_at=10)
    before = clock.now_ms
    result = repo.transition("ep-1", "SCOUTED")
    assert result.status == ADVANCED
    assert result.state == "SCOUTED"
    assert result.updated_at == before + 1
    assert _updated_at(conn, "ep-1") == result.updated_at
    advance(repo, "ep-1", "PENDING_HUMAN_SIGNOFF")
    assert repo.get_state("ep-1") == "PENDING_HUMAN_SIGNOFF"
    assert _updated_at(conn, "ep-1") == clock.now_ms


def test_release_gate_blocks_then_publish_is_terminal(
    repo: ConveyorStateRepository, conn: sqlite3.Connection
) -> None:
    insert_case(conn, "case-pub")
    insert_episode(conn, "ep-pub", created_at=2, case_id="case-pub")
    advance(repo, "ep-pub", "PENDING_HUMAN_SIGNOFF")
    stamped = _updated_at(conn, "ep-pub")
    with pytest.raises(sqlite3.IntegrityError, match="RELEASE_GATE_BLOCKED"):
        repo.transition("ep-pub", "READY_TO_UPLOAD")
    assert repo.get_state("ep-pub") == "PENDING_HUMAN_SIGNOFF"
    assert _updated_at(conn, "ep-pub") == stamped

    arm_release_gate(conn, "ep-pub", "case-pub")
    ready = repo.transition("ep-pub", "READY_TO_UPLOAD")
    published = repo.transition("ep-pub", "PUBLISHED")
    assert ready.status == ADVANCED
    assert published.status == ADVANCED
    assert repo.get_state("ep-pub") == "PUBLISHED"
    with pytest.raises(IllegalTransition, match="terminal state"):
        repo.transition("ep-pub", "READY_TO_UPLOAD")
    assert repo.get_state("ep-pub") == "PUBLISHED"


def test_skips_backward_and_side_states_stay_put(
    repo: ConveyorStateRepository, conn: sqlite3.Connection, clock: Clock
) -> None:
    insert_case(conn)
    insert_episode(conn, "ep-1", created_at=5)
    seen = clock.now_ms
    with pytest.raises(IllegalTransition, match="skip") as skip:
        repo.transition("ep-1", "EVIDENCE_AND_2K_LOCKED")
    assert skip.value.from_state == "QUEUED"
    assert skip.value.to_state == "EVIDENCE_AND_2K_LOCKED"
    assert repo.get_state("ep-1") == "QUEUED"
    assert clock.now_ms == seen

    repo.transition("ep-1", "SCOUTED")
    stamped = _updated_at(conn, "ep-1")
    seen = clock.now_ms
    with pytest.raises(IllegalTransition, match="backward move"):
        repo.transition("ep-1", "QUEUED")
    with pytest.raises(IllegalTransition, match="not a legal conveyor state"):
        repo.transition("ep-1", "QUARANTINED_LEGAL_HOLD")
    with pytest.raises(IllegalTransition, match="not a legal conveyor state"):
        repo.transition("ep-1", "REJECTED_KILL_SWITCH")
    with pytest.raises(IllegalTransition, match="not a legal conveyor state"):
        repo.transition("ep-1", "ABORTED_COPYCAT_WAVE")
    with pytest.raises(IllegalTransition, match="not a legal conveyor state"):
        repo.transition("ep-1", "NOT_A_STATE")
    with pytest.raises(IllegalTransition, match="skip"):
        repo.transition("ep-1", "AWAITING_FLOW_BATCH")
    assert repo.get_state("ep-1") == "SCOUTED"
    assert _updated_at(conn, "ep-1") == stamped
    assert clock.now_ms == seen
    with pytest.raises(EpisodeNotFound):
        repo.transition("missing", "SCOUTED")


def test_three_slots_list_oldest_created_at_first(
    repo: ConveyorStateRepository, conn: sqlite3.Connection
) -> None:
    insert_case(conn)
    for episode_id, created_at in (("ep-c", 300), ("ep-a", 100), ("ep-b", 200)):
        insert_episode(conn, episode_id, created_at)
        advance(repo, episode_id, "AWAITING_FLOW_BATCH")
    listed = repo.list_awaiting_flow_batch()
    assert listed == (
        AwaitingFlowEpisode("ep-a", 100),
        AwaitingFlowEpisode("ep-b", 200),
        AwaitingFlowEpisode("ep-c", 300),
    )
    assert [item.created_at for item in listed] == sorted(item.created_at for item in listed)


def test_fourth_entry_returns_backpressure_and_stays(
    repo: ConveyorStateRepository, conn: sqlite3.Connection, clock: Clock
) -> None:
    insert_case(conn)
    for index, episode_id in enumerate(("ep-a", "ep-b", "ep-c")):
        insert_episode(conn, episode_id, created_at=100 + index)
        advance(repo, episode_id, "AWAITING_FLOW_BATCH")
    insert_episode(conn, "ep-d", created_at=50)
    advance(repo, "ep-d", "CODE_RENDERED")
    stamped = _updated_at(conn, "ep-d")
    seen = clock.now_ms

    result = repo.transition("ep-d", "AWAITING_FLOW_BATCH")

    assert result.status == BACKPRESSURE_QUEUE_FULL
    assert result.status == "BACKPRESSURE_QUEUE_FULL"
    assert result.state == "CODE_RENDERED"
    assert result.updated_at is None
    assert repo.get_state("ep-d") == "CODE_RENDERED"
    assert _updated_at(conn, "ep-d") == stamped
    assert clock.now_ms == seen
    assert [item.episode_id for item in repo.list_awaiting_flow_batch()] == [
        "ep-a",
        "ep-b",
        "ep-c",
    ]


def test_full_queue_does_not_turn_a_skip_into_backpressure(
    repo: ConveyorStateRepository, conn: sqlite3.Connection
) -> None:
    insert_case(conn)
    for episode_id, created_at in (("ep-a", 1), ("ep-b", 2), ("ep-c", 3)):
        insert_episode(conn, episode_id, created_at)
        advance(repo, episode_id, "AWAITING_FLOW_BATCH")
    insert_episode(conn, "ep-d", created_at=4)
    with pytest.raises(IllegalTransition, match="skip"):
        repo.transition("ep-d", "AWAITING_FLOW_BATCH")
    assert repo.get_state("ep-d") == "QUEUED"
    assert len(repo.list_awaiting_flow_batch()) == 3


def test_draining_oldest_frees_a_slot_and_keeps_fifo(
    repo: ConveyorStateRepository, conn: sqlite3.Connection
) -> None:
    insert_case(conn)
    for episode_id, created_at in (("ep-c", 300), ("ep-a", 100), ("ep-b", 200)):
        insert_episode(conn, episode_id, created_at)
        advance(repo, episode_id, "AWAITING_FLOW_BATCH")
    left = repo.transition("ep-a", "POST_FLOW_PROCESSING")
    assert left.status == ADVANCED
    assert repo.get_state("ep-a") == "POST_FLOW_PROCESSING"

    insert_episode(conn, "ep-d", created_at=50)
    advance(repo, "ep-d", "AWAITING_FLOW_BATCH")
    assert [item.episode_id for item in repo.list_awaiting_flow_batch()] == [
        "ep-d",
        "ep-b",
        "ep-c",
    ]

    insert_episode(conn, "ep-e", created_at=400)
    advance(repo, "ep-e", "CODE_RENDERED")
    held = repo.transition("ep-e", "AWAITING_FLOW_BATCH")
    assert held.status == BACKPRESSURE_QUEUE_FULL
    assert repo.get_state("ep-e") == "CODE_RENDERED"


def test_equal_created_at_breaks_ties_by_episode_id(
    repo: ConveyorStateRepository, conn: sqlite3.Connection
) -> None:
    insert_case(conn)
    for episode_id in ("ep-b", "ep-a", "ep-c"):
        insert_episode(conn, episode_id, created_at=15)
        advance(repo, episode_id, "AWAITING_FLOW_BATCH")
    assert [item.episode_id for item in repo.list_awaiting_flow_batch()] == [
        "ep-a",
        "ep-b",
        "ep-c",
    ]


def test_disposition_trigger_still_quarantines_and_repo_will_not(
    repo: ConveyorStateRepository, conn: sqlite3.Connection
) -> None:
    insert_case(conn, "case-q")
    insert_episode(conn, "ep-q", created_at=7, case_id="case-q")
    with pytest.raises(IllegalTransition, match="not a legal conveyor state"):
        repo.transition("ep-q", "QUARANTINED_LEGAL_HOLD")
    assert repo.get_state("ep-q") == "QUEUED"

    advance(repo, "ep-q", "AWAITING_FLOW_BATCH")
    conn.execute(
        """
        UPDATE cases
        SET disposition_status = 'REVERSED', updated_at = 77
        WHERE case_id = 'case-q'
        """
    )
    assert repo.get_state("ep-q") == "QUARANTINED_LEGAL_HOLD"
    assert repo.list_awaiting_flow_batch() == ()
    with pytest.raises(IllegalTransition, match="off the legal forward path"):
        repo.transition("ep-q", "POST_FLOW_PROCESSING")
    assert repo.get_state("ep-q") == "QUARANTINED_LEGAL_HOLD"


def test_kill_switch_is_left_alone_by_the_quarantine_trigger(
    conn: sqlite3.Connection,
) -> None:
    insert_case(conn, "case-k")
    insert_episode(conn, "ep-k", created_at=3, case_id="case-k", state="REJECTED_KILL_SWITCH")
    conn.execute(
        """
        UPDATE cases
        SET disposition_status = 'VACATED', updated_at = 6
        WHERE case_id = 'case-k'
        """
    )
    row = conn.execute("SELECT state FROM episodes WHERE episode_id = 'ep-k'").fetchone()
    assert row is not None
    assert row["state"] == "REJECTED_KILL_SWITCH"


def test_schema_checks_still_reject_bad_rows(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError, match="LEGAL_DISPOSITION"):
        conn.execute(
            """
            INSERT INTO cases (
              case_id, defendant_name, incident_year, jurisdiction, verification_source,
              disposition_status, conviction_confirmed, created_at, updated_at
            ) VALUES (
              'case-bad', 'Alex Rivera', 2018, 'Mercer, NJ', 'courtlistener',
              'PENDING', 1, 1, 1
            )
            """
        )
    insert_case(conn)
    with pytest.raises(sqlite3.IntegrityError):
        insert_episode(conn, "ep-orphan", created_at=1, case_id="missing-case")


def test_now_must_be_callable_and_return_int(conn: sqlite3.Connection) -> None:
    with pytest.raises(TypeError, match="callable"):
        ConveyorStateRepository(conn, now=5)  # type: ignore[arg-type]
    repo = ConveyorStateRepository(conn, now=lambda: "nope")  # type: ignore[arg-type, return-value]
    insert_case(conn)
    insert_episode(conn, "ep-1", created_at=1)
    with pytest.raises(TypeError, match="int"):
        repo.transition("ep-1", "SCOUTED")
    assert repo.get_state("ep-1") == "QUEUED"
