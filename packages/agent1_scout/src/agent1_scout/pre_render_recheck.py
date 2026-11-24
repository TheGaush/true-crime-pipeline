"""Per-day pre-render saturation re-check and sunk-cost guard.

``PreRenderSaturationGate`` runs before the first Flow spend and again before
each later Batch Desk day. One check is exactly three ``search.list`` calls,
drawn from the 15-call daily reserve. The search client is injected. This
module never opens a socket.

Abort ``ABORTED_COPYCAT_WAVE`` when ``N_14d_wave > 3`` or
``has_90d_200k_kill == 1``.

Exception: if ``spent_credits_pct > 0.50`` and ``N_14d_wave <= 5`` and no
Tier-1 giant was in the three-call union, set ``sunk_cost_override = 1`` and
finish the episode.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

SEARCH_LIST_CALLS_PER_CHECK = 3
DAILY_RECHECK_RESERVE = 15

WAVE_ABORT_ABOVE = 3
SUNK_COST_SPENT_ABOVE = 0.50
SUNK_COST_WAVE_AT_MOST = 5
KILL_VIEWS_EXCLUSIVE = 200_000

MS_PER_DAY = 24 * 60 * 60 * 1000
DAYS_14 = 14
DAYS_90 = 90

ABORTED_COPYCAT_WAVE = "ABORTED_COPYCAT_WAVE"
DECISION_FINISH = "FINISH"
MOMENT_BEFORE_FLOW_SPEND = "BEFORE_FLOW_SPEND"
MOMENT_BATCH_DESK_DAY = "BATCH_DESK_DAY"
PHASE_PRE_RENDER_DAILY_RECHECK = "PRE_RENDER_DAILY_RECHECK"

# Same canonical names as the Tier-1 registry (Task 021). Matching is local.
_TIER1_TITLES: tuple[str, ...] = (
    "EWU",
    "EWU Criminal Psychology",
    "Exploring With U",
    "JCS",
    "JCS - Criminal Psychology",
    "That Chapter",
    "48 Hours",
    "CBS 48 Hours",
    "Dateline NBC",
    "Dateline",
    "20/20",
    "ABC 20/20",
    "Law&Crime",
    "Law & Crime Network",
)
_TIER1_CHANNEL_IDS = frozenset(
    {
        "UCewuTier1Fixture01",
        "UCjcsTier1Fixture01",
        "UCthatChapterFixture01",
        "UC48HoursFixture01",
        "UCDatelineFixture01",
        "UC2020Fixture01",
        "UCLawCrimeFixture01",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_TRUE_FLAGS = frozenset({True, 1, "1", "true", "TRUE"})


class RecheckCallLimitExceeded(Exception):
    """A single pre-render check tried to call ``search.list`` more than 3 times."""


class SearchReserveExhausted(Exception):
    """The 15-call daily reserve cannot cover another 3-call re-check."""


class SearchListClient(Protocol):
    """Injected ``search.list``. One call receives one query string."""

    def search_list(self, query: str) -> Mapping[str, object] | Sequence[object]:
        """Return a ``searchListResponse`` mapping or a sequence of items."""


def normalize_channel_title(title: str) -> str:
    """Casefold, strip punctuation, and collapse whitespace."""

    folded = title.casefold().strip()
    without_punct = _PUNCT_RE.sub("", folded)
    return " ".join(without_punct.split())


_TIER1_TITLE_INDEX = frozenset(normalize_channel_title(title) for title in _TIER1_TITLES)


@dataclass
class SearchListReserve:
    """Daily pool of 15 ``search.list`` calls kept for pre-render re-checks.

    Each check draws 3. Ordinary scouting does not spend this pool; that floor
    lives in the quota tracker. This object is the re-check side of the same
    15-call reserve.
    """

    daily_limit: int = DAILY_RECHECK_RESERVE
    remaining: int = DAILY_RECHECK_RESERVE

    def __post_init__(self) -> None:
        _require_call_count(self.daily_limit, "daily_limit")
        _require_call_count(self.remaining, "remaining")
        if self.daily_limit != DAILY_RECHECK_RESERVE:
            raise ValueError(
                f"pre-render search reserve is {DAILY_RECHECK_RESERVE} calls"
            )
        if self.remaining > self.daily_limit:
            raise ValueError("reserve remaining cannot exceed the daily limit")

    def draw(self, calls: int = SEARCH_LIST_CALLS_PER_CHECK) -> int:
        """Subtract one re-check from the reserve and return the new balance."""

        if calls != SEARCH_LIST_CALLS_PER_CHECK:
            raise RecheckCallLimitExceeded(
                "a pre-render re-check draws exactly "
                f"{SEARCH_LIST_CALLS_PER_CHECK} search.list calls"
            )
        if self.remaining < calls:
            raise SearchReserveExhausted(
                "pre-render reserve has "
                f"{self.remaining} search.list calls left; a check needs {calls}"
            )
        self.remaining -= calls
        return self.remaining


@dataclass
class BoundedSearchListClient:
    """Refuse ``search.list`` after 3 calls inside one re-check."""

    inner: SearchListClient
    limit: int = SEARCH_LIST_CALLS_PER_CHECK
    calls: int = 0

    def __post_init__(self) -> None:
        if self.limit != SEARCH_LIST_CALLS_PER_CHECK:
            raise ValueError(
                f"one pre-render check allows {SEARCH_LIST_CALLS_PER_CHECK} calls"
            )
        if self.calls != 0:
            raise ValueError("a bounded search client starts at zero calls")

    def search_list(self, query: str) -> Mapping[str, object] | Sequence[object]:
        if self.calls >= self.limit:
            raise RecheckCallLimitExceeded(
                "search.list refused: a pre-render re-check allows "
                f"{self.limit} calls"
            )
        self.calls += 1
        return self.inner.search_list(query)


@dataclass(frozen=True, slots=True)
class PreRenderRecheckResult:
    """Decision for one day, after exactly three ``search.list`` calls."""

    moment: str
    batch_day: int
    phase: str
    decision: str
    aborted: int
    sunk_cost_override: int
    n_14d_wave: int
    has_90d_200k_kill: int
    tier1_giant_hit: int
    spent_credits_pct: float
    search_list_calls: int
    reserve_drawn: int
    reserve_remaining: int
    queries: tuple[str, ...]
    checked_at_ms: int

    @property
    def episode_state(self) -> str | None:
        """Terminal episode state when the check aborts. ``None`` means finish."""

        if self.decision == ABORTED_COPYCAT_WAVE:
            return ABORTED_COPYCAT_WAVE
        return None


@dataclass
class _VideoAcc:
    video_id: str
    channel_id: str
    channel_title: str
    published_at_ms: int
    view_count: int
    tier1: bool


class PreRenderSaturationGate:
    """Re-check copycat saturation before Flow spend and before each later day.

    Parameters
    ----------
    search_client:
        Injected client. ``search_list(query)`` is one ``search.list`` call.
        View counts are read from the returned items (``statistics.viewCount``
        or ``viewCount``). This gate does not call ``videos.list``.
    reserve:
        The 15-call daily re-check reserve. A new gate starts at 15.
    """

    def __init__(
        self,
        search_client: SearchListClient,
        *,
        reserve: SearchListReserve | None = None,
    ) -> None:
        if not callable(getattr(search_client, "search_list", None)):
            raise TypeError("search client must provide search_list(query)")
        self._client = search_client
        self.reserve = reserve if reserve is not None else SearchListReserve()

    @property
    def reserve_remaining(self) -> int:
        return self.reserve.remaining

    def before_flow_spend(
        self,
        *,
        queries: Sequence[str],
        now_ms: int,
        spent_credits_pct: float = 0.0,
    ) -> PreRenderRecheckResult:
        """Day 1. Run the 3-call re-check before any Flow credit is spent."""

        return self.recheck(
            batch_day=1,
            queries=queries,
            spent_credits_pct=spent_credits_pct,
            now_ms=now_ms,
        )

    def before_batch_desk_day(
        self,
        batch_day: int,
        *,
        queries: Sequence[str],
        spent_credits_pct: float,
        now_ms: int,
    ) -> PreRenderRecheckResult:
        """A later Batch Desk day. ``batch_day`` is 2, 3, ..."""

        if isinstance(batch_day, bool) or not isinstance(batch_day, int):
            raise TypeError("batch_day must be an int")
        if batch_day < 2:
            raise ValueError("Batch Desk re-check starts on day 2")
        return self.recheck(
            batch_day=batch_day,
            queries=queries,
            spent_credits_pct=spent_credits_pct,
            now_ms=now_ms,
        )

    def recheck(
        self,
        *,
        batch_day: int,
        queries: Sequence[str],
        spent_credits_pct: float,
        now_ms: int,
    ) -> PreRenderRecheckResult:
        """Draw 3 reserve calls, run them, and abort or finish."""

        moment = _moment_for_day(batch_day)
        planned = _require_three_queries(queries)
        spent = _require_spent_pct(spent_credits_pct)
        checked_at = _require_now_ms(now_ms)
        # Draw before the calls so a check that cannot be paid for never
        # touches search.list. draw() itself refuses a balance under 3.
        self.reserve.draw(SEARCH_LIST_CALLS_PER_CHECK)
        bound = BoundedSearchListClient(self._client)
        pages: list[object] = []
        for query in planned:
            pages.append(bound.search_list(query))
        if bound.calls != SEARCH_LIST_CALLS_PER_CHECK:
            raise RecheckCallLimitExceeded(
                "pre-render re-check must issue exactly "
                f"{SEARCH_LIST_CALLS_PER_CHECK} search.list calls"
            )

        videos = _union_videos(pages)
        n_14d_wave, has_90d_200k_kill, tier1_giant_hit = _score(videos, checked_at)
        decision, sunk_cost_override, aborted = decide_pre_render(
            n_14d_wave=n_14d_wave,
            has_90d_200k_kill=has_90d_200k_kill,
            tier1_giant_hit=tier1_giant_hit,
            spent_credits_pct=spent,
        )
        return PreRenderRecheckResult(
            moment=moment,
            batch_day=batch_day,
            phase=PHASE_PRE_RENDER_DAILY_RECHECK,
            decision=decision,
            aborted=aborted,
            sunk_cost_override=sunk_cost_override,
            n_14d_wave=n_14d_wave,
            has_90d_200k_kill=has_90d_200k_kill,
            tier1_giant_hit=tier1_giant_hit,
            spent_credits_pct=spent,
            search_list_calls=bound.calls,
            reserve_drawn=SEARCH_LIST_CALLS_PER_CHECK,
            reserve_remaining=self.reserve.remaining,
            queries=planned,
            checked_at_ms=checked_at,
        )


def decide_pre_render(
    *,
    n_14d_wave: int,
    has_90d_200k_kill: int,
    tier1_giant_hit: int,
    spent_credits_pct: float,
) -> tuple[str, int, int]:
    """Return ``(decision, sunk_cost_override, aborted)``.

    The sunk-cost exception finishes the episode only when more than half the
    credits are already spent, the 14-day wave is still at most 5, and the
    three-call union contains no Tier-1 giant.
    """

    threat = n_14d_wave > WAVE_ABORT_ABOVE or has_90d_200k_kill == 1
    sunk_cost = (
        spent_credits_pct > SUNK_COST_SPENT_ABOVE
        and n_14d_wave <= SUNK_COST_WAVE_AT_MOST
        and tier1_giant_hit == 0
    )
    if threat and sunk_cost:
        return DECISION_FINISH, 1, 0
    if threat:
        return ABORTED_COPYCAT_WAVE, 0, 1
    return DECISION_FINISH, 0, 0


def _moment_for_day(batch_day: int) -> str:
    if isinstance(batch_day, bool) or not isinstance(batch_day, int):
        raise TypeError("batch_day must be an int")
    if batch_day == 1:
        return MOMENT_BEFORE_FLOW_SPEND
    if batch_day >= 2:
        return MOMENT_BATCH_DESK_DAY
    raise ValueError("batch_day must be >= 1")


def _require_three_queries(queries: Sequence[str]) -> tuple[str, ...]:
    if isinstance(queries, (str, bytes)) or not isinstance(queries, Sequence):
        raise TypeError("queries must be a sequence of 3 search strings")
    if len(queries) > SEARCH_LIST_CALLS_PER_CHECK:
        raise RecheckCallLimitExceeded(
            "search.list refused: a pre-render re-check allows "
            f"{SEARCH_LIST_CALLS_PER_CHECK} calls"
        )
    if len(queries) != SEARCH_LIST_CALLS_PER_CHECK:
        raise ValueError(
            "a pre-render re-check runs exactly "
            f"{SEARCH_LIST_CALLS_PER_CHECK} search.list calls"
        )
    cleaned: list[str] = []
    for query in queries:
        if not isinstance(query, str):
            raise TypeError("each search query must be a string")
        text = query.strip()
        if not text:
            raise ValueError("search queries must be non-empty")
        cleaned.append(text)
    return tuple(cleaned)


def _require_spent_pct(spent_credits_pct: float) -> float:
    if isinstance(spent_credits_pct, bool) or not isinstance(
        spent_credits_pct, (int, float)
    ):
        raise TypeError("spent_credits_pct must be a real number")
    spent = float(spent_credits_pct)
    if spent != spent or spent < 0.0:  # NaN, or negative
        raise ValueError("spent_credits_pct must be >= 0")
    return spent


def _require_now_ms(now_ms: int) -> int:
    if isinstance(now_ms, bool) or not isinstance(now_ms, int):
        raise TypeError("now_ms must be an int")
    if now_ms < 0:
        raise ValueError("now_ms must be >= 0")
    return now_ms


def _require_call_count(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int")
    if value < 0:
        raise ValueError(f"{label} must be >= 0")


def _union_videos(pages: Sequence[object]) -> dict[str, _VideoAcc]:
    videos: dict[str, _VideoAcc] = {}
    for page in pages:
        for item in _items(page):
            video = _video_from_item(item)
            if video is None:
                continue
            current = videos.get(video.video_id)
            if current is None:
                videos[video.video_id] = video
                continue
            if video.view_count > current.view_count:
                current.view_count = video.view_count
            if video.tier1:
                current.tier1 = True
            if video.published_at_ms < current.published_at_ms:
                current.published_at_ms = video.published_at_ms
    return videos


def _score(
    videos: Mapping[str, _VideoAcc],
    now_ms: int,
) -> tuple[int, int, int]:
    n_14d_wave = 0
    has_90d_200k_kill = 0
    tier1_giant_hit = 0
    for video in videos.values():
        age_days = (now_ms - video.published_at_ms) / MS_PER_DAY
        if 0 <= age_days <= DAYS_14:
            n_14d_wave += 1
        if video.view_count > KILL_VIEWS_EXCLUSIVE and 0 <= age_days <= DAYS_90:
            has_90d_200k_kill = 1
        if video.tier1:
            tier1_giant_hit = 1
    return n_14d_wave, has_90d_200k_kill, tier1_giant_hit


def _items(payload: object) -> list[Mapping[str, object]]:
    if payload is None:
        return []
    if isinstance(payload, Mapping):
        raw_items = payload.get("items", [])
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        raw_items = payload
    else:
        raise TypeError(
            "search.list must return a mapping with items or a sequence of items"
        )
    if isinstance(raw_items, (str, bytes)) or not isinstance(raw_items, Sequence):
        raise TypeError("search.list items must be a sequence")
    return [item for item in raw_items if isinstance(item, Mapping)]


def _video_from_item(item: Mapping[str, object]) -> _VideoAcc | None:
    video_id = _video_id(item)
    if video_id is None:
        return None
    snippet = _mapping(item.get("snippet"))
    channel_id = _text(snippet.get("channelId")) or _text(item.get("channelId"))
    channel_title = _text(snippet.get("channelTitle")) or _text(item.get("channelTitle"))
    return _VideoAcc(
        video_id=video_id,
        channel_id=channel_id,
        channel_title=channel_title,
        published_at_ms=_published_at_ms(item, snippet, video_id),
        view_count=_view_count(item, snippet),
        tier1=_is_tier1(item, snippet, channel_id, channel_title),
    )


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
    video_id = item.get("videoId")
    if isinstance(video_id, str) and video_id.strip():
        return video_id.strip()
    return None


def _published_at_ms(
    item: Mapping[str, object],
    snippet: Mapping[str, object],
    video_id: str,
) -> int:
    for source in (item, snippet):
        for key in ("published_at_ms", "publishedAtMs"):
            if key in source:
                return _coerce_ms(source.get(key), video_id)
    for source in (snippet, item):
        for key in ("publishedAt", "published_at"):
            if key in source and source.get(key) not in (None, ""):
                return _coerce_published(source.get(key), video_id)
    raise ValueError(f"search item {video_id!r} is missing publishedAt")


def _coerce_published(value: object, video_id: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"search item {video_id!r} has a bad publishedAt")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        return _parse_iso_ms(value.strip(), video_id)
    raise ValueError(f"search item {video_id!r} has a bad publishedAt")


def _coerce_ms(value: object, video_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"search item {video_id!r} has a bad published_at_ms")
    return value


def _parse_iso_ms(text: str, video_id: str) -> int:
    parsed = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        moment = datetime.fromisoformat(parsed)
    except ValueError as exc:
        raise ValueError(f"search item {video_id!r} has a bad publishedAt") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def _view_count(item: Mapping[str, object], snippet: Mapping[str, object]) -> int:
    statistics = _mapping(item.get("statistics"))
    for source in (statistics, snippet, item):
        for key in ("viewCount", "view_count", "views"):
            if key in source:
                parsed = _parse_count(source.get(key))
                if parsed is not None:
                    return parsed
    return 0


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


def _is_tier1(
    item: Mapping[str, object],
    snippet: Mapping[str, object],
    channel_id: str,
    channel_title: str,
) -> bool:
    if channel_id in _TIER1_CHANNEL_IDS:
        return True
    if channel_title and normalize_channel_title(channel_title) in _TIER1_TITLE_INDEX:
        return True
    for source in (item, snippet):
        for key in ("tier1Giant", "tier1_giant", "is_tier1_giant"):
            if source.get(key) in _TRUE_FLAGS:
                return True
    return False


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
