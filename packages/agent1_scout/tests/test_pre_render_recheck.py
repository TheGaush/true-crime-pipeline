"""Offline pre-render re-check: Day 1 abort, Day 2 abort, sunk-cost finish.

The search client is a fake. No socket is opened. Each check is three
``search.list`` calls taken from the 15-call reserve.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent1_scout.pre_render_recheck import (
    ABORTED_COPYCAT_WAVE,
    DAILY_RECHECK_RESERVE,
    DECISION_FINISH,
    MOMENT_BATCH_DESK_DAY,
    MOMENT_BEFORE_FLOW_SPEND,
    SEARCH_LIST_CALLS_PER_CHECK,
    BoundedSearchListClient,
    PreRenderSaturationGate,
    RecheckCallLimitExceeded,
    SearchReserveExhausted,
)

DAY_MS = 24 * 60 * 60 * 1000
NOW_MS = 1_763_904_000_000

QUERIES = (
    "case alias suspect year",
    "case alias victim crime",
    "case alias city nickname",
)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _item(
    video_id: str,
    *,
    days_ago: int,
    views: int,
    channel_title: str,
    channel_id: str,
) -> dict:
    published_ms = NOW_MS - days_ago * DAY_MS
    return {
        "id": {"kind": "youtube#video", "videoId": video_id},
        "snippet": {
            "publishedAt": _iso(published_ms),
            "channelId": channel_id,
            "channelTitle": channel_title,
            "title": video_id,
        },
        "statistics": {"viewCount": str(views)},
    }


def _small(video_id: str, *, days_ago: int, views: int) -> dict:
    return _item(
        video_id,
        days_ago=days_ago,
        views=views,
        channel_title=f"County File {video_id}",
        channel_id=f"UC-small-{video_id}",
    )


class FakeSearchClient:
    """Replay one page of items per query. Records every ``search.list`` call."""

    def __init__(self, pages: dict[str, list]) -> None:
        self.pages = pages
        self.queries: list[str] = []

    def search_list(self, query: str) -> dict:
        self.queries.append(query)
        try:
            items = self.pages[query]
        except KeyError as exc:
            raise AssertionError(f"unexpected search.list query: {query}") from exc
        return {"kind": "youtube#searchListResponse", "items": items}


def test_day1_aborts_before_flow_spend() -> None:
    """Four recent copycats and nothing spent: abort before Flow."""

    pages = {
        QUERIES[0]: [
            _small("d1-a", days_ago=1, views=11_000),
            _small("d1-b", days_ago=2, views=8_400),
        ],
        QUERIES[1]: [_small("d1-c", days_ago=4, views=6_200)],
        QUERIES[2]: [_small("d1-d", days_ago=6, views=9_900)],
    }
    client = FakeSearchClient(pages)
    gate = PreRenderSaturationGate(client)

    result = gate.before_flow_spend(queries=QUERIES, now_ms=NOW_MS)

    assert result.moment == MOMENT_BEFORE_FLOW_SPEND
    assert result.batch_day == 1
    assert result.decision == ABORTED_COPYCAT_WAVE
    assert result.episode_state == ABORTED_COPYCAT_WAVE
    assert result.aborted == 1
    assert result.sunk_cost_override == 0
    assert result.n_14d_wave == 4
    assert result.has_90d_200k_kill == 0
    assert result.tier1_giant_hit == 0
    assert result.spent_credits_pct == 0.0
    assert result.search_list_calls == SEARCH_LIST_CALLS_PER_CHECK
    assert result.reserve_drawn == 3
    assert result.reserve_remaining == DAILY_RECHECK_RESERVE - 3
    assert client.queries == list(QUERIES)
    assert gate.reserve_remaining == 12


def test_day2_aborts_large_wave_at_twenty_percent_spent() -> None:
    """A 6-video wave on Batch Desk day 2 at 20% spent aborts the rest."""

    pages = {
        QUERIES[0]: [
            _small("d2-a", days_ago=1, views=18_000),
            _small("d2-b", days_ago=2, views=22_000),
        ],
        QUERIES[1]: [
            _small("d2-c", days_ago=3, views=14_500),
            _small("d2-d", days_ago=3, views=19_200),
        ],
        QUERIES[2]: [
            _small("d2-e", days_ago=5, views=7_700),
            _small("d2-f", days_ago=8, views=12_400),
        ],
    }
    client = FakeSearchClient(pages)
    gate = PreRenderSaturationGate(client)

    result = gate.before_batch_desk_day(
        2,
        queries=QUERIES,
        spent_credits_pct=0.20,
        now_ms=NOW_MS,
    )

    assert result.moment == MOMENT_BATCH_DESK_DAY
    assert result.batch_day == 2
    assert result.decision == ABORTED_COPYCAT_WAVE
    assert result.episode_state == ABORTED_COPYCAT_WAVE
    assert result.aborted == 1
    assert result.sunk_cost_override == 0
    assert result.n_14d_wave == 6
    assert result.n_14d_wave > 5
    assert result.has_90d_200k_kill == 0
    assert result.tier1_giant_hit == 0
    assert result.spent_credits_pct == 0.20
    assert result.search_list_calls == 3
    assert client.queries == list(QUERIES)
    assert gate.reserve_remaining == 12


def test_finishes_at_seventy_five_percent_with_four_small_copycats() -> None:
    """75% spent and four small copycats: sunk-cost override finishes the episode.

    One video id is repeated across two queries and still counts once.
    """

    shared = _small("copy-a", days_ago=2, views=4_200)
    pages = {
        QUERIES[0]: [shared, _small("copy-b", days_ago=3, views=8_800)],
        QUERIES[1]: [_small("copy-c", days_ago=5, views=15_000)],
        QUERIES[2]: [shared, _small("copy-d", days_ago=9, views=21_000)],
    }
    client = FakeSearchClient(pages)
    gate = PreRenderSaturationGate(client)

    result = gate.before_batch_desk_day(
        3,
        queries=QUERIES,
        spent_credits_pct=0.75,
        now_ms=NOW_MS,
    )

    assert result.moment == MOMENT_BATCH_DESK_DAY
    assert result.batch_day == 3
    assert result.decision == DECISION_FINISH
    assert result.episode_state is None
    assert result.aborted == 0
    assert result.sunk_cost_override == 1
    assert result.n_14d_wave == 4
    assert result.has_90d_200k_kill == 0
    assert result.tier1_giant_hit == 0
    assert result.spent_credits_pct == 0.75
    assert result.search_list_calls == 3
    assert result.reserve_drawn == 3
    assert result.reserve_remaining == 12
    assert client.queries == list(QUERIES)


def test_fourth_search_list_call_in_one_check_is_refused() -> None:
    client = FakeSearchClient({query: [] for query in QUERIES})
    bounded = BoundedSearchListClient(client)
    for query in QUERIES:
        bounded.search_list(query)
    with pytest.raises(RecheckCallLimitExceeded):
        bounded.search_list("fourth alias")
    assert client.queries == list(QUERIES)

    gate = PreRenderSaturationGate(FakeSearchClient({query: [] for query in (*QUERIES, "extra")}))
    with pytest.raises(RecheckCallLimitExceeded):
        gate.before_flow_spend(
            queries=(*QUERIES, "extra alias"),
            now_ms=NOW_MS,
        )
    assert gate.reserve_remaining == DAILY_RECHECK_RESERVE


def test_tier1_giant_blocks_sunk_cost_override() -> None:
    """75% spent and a wave of 4 still aborts when one hit is a Tier-1 giant."""

    giant = _item(
        "dateline-hit",
        days_ago=1,
        views=30_000,
        channel_title="Dateline",
        channel_id="UCDatelineFixture01",
    )
    pages = {
        QUERIES[0]: [giant, _small("g-b", days_ago=2, views=5_000)],
        QUERIES[1]: [_small("g-c", days_ago=3, views=6_000)],
        QUERIES[2]: [_small("g-d", days_ago=4, views=7_000)],
    }
    gate = PreRenderSaturationGate(FakeSearchClient(pages))

    result = gate.before_batch_desk_day(
        2,
        queries=QUERIES,
        spent_credits_pct=0.75,
        now_ms=NOW_MS,
    )

    assert result.n_14d_wave == 4
    assert result.tier1_giant_hit == 1
    assert result.has_90d_200k_kill == 0
    assert result.sunk_cost_override == 0
    assert result.decision == ABORTED_COPYCAT_WAVE


def test_reserve_funds_five_checks_and_refuses_the_sixth() -> None:
    def client() -> FakeSearchClient:
        return FakeSearchClient({query: [] for query in QUERIES})

    gate = PreRenderSaturationGate(client())
    gate.before_flow_spend(queries=QUERIES, now_ms=NOW_MS)
    for day in (2, 3, 4, 5):
        gate.before_batch_desk_day(
            day,
            queries=QUERIES,
            spent_credits_pct=0.0,
            now_ms=NOW_MS,
        )
    assert gate.reserve_remaining == 0

    with pytest.raises(SearchReserveExhausted):
        gate.before_batch_desk_day(
            6,
            queries=QUERIES,
            spent_credits_pct=0.0,
            now_ms=NOW_MS,
        )
    assert gate.reserve_remaining == 0
