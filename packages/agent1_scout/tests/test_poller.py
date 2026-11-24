"""Offline tests for NightlyZeroSearchPoller."""

from __future__ import annotations

import pytest

from poller import (
    ActiveChannel,
    NightlyZeroSearchPoller,
    SearchListForbiddenError,
    YT_TTL_MS,
    is_long_form,
    parse_iso8601_duration,
)

NOW_MS = 1_700_000_000_000


@pytest.mark.parametrize(
    ("raw", "expected_sec"),
    [
        ("PT58S", 58),
        ("PT4M10S", 250),
        ("PT10M", 600),
        ("PT1H2M3S", 3723),
    ],
)
def test_parse_iso8601_duration_examples(raw: str, expected_sec: int) -> None:
    assert parse_iso8601_duration(raw) == expected_sec


def test_is_long_form_rejects_short_duration_and_hashtag() -> None:
    assert not is_long_form(duration_sec=599, title="doc", description="x")
    assert not is_long_form(duration_sec=600, title="case #Shorts", description="x")
    assert not is_long_form(duration_sec=900, title="x", description="tagged #SHORTS here")
    assert is_long_form(duration_sec=600, title="long form", description="no tag")


def test_poller_rejects_search_list() -> None:
    def playlist_items_list(**_kwargs):  # noqa: ANN003
        return {"items": []}

    def videos_list(**_kwargs):  # noqa: ANN003
        return {"items": []}

    poller = NightlyZeroSearchPoller(
        now_ms=NOW_MS,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    with pytest.raises(SearchListForbiddenError):
        poller.try_search(q="true crime")


def test_poller_filters_shorts_and_tags_ttl() -> None:
    playlist_ids: list[str] = []

    def playlist_items_list(*, playlistId: str, pageToken=None, **_kwargs):  # noqa: ANN001
        playlist_ids.append(playlistId)
        assert pageToken is None
        return {
            "items": [
                {"contentDetails": {"videoId": "v_short_time"}},
                {"contentDetails": {"videoId": "v_short_tag"}},
                {"contentDetails": {"videoId": "v_ok"}},
            ]
        }

    videos_batches: list[list[str]] = []

    def videos_list(*, id: str, **_kwargs):  # noqa: A002, ANN001
        batch = id.split(",")
        videos_batches.append(batch)
        payloads = {
            "v_short_time": {
                "id": "v_short_time",
                "snippet": {"title": "Too short", "description": ""},
                "contentDetails": {"duration": "PT58S"},
            },
            "v_short_tag": {
                "id": "v_short_tag",
                "snippet": {"title": "Hashtag", "description": "#shorts"},
                "contentDetails": {"duration": "PT20M"},
            },
            "v_ok": {
                "id": "v_ok",
                "snippet": {"title": "Cold case documentary", "description": "deep dive"},
                "contentDetails": {"duration": "PT10M"},
            },
        }
        return {"items": [payloads[vid] for vid in batch]}

    poller = NightlyZeroSearchPoller(
        now_ms=NOW_MS,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    result = poller.poll(
        [
            ActiveChannel(
                channel_id="UCabc",
                uploads_playlist_id="UUuploads",
            )
        ]
    )

    assert result.yt_search_calls == 0
    assert result.playlist_items_calls == 1
    assert result.videos_list_calls == 1
    assert result.yt_general_units == 2
    assert result.dropped_short_count == 2
    assert len(result.videos) == 1
    kept = result.videos[0]
    assert kept.video_id == "v_ok"
    assert kept.duration_sec == 600
    assert kept.yt_ttl_expires_at == NOW_MS + YT_TTL_MS
    assert playlist_ids == ["UUuploads"]
    assert videos_batches == [["v_short_time", "v_short_tag", "v_ok"]]


def test_videos_list_batches_fifty_ids() -> None:
    video_count = 125
    ids = [f"vid_{i:03d}" for i in range(video_count)]

    def playlist_items_list(*, playlistId: str, pageToken=None, **_kwargs):  # noqa: ANN001
        if pageToken is not None:
            return {"items": []}
        return {
            "items": [{"contentDetails": {"videoId": vid}} for vid in ids],
        }

    batches: list[list[str]] = []

    def videos_list(*, id: str, **_kwargs):  # noqa: A002, ANN001
        batch = id.split(",")
        batches.append(batch)
        return {
            "items": [
                {
                    "id": vid,
                    "snippet": {"title": f"t {vid}", "description": ""},
                    "contentDetails": {"duration": "PT15M"},
                }
                for vid in batch
            ]
        }

    poller = NightlyZeroSearchPoller(
        now_ms=NOW_MS,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    result = poller.poll(
        [ActiveChannel(channel_id="ch0", uploads_playlist_id="UU000")]
    )

    assert result.yt_search_calls == 0
    assert result.videos_list_calls == 3
    assert result.playlist_items_calls == 1
    assert result.yt_general_units == 4
    assert [len(b) for b in batches] == [50, 50, 25]
    assert len(result.videos) == video_count


def test_three_hundred_channel_scale_stand_in() -> None:
    """Synthetic stand-in for the 300-channel nightly poll acceptance fixture."""

    channel_count = 300
    channels = [
        ActiveChannel(
            channel_id=f"UC{i:04d}",
            uploads_playlist_id=f"UU{i:04d}",
            is_active=i % 5 != 0,
        )
        for i in range(channel_count)
    ]
    active_count = sum(1 for ch in channels if ch.is_active)

    playlist_calls: list[str] = []

    def playlist_items_list(*, playlistId: str, pageToken=None, **_kwargs):  # noqa: ANN001
        playlist_calls.append(playlistId)
        assert pageToken is None
        suffix = playlistId.removeprefix("UU")
        return {
            "items": [{"contentDetails": {"videoId": f"{suffix}_only"}}],
        }

    videos_batches: list[int] = []

    def videos_list(*, id: str, **_kwargs):  # noqa: A002, ANN001
        batch = id.split(",")
        videos_batches.append(len(batch))
        return {
            "items": [
                {
                    "id": vid,
                    "snippet": {"title": "Episode", "description": ""},
                    "contentDetails": {"duration": "PT12M"},
                }
                for vid in batch
            ]
        }

    poller = NightlyZeroSearchPoller(
        now_ms=NOW_MS,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    result = poller.poll(channels)

    assert result.yt_search_calls == 0
    assert len(playlist_calls) == active_count
    assert result.playlist_items_calls == active_count
    assert sum(videos_batches) == active_count
    assert max(videos_batches) <= 50
    assert result.videos_list_calls == (active_count + 49) // 50
    assert result.yt_general_units == result.playlist_items_calls + result.videos_list_calls
    assert len(result.videos) == active_count
    assert all(v.yt_ttl_expires_at == NOW_MS + YT_TTL_MS for v in result.videos)


def test_inactive_channels_skipped() -> None:
    calls: list[str] = []

    def playlist_items_list(*, playlistId: str, **_kwargs):  # noqa: ANN001
        calls.append(playlistId)
        return {"items": [{"contentDetails": {"videoId": "x"}}]}

    def videos_list(*, id: str, **_kwargs):  # noqa: A002, ANN001
        return {
            "items": [
                {
                    "id": "x",
                    "snippet": {"title": "t", "description": ""},
                    "contentDetails": {"duration": "PT11M"},
                }
            ]
        }

    poller = NightlyZeroSearchPoller(
        now_ms=NOW_MS,
        playlist_items_list=playlist_items_list,
        videos_list=videos_list,
    )
    result = poller.poll(
        [
            ActiveChannel("UC1", "UU1", is_active=False),
            ActiveChannel("UC2", "UU2", is_active=True),
        ]
    )

    assert calls == ["UU2"]
    assert len(result.videos) == 1
    assert result.yt_search_calls == 0