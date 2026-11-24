"""Offline tests for the Tier-1 giant channel matcher."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agent1_scout.tier1_giants import (  # noqa: E402
    BUCKET_14D,
    BUCKET_MEGA,
    BUCKET_NONE,
    DAYS_14,
    MS_PER_DAY,
    GiantVideo,
    Tier1GiantMatcher,
    normalize_title,
)

NOW_MS = 1_700_000_000_000
DAY_MS = MS_PER_DAY


def _video(
    *,
    channel_id: str = "",
    channel_title: str = "",
    published_at_ms: int | None = None,
    age_days: float = 30,
) -> GiantVideo:
    if published_at_ms is None:
        published_at_ms = NOW_MS - int(age_days * DAY_MS)
    return GiantVideo(
        channel_id=channel_id,
        channel_title=channel_title,
        published_at_ms=published_at_ms,
    )


@pytest.fixture(scope="module")
def matcher() -> Tier1GiantMatcher:
    return Tier1GiantMatcher()


def test_normalize_title_strips_case_and_punctuation():
    assert normalize_title("  Law&Crime  ") == "lawcrime"
    assert normalize_title("20/20") == "2020"
    assert normalize_title("That Chapter!!!") == "that chapter"


def test_match_by_channel_id(matcher: Tier1GiantMatcher):
    video = _video(channel_id="UCjcsTier1Fixture01", channel_title="unknown")
    result = matcher.classify(video, NOW_MS)
    assert result.is_tier1_giant
    assert result.matched_giant_key == "jcs"
    assert result.bucket == BUCKET_MEGA


def test_match_by_normalized_title(matcher: Tier1GiantMatcher):
    video = _video(channel_title="  THAT   CHAPTER!! ")
    result = matcher.classify(video, NOW_MS)
    assert result.matched_giant_key == "that_chapter"
    assert result.bucket == BUCKET_MEGA


def test_fresh_tier1_giant_is_14d_with_instant_kill(matcher: Tier1GiantMatcher):
    video = _video(channel_id="UCewuTier1Fixture01", age_days=1)
    result = matcher.classify(video, NOW_MS)
    assert result.bucket == BUCKET_14D
    assert result.instant_kill is True
    assert result.bucket != BUCKET_MEGA


def test_14_day_boundary_inclusive(matcher: Tier1GiantMatcher):
    video = _video(channel_id="UCDatelineFixture01", age_days=DAYS_14)
    result = matcher.classify(video, NOW_MS)
    assert result.bucket == BUCKET_14D
    assert result.instant_kill is True


def test_older_tier1_giant_is_mega_without_instant_kill(matcher: Tier1GiantMatcher):
    video = _video(channel_id="UC48HoursFixture01", age_days=DAYS_14 + 1)
    result = matcher.classify(video, NOW_MS)
    assert result.bucket == BUCKET_MEGA
    assert result.instant_kill is False


def test_non_match_returns_none_bucket(matcher: Tier1GiantMatcher):
    video = _video(channel_id="UC_small_creator", channel_title="Random Docs")
    result = matcher.classify(video, NOW_MS)
    assert result.is_tier1_giant is False
    assert result.bucket == BUCKET_NONE
    assert result.instant_kill is False


def test_extra_yaml_adds_giant(tmp_path: Path):
    extra = tmp_path / "extra_giants.yaml"
    extra.write_text(
        """
giants:
  - key: indie_network
    titles:
      - Custom Giant Network
    channel_ids:
      - UCcustomGiant99
""",
        encoding="utf-8",
    )
    matcher = Tier1GiantMatcher(extra_yaml_path=extra)
    video = _video(channel_id="UCcustomGiant99", age_days=2)
    result = matcher.classify(video, NOW_MS)
    assert result.matched_giant_key == "indie_network"
    assert result.bucket == BUCKET_14D


def test_default_registry_includes_all_seven_giants(matcher: Tier1GiantMatcher):
    expected = {
        "ewu",
        "jcs",
        "that_chapter",
        "cbs_48_hours",
        "dateline",
        "abc_2020",
        "law_and_crime",
    }
    assert set(matcher.giant_keys) == expected


def test_law_and_crime_title_alias(matcher: Tier1GiantMatcher):
    video = _video(channel_title="Law & Crime Network", age_days=60)
    result = matcher.classify(video, NOW_MS)
    assert result.matched_giant_key == "law_and_crime"
    assert result.bucket == BUCKET_MEGA