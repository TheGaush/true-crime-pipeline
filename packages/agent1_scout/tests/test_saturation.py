"""Offline tests for the mutually exclusive saturation index."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from saturation import (  # noqa: E402
    BUCKET_14D,
    BUCKET_MEGA,
    BUCKET_RECENT,
    DAYS_14,
    DAYS_18_MONTHS,
    DAYS_3_YEARS,
    DAYS_36_MONTHS,
    DAYS_90,
    DECISION_MARGINAL,
    DECISION_REJECTED,
    DECISION_SWEET_SPOT,
    MONTH_DAYS,
    MS_PER_DAY,
    SI_HARD_KILL,
    SI_SWEET_SPOT_MAX,
    CompetingVideo,
    SaturationCalculator,
    SaturationResult,
    _half_up_reference,
)

NOW_MS = 1_763_942_400_000


def _calc(
    *videos: CompetingVideo,
    now_ms: int | None = None,
) -> SaturationResult:
    return SaturationCalculator().calculate(videos, now_ms=now_ms)


def _assert_exclusive(result: SaturationResult) -> None:
    assert result.partition_holds()
    ids = [row.video_id for row in result.assignments]
    assert len(ids) == len(set(ids))
    assert result.placed_video_count <= result.total_unique_videos
    assert result.n_14d_excl + result.n_mega_count + result.n_recent_excl == len(ids)


def test_month_length_pins_18_and_36_month_gates():
    assert MONTH_DAYS == 30
    assert DAYS_18_MONTHS == 540
    assert DAYS_36_MONTHS == 1080
    assert DAYS_3_YEARS == 1080
    assert DAYS_14 == 14
    assert DAYS_90 == 90
    assert 28 * MONTH_DAYS == 840


def test_half_up_rounding_makes_single_half_mega_13_not_bankers_12():
    assert _half_up_reference(25 * 0.5) == 13
    assert round(25 * 0.5) == 12


def test_five_day_600k_is_only_14d_and_sets_90d_kill():
    result = _calc(CompetingVideo("fresh-600k", views=600_000, age_days=5))

    assert result.si == 8
    assert result.n_14d_excl == 1
    assert result.n_mega_decayed == 0
    assert result.n_mega_count == 0
    assert result.n_recent_excl == 0
    assert result.total_unique_videos == 1
    assert [row.bucket for row in result.assignments] == [BUCKET_14D]
    assert result.assignments[0].decay_weight is None
    assert result.has_90d_200k_kill == 1
    assert result.decision == DECISION_REJECTED
    assert result.track_a_sweet_spot is False
    assert result.si_hard_kill is False
    _assert_exclusive(result)


def test_five_day_600k_from_injected_now_ms():
    video = CompetingVideo(
        "fresh-600k-clock",
        views=600_000,
        published_at_ms=NOW_MS - 5 * MS_PER_DAY,
    )
    result = _calc(video, now_ms=NOW_MS)

    assert result.si == 8
    assert result.n_14d_excl == 1
    assert result.n_mega_count == 0
    assert result.n_recent_excl == 0
    assert result.has_90d_200k_kill == 1
    assert result.decision == DECISION_REJECTED
    assert result.assignments[0].age_days == 5
    _assert_exclusive(result)


def test_five_day_400k_sets_90d_kill_and_is_only_14d():
    result = _calc(CompetingVideo("fresh-400k", views=400_000, age_days=5))

    assert result.si == 8
    assert 400_000 < 500_000
    assert result.n_14d_excl == 1
    assert result.n_mega_count == 0
    assert result.n_mega_decayed == 0
    assert result.n_recent_excl == 0
    assert [row.bucket for row in result.assignments] == [BUCKET_14D]
    assert result.has_90d_200k_kill == 1
    assert result.decision == DECISION_REJECTED
    assert result.track_a_sweet_spot is False
    _assert_exclusive(result)


def test_28_month_700k_decays_half_and_stays_in_sweet_spot():
    age_days = 28 * 30
    assert age_days == 840
    result = _calc(CompetingVideo("old-mega", views=700_000, age_days=age_days))

    assert result.n_mega_decayed == 0.5
    assert result.n_mega_count == 1
    assert result.n_14d_excl == 0
    assert result.n_recent_excl == 0
    assert result.si == 13
    assert result.si == _half_up_reference(25 * 0.5)
    assert result.si <= SI_SWEET_SPOT_MAX
    assert result.has_90d_200k_kill == 0
    assert result.si_hard_kill is False
    assert result.track_a_sweet_spot is True
    assert result.decision == DECISION_SWEET_SPOT
    assert result.assignments[0].bucket == BUCKET_MEGA
    assert result.assignments[0].decay_weight == 0.5
    _assert_exclusive(result)


def test_28_month_700k_from_injected_now_ms():
    age_days = 28 * MONTH_DAYS
    video = CompetingVideo(
        "old-mega-clock",
        views=700_000,
        published_at_ms=NOW_MS - age_days * MS_PER_DAY,
    )
    result = _calc(video, now_ms=NOW_MS)

    assert result.assignments[0].age_days == 840
    assert result.n_mega_decayed == 0.5
    assert result.si == 13
    assert result.has_90d_200k_kill == 0
    assert result.track_a_sweet_spot is True
    _assert_exclusive(result)


def test_zombie_supply_of_recent_videos_crosses_si_hard_kill():
    videos = [
        CompetingVideo(f"zombie-{index}", views=80_000, age_days=40)
        for index in range(5)
    ]
    result = _calc(*videos)

    assert result.n_recent_excl == 5
    assert result.n_14d_excl == 0
    assert result.n_mega_count == 0
    assert result.n_mega_decayed == 0
    assert result.si == 60
    assert result.si >= SI_HARD_KILL
    assert result.si_hard_kill is True
    assert result.has_90d_200k_kill == 0
    assert result.decision == DECISION_REJECTED
    assert result.track_a_sweet_spot is False
    assert {row.bucket for row in result.assignments} == {BUCKET_RECENT}
    _assert_exclusive(result)


def test_duplicate_video_id_is_not_counted_twice():
    first = CompetingVideo("same", views=600_000, age_days=5)
    replay = CompetingVideo("same", views=700_000, age_days=840)
    result = _calc(first, replay, first)

    assert result.total_unique_videos == 1
    assert result.n_14d_excl == 1
    assert result.n_mega_count == 0
    assert result.si == 8
    assert result.has_90d_200k_kill == 1
    assert [row.video_id for row in result.assignments] == ["same"]
    _assert_exclusive(result)


def test_mixed_case_keeps_buckets_disjoint_and_leaves_ancient_mega_out():
    result = _calc(
        CompetingVideo("fresh-small", views=100, age_days=5),
        CompetingVideo("decayed", views=700_000, age_days=840),
        CompetingVideo("mid", views=60_000, age_days=40),
        CompetingVideo("ancient", views=1_000_000, age_days=2000),
        CompetingVideo("fresh-small", views=999_999, age_days=1),
    )

    assert result.total_unique_videos == 4
    assert result.placed_video_count == 3
    assert result.n_14d_excl == 1
    assert result.n_mega_decayed == 0.5
    assert result.n_mega_count == 1
    assert result.n_recent_excl == 1
    assert result.si == 33
    assert result.has_90d_200k_kill == 0
    assert result.track_a_sweet_spot is True
    assert result.decision == DECISION_SWEET_SPOT
    by_id = {row.video_id: row.bucket for row in result.assignments}
    assert by_id == {
        "fresh-small": BUCKET_14D,
        "decayed": BUCKET_MEGA,
        "mid": BUCKET_RECENT,
    }
    assert "ancient" not in by_id
    _assert_exclusive(result)


def test_young_mega_is_not_also_recent():
    result = _calc(CompetingVideo("young-mega", views=700_000, age_days=100))

    assert result.n_mega_decayed == 1.0
    assert result.n_mega_count == 1
    assert result.n_recent_excl == 0
    assert result.n_14d_excl == 0
    assert result.si == 25
    assert result.has_90d_200k_kill == 0
    assert result.assignments[0].bucket == BUCKET_MEGA
    _assert_exclusive(result)


def test_tier1_giant_without_500k_enters_mega_only():
    result = _calc(
        CompetingVideo(
            "giant",
            views=1_000,
            age_days=200,
            is_tier1_giant=True,
        )
    )

    assert result.n_mega_decayed == 1.0
    assert result.n_mega_count == 1
    assert result.n_recent_excl == 0
    assert result.si == 25
    assert result.has_90d_200k_kill == 0
    assert result.assignments[0].bucket == BUCKET_MEGA
    _assert_exclusive(result)


def test_tier1_inside_14_days_stays_in_14d_only():
    result = _calc(
        CompetingVideo(
            "giant-yesterday",
            views=1_000,
            age_days=1,
            is_tier1_giant=True,
        )
    )

    assert result.n_14d_excl == 1
    assert result.n_mega_count == 0
    assert result.n_recent_excl == 0
    assert result.si == 8
    assert result.has_90d_200k_kill == 0
    assert result.decision == DECISION_SWEET_SPOT
    _assert_exclusive(result)


def test_view_thresholds_are_strictly_greater_than():
    at_kill = _calc(CompetingVideo("at-200k", views=200_000, age_days=5))
    assert at_kill.has_90d_200k_kill == 0
    assert at_kill.n_14d_excl == 1
    assert at_kill.si == 8
    assert at_kill.decision == DECISION_SWEET_SPOT

    over_kill = _calc(CompetingVideo("over-200k", views=200_001, age_days=5))
    assert over_kill.has_90d_200k_kill == 1
    assert over_kill.decision == DECISION_REJECTED

    at_mega = _calc(CompetingVideo("at-500k", views=500_000, age_days=100))
    assert at_mega.n_mega_count == 0
    assert at_mega.n_recent_excl == 1
    assert at_mega.si == 12
    assert at_mega.has_90d_200k_kill == 0

    over_mega = _calc(CompetingVideo("over-500k", views=500_001, age_days=100))
    assert over_mega.n_mega_decayed == 1.0
    assert over_mega.n_recent_excl == 0
    assert over_mega.si == 25

    at_recent = _calc(CompetingVideo("at-50k", views=50_000, age_days=100))
    assert at_recent.placed_video_count == 0
    assert at_recent.si == 0

    over_recent = _calc(CompetingVideo("over-50k", views=50_001, age_days=100))
    assert over_recent.n_recent_excl == 1
    assert over_recent.si == 12


def test_age_boundaries_for_14d_18_months_and_3_years():
    on_14 = _calc(CompetingVideo("day-14", views=600_000, age_days=14))
    assert on_14.n_14d_excl == 1
    assert on_14.n_mega_count == 0
    assert on_14.has_90d_200k_kill == 1
    assert on_14.si == 8

    day_15 = _calc(CompetingVideo("day-15", views=600_000, age_days=15))
    assert day_15.n_14d_excl == 0
    assert day_15.n_mega_decayed == 1.0
    assert day_15.n_recent_excl == 0
    assert day_15.has_90d_200k_kill == 1
    assert day_15.si == 25

    on_18_months = _calc(CompetingVideo("mo-18", views=700_000, age_days=540))
    assert on_18_months.n_mega_decayed == 1.0
    assert on_18_months.si == 25
    assert on_18_months.has_90d_200k_kill == 0

    just_over_18_months = _calc(
        CompetingVideo("mo-18-plus", views=700_000, age_days=541)
    )
    assert just_over_18_months.n_mega_decayed == 0.5
    assert just_over_18_months.n_recent_excl == 0
    assert just_over_18_months.si == 13

    on_3_years = _calc(CompetingVideo("yr-3", views=700_000, age_days=1080))
    assert on_3_years.n_mega_decayed == 0.5
    assert on_3_years.si == 13
    assert on_3_years.track_a_sweet_spot is True

    past_3_years = _calc(CompetingVideo("yr-3-plus", views=700_000, age_days=1081))
    assert past_3_years.placed_video_count == 0
    assert past_3_years.si == 0
    assert past_3_years.decision == DECISION_SWEET_SPOT

    on_90 = _calc(CompetingVideo("day-90", views=250_000, age_days=90))
    assert on_90.has_90d_200k_kill == 1
    assert on_90.n_recent_excl == 1
    assert on_90.n_mega_count == 0
    assert on_90.decision == DECISION_REJECTED

    day_91 = _calc(CompetingVideo("day-91", views=250_000, age_days=91))
    assert day_91.has_90d_200k_kill == 0
    assert day_91.n_recent_excl == 1
    assert day_91.si == 12
    assert day_91.decision == DECISION_SWEET_SPOT


def test_si_hard_kill_from_14d_weight_without_90d_kill():
    videos = [
        CompetingVideo(f"wave-{index}", views=1_000, age_days=5)
        for index in range(7)
    ]
    result = _calc(*videos)

    assert result.n_14d_excl == 7
    assert result.si == 56
    assert result.si_hard_kill is True
    assert result.has_90d_200k_kill == 0
    assert result.decision == DECISION_REJECTED
    _assert_exclusive(result)


def test_marginal_band_is_neither_sweet_spot_nor_hard_kill():
    videos = [
        CompetingVideo(f"mid-{index}", views=60_000, age_days=40)
        for index in range(4)
    ]
    result = _calc(*videos)

    assert result.si == 48
    assert SI_SWEET_SPOT_MAX < result.si < SI_HARD_KILL
    assert result.decision == DECISION_MARGINAL
    assert result.track_a_sweet_spot is False
    assert result.si_hard_kill is False
    assert result.has_90d_200k_kill == 0
    _assert_exclusive(result)


def test_si_caps_at_100():
    videos = [
        CompetingVideo(f"mega-{index}", views=600_000, age_days=100)
        for index in range(5)
    ]
    result = _calc(*videos)

    assert result.n_mega_decayed == 5.0
    assert result.n_recent_excl == 0
    assert result.si == 100
    assert result.has_90d_200k_kill == 0
    assert result.si_hard_kill is True
    assert result.decision == DECISION_REJECTED
    _assert_exclusive(result)


def test_empty_case_is_a_sweet_spot():
    result = _calc()

    assert result.si == 0
    assert result.total_unique_videos == 0
    assert result.placed_video_count == 0
    assert result.has_90d_200k_kill == 0
    assert result.track_a_sweet_spot is True
    assert result.decision == DECISION_SWEET_SPOT
    _assert_exclusive(result)


def test_published_at_without_now_ms_raises():
    video = CompetingVideo("needs-clock", views=10, published_at_ms=NOW_MS)
    with pytest.raises(ValueError, match="now_ms"):
        _calc(video)


def test_blank_video_id_raises():
    with pytest.raises(ValueError, match="video_id"):
        _calc(CompetingVideo("  ", views=10, age_days=1))


def test_age_days_wins_when_published_at_is_also_set():
    video = CompetingVideo(
        "explicit-age",
        views=700_000,
        age_days=840,
        published_at_ms=NOW_MS - 5 * MS_PER_DAY,
    )
    result = _calc(video, now_ms=NOW_MS)

    assert result.n_mega_decayed == 0.5
    assert result.n_14d_excl == 0
    assert result.si == 13
    assert result.has_90d_200k_kill == 0
