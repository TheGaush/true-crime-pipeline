"""Offline tests for the 70/30 dual-track monthly slate allocator."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent1_scout.slate_balancer import (  # noqa: E402
    DEFAULT_TRACK_A_SLOTS,
    DEFAULT_TRACK_B_SLOTS,
    SHIFTED_TRACK_A_SLOTS,
    SHIFTED_TRACK_B_SLOTS,
    TRACK_A_OUTLIER,
    TRACK_B_FOIA_RADAR,
    MonthlySlateAllocator,
    SlateCandidate,
    deduplicate_candidates,
    normalize_defendant,
    resolve_track_mix,
)


def _candidate(
    cid: str,
    track: str,
    defendant: str,
    year: int,
    score: float = 0.0,
    foia_ids: tuple[str, ...] = (),
) -> SlateCandidate:
    return SlateCandidate(
        candidate_id=cid,
        track=track,  # type: ignore[arg-type]
        defendant_name=defendant,
        incident_year=year,
        composite_score=score,
        foia_document_ids=foia_ids,
    )


def _rich_pool() -> list[SlateCandidate]:
    rows: list[SlateCandidate] = []
    for index in range(12):
        rows.append(
            _candidate(
                f"a{index:02d}",
                TRACK_A_OUTLIER,
                f"Defendant Alpha {index}",
                2010 + index,
                score=float(100 - index),
            )
        )
    for index in range(8):
        rows.append(
            _candidate(
                f"b{index:02d}",
                TRACK_B_FOIA_RADAR,
                f"Defendant Bravo {index}",
                2000 + index,
                score=float(90 - index),
                foia_ids=(f"FOIA-{index}",),
            )
        )
    return rows


def test_normalize_defendant_strips_punctuation_and_case():
    assert normalize_defendant("  John Q. Public ") == normalize_defendant("john q public")


def test_default_7_3_split_from_rich_pool():
    allocation = MonthlySlateAllocator().allocate(_rich_pool())
    assert allocation.track_a_quota == DEFAULT_TRACK_A_SLOTS
    assert allocation.track_b_quota == DEFAULT_TRACK_B_SLOTS
    assert allocation.track_a_count == 7
    assert allocation.track_b_count == 3
    assert len(allocation.slots) == 10


def test_duplicate_merge_keeps_track_b_foia_ids():
    pool = [
        _candidate("a-dup", TRACK_A_OUTLIER, "Samuel Reed", 2018, score=95.0),
        _candidate(
            "b-dup",
            TRACK_B_FOIA_RADAR,
            "Samuel R. Reed",
            2018,
            score=90.0,
            foia_ids=("DOC-B-1", "DOC-B-2"),
        ),
        *[
            _candidate(f"a{i}", TRACK_A_OUTLIER, f"Only A {i}", 1990 + i, score=80.0 - i)
            for i in range(10)
        ],
        *[
            _candidate(
                f"b{i}",
                TRACK_B_FOIA_RADAR,
                f"Only B {i}",
                1980 + i,
                score=70.0 - i,
                foia_ids=(f"FOIA-{i}",),
            )
            for i in range(5)
        ],
    ]

    merged = deduplicate_candidates(pool)
    samuel = next(row for row in merged if row.defendant_normalized == normalize_defendant("Samuel Reed"))
    assert samuel.track == TRACK_B_FOIA_RADAR
    assert samuel.foia_document_ids == ("DOC-B-1", "DOC-B-2")

    allocation = MonthlySlateAllocator().allocate(pool)
    samuel_slots = [
        slot
        for slot in allocation.slots
        if slot.defendant_normalized == normalize_defendant("Samuel Reed")
    ]
    assert len(samuel_slots) == 1
    assert samuel_slots[0].foia_document_ids == ("DOC-B-1", "DOC-B-2")
    assert samuel_slots[0].merged_dual_track is True


def test_never_duplicate_defendant_year_in_slots():
    allocation = MonthlySlateAllocator().allocate(_rich_pool())
    keys = {(slot.defendant_normalized, slot.incident_year) for slot in allocation.slots}
    assert len(keys) == len(allocation.slots)


def test_resolve_track_mix_shifts_to_6_4_when_b_roi_wins():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE outlier_candidates (
            candidate_id TEXT PRIMARY KEY,
            track TEXT NOT NULL
        );
        CREATE TABLE cases (
            case_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL
        );
        CREATE TABLE episodes (
            episode_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL
        );
        CREATE TABLE episode_analytics (
            snapshot_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            rpm_micro_usd INTEGER,
            captured_at INTEGER NOT NULL
        );
        """
    )

    for index, (track, rpm) in enumerate(
        [
            (TRACK_A_OUTLIER, 1000),
            (TRACK_A_OUTLIER, 1100),
            (TRACK_A_OUTLIER, 1200),
            (TRACK_B_FOIA_RADAR, 2000),
            (TRACK_B_FOIA_RADAR, 2100),
            (TRACK_B_FOIA_RADAR, 2200),
        ]
    ):
        cid = f"c{index}"
        case_id = f"case{index}"
        ep_id = f"ep{index}"
        conn.execute(
            "INSERT INTO outlier_candidates VALUES (?, ?)",
            (cid, track),
        )
        conn.execute(
            "INSERT INTO cases VALUES (?, ?)",
            (case_id, cid),
        )
        conn.execute(
            "INSERT INTO episodes VALUES (?, ?)",
            (ep_id, case_id),
        )
        conn.execute(
            "INSERT INTO episode_analytics VALUES (?, ?, ?, ?)",
            (f"snap{index}", ep_id, rpm, 1000 + index),
        )

    assert resolve_track_mix(conn) == (SHIFTED_TRACK_A_SLOTS, SHIFTED_TRACK_B_SLOTS)

    allocation = MonthlySlateAllocator().allocate(_rich_pool(), conn=conn)
    assert allocation.track_a_quota == 6
    assert allocation.track_b_quota == 4


