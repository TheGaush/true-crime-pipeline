"""Offline tests for AliasDedupSearchRunner.

No live YouTube calls. search.list and videos.list are injected. The recorded
payload lives under this test folder because fixtures/recorded_apis/ is not
on the task branch.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from search_runner import (  # noqa: E402
    SEARCH_LIST_QUOTA_UNITS,
    SPILLOVER_DISCOVERED_VIA,
    VIDEOS_LIST_BATCH_SIZE,
    YT_SEARCH_CALL_RESERVE,
    AliasDedupSearchRunner,
    OutlierCandidate,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "recorded_apis"
    / "yt_search_aliases.json"
)

ALIASES = (
    "Mara Ellison 2018",
    "Mara Ellison homicide",
    "Riverside Jane Doe",
    "copper-green fiber under fingernail",
)
KNOWN = frozenset({"UC_known_watchlist"})
SHARED_VIDEO = "yt_shared_all4"


class RecordedLists:
    """Replay yt_search_aliases.json. Raises if a query was not recorded."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.queries: list[str] = []
        self.batches: list[list[str]] = []

    def search_list(self, query: str) -> dict:
        self.queries.append(query)
        try:
            return self.payload["search_list"][query]
        except KeyError as exc:
            raise AssertionError(f"unexpected search.list query: {query}") from exc

    def videos_list(self, video_ids) -> dict:
        ids = list(video_ids)
        self.batches.append(ids)
        catalog = self.payload["videos_list"]
        return {
            "kind": "youtube#videoListResponse",
            "items": [catalog[video_id] for video_id in ids],
        }


class CountingLists:
    def __init__(self, videos_per_query: int = 1) -> None:
        self.videos_per_query = videos_per_query
        self.queries: list[str] = []
        self.batches: list[list[str]] = []

    def search_list(self, query: str) -> dict:
        self.queries.append(query)
        items = []
        for offset in range(self.videos_per_query):
            video_id = f"vid-{len(self.queries) - 1}-{offset}"
            items.append(
                {
                    "id": {"kind": "youtube#video", "videoId": video_id},
                    "snippet": {
                        "channelId": f"UC-{video_id}",
                        "title": video_id,
                    },
                }
            )
        return {"items": items}

    def videos_list(self, video_ids) -> dict:
        ids = list(video_ids)
        self.batches.append(ids)
        return {
            "items": [
                {
                    "id": video_id,
                    "snippet": {"channelId": f"UC-{video_id}", "title": video_id},
                    "statistics": {"viewCount": "30000", "subscriberCount": "5000"},
                }
                for video_id in ids
            ]
        }


class RaisingLists:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_list(self, query: str) -> dict:
        self.calls.append(f"search:{query}")
        raise AssertionError("search.list must not be called when the reserve is held")

    def videos_list(self, video_ids) -> dict:
        self.calls.append("videos")
        raise AssertionError("videos.list must not be called when the reserve is held")


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _recorded_runner() -> tuple[AliasDedupSearchRunner, RecordedLists]:
    client = RecordedLists(_load_fixture())
    return AliasDedupSearchRunner(client.search_list, client.videos_list), client


def _shortlist() -> list[dict[str, object]]:
    return [{"candidate_id": "outlier-riverside", "aliases": ALIASES}]


def test_fixture_file_is_under_the_test_folder() -> None:
    assert FIXTURE.is_file()
    assert "tests" in FIXTURE.parts
    assert FIXTURE.name == "yt_search_aliases.json"


