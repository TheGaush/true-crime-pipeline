"""70/30 dual-track monthly slate allocator for Agent 1 scouting.

``MonthlySlateAllocator`` fills a 10-episode window from greenlit candidates,
defaulting to 7 ``TRACK_A_OUTLIER`` and 3 ``TRACK_B_FOIA_RADAR`` slots. When
recent ``episode_analytics`` show enough Track B ROI advantage, the mix shifts
to 6/4. Candidates deduplicate on ``(defendant_normalized, incident_year)``;
dual-track hits merge into one slot that keeps Track B FOIA document ids.
"""

from __future__ import annotations

import re
import sqlite3
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

TRACK_A_OUTLIER = "TRACK_A_OUTLIER"
TRACK_B_FOIA_RADAR = "TRACK_B_FOIA_RADAR"
Track = Literal["TRACK_A_OUTLIER", "TRACK_B_FOIA_RADAR"]

WINDOW_SIZE = 10
DEFAULT_TRACK_A_SLOTS = 7
DEFAULT_TRACK_B_SLOTS = 3
SHIFTED_TRACK_A_SLOTS = 6
SHIFTED_TRACK_B_SLOTS = 4

MIN_EPISODES_PER_TRACK = 3
TRACK_B_ROI_MULTIPLIER = 1.25

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)

_ANALYTICS_SQL = """
WITH latest AS (
    SELECT episode_id, MAX(captured_at) AS captured_at
    FROM episode_analytics
    WHERE rpm_micro_usd IS NOT NULL
    GROUP BY episode_id
)
SELECT DISTINCT e.episode_id, oc.track, ea.rpm_micro_usd
FROM latest l
JOIN episode_analytics ea
  ON ea.episode_id = l.episode_id AND ea.captured_at = l.captured_at
JOIN episodes e ON e.episode_id = ea.episode_id
JOIN cases c ON c.case_id = e.case_id
JOIN outlier_candidates oc ON oc.candidate_id = c.candidate_id
"""


def normalize_defendant(name: str) -> str:
    """Casefold, strip punctuation, drop middle initials, collapse whitespace."""

    folded = name.casefold().strip()
    without_punct = _PUNCT_RE.sub("", folded)
    tokens = [token for token in without_punct.split() if len(token) > 1]
    return " ".join(tokens)


@dataclass(frozen=True, slots=True)
class SlateCandidate:
    """One scout candidate eligible for monthly slate placement."""

    candidate_id: str
    track: Track
    defendant_name: str
    incident_year: int
    composite_score: float = 0.0
    foia_document_ids: tuple[str, ...] = ()

    @property
    def defendant_normalized(self) -> str:
        return normalize_defendant(self.defendant_name)


@dataclass(frozen=True, slots=True)
class SlateSlot:
    """One allocated episode slot in the rolling window."""

    slot_index: int
    track: Track
    candidate_id: str
    defendant_normalized: str
    incident_year: int
    foia_document_ids: tuple[str, ...]
    merged_dual_track: bool = False


@dataclass(frozen=True, slots=True)
class SlateAllocation:
    """Result of filling one monthly slate window."""

    slots: tuple[SlateSlot, ...]
    track_a_quota: int
    track_b_quota: int
    window_size: int = WINDOW_SIZE

    @property
    def track_a_count(self) -> int:
        return sum(1 for slot in self.slots if slot.track == TRACK_A_OUTLIER)

    @property
    def track_b_count(self) -> int:
        return sum(1 for slot in self.slots if slot.track == TRACK_B_FOIA_RADAR)


def _candidate_sort_key(candidate: SlateCandidate) -> tuple[float, str]:
    return (candidate.composite_score, candidate.candidate_id)


def deduplicate_candidates(candidates: Sequence[SlateCandidate]) -> list[SlateCandidate]:
    """Merge rows sharing ``(defendant_normalized, incident_year)``."""

    buckets: dict[tuple[str, int], list[SlateCandidate]] = {}
    for candidate in candidates:
        key = (candidate.defendant_normalized, candidate.incident_year)
        buckets.setdefault(key, []).append(candidate)

    merged: list[SlateCandidate] = []
    for group in buckets.values():
        if len(group) == 1:
            merged.append(group[0])
            continue

        track_b = [row for row in group if row.track == TRACK_B_FOIA_RADAR]
        track_a = [row for row in group if row.track == TRACK_A_OUTLIER]
        best = max(group, key=_candidate_sort_key)
        foia_ids: tuple[str, ...] = ()
        if track_b and track_a:
            best_b = max(track_b, key=_candidate_sort_key)
            foia_ids = best_b.foia_document_ids
            effective_track: Track = TRACK_B_FOIA_RADAR
            representative = best_b
        elif track_b:
            representative = max(track_b, key=_candidate_sort_key)
            foia_ids = representative.foia_document_ids
            effective_track = TRACK_B_FOIA_RADAR
        else:
            representative = best
            effective_track = representative.track

        merged.append(
            SlateCandidate(
                candidate_id=representative.candidate_id,
                track=effective_track,
                defendant_name=representative.defendant_name,
                incident_year=representative.incident_year,
                composite_score=max(row.composite_score for row in group),
                foia_document_ids=foia_ids,
            )
        )
    return merged