def test_resolve_track_mix_stays_7_3_with_insufficient_track_b_episodes():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE outlier_candidates (candidate_id TEXT PRIMARY KEY, track TEXT NOT NULL);
        CREATE TABLE cases (case_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL);
        CREATE TABLE episodes (episode_id TEXT PRIMARY KEY, case_id TEXT NOT NULL);
        CREATE TABLE episode_analytics (
            snapshot_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            rpm_micro_usd INTEGER,
            captured_at INTEGER NOT NULL
        );
        """
    )
    specs = [
        (TRACK_A_OUTLIER, 1000),
        (TRACK_A_OUTLIER, 1100),
        (TRACK_A_OUTLIER, 1200),
        (TRACK_B_FOIA_RADAR, 5000),
        (TRACK_B_FOIA_RADAR, 6000),
    ]
    for index, (track, rpm) in enumerate(specs):
        conn.execute("INSERT INTO outlier_candidates VALUES (?, ?)", (f"c{index}", track))
        conn.execute("INSERT INTO cases VALUES (?, ?)", (f"case{index}", f"c{index}"))
        conn.execute("INSERT INTO episodes VALUES (?, ?)", (f"ep{index}", f"case{index}"))
        conn.execute(
            "INSERT INTO episode_analytics VALUES (?, ?, ?, ?)",
            (f"snap{index}", f"ep{index}", rpm, 2000 + index),
        )

    assert resolve_track_mix(conn) == (DEFAULT_TRACK_A_SLOTS, DEFAULT_TRACK_B_SLOTS)


def test_resolve_track_mix_stays_7_3_when_roi_threshold_not_met():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE outlier_candidates (candidate_id TEXT PRIMARY KEY, track TEXT NOT NULL);
        CREATE TABLE cases (case_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL);
        CREATE TABLE episodes (episode_id TEXT PRIMARY KEY, case_id TEXT NOT NULL);
        CREATE TABLE episode_analytics (
            snapshot_id TEXT PRIMARY KEY,
            episode_id TEXT NOT NULL,
            rpm_micro_usd INTEGER,
            captured_at INTEGER NOT NULL
        );
        """
    )
    specs = [
        (TRACK_A_OUTLIER, 1000),
        (TRACK_A_OUTLIER, 1000),
        (TRACK_A_OUTLIER, 1000),
        (TRACK_B_FOIA_RADAR, 1200),
        (TRACK_B_FOIA_RADAR, 1200),
        (TRACK_B_FOIA_RADAR, 1200),
    ]
    for index, (track, rpm) in enumerate(specs):
        conn.execute("INSERT INTO outlier_candidates VALUES (?, ?)", (f"c{index}", track))
        conn.execute("INSERT INTO cases VALUES (?, ?)", (f"case{index}", f"c{index}"))
        conn.execute("INSERT INTO episodes VALUES (?, ?)", (f"ep{index}", f"case{index}"))
        conn.execute(
            "INSERT INTO episode_analytics VALUES (?, ?, ?, ?)",
            (f"snap{index}", f"ep{index}", rpm, 3000 + index),
        )

    assert resolve_track_mix(conn) == (DEFAULT_TRACK_A_SLOTS, DEFAULT_TRACK_B_SLOTS)


def test_allocate_rejects_invalid_quota_sum():
    with pytest.raises(ValueError, match="quotas must sum"):
        MonthlySlateAllocator().allocate(_rich_pool(), track_a_quota=5, track_b_quota=4)