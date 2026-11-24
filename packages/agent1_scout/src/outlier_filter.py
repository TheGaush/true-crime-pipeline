"""Rolling 20-video median outlier-ratio filter for Track A scouting.

Baseline uses ``statistics.median`` on up to 20 prior long-form uploads per
channel. Mean is intentionally not used so legacy viral spikes do not inflate
the baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class ChannelVideo:
    """One channel upload used for baseline history or candidate scoring."""

    video_id: str
    channel_id: str
    views: int
    published_at_ms: int
    duration_sec: int

    @property
    def is_long_form(self) -> bool:
        return self.duration_sec >= OutlierRatioScorer.LONG_FORM_MIN_DURATION_SEC


@dataclass(frozen=True, slots=True)
class ScoredOutlierCandidate:
    """A video that passed sweet-spot gates and has a computed outlier ratio."""

    video_id: str
    channel_id: str
    views: int
    outlier_ratio: float
    baseline_median_views: float
    published_at_ms: int


class OutlierRatioScorer:
    """Score uploads as ``OR = views / channel_median`` and retain 15–20 hits."""

    ROLLING_MEDIAN_WINDOW = 20
    MIN_HISTORY_VIDEOS = 5
    MIN_OUTLIER_RATIO = 3.5
    MIN_VIEWS = 20_000
    TWELVE_MONTHS_MS = 12 * 30 * 24 * 60 * 60 * 1000
    LONG_FORM_MIN_DURATION_SEC = 600
    MAX_RETAIN = 20

    def score_candidates(
        self,
        videos: Sequence[ChannelVideo],
        *,
        now_ms: int,
    ) -> list[ScoredOutlierCandidate]:
        """Return up to 20 top outlier candidates across all channels."""
        by_channel: dict[str, list[ChannelVideo]] = {}
        for video in videos:
            by_channel.setdefault(video.channel_id, []).append(video)

        qualifiers: list[ScoredOutlierCandidate] = []
        for channel_videos in by_channel.values():
            qualifiers.extend(
                self._score_channel(channel_videos, now_ms=now_ms),
            )

        qualifiers.sort(key=lambda row: row.outlier_ratio, reverse=True)
        return qualifiers[: self.MAX_RETAIN]

    def _score_channel(
        self,
        videos: Sequence[ChannelVideo],
        *,
        now_ms: int,
    ) -> list[ScoredOutlierCandidate]:
        ordered = sorted(videos, key=lambda v: v.published_at_ms)
        prior_long_form: list[ChannelVideo] = []
        hits: list[ScoredOutlierCandidate] = []

        for current in ordered:
            if not current.is_long_form:
                continue

            window = prior_long_form[-self.ROLLING_MEDIAN_WINDOW :]
            prior_long_form.append(current)

            if not self._passes_freshness(current, now_ms=now_ms):
                continue
            if current.views < self.MIN_VIEWS:
                continue
            if len(window) < self.MIN_HISTORY_VIDEOS:
                continue

            baseline = float(median(v.views for v in window))
            if baseline <= 0:
                continue

            outlier_ratio = current.views / baseline
            if outlier_ratio < self.MIN_OUTLIER_RATIO:
                continue

            hits.append(
                ScoredOutlierCandidate(
                    video_id=current.video_id,
                    channel_id=current.channel_id,
                    views=current.views,
                    outlier_ratio=outlier_ratio,
                    baseline_median_views=baseline,
                    published_at_ms=current.published_at_ms,
                ),
            )

        return hits

    def _passes_freshness(self, video: ChannelVideo, *, now_ms: int) -> bool:
        age_ms = now_ms - video.published_at_ms
        return 0 <= age_ms <= self.TWELVE_MONTHS_MS


def channel_median_for_test(
    prior_view_counts: Iterable[int],
) -> float:
    """Test helper: median of prior views (explicitly not mean)."""
    values = list(prior_view_counts)
    return float(median(values))