"""Deduplicated surgical ``search.list`` runner for Agent 1.

Offline. This module never opens a socket and never constructs a YouTube
client. The caller injects ``search_list`` and ``videos_list``.

Two different budgets are in play, and only one of them gates this runner:

* On the live YouTube Data API, one ``search.list`` call costs **100 quota
  units**. ``videos.list`` is a general-quota call (1 unit) and is not part
  of the ``yt_search`` reserve. ``SearchRunResult.real_api_search_quota_units``
  reports ``search_calls * 100`` so that cost stays visible.
* The reserve this runner actually enforces is a **call floor of 15**, matching
  Task 007's 15-call ``yt_search`` pre-render reserve (``IMPLEMENTATION_TASKS``
  Task 007 / Task 019). ``search_units_remaining`` is the remaining call budget
  the caller (and the tests) pass in. Each alias query consumes **one call**
  from that budget. When ``search_units_remaining <= 15`` the runner makes
  zero ``search.list`` calls and returns a reserve-held result. It will not
  spend the budget down through the floor: the most it can spend on a run is
  ``search_units_remaining - 15``, and never more than 20 calls.

The shortlist is the top outliers already chosen upstream (Task 017 keeps
15–20). This runner searches only those candidates, and at most the first 20.
It does not go looking for more.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

# Live Data API cost of one search.list. Not the unit this reserve subtracts.
SEARCH_LIST_QUOTA_UNITS = 100
# Task 007 / Task 019: calls kept for the daily pre-render re-check.
YT_SEARCH_CALL_RESERVE = 15
MAX_SEARCH_CALLS_PER_RUN = 20
MAX_CANDIDATES_PER_RUN = 20
VIDEOS_LIST_BATCH_SIZE = 50
SUBSCRIBER_COUNT_MIN = 2_000
SUBSCRIBER_COUNT_MAX = 120_000
SPILLOVER_DISCOVERED_VIA = "SPILLOVER"

RESERVE_HELD_REASON = (
    "yt_search call reserve of 15; search_units_remaining is at or below the floor"
)

SearchList = Callable[[str], Mapping[str, object] | Sequence[object]]
VideosList = Callable[[Sequence[str]], Mapping[str, object] | Sequence[object]]


@dataclass(frozen=True, slots=True)
class OutlierCandidate:
    """One already-ranked outlier and the alias queries to check for it.

    ``aliases`` is the 3–4 canonical queries from the alias expander. This
    runner does not invent aliases. Order is the search order.
    """

    candidate_id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DedupedVideo:
    """One video id, no matter how many alias queries returned it."""

    video_id: str
    channel_id: str
    title: str
    published_at: str
    alias_queries: tuple[str, ...]
    view_count: int | None
    statistics: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class SpilloverCandidate:
    """A channel to hand to ``WatchlistManager``. Nothing is inserted here."""

    channel_id: str
    subscriber_count: int
    source_video_ids: tuple[str, ...]
    discovered_via: str = SPILLOVER_DISCOVERED_VIA


@dataclass(frozen=True, slots=True)
class SearchRunResult:
    """Outcome of one surgical alias pass.

    ``call_budget_before`` / ``call_budget_after`` are call counts.
    ``real_api_search_quota_units`` is the live-API equivalent (100 per
    ``search.list``) and is not subtracted from the call budget.
    """

    reserve_held: bool
    reason: str
    search_calls: int
    videos_list_calls: int
    videos: tuple[DedupedVideo, ...]
    spillover_candidates: tuple[SpilloverCandidate, ...]
    alias_queries_run: tuple[str, ...]
    alias_queries_skipped: tuple[str, ...]
    candidates_considered: int
    candidates_skipped: int
    call_budget_before: int
    call_budget_after: int
    real_api_search_quota_units: int


@dataclass(slots=True)
class _VideoAcc:
    video_id: str
    channel_id: str
    title: str
    published_at: str
    queries: list[str]
    search_subscriber_count: int | None
    search_hidden: bool
    statistics: dict[str, str] = field(default_factory=dict)
    list_subscriber_count: int | None = None
    list_hidden: bool = False


class AliasDedupSearchRunner:
    """Run ``search.list`` for a short outlier list and union the video ids.

    Parameters
    ----------
    search_list:
        Injected ``search.list``. Called as ``search_list(query)`` where
        ``query`` is one alias string. Returns a YouTube ``searchListResponse``
        mapping (``items``) or a bare sequence of those items.
    videos_list:
        Injected ``videos.list``. Called as ``videos_list(video_ids)`` with at
        most 50 ids. Returns a ``videoListResponse`` mapping or a bare sequence.
        Live ``videos.list`` statistics do not include channel
        ``subscriberCount`` (that field belongs to ``channels.list``, which
        this runner does not call). The injected payload must carry
        ``statistics.subscriberCount`` (or ``snippet.subscriberCount``) for the
        spillover band check. Hidden counts (``hiddenSubscriberCount``) are
        not candidates.
    """

    def __init__(self, search_list: SearchList, videos_list: VideosList) -> None:
        if not callable(search_list) or not callable(videos_list):
            raise TypeError("search_list and videos_list must be injected callables")
        self._search_list = search_list
        self._videos_list = videos_list

    def run(
        self,
        candidates: Sequence[OutlierCandidate | Mapping[str, object]],
        *,
        search_units_remaining: int,
        known_channel_ids: Sequence[str] | None = None,
    ) -> SearchRunResult:
        """Search the shortlist, union video ids, and return spillover channels.

        ``search_units_remaining`` is a **call** budget. ``<= 15`` holds the
        whole run: no ``search.list`` and no ``videos.list``.
        """

        remaining = _require_call_budget(search_units_remaining)
        known = frozenset(known_channel_ids or ())
        considered, queries, candidates_skipped = _plan_queries(candidates)

        if remaining <= YT_SEARCH_CALL_RESERVE:
            return _empty_result(
                reserve_held=True,
                reason=RESERVE_HELD_REASON,
                skipped=tuple(queries),
                candidates_considered=len(considered),
                candidates_skipped=candidates_skipped,
                call_budget=remaining,
            )

        allowed = min(
            MAX_SEARCH_CALLS_PER_RUN,
            remaining - YT_SEARCH_CALL_RESERVE,
            len(queries),
        )
        to_run = queries[:allowed]
        skipped = tuple(queries[allowed:])
        self._videos_list_calls = 0
        videos = self._collect_videos(to_run)
        if videos:
            self._attach_video_statistics(videos)
        spillover = _spillover_channels(videos, known)
        search_calls = len(to_run)
        return SearchRunResult(
            reserve_held=False,
            reason="",
            search_calls=search_calls,
            videos_list_calls=self._videos_list_calls,
            videos=tuple(_finish_video(video) for video in videos.values()),
            spillover_candidates=tuple(spillover),
            alias_queries_run=tuple(to_run),
            alias_queries_skipped=skipped,
            candidates_considered=len(considered),
            candidates_skipped=candidates_skipped,
            call_budget_before=remaining,
            call_budget_after=remaining - search_calls,
            real_api_search_quota_units=search_calls * SEARCH_LIST_QUOTA_UNITS,
        )

    def _collect_videos(self, queries: Sequence[str]) -> dict[str, _VideoAcc]:
        videos: dict[str, _VideoAcc] = {}
        for index, query in enumerate(queries):
            if index >= MAX_SEARCH_CALLS_PER_RUN:
                break
            payload = self._search_list(query)
            for item in _items(payload):
                video_id = _video_id(item)
                if video_id is None:
                    continue
                snippet = _mapping(item.get("snippet"))
                acc = videos.get(video_id)
                if acc is None:
                    acc = _VideoAcc(
                        video_id=video_id,
                        channel_id=_text(snippet.get("channelId")),
                        title=_text(snippet.get("title")),
                        published_at=_text(snippet.get("publishedAt")),
                        queries=[],
                        search_subscriber_count=_subscriber_count(snippet),
                        search_hidden=_is_hidden(snippet),
                    )
                    videos[video_id] = acc
                if query not in acc.queries:
                    acc.queries.append(query)
        return videos

    def _attach_video_statistics(self, videos: dict[str, _VideoAcc]) -> None:
        ordered_ids = list(videos)
        for batch in _chunks(ordered_ids, VIDEOS_LIST_BATCH_SIZE):
            self._videos_list_calls += 1
            payload = self._videos_list(tuple(batch))
            for item in _items(payload):
                video_id = _listed_video_id(item)
                acc = videos.get(video_id) if video_id else None
                if acc is None:
                    continue
                snippet = _mapping(item.get("snippet"))
                raw_statistics = _mapping(item.get("statistics"))
                channel_id = _text(snippet.get("channelId"))
                title = _text(snippet.get("title"))
                published_at = _text(snippet.get("publishedAt"))
                if channel_id:
                    acc.channel_id = channel_id
                if title:
                    acc.title = title
                if published_at:
                    acc.published_at = published_at
                acc.statistics = _string_map(raw_statistics)
                acc.list_hidden = _is_hidden(raw_statistics) or _is_hidden(snippet)
                if acc.list_hidden:
                    acc.list_subscriber_count = None
                else:
                    acc.list_subscriber_count = _subscriber_count(raw_statistics)
                    if acc.list_subscriber_count is None:
                        acc.list_subscriber_count = _subscriber_count(snippet)


def _finish_video(acc: _VideoAcc) -> DedupedVideo:
    statistics = acc.statistics
    view_count = _parse_count(statistics.get("viewCount")) if statistics else None
    return DedupedVideo(
        video_id=acc.video_id,
        channel_id=acc.channel_id,
        title=acc.title,
        published_at=acc.published_at,
        alias_queries=tuple(acc.queries),
        view_count=view_count,
        statistics=MappingProxyType(dict(statistics)),
    )


def _spillover_channels(
    videos: Mapping[str, _VideoAcc],
    known_channel_ids: frozenset[str],
) -> list[SpilloverCandidate]:
    """Unknown channels whose subscriber count sits inside 2_000..120_000.

    The first ``videos.list`` count wins when several videos share a channel.
    Channels already on the watchlist are left out. This function only builds
    the return value; it does not write a watchlist row.
    """

    grouped: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for acc in videos.values():
        channel_id = acc.channel_id
        if not channel_id or channel_id in known_channel_ids:
            continue
        if acc.list_hidden or acc.search_hidden:
            continue
        count = acc.list_subscriber_count
        if count is None:
            count = acc.search_subscriber_count
        if count is None:
            continue
        if count < SUBSCRIBER_COUNT_MIN or count > SUBSCRIBER_COUNT_MAX:
            continue
        bucket = grouped.get(channel_id)
        if bucket is None:
            grouped[channel_id] = [acc.video_id]
            counts[channel_id] = count
        elif acc.video_id not in bucket:
            bucket.append(acc.video_id)
    return [
        SpilloverCandidate(
            channel_id=channel_id,
            subscriber_count=counts[channel_id],
            source_video_ids=tuple(video_ids),
        )
        for channel_id, video_ids in grouped.items()
    ]


def _plan_queries(
    candidates: Sequence[OutlierCandidate | Mapping[str, object]],
) -> tuple[tuple[OutlierCandidate, ...], list[str], int]:
    raw = list(candidates)
    considered = tuple(_coerce_candidate(raw[index], index) for index in range(min(len(raw), MAX_CANDIDATES_PER_RUN)))
    candidates_skipped = max(0, len(raw) - MAX_CANDIDATES_PER_RUN)
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in considered:
        for alias in candidate.aliases:
            query = " ".join(str(alias).split())
            if not query or query in seen:
                continue
            seen.add(query)
            queries.append(query)
    return considered, queries, candidates_skipped


def _coerce_candidate(raw: OutlierCandidate | Mapping[str, object], index: int) -> OutlierCandidate:
    if isinstance(raw, OutlierCandidate):
        aliases = tuple(" ".join(str(alias).split()) for alias in raw.aliases)
        aliases = tuple(alias for alias in aliases if alias)
        return OutlierCandidate(str(raw.candidate_id), aliases)
    if isinstance(raw, Mapping):
        candidate_id = raw.get("candidate_id", raw.get("id", f"candidate-{index}"))
        alias_raw = raw.get("aliases", raw.get("queries", ()))
        if isinstance(alias_raw, str):
            alias_seq: Sequence[object] = (alias_raw,)
        elif isinstance(alias_raw, Sequence) and not isinstance(alias_raw, (bytes, bytearray)):
            alias_seq = alias_raw
        else:
            raise TypeError("candidate aliases must be a string or a sequence of strings")
        aliases = tuple(" ".join(str(alias).split()) for alias in alias_seq)
        aliases = tuple(alias for alias in aliases if alias)
        return OutlierCandidate(str(candidate_id), aliases)
    raise TypeError(
        "each candidate must be an OutlierCandidate or a mapping with candidate_id and aliases"
    )


def _empty_result(
    *,
    reserve_held: bool,
    reason: str,
    skipped: tuple[str, ...],
    candidates_considered: int,
    candidates_skipped: int,
    call_budget: int,
) -> SearchRunResult:
    return SearchRunResult(
        reserve_held=reserve_held,
        reason=reason,
        search_calls=0,
        videos_list_calls=0,
        videos=(),
        spillover_candidates=(),
        alias_queries_run=(),
        alias_queries_skipped=skipped,
        candidates_considered=candidates_considered,
        candidates_skipped=candidates_skipped,
        call_budget_before=call_budget,
        call_budget_after=call_budget,
        real_api_search_quota_units=0,
    )


def _require_call_budget(search_units_remaining: int) -> int:
    if isinstance(search_units_remaining, bool) or not isinstance(search_units_remaining, int):
        raise TypeError("search_units_remaining must be an int call budget")
    if search_units_remaining < 0:
        raise ValueError("search_units_remaining must be >= 0")
    return search_units_remaining


def _items(payload: object) -> list[Mapping[str, object]]:
    if payload is None:
        return []
    if isinstance(payload, Mapping):
        raw_items = payload.get("items", [])
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        raw_items = payload
    else:
        raise TypeError("injected list call must return a mapping with items or a sequence of items")
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
        raise TypeError("injected list payload items must be a sequence")
    return [item for item in raw_items if isinstance(item, Mapping)]


def _video_id(item: Mapping[str, object]) -> str | None:
    ident = item.get("id")
    if isinstance(ident, str):
        text = ident.strip()
        return text or None
    if isinstance(ident, Mapping):
        kind = ident.get("kind")
        if kind not in (None, "youtube#video"):
            return None
        video_id = ident.get("videoId")
        if isinstance(video_id, str) and video_id.strip():
            return video_id.strip()
    return None


def _listed_video_id(item: Mapping[str, object]) -> str | None:
    ident = item.get("id")
    if isinstance(ident, str) and ident.strip():
        return ident.strip()
    return _video_id(item)


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, str] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or raw is None:
            continue
        out[str(key)] = raw if isinstance(raw, str) else str(raw)
    return out


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _subscriber_count(mapping: Mapping[str, object]) -> int | None:
    if _is_hidden(mapping):
        return None
    for key in ("subscriberCount", "channelSubscriberCount"):
        if key in mapping:
            return _parse_count(mapping.get(key))
    return None


def _is_hidden(mapping: Mapping[str, object]) -> bool:
    flag = mapping.get("hiddenSubscriberCount")
    return flag is True or flag == "true"


def _parse_count(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            return None
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.isdigit():
            return int(text)
    return None


def _chunks(ids: Sequence[str], size: int) -> list[list[str]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    return [list(ids[start : start + size]) for start in range(0, len(ids), size)]
