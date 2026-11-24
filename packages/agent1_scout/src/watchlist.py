"""Dynamic watchlist seeding, spillover discovery, and weekly pruning for Agent 1."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

CHANNELS_LIST_BATCH_SIZE = 50
VIDEOS_LIST_BATCH_SIZE = 50
PLAYLIST_ITEMS_PAGE_SIZE = 10

SUBSCRIBER_COUNT_MIN = 2_000
SUBSCRIBER_COUNT_MAX = 120_000
TARGET_ACTIVE_MIN = 250
TARGET_ACTIVE_MAX = 400

MIN_LONG_FORM_DURATION_SEC = 600
MIN_CRIME_LONG_FORM_IN_LAST_10 = 3
DORMANT_DAYS = 180
DORMANT_MS = DORMANT_DAYS * 24 * 60 * 60 * 1000
YT_TTL_MS = 30 * 24 * 60 * 60 * 1000

DISCOVERED_VIA_SEED = "SEED"
DISCOVERED_VIA_SPILLOVER = "SPILLOVER"

_ISO8601_DURATION = re.compile(
    r"^PT"
    r"(?:(\d+)H)?"
    r"(?:(\d+)M)?"
    r"(?:(\d+(?:\.\d+)?)S)?$"
)

ChannelsList = Callable[..., Mapping[str, Any]]
PlaylistItemsList = Callable[..., Mapping[str, Any]]
VideosList = Callable[..., Mapping[str, Any]]

# YouTube Freebase topic id for Society / Crime (channel topicDetails).
TRUE_CRIME_TOPIC_IDS = frozenset({"/m/0jm_", "/m/04g51"})

_CRIME_KEYWORDS = (
    "true crime",
    "cold case",
    "serial killer",
    "homicide",
    "murder",
    "missing person",
    "unsolved",
    "forensic",
    "investigation",
    "kidnapping",
    "detective",
)

_POP_CULTURE_KEYWORDS = (
    "celebrity gossip",
    "pop culture",
    "movie review",
    "tv recap",
    "entertainment news",
    "reaction video",
    "drama recap",
    "netflix review",
    "celebrity news",
)


class SearchListForbiddenError(RuntimeError):
    """Raised when watchlist seeding or maintenance would call search.list."""


@dataclass(frozen=True, slots=True)
class WatchlistChannel:
    channel_id: str
    uploads_playlist_id: str
    channel_name: str
    subscriber_count: int
    yt_ttl_expires_at: int
    discovered_via: str
    is_active: bool = True
    median_20_views: int = 0
    last_polled_at: int = 0
    last_upload_at_ms: int = 0


@dataclass(frozen=True, slots=True)
class ApiCallLedger:
    search_list_calls: int = 0
    channels_list_calls: int = 0
    playlist_items_list_calls: int = 0
    videos_list_calls: int = 0


@dataclass(frozen=True, slots=True)
class SeedResult:
    admitted: tuple[WatchlistChannel, ...]
    rejected_band: tuple[str, ...]
    ledger: ApiCallLedger


@dataclass(frozen=True, slots=True)
class SpilloverDiscoveryResult:
    promoted: tuple[WatchlistChannel, ...]
    rejected: tuple[str, ...]
    ledger: ApiCallLedger


@dataclass(frozen=True, slots=True)
class PruneResult:
    dormant_deactivated: tuple[str, ...]
    graduated_deactivated: tuple[str, ...]
    ledger: ApiCallLedger


def channel_to_uploads_playlist_id(channel_id: str) -> str:
    """Map a ``UC…`` channel id to its ``UU…`` uploads playlist id."""
    if channel_id.startswith("UC") and len(channel_id) > 2:
        return "UU" + channel_id[2:]
    msg = f"expected UC-prefixed channel id, got {channel_id!r}"
    raise ValueError(msg)


def parse_iso8601_duration(duration: str) -> int:
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


def _parse_count(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return None


def _text_blob(*parts: str) -> str:
    return " ".join(part.casefold() for part in parts if part)


def topic_matches_true_crime(
    *,
    title: str,
    description: str,
    topic_ids: Sequence[str] | None = None,
) -> bool:
    if topic_ids:
        if any(topic_id in TRUE_CRIME_TOPIC_IDS for topic_id in topic_ids):
            return True
    blob = _text_blob(title, description)
    if any(keyword in blob for keyword in _POP_CULTURE_KEYWORDS):
        return False
    return any(keyword in blob for keyword in _CRIME_KEYWORDS)


def title_looks_like_crime_video(title: str, description: str = "") -> bool:
    blob = _text_blob(title, description)
    if any(keyword in blob for keyword in _POP_CULTURE_KEYWORDS):
        return False
    return any(keyword in blob for keyword in _CRIME_KEYWORDS)


def _batched(ids: Sequence[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(ids[index : index + size]) for index in range(0, len(ids), size)]


def _guard_youtube(
    *,
    channels_list: ChannelsList | None,
    playlist_items_list: PlaylistItemsList | None,
    videos_list: VideosList | None,
    ledger: MutableMapping[str, int],
) -> Callable[[str], Mapping[str, Any]]:
    def fetch(method: str, /, **params: Any) -> Mapping[str, Any]:
        if method == "search.list":
            raise SearchListForbiddenError(
                "watchlist manager must not call search.list"
            )
        if method == "channels.list":
            if channels_list is None:
                msg = "channels_list callable required"
                raise RuntimeError(msg)
            ledger["channels_list_calls"] += 1
            return channels_list(**params)
        if method == "playlistItems.list":
            if playlist_items_list is None:
                msg = "playlist_items_list callable required"
                raise RuntimeError(msg)
            ledger["playlist_items_list_calls"] += 1
            return playlist_items_list(**params)
        if method == "videos.list":
            if videos_list is None:
                msg = "videos_list callable required"
                raise RuntimeError(msg)
            ledger["videos_list_calls"] += 1
            return videos_list(**params)
        msg = f"unsupported YouTube API method {method!r}"
        raise ValueError(msg)

    return fetch


def _channel_items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = payload.get("items", ())
    if isinstance(items, Mapping):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def _subscriber_count(item: Mapping[str, Any]) -> int | None:
    statistics = item.get("statistics")
    if not isinstance(statistics, Mapping):
        return None
    if statistics.get("hiddenSubscriberCount") in (True, "true", "True", 1):
        return None
    return _parse_count(statistics.get("subscriberCount"))


def _channel_name(item: Mapping[str, Any]) -> str:
    snippet = item.get("snippet")
    if isinstance(snippet, Mapping):
        title = snippet.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    channel_id = item.get("id")
    if isinstance(channel_id, str):
        return channel_id
    return "unknown"


def _topic_ids(item: Mapping[str, Any]) -> tuple[str, ...]:
    topic = item.get("topicDetails")
    if not isinstance(topic, Mapping):
        return ()
    ids = topic.get("topicIds")
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
        return ()
    return tuple(str(topic_id) for topic_id in ids)


def _snippet_text(item: Mapping[str, Any]) -> tuple[str, str]:
    snippet = item.get("snippet")
    if not isinstance(snippet, Mapping):
        return "", ""
    title = snippet.get("title")
    description = snippet.get("description")
    return (
        str(title) if title is not None else "",
        str(description) if description is not None else "",
    )


def _coerce_search_result(raw: Mapping[str, object]) -> tuple[str, int | None]:
    channel_id = str(raw.get("channel_id", raw.get("channelId", ""))).strip()
    count = _parse_count(raw.get("subscriber_count", raw.get("subscriberCount")))
    return channel_id, count


@dataclass
class WatchlistManager:
    """In-memory watchlist with injected YouTube API callables (offline-safe)."""

    now_ms: int
    channels_list: ChannelsList
    playlist_items_list: PlaylistItemsList | None = None
    videos_list: VideosList | None = None
    _channels: dict[str, WatchlistChannel] = field(default_factory=dict)
    _ledger: MutableMapping[str, int] = field(
        default_factory=lambda: {
            "search_list_calls": 0,
            "channels_list_calls": 0,
            "playlist_items_list_calls": 0,
            "videos_list_calls": 0,
        }
    )

    def __post_init__(self) -> None:
        self._db = sqlite3.connect(":memory:")
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        pipeline_sql = _repo_root() / "schema" / "pipeline.sql"
        self._db.executescript(pipeline_sql.read_text(encoding="utf-8"))

    @property
    def search_units(self) -> int:
        """Search-quota units spent. Seeding and spillover never add any."""
        return int(self._ledger["search_list_calls"])

    def active_count(self) -> int:
        return sum(
            1
            for row in self._channels.values()
            if row.is_active and self._in_subscriber_band(row.subscriber_count)
        )

    def snapshot(self) -> tuple[WatchlistChannel, ...]:
        return tuple(self._channels[ch_id] for ch_id in sorted(self._channels))

    def known_channel_ids(self) -> frozenset[str]:
        return frozenset(self._channels)

    def _ledger_snapshot(self) -> ApiCallLedger:
        return ApiCallLedger(
            search_list_calls=self._ledger["search_list_calls"],
            channels_list_calls=self._ledger["channels_list_calls"],
            playlist_items_list_calls=self._ledger["playlist_items_list_calls"],
            videos_list_calls=self._ledger["videos_list_calls"],
        )

    def _youtube(self) -> Callable[[str], Mapping[str, Any]]:
        return _guard_youtube(
            channels_list=self.channels_list,
            playlist_items_list=self.playlist_items_list,
            videos_list=self.videos_list,
            ledger=self._ledger,
        )

    def _in_subscriber_band(self, count: int | None) -> bool:
        return count is not None and SUBSCRIBER_COUNT_MIN <= count <= SUBSCRIBER_COUNT_MAX

    def _room_for_spillover(self) -> bool:
        return self.active_count() < TARGET_ACTIVE_MAX

    def seed(self, channel_ids: Sequence[str]) -> SeedResult:
        """Bulk-seed via ``channels.list`` only (50 ids per call, zero ``search.list``)."""
        fetch = self._youtube()
        unique = list(dict.fromkeys(channel_ids))
        admitted: list[WatchlistChannel] = []
        rejected_band: list[str] = []

        for batch in _batched(unique, CHANNELS_LIST_BATCH_SIZE):
            payload = fetch(
                "channels.list",
                part="snippet,statistics,contentDetails,topicDetails",
                id=",".join(batch),
            )
            for item in _channel_items(payload):
                channel_id = str(item.get("id", ""))
                if not channel_id or channel_id in self._channels:
                    continue
                subs = _subscriber_count(item)
                if not self._in_subscriber_band(subs):
                    rejected_band.append(channel_id)
                    continue
                title, description = _snippet_text(item)
                if not topic_matches_true_crime(
                    title=title,
                    description=description,
                    topic_ids=_topic_ids(item),
                ):
                    rejected_band.append(channel_id)
                    continue
                uploads = channel_to_uploads_playlist_id(channel_id)
                row = WatchlistChannel(
                    channel_id=channel_id,
                    uploads_playlist_id=uploads,
                    channel_name=_channel_name(item),
                    subscriber_count=int(subs),
                    yt_ttl_expires_at=self.now_ms + YT_TTL_MS,
                    discovered_via=DISCOVERED_VIA_SEED,
                    last_upload_at_ms=self.now_ms,
                )
                self._channels[channel_id] = row
                self._persist(row)
                admitted.append(row)

        return SeedResult(
            admitted=tuple(admitted),
            rejected_band=tuple(rejected_band),
            ledger=self._ledger_snapshot(),
        )

    def seed_from_channel_ids(
        self,
        ids: Sequence[str],
        fetcher: Callable[..., object],
        now_ms: int | None = None,
    ) -> SeedResult:
        """Seed from an injected ``channels.list`` fetcher, 50 ids per call.

        ``fetcher`` may accept the batch as a list, or the YouTube-style
        ``id`` keyword of comma-separated channel ids. This path never calls
        ``search.list`` and leaves ``search_units`` at 0.
        """
        if now_ms is not None:
            self.now_ms = now_ms
        previous = self.channels_list
        self.channels_list = _adapt_channels_fetcher(fetcher)
        try:
            return self.seed(list(ids))
        finally:
            self.channels_list = previous

    def discover_spillover_channels(
        self,
        search_results: Sequence[Mapping[str, object]],
        now_ms: int | None = None,
    ) -> SpilloverDiscoveryResult:
        """Promote spillover channels that pass band, topic, and long-form crime checks."""
        if now_ms is not None:
            self.now_ms = now_ms
        embedded = [
            raw
            for raw in search_results
            if isinstance(raw, Mapping) and isinstance(raw.get("uploads"), list)
        ]
        remote = [
            raw
            for raw in search_results
            if not (isinstance(raw, Mapping) and isinstance(raw.get("uploads"), list))
        ]
        promoted: list[WatchlistChannel] = []
        rejected: list[str] = []
        for raw in embedded:
            row, reason = self._admit_embedded(raw)
            if row is None:
                if reason:
                    rejected.append(reason)
                continue
            promoted.append(row)
        if not remote:
            return SpilloverDiscoveryResult(
                promoted=tuple(promoted),
                rejected=tuple(rejected),
                ledger=self._ledger_snapshot(),
            )
        remote_result = self._discover_remote(remote)
        return SpilloverDiscoveryResult(
            promoted=tuple(promoted) + remote_result.promoted,
            rejected=tuple(rejected) + remote_result.rejected,
            ledger=remote_result.ledger,
        )

    def _discover_remote(
        self,
        search_results: Sequence[Mapping[str, object]],
    ) -> SpilloverDiscoveryResult:
        """Promote channels by calling the injected YouTube readers."""
        if not search_results:
            return SpilloverDiscoveryResult(
                promoted=(),
                rejected=(),
                ledger=self._ledger_snapshot(),
            )
        if not self._room_for_spillover():
            return SpilloverDiscoveryResult(
                promoted=(),
                rejected=tuple(_coerce_search_result(r)[0] for r in search_results if _coerce_search_result(r)[0]),
                ledger=self._ledger_snapshot(),
            )
        if self.playlist_items_list is None or self.videos_list is None:
            msg = "playlist_items_list and videos_list are required for spillover discovery"
            raise RuntimeError(msg)

        fetch = self._youtube()
        promoted: list[WatchlistChannel] = []
        rejected: list[str] = []

        unknown: list[str] = []
        for raw in search_results:
            channel_id, pre_count = _coerce_search_result(raw)
            if not channel_id or channel_id in self._channels:
                continue
            if pre_count is not None and not self._in_subscriber_band(pre_count):
                rejected.append(channel_id)
                continue
            unknown.append(channel_id)

        if not unknown:
            return SpilloverDiscoveryResult(
                promoted=(),
                rejected=tuple(rejected),
                ledger=self._ledger_snapshot(),
            )

        channel_meta: dict[str, Mapping[str, Any]] = {}
        for batch in _batched(unknown, CHANNELS_LIST_BATCH_SIZE):
            payload = fetch(
                "channels.list",
                part="snippet,statistics,topicDetails",
                id=",".join(batch),
            )
            for item in _channel_items(payload):
                channel_id = str(item.get("id", ""))
                if channel_id:
                    channel_meta[channel_id] = item

        for channel_id in unknown:
            if not self._room_for_spillover():
                rejected.append(channel_id)
                continue
            item = channel_meta.get(channel_id)
            if item is None:
                rejected.append(channel_id)
                continue
            subs = _subscriber_count(item)
            if not self._in_subscriber_band(subs):
                rejected.append(channel_id)
                continue
            title, description = _snippet_text(item)
            if not topic_matches_true_crime(
                title=title,
                description=description,
                topic_ids=_topic_ids(item),
            ):
                rejected.append(channel_id)
                continue
            crime_long = self._count_crime_long_form_uploads(fetch, channel_id)
            if crime_long < MIN_CRIME_LONG_FORM_IN_LAST_10:
                rejected.append(channel_id)
                continue
            row = WatchlistChannel(
                channel_id=channel_id,
                uploads_playlist_id=channel_to_uploads_playlist_id(channel_id),
                channel_name=_channel_name(item),
                subscriber_count=int(subs),
                yt_ttl_expires_at=self.now_ms + YT_TTL_MS,
                discovered_via=DISCOVERED_VIA_SPILLOVER,
                last_upload_at_ms=self.now_ms,
            )
            self._channels[channel_id] = row
            self._persist(row)
            promoted.append(row)

        return SpilloverDiscoveryResult(
            promoted=tuple(promoted),
            rejected=tuple(rejected),
            ledger=self._ledger_snapshot(),
        )

    def _count_crime_long_form_uploads(
        self,
        fetch: Callable[[str], Mapping[str, Any]],
        channel_id: str,
    ) -> int:
        playlist_id = channel_to_uploads_playlist_id(channel_id)
        page = fetch(
            "playlistItems.list",
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=PLAYLIST_ITEMS_PAGE_SIZE,
        )
        video_ids: list[str] = []
        for item in _channel_items(page):
            details = item.get("contentDetails")
            if isinstance(details, Mapping):
                video_id = details.get("videoId")
                if isinstance(video_id, str) and video_id:
                    video_ids.append(video_id)
        if not video_ids:
            return 0

        crime_count = 0
        for batch in _batched(video_ids, VIDEOS_LIST_BATCH_SIZE):
            payload = fetch(
                "videos.list",
                part="snippet,contentDetails",
                id=",".join(batch),
            )
            for item in _channel_items(payload):
                snippet = item.get("snippet")
                content = item.get("contentDetails")
                if not isinstance(snippet, Mapping) or not isinstance(content, Mapping):
                    continue
                title = str(snippet.get("title", ""))
                description = str(snippet.get("description", ""))
                duration_raw = content.get("duration")
                if not isinstance(duration_raw, str):
                    continue
                try:
                    duration_sec = parse_iso8601_duration(duration_raw)
                except ValueError:
                    continue
                if not is_long_form(
                    duration_sec=duration_sec,
                    title=title,
                    description=description,
                ):
                    continue
                if title_looks_like_crime_video(title, description):
                    crime_count += 1
        return crime_count

    def prune(self, now_ms: int | None = None) -> PruneResult:
        """Deactivate dormant channels (>180d since last upload) and graduated (>120K subs)."""
        effective_now = self.now_ms if now_ms is None else now_ms
        fetch = self._youtube()
        dormant: list[str] = []
        graduated: list[str] = []

        active_ids = [
            channel_id
            for channel_id, row in self._channels.items()
            if row.is_active
        ]
        refreshed: dict[str, tuple[int, int]] = {}
        for batch in _batched(active_ids, CHANNELS_LIST_BATCH_SIZE):
            payload = fetch(
                "channels.list",
                part="statistics",
                id=",".join(batch),
            )
            for item in _channel_items(payload):
                channel_id = str(item.get("id", ""))
                subs = _subscriber_count(item)
                if channel_id and subs is not None:
                    refreshed[channel_id] = (subs, self._channels[channel_id].last_upload_at_ms)

        for channel_id, row in list(self._channels.items()):
            if not row.is_active:
                continue
            subs, last_upload = refreshed.get(channel_id, (row.subscriber_count, row.last_upload_at_ms))
            if subs > SUBSCRIBER_COUNT_MAX:
                updated = replace(
                    row,
                    is_active=False,
                    subscriber_count=subs,
                )
                self._channels[channel_id] = updated
                self._persist(updated)
                graduated.append(channel_id)
                continue
            if last_upload and effective_now - last_upload > DORMANT_MS:
                updated = replace(row, is_active=False)
                self._channels[channel_id] = updated
                self._persist(updated)
                dormant.append(channel_id)

        return PruneResult(
            dormant_deactivated=tuple(dormant),
            graduated_deactivated=tuple(graduated),
            ledger=self._ledger_snapshot(),
        )

    def _persist(self, row: WatchlistChannel) -> None:
        """Write one row using the real ``channels_watchlist`` columns."""
        self._db.execute(
            """
            INSERT INTO channels_watchlist (
                channel_id,
                uploads_playlist_id,
                channel_name,
                subscriber_count,
                median_20_views,
                last_polled_at,
                yt_ttl_expires_at,
                discovered_via,
                is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                uploads_playlist_id = excluded.uploads_playlist_id,
                channel_name = excluded.channel_name,
                subscriber_count = excluded.subscriber_count,
                median_20_views = excluded.median_20_views,
                last_polled_at = excluded.last_polled_at,
                yt_ttl_expires_at = excluded.yt_ttl_expires_at,
                discovered_via = excluded.discovered_via,
                is_active = excluded.is_active
            """,
            (
                row.channel_id,
                row.uploads_playlist_id,
                row.channel_name,
                int(row.subscriber_count),
                int(row.median_20_views),
                int(row.last_polled_at),
                int(row.yt_ttl_expires_at),
                row.discovered_via,
                1 if row.is_active else 0,
            ),
        )
        self._db.commit()

    def _admit_embedded(
        self,
        raw: Mapping[str, object],
    ) -> tuple[WatchlistChannel | None, str]:
        """Admit a spillover candidate whose uploads are already on the payload."""
        channel_id, subscriber_count = _coerce_search_result(raw)
        if not channel_id:
            return None, ""
        if channel_id in self._channels or not self._room_for_spillover():
            return None, "" if channel_id in self._channels else channel_id
        if not channel_id.startswith("UC"):
            return None, channel_id
        if subscriber_count is None:
            subscriber_count = _subscriber_count(raw)
        if not self._in_subscriber_band(subscriber_count):
            return None, channel_id
        uploads = raw.get("uploads")
        if not isinstance(uploads, list):
            return None, channel_id
        recent = _recent_embedded(uploads)
        crime_long = sum(1 for video in recent if _embedded_long_form_crime(video))
        if crime_long < MIN_CRIME_LONG_FORM_IN_LAST_10:
            return None, channel_id
        name = raw.get("channel_name") or raw.get("channelTitle") or raw.get("title")
        channel_name = name.strip() if isinstance(name, str) and name.strip() else channel_id
        stamps = [
            stamp
            for stamp in (_embedded_published_ms(video) for video in recent)
            if stamp is not None
        ]
        row = WatchlistChannel(
            channel_id=channel_id,
            uploads_playlist_id=channel_to_uploads_playlist_id(channel_id),
            channel_name=channel_name,
            subscriber_count=int(subscriber_count),
            yt_ttl_expires_at=self.now_ms + YT_TTL_MS,
            discovered_via=DISCOVERED_VIA_SPILLOVER,
            last_upload_at_ms=max(stamps) if stamps else self.now_ms,
        )
        self._channels[channel_id] = row
        self._persist(row)
        return row, ""


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "schema" / "pipeline.sql").is_file():
            return parent
    raise FileNotFoundError("schema/pipeline.sql not found")


def _adapt_channels_fetcher(fetcher: Callable[..., object]) -> ChannelsList:
    """Adapt a batch-list fetcher or a keyword ``id=`` channels.list callable."""

    def channels_list(*, id: str, **kwargs: Any) -> Mapping[str, Any]:
        batch = [part for part in str(id).split(",") if part]
        try:
            payload = fetcher(batch)
        except TypeError:
            payload = fetcher(id=id, **kwargs)
        if isinstance(payload, Mapping):
            return payload
        if isinstance(payload, list):
            return {"items": payload}
        raise TypeError("channels.list fetcher must return a response object or items")

    return channels_list


def _recent_embedded(uploads: Sequence[object]) -> list[Mapping[str, Any]]:
    videos = [video for video in uploads if isinstance(video, Mapping)]
    if any(_embedded_published_ms(video) is not None for video in videos):
        ranked = sorted(
            enumerate(videos),
            key=lambda pair: (
                _embedded_published_ms(pair[1]) is None,
                -(_embedded_published_ms(pair[1]) or 0),
                pair[0],
            ),
        )
        videos = [video for _, video in ranked]
    return videos[:PLAYLIST_ITEMS_PAGE_SIZE]


def _embedded_long_form_crime(video: Mapping[str, Any]) -> bool:
    title, description = _embedded_text(video)
    duration = _embedded_duration_sec(video)
    if duration is None:
        return False
    if not is_long_form(duration_sec=duration, title=title, description=description):
        return False
    if isinstance(video.get("crime"), bool):
        return bool(video["crime"])
    return title_looks_like_crime_video(title, description)


def _embedded_text(video: Mapping[str, Any]) -> tuple[str, str]:
    snippet = video.get("snippet")
    snippet_map = snippet if isinstance(snippet, Mapping) else {}
    title = video.get("title") if isinstance(video.get("title"), str) else ""
    if not title and isinstance(snippet_map.get("title"), str):
        title = str(snippet_map["title"])
    description = video.get("description") if isinstance(video.get("description"), str) else ""
    if not description and isinstance(snippet_map.get("description"), str):
        description = str(snippet_map["description"])
    return title, description


def _embedded_duration_sec(video: Mapping[str, Any]) -> int | None:
    raw_duration = video.get("duration_sec")
    if isinstance(raw_duration, int) and not isinstance(raw_duration, bool):
        return raw_duration
    raw = video.get("duration")
    content = video.get("contentDetails")
    if raw is None and isinstance(content, Mapping):
        raw = content.get("duration")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        if raw.isdigit():
            return int(raw)
        try:
            return parse_iso8601_duration(raw)
        except ValueError:
            return None
    return None


def _embedded_published_ms(video: Mapping[str, Any]) -> int | None:
    for key in ("published_at_ms", "publishedAtMs"):
        value = video.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None