"""Offline unit tests for OutlierRatioScorer."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outlier_filter import (  # noqa: E402
    ChannelVideo,
    OutlierRatioScorer,
    channel_median_for_test,
)

NOW_MS = 1_700_000_000_000
DAY_MS = 24 * 60 * 60 * 1000
LONG = OutlierRatioScorer.LONG_FORM_MIN_DURATION_SEC
SHORT = 59


def v(
    video_id: str,
    channel_id: str = "ch",
    views: int = 10_000,
    *,
    age_days: int = 30,
    duration_sec: int = LONG,
) -> ChannelVideo:
    return ChannelVideo(
        video_id=video_id,
        channel_id=channel_id,
        views=views,
        published_at_ms=NOW_MS - age_days * DAY_MS,
        duration_sec=duration_sec,
    )


def baseline_history(n: int, views: int = 10_000, *, channel_id: str = "ch") -> list[ChannelVideo]:
    """``n`` long-form uploads older than any candidate under test."""
    rows: list[ChannelVideo] = []
    for i in range(n):
        rows.append(
            ChannelVideo(
                video_id=f"hist-{i}",
                channel_id=channel_id,
                views=views,
                published_at_ms=NOW_MS - (400 - i) * DAY_MS,
                duration_sec=LONG,
            )
        )
    return rows


class TestMinimumHistory:
    def test_two_video_channel_produces_no_candidate(self) -> None:
        scorer = OutlierRatioScorer()
        videos = [
            v("a", views=100_000, age_days=60),
            v("b", views=100_000, age_days=10),
        ]
        assert scorer.score_candidates(videos, now_ms=NOW_MS) == []

    def test_four_prior_long_form_insufficient(self) -> None:
        scorer = OutlierRatioScorer()
        videos = baseline_history(4) + [v("target", views=100_000, age_days=5)]
        assert scorer.score_candidates(videos, now_ms=NOW_MS) == []


class TestSweetSpotGates:
    def test_rejects_shorts(self) -> None:
        scorer = OutlierRatioScorer()
        videos = baseline_history(5) + [
            v("short-hit", views=1_000_000, age_days=1, duration_sec=SHORT),
        ]
        assert scorer.score_candidates(videos, now_ms=NOW_MS) == []

    def test_rejects_low_views(self) -> None:
        scorer = OutlierRatioScorer()
        videos = baseline_history(5, views=1_000) + [
            v("low", views=19_999, age_days=1),
        ]
        assert scorer.score_candidates(videos, now_ms=NOW_MS) == []

    def test_rejects_stale_upload(self) -> None:
        scorer = OutlierRatioScorer()
        videos = baseline_history(5) + [v("old", views=200_000, age_days=400)]
        assert scorer.score_candidates(videos, now_ms=NOW_MS) == []

    def test_rejects_or_below_threshold(self) -> None:
        scorer = OutlierRatioScorer()
        videos = baseline_history(5, views=10_000) + [
            v("weak", views=34_999, age_days=2),
        ]
        assert scorer.score_candidates(videos, now_ms=NOW_MS) == []

    def test_accepts_or_at_threshold(self) -> None:
        scorer = OutlierRatioScorer()
        videos = baseline_history(5, views=10_000) + [
            v("edge", views=35_000, age_days=2),
        ]
        hits = scorer.score_candidates(videos, now_ms=NOW_MS)
        assert len(hits) == 1
        assert hits[0].video_id == "edge"
        assert hits[0].outlier_ratio == pytest.approx(3.5)
        assert hits[0].baseline_median_views == pytest.approx(10_000.0)


class TestMedianSkewImmunity:
    def test_legacy_viral_does_not_inflate_median_like_mean_would(self) -> None:
        """One 10M-view legacy upload must not lift the baseline the way a mean would."""
        base_views = 10_000
        history_views = [base_views] * 9 + [10_000_000]
        med = channel_median_for_test(history_views)
        mean = sum(history_views) / len(history_views)
        assert med == pytest.approx(base_views)
        assert mean > 900_000

        scorer = OutlierRatioScorer()
        history = []
        for i, views in enumerate(history_views):
            history.append(
                ChannelVideo(
                    video_id=f"h{i}",
                    channel_id="skew",
                    views=views,
                    published_at_ms=NOW_MS - (500 - i) * DAY_MS,
                    duration_sec=LONG,
                )
            )
        candidate_views = 35_000
        candidate = v("outlier", channel_id="skew", views=candidate_views, age_days=1)
        hits = scorer.score_candidates(history + [candidate], now_ms=NOW_MS)

        assert len(hits) == 1
        assert hits[0].baseline_median_views == pytest.approx(base_views)
        assert hits[0].outlier_ratio == pytest.approx(candidate_views / base_views)

        mean_baseline = mean
        assert candidate_views / mean_baseline < OutlierRatioScorer.MIN_OUTLIER_RATIO


class TestRetentionBounds:
    def test_returns_all_when_fewer_than_fifteen_qualify(self) -> None:
        scorer = OutlierRatioScorer()
        videos: list[ChannelVideo] = []
        for ch in range(10):
            videos.extend(baseline_history(5, views=5_000, channel_id=f"c{ch}"))
            videos.append(
                v(f"hit-{ch}", channel_id=f"c{ch}", views=20_000, age_days=3),
            )
        hits = scorer.score_candidates(videos, now_ms=NOW_MS)
        assert len(hits) == 10

    def test_returns_all_when_between_fifteen_and_twenty(self) -> None:
        scorer = OutlierRatioScorer()
        videos: list[ChannelVideo] = []
        for ch in range(17):
            videos.extend(baseline_history(5, views=4_000, channel_id=f"b{ch}"))
            videos.append(
                v(f"ok-{ch}", channel_id=f"b{ch}", views=20_000, age_days=4),
            )
        hits = scorer.score_candidates(videos, now_ms=NOW_MS)
        assert len(hits) == 17

    def test_caps_at_twenty_when_more_qualify(self) -> None:
        scorer = OutlierRatioScorer()
        videos: list[ChannelVideo] = []
        for ch in range(25):
            videos.extend(baseline_history(5, views=3_000, channel_id=f"d{ch}"))
            views = 20_000 + ch * 1_000
            videos.append(
                v(f"top-{ch}", channel_id=f"d{ch}", views=views, age_days=2),
            )
        hits = scorer.score_candidates(videos, now_ms=NOW_MS)
        assert len(hits) == 20
        ratios = [h.outlier_ratio for h in hits]
        assert ratios == sorted(ratios, reverse=True)


class TestRollingWindow:
    def test_uses_only_last_twenty_prior_long_form(self) -> None:
        scorer = OutlierRatioScorer()
        videos: list[ChannelVideo] = []
        for i in range(15):
            videos.append(
                ChannelVideo(
                    video_id=f"old-{i}",
                    channel_id="roll",
                    views=1_000,
                    published_at_ms=NOW_MS - (700 - i) * DAY_MS,
                    duration_sec=LONG,
                )
            )
        for i in range(20):
            videos.append(
                ChannelVideo(
                    video_id=f"recent-{i}",
                    channel_id="roll",
                    views=10_000,
                    published_at_ms=NOW_MS - (500 - i) * DAY_MS,
                    duration_sec=LONG,
                )
            )
        candidate = v("winner", channel_id="roll", views=40_000, age_days=1)
        hits = scorer.score_candidates(videos + [candidate], now_ms=NOW_MS)
        assert len(hits) == 1
        assert hits[0].baseline_median_views == pytest.approx(10_000.0)