def test_union_stores_a_video_from_all_four_aliases_once() -> None:
    runner, client = _recorded_runner()
    result = runner.run(
        _shortlist(),
        search_units_remaining=YT_SEARCH_CALL_RESERVE + len(ALIASES),
        known_channel_ids=KNOWN,
    )

    assert result.reserve_held is False
    assert result.search_calls == 4
    assert client.queries == list(ALIASES)
    assert result.real_api_search_quota_units == 4 * SEARCH_LIST_QUOTA_UNITS
    assert result.call_budget_before == 19
    assert result.call_budget_after == YT_SEARCH_CALL_RESERVE
    assert result.call_budget_after != result.call_budget_before - result.real_api_search_quota_units

    ids = [video.video_id for video in result.videos]
    assert len(ids) == len(set(ids))
    assert ids.count(SHARED_VIDEO) == 1
    shared = next(video for video in result.videos if video.video_id == SHARED_VIDEO)
    assert shared.alias_queries == ALIASES
    assert shared.channel_id == "UC_known_watchlist"
    assert shared.view_count == 88_000

    flat = [video_id for batch in client.batches for video_id in batch]
    assert flat.count(SHARED_VIDEO) == 1
    assert flat == ids
    assert result.videos_list_calls == 1
    assert all(len(batch) <= VIDEOS_LIST_BATCH_SIZE for batch in client.batches)


def test_spillover_keeps_unknown_channels_inside_2k_to_120k() -> None:
    runner, _client = _recorded_runner()
    result = runner.run(
        _shortlist(),
        search_units_remaining=19,
        known_channel_ids=KNOWN,
    )

    spillover = {item.channel_id: item for item in result.spillover_candidates}
    assert list(spillover) == ["UC_spill_mid", "UC_spill_floor", "UC_spill_ceil"]
    assert spillover["UC_spill_mid"].subscriber_count == 24_000
    assert spillover["UC_spill_mid"].source_video_ids == ("yt_spill_mid", "yt_spill_mid_2")
    assert spillover["UC_spill_floor"].subscriber_count == 2_000
    assert spillover["UC_spill_ceil"].subscriber_count == 120_000
    assert all(item.discovered_via == SPILLOVER_DISCOVERED_VIA for item in result.spillover_candidates)

    rejected = {
        "UC_known_watchlist",
        "UC_too_small",
        "UC_too_big",
        "UC_hidden",
        "UC_playlist_owner",
        "UC_search_channel_hit",
    }
    assert rejected.isdisjoint(spillover)

    without_known = runner.run(
        _shortlist(),
        search_units_remaining=19,
        known_channel_ids=(),
    )
    assert "UC_known_watchlist" in {item.channel_id for item in without_known.spillover_candidates}


@pytest.mark.parametrize("remaining", [0, 1, 14, 15])
def test_reserve_floor_runs_zero_searches(remaining: int) -> None:
    client = RaisingLists()
    runner = AliasDedupSearchRunner(client.search_list, client.videos_list)
    result = runner.run(
        _shortlist(),
        search_units_remaining=remaining,
        known_channel_ids=KNOWN,
    )

    assert result.reserve_held is True
    assert result.search_calls == 0
    assert result.videos_list_calls == 0
    assert result.videos == ()
    assert result.spillover_candidates == ()
    assert result.alias_queries_run == ()
    assert result.alias_queries_skipped == ALIASES
    assert result.call_budget_before == remaining
    assert result.call_budget_after == remaining
    assert result.real_api_search_quota_units == 0
    assert client.calls == []


def test_one_call_above_the_floor_spends_one_search() -> None:
    runner, client = _recorded_runner()
    result = runner.run(
        _shortlist(),
        search_units_remaining=YT_SEARCH_CALL_RESERVE + 1,
        known_channel_ids=KNOWN,
    )

    assert result.reserve_held is False
    assert result.search_calls == 1
    assert result.videos_list_calls == 1
    assert client.queries == ["Mara Ellison 2018"]
    assert [video.video_id for video in result.videos] == ["yt_shared_all4", "yt_spill_mid"]
    assert result.call_budget_after == YT_SEARCH_CALL_RESERVE
    assert result.real_api_search_quota_units == SEARCH_LIST_QUOTA_UNITS
    assert [item.channel_id for item in result.spillover_candidates] == ["UC_spill_mid"]


