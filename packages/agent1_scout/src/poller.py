"""Nightly zero-search playlist poller for Agent 1 Track A scouting."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

VIDEOS_LIST_BATCH_SIZE = 50
MIN_LONG_FORM_DURATION_SEC = 600
YT_TTL_MS = 30 * 24 * 60 * 60 * 1000

_ISO8601_DURATION = re.compile(
    r"^PT"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?$"
)

PlaylistItemsList = Callable[..., Mapping[str, Any]]
VideosList = Callable[..., Mapping[str, Any]]
YoutubeFetcher = Callable[[str], Mapping[str, Any]]


class SearchListForbiddenError(RuntimeError):
    """Raised when a nightly poll would consume the yt_search bucket."""


@dataclass(frozen=True, slots=True)
class ActiveChannel:
    channel_id: str
    uploads_playlist_id: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class PolledVideo:
    video_id: str
    channel_id: str
    title: str
    description: str
    duration_sec: int
    yt_ttl_expires_at: int


@dataclass(frozen=True, slots=True)
class PollRunResult:
    videos: tuple[PolledVideo, ...]
    yt_general_units: int
    playlist_items_calls: int
    videos_list_calls: int
    yt_search_calls: int
    dropped_short_count: int


def parse_iso8601_duration(duration: str) -> int:
    """Parse YouTube-style ISO-8601 durations (``PT58S``, ``PT4M10S``, …) to seconds."""
    if not duration.startswith("PT"):
        msg = f"unsupported duration {duration!r}"
        raise ValueError(msg)
    match = _ISO8601_DURATION.match(duration)
    if not match or match.group(0) == "PT":
        msg = f"unsupported duration {duration!r}"
        raise ValueError(msg)
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + int(seconds)


def _contains_shorts_hashtag(text: str) -> bool:
    return "#shorts" in text.casefold()


def is_long_form(*, duration_sec: int, title: str, description: str) -> bool:
    if duration_sec < MIN_LONG_FORM_DURATION_SEC:
        return False
    if _contains_shorts_hashtag(title) or _contains_shorts_hashtag(description):
        return False
    return True


def _guard_fetcher(
    playlist_items_list: PlaylistItemsList,
    videos_list: VideosList,
) -> YoutubeFetcher:
    search_calls = {"count": 0}

    def fetch(method: str, /, **params: Any) -> Mapping[str, Any]:
        if method == "search.list":
            search_calls["count"] += 1
            raise SearchListForbiddenError(
                "nightly poll must not call search.list (yt_search forbidden)"
            )
        if method == "playlistItems.list":
            return playlist_items_list(**params)
        if method == "videos.list":
            return videos_list(**params)
        msg = f"unsupported YouTube API method {method!r}"
        raise ValueError(msg)

    fetch.search_call_count = lambda: search_calls["count"]  # type: ignore[attr-defined]
    return fetch


class NightlyZeroSearchPoller:
    """Poll ``UU…`` uploads playlists and batch-fetch long-form video metadata."""

    def __init__(
        self,
        *,
        now_ms: int,
        playlist_items_list: PlaylistItemsList,
        videos_list: VideosList,
    ) -> None:
        self._now_ms = now_ms
        self._fetch = _guard_fetcher(playlist_items_list, videos_list)
        self._ttl_expires_at = now_ms + YT_TTL_MS

    @property
    def now_ms(self) -> int:
        return self._now_ms

    def poll(self, channels: Sequence[ActiveChannel]) -> PollRunResult:
        playlist_calls = 0
        videos_calls = 0
        dropped_short = 0
        video_ids_by_channel: dict[str, str] = {}

        for channel in channels:
            if not channel.is_active:
                continue
            if not channel.uploads_playlist_id.startswith("UU"):
                msg = (
                    f"uploads_playlist_id must be a UU… playlist, "
                    f"got {channel.uploads_playlist_id!r}"
                )
                raise ValueError(msg)

            page_token: str | None = None
            while True:
                response = self._fetch(
                    "playlistItems.list",
                    playlistId=channel.uploads_playlist_id,
                    pageToken=page_token,
                    maxResults=50,
                )
                playlist_calls += 1
                for item in response.get("items", ()):
                    video_id = (
                        item.get("contentDetails", {}).get("videoId")
                        or item.get("snippet", {}).get("resourceId", {}).get("videoId")
                    )
                    if video_id:
                        video_ids_by_channel[video_id] = channel.channel_id
                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        all_ids = list(video_ids_by_channel.keys())
        kept: list[PolledVideo] = []

        for offset in range(0, len(all_ids), VIDEOS_LIST_BATCH_SIZE):
            batch = all_ids[offset : offset + VIDEOS_LIST_BATCH_SIZE]
            if not batch:
                continue
            response = self._fetch("videos.list", id=",".join(batch), part="snippet,contentDetails")
            videos_calls += 1
            for item in response.get("items", ()):
                video_id = item["id"]
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                description = snippet.get("description", "")
                raw_duration = item.get("contentDetails", {}).get("duration", "PT0S")
                duration_sec = parse_iso8601_duration(raw_duration)
                if not is_long_form(
                    duration_sec=duration_sec,
                    title=title,
                    description=description,
                ):
                    dropped_short += 1
                    continue
                kept.append(
                    PolledVideo(
                        video_id=video_id,
                        channel_id=video_ids_by_channel[video_id],
                        title=title,
                        description=description,
                        duration_sec=duration_sec,
                        yt_ttl_expires_at=self._ttl_expires_at,
                    )
                )

        yt_general_units = playlist_calls + videos_calls
        search_calls = getattr(self._fetch, "search_call_count", lambda: 0)()

        return PollRunResult(
            videos=tuple(kept),
            yt_general_units=yt_general_units,
            playlist_items_calls=playlist_calls,
            videos_list_calls=videos_calls,
            yt_search_calls=search_calls,
            dropped_short_count=dropped_short,
        )

    def try_search(self, **params: Any) -> Mapping[str, Any]:
        """Expose guarded fetcher so tests can assert ``search.list`` is rejected."""
        return self._fetch("search.list", **params)