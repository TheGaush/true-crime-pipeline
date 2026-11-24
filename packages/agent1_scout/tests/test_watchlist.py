"""Offline tests for WatchlistManager."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from agent1_scout.watchlist import (
    YT_TTL_MS,
    DORMANT_MS,
    MIN_CRIME_LONG_FORM_IN_LAST_10,
    SUBSCRIBER_COUNT_MAX,
    SUBSCRIBER_COUNT_MIN,
    SearchListForbiddenError,
    WatchlistManager,
    channel_to_uploads_playlist_id,
)

NOW_MS = 1_700_000_000_000


def _channel_item(
    channel_id: str,
    *,
    subs: int,
    title: str = "Cold Case Files",
    description: str = "True crime documentary channel",
    topic_ids: tuple[str, ...] = (),
    hidden_subs: bool = False,
) -> dict:
    stats: dict = {"hiddenSubscriberCount": hidden_subs}
    if not hidden_subs:
        stats["subscriberCount"] = str(subs)
    topic_block: dict = {}
    if topic_ids:
        topic_block["topicDetails"] = {"topicIds": list(topic_ids)}
    return {
        "id": channel_id,
        "snippet": {"title": title, "description": description},
        "statistics": stats,
        **topic_block,
    }


def test_uc_to_uu_mapping() -> None:
    assert channel_to_uploads_playlist_id("UCabc123") == "UUabc123"


def test_seed_uses_channels_list_only_batches_fifty() -> None:
    seed_ids = [f"UC{i:020d}" for i in range(51)]
    calls: list[list[str]] = []

    def channels_list(*, id: str, **_kwargs):  # noqa: A002
        batch = id.split(",")
        calls.append(batch)
        items = [
            _channel_item(cid, subs=10_000, topic_ids=("/m/0jm_",))
            for cid in batch
        ]
        return {"items": items}

    manager = WatchlistManager(now_ms=NOW_MS, channels_list=channels_list)
    result = manager.seed(seed_ids)

    assert result.ledger.search_list_calls == 0
    assert result.ledger.channels_list_calls == 2
    assert len(result.admitted) == 51
    assert len(calls[0]) == 50
    assert len(calls[1]) == 1
    row = result.admitted[0]
    assert row.uploads_playlist_id == channel_to_uploads_playlist_id(row.channel_id)
    assert row.discovered_via == "SEED"
    assert row.yt_ttl_expires_at == NOW_MS + YT_TTL_MS


def test_seed_rejects_subscriber_band_edges() -> None:
    def channels_list(*, id: str, **_kwargs):  # noqa: A002
        items = [
            _channel_item("UC_low", subs=SUBSCRIBER_COUNT_MIN - 1),
            _channel_item("UC_ok", subs=SUBSCRIBER_COUNT_MIN),
            _channel_item("UC_high", subs=SUBSCRIBER_COUNT_MAX + 1),
        ]
        return {"items": items}

    manager = WatchlistManager(now_ms=NOW_MS, channels_list=channels_list)
    result = manager.seed(["UC_low", "UC_ok", "UC_high"])

    assert [c.channel_id for c in result.admitted] == ["UC_ok"]
    assert set(result.rejected_band) == {"UC_low", "UC_high"}


def test_seed_rejects_pop_culture_topic() -> None:
    def channels_list(*, id: str, **_kwargs):  # noqa: A002
        return {
            "items": [
                _channel_item(
                    "UC_pop",
                    subs=50_000,
                    title="Celebrity gossip weekly",
                    description="Pop culture drama recap",
                )
            ]
        }

    manager = WatchlistManager(now_ms=NOW_MS, channels_list=channels_list)
    result = manager.seed(["UC_pop"])
    assert result.admitted == ()
    assert result.rejected_band == ("UC_pop",)


def test_seed_forbids_search_list() -> None:
    def channels_list(**_kwargs):
        return {"items": []}

    manager = WatchlistManager(now_ms=NOW_MS, channels_list=channels_list)
    with pytest.raises(SearchListForbiddenError):
        manager._youtube()("search.list", q="true crime")


def test_spillover_promotes_qualifying_channel() -> None:
    admitted_channel = _channel_item("UC_seed", subs=20_000, topic_ids=("/m/0jm_",))

    def channels_list(*, id: str, part: str, **_kwargs):  # noqa: A002
        ids = id.split(",")
        if "UC_spill" in ids:
            return {
                "items": [
                    _channel_item(
                        "UC_spill",
                        subs=25_000,
                        title="Unsolved Homicide Files",
                        description="Murder investigations",
                        topic_ids=("/m/0jm_",),
                    )
                ]
            }
        return {"items": [admitted_channel]}

    crime_titles = [
        "Murder on Route 9 documentary",
        "Cold case homicide special",
        "Serial killer investigation",
        "Missing person unsolved",
    ]

    def playlist_items_list(*, playlistId: str, **_kwargs):  # noqa: N803
        assert playlistId == "UU_spill"
        return {
            "items": [
                {"contentDetails": {"videoId": f"v{i}"}}
                for i in range(MIN_CRIME_LONG_FORM_IN_LAST_10)
            ]
        }

    def videos_list(*, id: str, **_kwargs):  # noqa: A002
        items = []
        for index, video_id in enumerate(id.split(",")):
            items.append(
                {
                    "id": video_id,
                    "snippet": {
                        "title": crime_titles[index],
                        "description": "true crime",
                    },
                    "contentDetails": {"duration": "PT15M"},
                }
            )
        return {"items": items}

    manager = WatchlistManager(
        now_ms=NOW_MS,
        channels_list=channels_list,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    manager.seed(["UC_seed"])
    spill = manager.discover_spillover_channels(
        [{"channel_id": "UC_spill", "subscriber_count": 25_000}]
    )

    assert spill.ledger.search_list_calls == 0
    assert len(spill.promoted) == 1
    assert spill.promoted[0].discovered_via == "SPILLOVER"
    assert spill.promoted[0].uploads_playlist_id == "UU_spill"


def test_spillover_rejects_shorts_farm() -> None:
    def channels_list(*, id: str, **_kwargs):  # noqa: A002
        return {
            "items": [
                _channel_item(
                    "UC_shorts",
                    subs=30_000,
                    title="True crime shorts",
                    description="Murder stories",
                )
            ]
        }

    def playlist_items_list(*, playlistId: str, **_kwargs):  # noqa: N803, ARG001
        return {
            "items": [
                {"contentDetails": {"videoId": f"v{i}"}} for i in range(10)
            ]
        }

    def videos_list(*, id: str, **_kwargs):  # noqa: A002
        return {
            "items": [
                {
                    "id": vid,
                    "snippet": {"title": "Murder recap #Shorts", "description": ""},
                    "contentDetails": {"duration": "PT45S"},
                }
                for vid in id.split(",")
            ]
        }

    manager = WatchlistManager(
        now_ms=NOW_MS,
        channels_list=channels_list,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    spill = manager.discover_spillover_channels([{"channel_id": "UC_shorts"}])
    assert spill.promoted == ()
    assert spill.rejected == ("UC_shorts",)


def test_spillover_rejects_insufficient_long_form_crime() -> None:
    def channels_list(*, id: str, **_kwargs):  # noqa: A002
        return {
            "items": [
                _channel_item(
                    "UC_mixed",
                    subs=15_000,
                    title="Crime commentary",
                    description="Homicide discussion",
                )
            ]
        }

    def playlist_items_list(*, playlistId: str, **_kwargs):  # noqa: N803, ARG001
        return {
            "items": [
                {"contentDetails": {"videoId": f"v{i}"}} for i in range(10)
            ]
        }

    def videos_list(*, id: str, **_kwargs):  # noqa: A002
        items = []
        for index, video_id in enumerate(id.split(",")):
            if index < 2:
                title = "Murder documentary special"
                duration = "PT20M"
            else:
                title = "Netflix drama recap"
                duration = "PT20M"
            items.append(
                {
                    "id": video_id,
                    "snippet": {"title": title, "description": ""},
                    "contentDetails": {"duration": duration},
                }
            )
        return {"items": items}

    manager = WatchlistManager(
        now_ms=NOW_MS,
        channels_list=channels_list,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    spill = manager.discover_spillover_channels([{"channel_id": "UC_mixed"}])
    assert spill.promoted == ()
    assert spill.rejected == ("UC_mixed",)


def test_prune_dormant_and_graduated() -> None:
    dormant_upload_ms = NOW_MS - DORMANT_MS - 1
    seed_channels = {
        "UC_dormant": _channel_item("UC_dormant", subs=40_000),
        "UC_grad": _channel_item("UC_grad", subs=100_000),
        "UC_ok": _channel_item("UC_ok", subs=50_000),
    }
    prune_channels = {
        **seed_channels,
        "UC_grad": _channel_item("UC_grad", subs=SUBSCRIBER_COUNT_MAX + 50_000),
    }

    def channels_list(*, id: str, part: str = "", **_kwargs):  # noqa: A002
        table = seed_channels if "snippet" in part else prune_channels
        return {
            "items": [table[cid] for cid in id.split(",") if cid in table]
        }

    manager = WatchlistManager(now_ms=NOW_MS, channels_list=channels_list)
    manager.seed(["UC_dormant", "UC_grad", "UC_ok"])
    manager._channels["UC_dormant"] = replace(
        manager._channels["UC_dormant"],
        last_upload_at_ms=dormant_upload_ms,
    )

    result = manager.prune(NOW_MS)
    assert result.dormant_deactivated == ("UC_dormant",)
    assert result.graduated_deactivated == ("UC_grad",)
    assert result.ledger.search_list_calls == 0
    assert manager.search_units == 0
    assert manager._channels["UC_ok"].is_active
    assert not manager._channels["UC_dormant"].is_active
    assert not manager._channels["UC_grad"].is_active
    stored = manager._db.execute(
        """
        SELECT channel_id, is_active, subscriber_count, discovered_via
        FROM channels_watchlist
        ORDER BY channel_id
        """
    ).fetchall()
    by_id = {row["channel_id"]: row for row in stored}
    assert by_id["UC_ok"]["is_active"] == 1
    assert by_id["UC_dormant"]["is_active"] == 0
    assert by_id["UC_grad"]["is_active"] == 0
    assert by_id["UC_grad"]["subscriber_count"] == SUBSCRIBER_COUNT_MAX + 50_000


def test_seed_from_recorded_batch_records_zero_search_units() -> None:
    fixture = Path(__file__).resolve().parent / "fixtures" / "yt_channels_batch.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    ids = [item["id"] for item in payload["items"]]
    calls: list[list[str]] = []

    def fetcher(batch: list[str]) -> dict:
        calls.append(list(batch))
        assert len(batch) <= 50
        wanted = set(batch)
        return {
            "kind": payload["kind"],
            "items": [item for item in payload["items"] if item["id"] in wanted],
        }

    manager = WatchlistManager(now_ms=NOW_MS, channels_list=lambda **_kwargs: {"items": []})
    result = manager.seed_from_channel_ids(ids, fetcher, now_ms=NOW_MS)

    assert calls == [ids]
    assert result.ledger.search_list_calls == 0
    assert result.ledger.channels_list_calls == 1
    assert manager.search_units == 0
    assert [row.channel_id for row in result.admitted] == ["UC1111111111111111111111"]
    stored = manager._db.execute(
        """
        SELECT uploads_playlist_id, channel_name, subscriber_count,
               median_20_views, last_polled_at, yt_ttl_expires_at,
               discovered_via, is_active
        FROM channels_watchlist
        WHERE channel_id = ?
        """,
        ("UC1111111111111111111111",),
    ).fetchone()
    assert stored["uploads_playlist_id"] == "UU1111111111111111111111"
    assert stored["uploads_playlist_id"] != "PLnotanuploadsplaylist01"
    assert stored["channel_name"] == "Lake County Cold Cases"
    assert stored["subscriber_count"] == 45_000
    assert stored["median_20_views"] == 0
    assert stored["last_polled_at"] == 0
    assert stored["yt_ttl_expires_at"] == NOW_MS + YT_TTL_MS
    assert stored["discovered_via"] == "SEED"
    assert stored["is_active"] == 1
    columns = [
        row[1]
        for row in manager._db.execute("PRAGMA table_info(channels_watchlist)")
    ]
    assert columns == [
        "channel_id",
        "uploads_playlist_id",
        "channel_name",
        "subscriber_count",
        "median_20_views",
        "last_polled_at",
        "yt_ttl_expires_at",
        "discovered_via",
        "is_active",
    ]


def test_embedded_spillover_respects_band_duration_and_prune_edges() -> None:
    manager = WatchlistManager(now_ms=NOW_MS, channels_list=lambda **_kwargs: {"items": []})
    keep = "UCkeep000000000000000001"
    dormant = "UCdorm000000000000000001"
    farm = "UCfarm000000000000000001"
    low = "UClow0000000000000000001"
    exact_upload = NOW_MS - DORMANT_MS
    too_old = NOW_MS - DORMANT_MS - 1

    def crime_uploads(published_at_ms: int) -> list[dict]:
        titles = (
            "The unsolved murder of Ada Brown",
            "Cold case homicide special",
            "A kidnapping that stayed open",
        )
        return [
            {
                "title": title,
                "duration_sec": 600,
                "published_at_ms": published_at_ms - index,
            }
            for index, title in enumerate(titles)
        ]

    discovered = manager.discover_spillover_channels(
        [
            {
                "channel_id": keep,
                "channel_name": "Band Ceiling",
                "subscriberCount": SUBSCRIBER_COUNT_MAX,
                "uploads": crime_uploads(exact_upload),
            },
            {
                "channel_id": dormant,
                "channel_name": "Gone Quiet",
                "subscriber_count": 8_000,
                "uploads": crime_uploads(too_old),
            },
            {
                "channel_id": farm,
                "channel_name": "Shorts Farm",
                "subscriberCount": 8_000,
                "uploads": [
                    {
                        "title": "Murder recap #shorts",
                        "duration_sec": 45,
                        "published_at_ms": NOW_MS - index,
                    }
                    for index in range(10)
                ],
            },
            {
                "channel_id": low,
                "channel_name": "Below Band",
                "subscriberCount": SUBSCRIBER_COUNT_MIN - 1,
                "uploads": crime_uploads(NOW_MS),
            },
        ],
        NOW_MS,
    )

    assert [row.channel_id for row in discovered.promoted] == [keep, dormant]
    assert discovered.rejected == (farm, low)
    assert discovered.ledger.search_list_calls == 0
    assert manager.search_units == 0
    ceiling = manager._db.execute(
        """
        SELECT uploads_playlist_id, discovered_via, subscriber_count
        FROM channels_watchlist
        WHERE channel_id = ?
        """,
        (keep,),
    ).fetchone()
    assert ceiling["uploads_playlist_id"] == channel_to_uploads_playlist_id(keep)
    assert ceiling["uploads_playlist_id"] == "UU" + keep[2:]
    assert ceiling["discovered_via"] == "SPILLOVER"
    assert ceiling["subscriber_count"] == SUBSCRIBER_COUNT_MAX

    pruned = manager.prune(NOW_MS)
    assert keep not in pruned.dormant_deactivated
    assert keep not in pruned.graduated_deactivated
    assert dormant in pruned.dormant_deactivated
    assert dormant not in pruned.graduated_deactivated
    assert manager._channels[keep].is_active
    assert not manager._channels[dormant].is_active
    assert manager.search_units == 0