def test_never_more_than_20_searches_per_run() -> None:
    client = CountingLists()
    runner = AliasDedupSearchRunner(client.search_list, client.videos_list)
    aliases = [f"alias-{index}" for index in range(25)]
    result = runner.run(
        [{"candidate_id": "only", "aliases": aliases}],
        search_units_remaining=1_000,
    )

    assert result.search_calls == 20
    assert result.alias_queries_run == tuple(aliases[:20])
    assert result.alias_queries_skipped == tuple(aliases[20:])
    assert client.queries == aliases[:20]
    assert result.call_budget_after == 1_000 - 20
    assert result.call_budget_after >= YT_SEARCH_CALL_RESERVE
    assert result.real_api_search_quota_units == 20 * SEARCH_LIST_QUOTA_UNITS


def test_only_the_first_20_candidates_are_searched() -> None:
    client = CountingLists()
    runner = AliasDedupSearchRunner(client.search_list, client.videos_list)
    candidates = [
        {"candidate_id": f"c{index}", "aliases": [f"query-{index}"]}
        for index in range(25)
    ]
    result = runner.run(candidates, search_units_remaining=1_000)

    assert result.candidates_considered == 20
    assert result.candidates_skipped == 5
    assert result.search_calls == 20
    assert result.alias_queries_run == tuple(f"query-{index}" for index in range(20))
    assert "query-20" not in result.alias_queries_run
    assert "query-24" not in client.queries


def test_duplicate_alias_query_is_a_single_search_call() -> None:
    client = CountingLists()
    runner = AliasDedupSearchRunner(client.search_list, client.videos_list)
    result = runner.run(
        [
            OutlierCandidate("a", ("Same Query", "Same Query")),
            {"candidate_id": "b", "aliases": ["  Same   Query  "]},
        ],
        search_units_remaining=40,
    )

    assert result.search_calls == 1
    assert client.queries == ["Same Query"]
    assert result.videos[0].alias_queries == ("Same Query",)


@pytest.mark.parametrize(
    ("count", "expected_lengths"),
    [(1, [1]), (50, [50]), (51, [50, 1]), (100, [50, 50])],
)
def test_videos_list_batches_unique_ids_by_50(count: int, expected_lengths: list[int]) -> None:
    client = CountingLists(videos_per_query=count)
    runner = AliasDedupSearchRunner(client.search_list, client.videos_list)
    result = runner.run(
        [{"candidate_id": "batch", "aliases": ["one-query"]}],
        search_units_remaining=16,
    )

    assert result.search_calls == 1
    assert [len(batch) for batch in client.batches] == expected_lengths
    assert result.videos_list_calls == len(expected_lengths)
    assert all(len(batch) <= VIDEOS_LIST_BATCH_SIZE for batch in client.batches)
    ids = [video.video_id for video in result.videos]
    assert len(ids) == count
    assert len(ids) == len(set(ids))


def test_empty_shortlist_with_budget_is_not_reserve_held() -> None:
    client = RaisingLists()
    runner = AliasDedupSearchRunner(client.search_list, client.videos_list)
    result = runner.run([], search_units_remaining=40)

    assert result.reserve_held is False
    assert result.search_calls == 0
    assert result.videos_list_calls == 0
    assert client.calls == []


def test_search_units_remaining_rejects_bool_and_negative() -> None:
    runner, _client = _recorded_runner()
    with pytest.raises(TypeError):
        runner.run(_shortlist(), search_units_remaining=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        runner.run(_shortlist(), search_units_remaining=-1)


def test_runner_source_does_not_import_an_http_client() -> None:
    source = (SRC / "search_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {
        "socket",
        "urllib",
        "requests",
        "httpx",
        "httplib",
        "http",
        "googleapiclient",
        "aiohttp",
        "sqlite3",
    }
    assert imported.isdisjoint(forbidden)
    assert "googleapis.com" not in source
    assert "search.list" in source
    assert "100" in source