def resolve_track_mix(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return ``(track_a_slots, track_b_slots)`` from analytics or the 7/3 default."""

    try:
        rows = conn.execute(_ANALYTICS_SQL).fetchall()
    except sqlite3.Error:
        return DEFAULT_TRACK_A_SLOTS, DEFAULT_TRACK_B_SLOTS

    by_track: dict[str, list[int]] = {TRACK_A_OUTLIER: [], TRACK_B_FOIA_RADAR: []}
    seen: set[tuple[str, str]] = set()
    for episode_id, track, rpm in rows:
        if track not in by_track or rpm is None:
            continue
        dedupe = (episode_id, track)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        by_track[track].append(int(rpm))

    if (
        len(by_track[TRACK_A_OUTLIER]) < MIN_EPISODES_PER_TRACK
        or len(by_track[TRACK_B_FOIA_RADAR]) < MIN_EPISODES_PER_TRACK
    ):
        return DEFAULT_TRACK_A_SLOTS, DEFAULT_TRACK_B_SLOTS

    median_a = statistics.median(by_track[TRACK_A_OUTLIER])
    median_b = statistics.median(by_track[TRACK_B_FOIA_RADAR])
    if median_b > median_a * TRACK_B_ROI_MULTIPLIER:
        return SHIFTED_TRACK_A_SLOTS, SHIFTED_TRACK_B_SLOTS
    return DEFAULT_TRACK_A_SLOTS, DEFAULT_TRACK_B_SLOTS


class MonthlySlateAllocator:
    """Allocate one 10-episode scouting slate with dual-track balance."""

    def __init__(
        self,
        *,
        window_size: int = WINDOW_SIZE,
        default_track_a: int = DEFAULT_TRACK_A_SLOTS,
        default_track_b: int = DEFAULT_TRACK_B_SLOTS,
        shifted_track_a: int = SHIFTED_TRACK_A_SLOTS,
        shifted_track_b: int = SHIFTED_TRACK_B_SLOTS,
    ) -> None:
        self.window_size = window_size
        self.default_track_a = default_track_a
        self.default_track_b = default_track_b
        self.shifted_track_a = shifted_track_a
        self.shifted_track_b = shifted_track_b

    def allocate(
        self,
        candidates: Sequence[SlateCandidate],
        *,
        conn: sqlite3.Connection | None = None,
        track_a_quota: int | None = None,
        track_b_quota: int | None = None,
    ) -> SlateAllocation:
        if track_a_quota is None or track_b_quota is None:
            if conn is not None:
                track_a_quota, track_b_quota = resolve_track_mix(conn)
            else:
                track_a_quota = track_a_quota if track_a_quota is not None else self.default_track_a
                track_b_quota = track_b_quota if track_b_quota is not None else self.default_track_b

        assert track_a_quota is not None and track_b_quota is not None
        if track_a_quota + track_b_quota != self.window_size:
            msg = f"quotas must sum to window_size={self.window_size}"
            raise ValueError(msg)

        deduped = deduplicate_candidates(candidates)
        dual_keys = {
            (normalize_defendant(c.defendant_name), c.incident_year)
            for c in candidates
            if sum(
                1
                for other in candidates
                if normalize_defendant(other.defendant_name)
                == normalize_defendant(c.defendant_name)
                and other.incident_year == c.incident_year
            )
            > 1
        }

        pool_a = sorted(
            [c for c in deduped if c.track == TRACK_A_OUTLIER],
            key=_candidate_sort_key,
            reverse=True,
        )
        pool_b = sorted(
            [c for c in deduped if c.track == TRACK_B_FOIA_RADAR],
            key=_candidate_sort_key,
            reverse=True,
        )

        chosen_b = pool_b[:track_b_quota]
        chosen_a = pool_a[:track_a_quota]

        slots: list[SlateSlot] = []
        for index, candidate in enumerate(chosen_a + chosen_b):
            key = (candidate.defendant_normalized, candidate.incident_year)
            slots.append(
                SlateSlot(
                    slot_index=index,
                    track=candidate.track,
                    candidate_id=candidate.candidate_id,
                    defendant_normalized=candidate.defendant_normalized,
                    incident_year=candidate.incident_year,
                    foia_document_ids=candidate.foia_document_ids,
                    merged_dual_track=key in dual_keys,
                )
            )

        _assert_unique_defendants(slots)
        return SlateAllocation(
            slots=tuple(slots),
            track_a_quota=track_a_quota,
            track_b_quota=track_b_quota,
            window_size=self.window_size,
        )


def _assert_unique_defendants(slots: Sequence[SlateSlot]) -> None:
    keys = [(slot.defendant_normalized, slot.incident_year) for slot in slots]
    if len(keys) != len(set(keys)):
        msg = "duplicate (defendant_normalized, incident_year) in slate slots"
        raise ValueError(msg)


__all__ = [
    "DEFAULT_TRACK_A_SLOTS",
    "DEFAULT_TRACK_B_SLOTS",
    "MIN_EPISODES_PER_TRACK",
    "MonthlySlateAllocator",
    "SHIFTED_TRACK_A_SLOTS",
    "SHIFTED_TRACK_B_SLOTS",
    "SlateAllocation",
    "SlateCandidate",
    "SlateSlot",
    "TRACK_A_OUTLIER",
    "TRACK_B_FOIA_RADAR",
    "TRACK_B_ROI_MULTIPLIER",
    "WINDOW_SIZE",
    "deduplicate_candidates",
    "normalize_defendant",
    "resolve_track_mix",
]