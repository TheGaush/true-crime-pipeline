"""Mutually exclusive saturation index (SI) for one case's competing videos.

Each video is placed in at most one bucket. Highest priority wins:

1. ``N_14d_excl`` — published age <= 14 days. Weight 8. A video in this
   bucket is not also counted as mega or recent.
2. ``N_mega_decayed`` — remaining videos with views > 500_000, or flagged
   tier-1 giants, and age <= 3 years. Each video contributes a decay weight
   of 1.0 when age <= 18 months, or 0.5 when age is 18–36 months. The symbol
   ``N_mega_decayed`` in the formula is the sum of those weights, not a raw
   video count. The raw count is ``n_mega_count``.
3. ``N_recent_excl`` — remaining videos with views > 50_000 and age <= 18
   months. Weight 12.

.. code-block:: text

    SI = min(100, round(25 * N_mega_decayed + 12 * N_recent_excl + 8 * N_14d_excl))

``round`` is half-up, so ``round(25 * 0.5) = 13``. Python's built-in
``round`` uses banker's rounding and would return 12.

Partition invariant: the number of videos placed in the three buckets is
<= the number of unique video ids, and no video id is assigned twice.
Videos that match no bucket stay in the unique total only.

The 90-day kill is independent of the bucket. If any video has views
> 200_000 and age <= 90 days, ``has_90d_200k_kill`` is 1 and ``decision``
is ``REJECTED``. That includes videos under 500_000 views and videos that
were bucketed only in ``N_14d_excl``.

Hard kill when ``SI >= 55`` (also ``REJECTED``). Track A sweet spot when
``SI <= 35`` and the 90-day kill is off.

Ages are days. Pass ``age_days`` or ``published_at_ms`` plus an injected
``now_ms``. A month is 30 days, so 18 months is 540 days and 36 months is
3 years (1080 days). The 0.5 decay band and the mega age gate therefore
share one boundary.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

MS_PER_DAY = 24 * 60 * 60 * 1000
MONTH_DAYS = 30

DAYS_14 = 14
DAYS_90 = 90
DAYS_18_MONTHS = 18 * MONTH_DAYS
DAYS_36_MONTHS = 36 * MONTH_DAYS
DAYS_3_YEARS = DAYS_36_MONTHS

MEGA_VIEWS_EXCLUSIVE = 500_000
RECENT_VIEWS_EXCLUSIVE = 50_000
KILL_VIEWS_EXCLUSIVE = 200_000

WEIGHT_MEGA = 25
WEIGHT_RECENT = 12
WEIGHT_14D = 8

SI_CAP = 100
SI_HARD_KILL = 55
SI_SWEET_SPOT_MAX = 35

BUCKET_14D = "N_14d_excl"
BUCKET_MEGA = "N_mega_decayed"
BUCKET_RECENT = "N_recent_excl"

DECISION_REJECTED = "REJECTED"
DECISION_SWEET_SPOT = "TRACK_A_SWEET_SPOT"
DECISION_MARGINAL = "MARGINAL"


@dataclass(frozen=True, slots=True)
class CompetingVideo:
    """One deduplicated competing upload on a case.

    ``age_days`` is published age. When it is omitted, ``published_at_ms``
    and the calculator's injected ``now_ms`` supply the age. If both are
    present, ``age_days`` wins.

    ``is_tier1_giant`` is a flag from the tier-1 registry (Task 021). This
    calculator does not look up channels.
    """

    video_id: str
    views: int
    age_days: float | None = None
    published_at_ms: int | None = None
    is_tier1_giant: bool = False


@dataclass(frozen=True, slots=True)
class BucketAssignment:
    """The single bucket a video was placed in.

    ``decay_weight`` is 1.0 or 0.5 for ``N_mega_decayed`` and ``None`` for
    the other buckets. It is not a second count of the video.
    """

    video_id: str
    bucket: str
    views: int
    age_days: float
    decay_weight: float | None = None


@dataclass(frozen=True, slots=True)
class SaturationResult:
    """SI outcome for one case.

    ``n_mega_decayed`` is the sum of mega decay weights (1.0 / 0.5).
    ``n_mega_count`` is how many videos were placed in that bucket.
    ``n_14d_excl`` and ``n_recent_excl`` are raw exclusive counts.
    """

    si: int
    n_14d_excl: int
    n_mega_decayed: float
    n_mega_count: int
    n_recent_excl: int
    total_unique_videos: int
    has_90d_200k_kill: int
    si_hard_kill: bool
    track_a_sweet_spot: bool
    decision: str
    assignments: tuple[BucketAssignment, ...]

    @property
    def placed_video_count(self) -> int:
        return self.n_14d_excl + self.n_mega_count + self.n_recent_excl

    def partition_holds(self) -> bool:
        """True when buckets are a disjoint partial assignment of unique ids."""
        ids = [row.video_id for row in self.assignments]
        if len(ids) != len(set(ids)):
            return False
        if len(ids) != self.placed_video_count:
            return False
        if self.placed_video_count > self.total_unique_videos:
            return False
        buckets = {row.bucket for row in self.assignments}
        if not buckets <= {BUCKET_14D, BUCKET_MEGA, BUCKET_RECENT}:
            return False
        counted = {
            BUCKET_14D: 0,
            BUCKET_MEGA: 0,
            BUCKET_RECENT: 0,
        }
        mega_halves = 0
        for row in self.assignments:
            counted[row.bucket] += 1
            if row.bucket == BUCKET_MEGA:
                if row.decay_weight not in (1.0, 0.5):
                    return False
                mega_halves += 2 if row.decay_weight == 1.0 else 1
            elif row.decay_weight is not None:
                return False
        if counted[BUCKET_14D] != self.n_14d_excl:
            return False
        if counted[BUCKET_MEGA] != self.n_mega_count:
            return False
        if counted[BUCKET_RECENT] != self.n_recent_excl:
            return False
        return mega_halves / 2 == self.n_mega_decayed


class SaturationCalculator:
    """Score competing videos into a mutually exclusive saturation index."""

    def calculate(
        self,
        videos: Sequence[CompetingVideo],
        *,
        now_ms: int | None = None,
    ) -> SaturationResult:
        """Return SI, exclusive bucket totals, and the gate decision.

        Duplicate ``video_id`` values count once. The first occurrence wins.
        """
        unique = _dedupe(videos)
        assignments: list[BucketAssignment] = []
        n_14d = 0
        n_mega_count = 0
        mega_halves = 0
        n_recent = 0
        has_90d_200k_kill = 0

        for video in unique:
            age_days = _age_days(video, now_ms)
            if _is_90d_kill(video.views, age_days):
                has_90d_200k_kill = 1

            bucket, decay_weight = _assign_bucket(
                views=video.views,
                age_days=age_days,
                is_tier1_giant=video.is_tier1_giant,
            )
            if bucket is None:
                continue

            assignments.append(
                BucketAssignment(
                    video_id=video.video_id,
                    bucket=bucket,
                    views=video.views,
                    age_days=age_days,
                    decay_weight=decay_weight,
                )
            )
            if bucket == BUCKET_14D:
                n_14d += 1
            elif bucket == BUCKET_MEGA:
                n_mega_count += 1
                mega_halves += 2 if decay_weight == 1.0 else 1
            else:
                n_recent += 1

        n_mega_decayed = mega_halves / 2
        si = _saturation_index(mega_halves, n_recent, n_14d)
        si_hard_kill = si >= SI_HARD_KILL
        track_a_sweet_spot = si <= SI_SWEET_SPOT_MAX and has_90d_200k_kill == 0
        if has_90d_200k_kill or si_hard_kill:
            decision = DECISION_REJECTED
        elif track_a_sweet_spot:
            decision = DECISION_SWEET_SPOT
        else:
            decision = DECISION_MARGINAL

        result = SaturationResult(
            si=si,
            n_14d_excl=n_14d,
            n_mega_decayed=n_mega_decayed,
            n_mega_count=n_mega_count,
            n_recent_excl=n_recent,
            total_unique_videos=len(unique),
            has_90d_200k_kill=has_90d_200k_kill,
            si_hard_kill=si_hard_kill,
            track_a_sweet_spot=track_a_sweet_spot,
            decision=decision,
            assignments=tuple(assignments),
        )
        if not result.partition_holds():
            raise RuntimeError("mutually exclusive partition invariant failed")
        return result


def _dedupe(videos: Sequence[CompetingVideo]) -> tuple[CompetingVideo, ...]:
    seen: set[str] = set()
    unique: list[CompetingVideo] = []
    for video in videos:
        video_id = video.video_id
        if not isinstance(video_id, str) or video_id.strip() == "":
            raise ValueError("competing video_id must be a non-empty string")
        if video_id in seen:
            continue
        seen.add(video_id)
        unique.append(video)
    return tuple(unique)


def _age_days(video: CompetingVideo, now_ms: int | None) -> float:
    if video.age_days is not None:
        return float(video.age_days)
    if video.published_at_ms is None:
        raise ValueError(
            f"video {video.video_id!r} needs age_days or published_at_ms"
        )
    if now_ms is None:
        raise ValueError(
            "now_ms is required when a video supplies published_at_ms without age_days"
        )
    return (now_ms - video.published_at_ms) / MS_PER_DAY


def _is_90d_kill(views: int, age_days: float) -> bool:
    return views > KILL_VIEWS_EXCLUSIVE and 0 <= age_days <= DAYS_90


def _assign_bucket(
    *,
    views: int,
    age_days: float,
    is_tier1_giant: bool,
) -> tuple[str | None, float | None]:
    """Return ``(bucket, decay_weight)``. Decay is only set for mega videos."""
    if 0 <= age_days <= DAYS_14:
        return BUCKET_14D, None
    if 0 <= age_days <= DAYS_3_YEARS and (
        views > MEGA_VIEWS_EXCLUSIVE or is_tier1_giant
    ):
        decay = 1.0 if age_days <= DAYS_18_MONTHS else 0.5
        return BUCKET_MEGA, decay
    if views > RECENT_VIEWS_EXCLUSIVE and 0 <= age_days <= DAYS_18_MONTHS:
        return BUCKET_RECENT, None
    return None, None


def _saturation_index(mega_halves: int, n_recent: int, n_14d: int) -> int:
    """Half-up SI, capped at 100.

    ``mega_halves`` counts 0.5 decay units (2 per full-weight mega). The
    score in half-points is ``25 * mega_halves + 24 * n_recent + 16 * n_14d``,
    and ``(raw_twice + 1) // 2`` rounds halves up. ``25 * 0.5`` is therefore
    13.
    """
    raw_twice = (WEIGHT_MEGA * mega_halves) + (2 * WEIGHT_RECENT * n_recent) + (
        2 * WEIGHT_14D * n_14d
    )
    rounded = (raw_twice + 1) // 2
    return min(SI_CAP, rounded)


def _half_up_reference(value: float) -> int:
    """Reference half-up used by tests to show why ``round`` is not used.

    Non-negative only. ``math.floor(x + 0.5)`` matches the integer formula
    for the exact halves this calculator produces.
    """
    if value < 0:
        raise ValueError("SI components are non-negative")
    return math.floor(value + 0.5)
