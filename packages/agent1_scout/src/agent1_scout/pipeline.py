"""Offline Agent 1 scout service.

Pure trap rules for the recorded-corpus suite. Scout modules from other
branches are not imported. Nothing in this module opens a socket.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

VIEWS_90D_KILL = 200_000
VIEWS_MEGA = 500_000
VIEWS_RECENT = 50_000
DAYS_14 = 14
DAYS_90 = 90
DAYS_18_MO = 18 * 30
DAYS_36_MO = 36 * 30
TTL_DAYS = 30
SI_HARD_KILL = 55
SI_SWEET_SPOT = 35
KILL_90D = "HARD_KILL_RECENT_DEMAND_EXHAUSTED"
ABORTED_COPYCAT_WAVE = "ABORTED_COPYCAT_WAVE"
FINISH = "FINISH"
TRACK_B = "TRACK_B_FOIA_RADAR"
LEAD_ONLY = "LEAD_ONLY"
BUCKETS = ("N_14d_excl", "N_mega_excl", "N_recent_excl")
SEED_FIELDS = (
    "suspect_names",
    "victim_names",
    "incident_date_or_year",
    "county_state",
    "docket_ids",
    "unanswered_comment_questions",
)
YT_SEED_KEYS = frozenset(
    {
        "yt_title",
        "yt_description",
        "yt_tags",
        "yt_metadata",
        "views_count",
        "outlier_ratio",
    }
)
TABLOID_TOKENS = (
    "chopped",
    "mutilat",
    "dismember",
    "gruesome",
    "bloodbath",
    "hacked up",
    "you won't believe",
    "shocking",
)
BLOCKED_DISPOSITIONS = frozenset(
    {"DENIED", "REVERSED", "REMANDED", "VACATED", "ACQUITTED", "PENDING"}
)
RESTRICTED_PLAYBACK = frozenset(
    {"PLAYBACK_RESTRICTED", "AGE_GATED", "AGE_RESTRICTED"}
)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_day(value: str) -> date:
    return date.fromisoformat(value)


def video_age_days(video: Mapping[str, object], today: date | None = None) -> int:
    if "age_days" in video:
        return int(video["age_days"])  # type: ignore[arg-type]
    published = parse_day(str(video["published_on"]))
    if today is None:
        raise ValueError("today is required when age_days is absent")
    return (today - published).days


def exclusive_bucket(age_days: int, views: int, tier1: bool) -> str | None:
    """Highest-priority saturation bucket. A video lands in at most one."""
    if age_days <= DAYS_14:
        return "N_14d_excl"
    mega = views > VIEWS_MEGA or tier1
    if mega and age_days <= DAYS_36_MO:
        return "N_mega_excl"
    if views > VIEWS_RECENT and age_days <= DAYS_18_MO:
        return "N_recent_excl"
    return None


def mega_decay(age_days: int) -> float:
    if age_days <= DAYS_18_MO:
        return 1.0
    if age_days <= DAYS_36_MO:
        return 0.5
    return 0.0


def recent_demand_exhausted(views: int, age_days: int) -> bool:
    """Any upload over 200K views inside 90 days is an instant kill."""
    return age_days <= DAYS_90 and views > VIEWS_90D_KILL


def saturation_index(n_mega_decayed: float, n_recent: int, n_14d: int) -> int:
    raw = 25 * n_mega_decayed + 12 * n_recent + 8 * n_14d
    return min(100, round(raw))


def safe_title_ok(title: str) -> int:
    """1 when an editorial title can carry the hook. 0 for tabloid titles."""
    letters = [char for char in title if char.isalpha()]
    if letters and all(char.isupper() for char in letters):
        return 0
    if "?!" in title or "!!" in title:
        return 0
    folded = title.casefold()
    if any(token in folded for token in TABLOID_TOKENS):
        return 0
    return 1


def delete_transcript_buffer(buffer: bytearray | list[object]) -> None:
    """Wipe caller-owned transcript bytes. The buffer object is emptied."""
    if isinstance(buffer, bytearray):
        for index in range(len(buffer)):
            buffer[index] = 0
        buffer.clear()
        return
    if isinstance(buffer, list):
        for index in range(len(buffer)):
            buffer[index] = ""
        buffer.clear()
        return
    raise TypeError("transcript buffer must be a bytearray or list")


def seal_seed_packet(
    leads: Mapping[str, object],
    transcript_buffer: bytearray | list[object],
) -> dict[str, object]:
    """Copy lookup keys only, then delete the transcript buffer."""
    try:
        return {
            "lead_classification": LEAD_ONLY,
            "suspect_names": list(leads["suspect_names"]),  # type: ignore[arg-type]
            "victim_names": list(leads["victim_names"]),  # type: ignore[arg-type]
            "incident_date_or_year": leads["incident_date_or_year"],
            "county_state": leads["county_state"],
            "docket_ids": list(leads["docket_ids"]),  # type: ignore[arg-type]
            "unanswered_comment_questions": list(
                leads["unanswered_comment_questions"]  # type: ignore[arg-type]
            ),
        }
    finally:
        delete_transcript_buffer(transcript_buffer)


def age_restricted(recorded: Mapping[str, object]) -> bool:
    if recorded.get("age_restricted") is True:
        return True
    playback = str(recorded.get("playback") or "").upper()
    return playback in RESTRICTED_PLAYBACK


def payload_age_days(record: Mapping[str, object], as_of: date) -> int:
    return (as_of - parse_day(str(record["created_on"]))).days


def purge_yt_payload(record: Mapping[str, object], as_of: date) -> dict[str, object]:
    """Drop YouTube-derived fields once the payload is older than 30 days."""
    age = payload_age_days(record, as_of)
    seed = dict(record.get("seed_packet_json") or {})
    purged = {
        "record_id": record["record_id"],
        "age_days": age,
        "status": record["status"],
        "raw_yt_payload_json": record.get("raw_yt_payload_json"),
        "views_count": record.get("views_count"),
        "outlier_ratio": record.get("outlier_ratio"),
        "seed_packet_json": seed,
    }
    if age > TTL_DAYS:
        purged["raw_yt_payload_json"] = None
        purged["views_count"] = None
        purged["outlier_ratio"] = None
        for key in list(seed):
            if key in YT_SEED_KEYS or str(key).startswith("yt_"):
                del seed[key]
        if record.get("status") != "CONSUMED":
            purged["status"] = "EXPIRED_TOS_PURGED"
    return purged


def tier1_hit(scenario: Mapping[str, object]) -> bool:
    if scenario.get("tier1_hit") is True:
        return True
    copycats = scenario.get("copycats") or []
    return any(
        isinstance(item, Mapping) and item.get("channel_tier") == "tier1"
        for item in copycats  # type: ignore[union-attr]
    )


def evaluate_sunk_cost(scenario: Mapping[str, object]) -> dict[str, object]:
    """Abort a copycat wave unless spend is already past half and the wave is small.

    Abort when N_14d_wave > 3. Finish anyway when spent_credits_pct > 0.50,
    N_14d_wave <= 5, and no Tier-1 giant is in the wave.
    """
    n_wave = int(scenario["n_14d_wave"])  # type: ignore[arg-type]
    spent = float(scenario["spent_credits_pct"])  # type: ignore[arg-type]
    copycats = scenario.get("copycats")
    if isinstance(copycats, Sequence) and len(copycats) != n_wave:
        raise ValueError("n_14d_wave must match the copycat count")
    giant = tier1_hit(scenario)
    must_abort = n_wave > 3
    override = spent > 0.50 and n_wave <= 5 and not giant
    if must_abort and not override:
        decision = ABORTED_COPYCAT_WAVE
        flag = 0
    else:
        decision = FINISH
        flag = 1 if must_abort and override else 0
    return {
        "scenario_id": scenario["scenario_id"],
        "shift_day": int(scenario["shift_day"]),  # type: ignore[arg-type]
        "spent_credits_pct": spent,
        "n_14d_wave": n_wave,
        "tier1_hit": giant,
        "decision": decision,
        "sunk_cost_override": flag,
    }


def is_track_b_winner(row: Mapping[str, object]) -> bool:
    if row.get("track") != TRACK_B:
        return False
    if row.get("substantive") is not True:
        return False
    disposition = str(row.get("disposition") or "").upper()
    return disposition not in BLOCKED_DISPOSITIONS


@dataclass(frozen=True)
class VideoScore:
    video_id: str
    views: int
    age_days: int
    bucket: str | None
    hard_kill: bool
    kill_reason: str | None
    mega_decay: float

    @property
    def buckets(self) -> tuple[str, ...]:
        if self.bucket is None:
            return ()
        return (self.bucket,)


@dataclass(frozen=True)
class SaturationReport:
    scores: tuple[VideoScore, ...]
    counts: dict[str, int]
    n_mega_decayed: float
    saturation_index: int


@dataclass(frozen=True)
class NightlyPoll:
    methods: tuple[str, ...]
    search_list_calls: int
    video_ids: tuple[str, ...]
    excluded_shorts: tuple[str, ...]


@dataclass(frozen=True)
class XrayInspection:
    fallback: str
    playback: str
    methods: tuple[str, ...]
    caption_downloads: int
    mp4_downloads: int
    title: str
    description: str
    tags: tuple[str, ...]
    comment_leads: tuple[str, ...]
    lead_classification: str


@dataclass(frozen=True)
class PurgedRecord:
    record_id: str
    age_days: int
    status: str
    raw_yt_payload_json: object
    views_count: object
    outlier_ratio: object
    seed_packet_json: dict[str, object]


@dataclass(frozen=True)
class SunkCostDecision:
    scenario_id: str
    shift_day: int
    spent_credits_pct: float
    n_14d_wave: int
    tier1_hit: bool
    decision: str
    sunk_cost_override: int


@dataclass(frozen=True)
class TrackWinner:
    candidate_id: str
    track: str
    source: str


@dataclass(frozen=True)
class SlateSelection:
    track_a_killed: tuple[str, ...]
    track_a_survivors: tuple[str, ...]
    winners: tuple[TrackWinner, ...]


def score_video(video: Mapping[str, object], today: date | None = None) -> VideoScore:
    age = video_age_days(video, today)
    views = int(video["views"])  # type: ignore[arg-type]
    tier1 = bool(video.get("tier1"))
    bucket = exclusive_bucket(age, views, tier1)
    killed = recent_demand_exhausted(views, age)
    return VideoScore(
        video_id=str(video["video_id"]),
        views=views,
        age_days=age,
        bucket=bucket,
        hard_kill=killed,
        kill_reason=KILL_90D if killed else None,
        mega_decay=mega_decay(age) if bucket == "N_mega_excl" else 0.0,
    )


def score_corpus(videos: Sequence[Mapping[str, object]], today: date | None = None) -> SaturationReport:
    scores = tuple(score_video(video, today) for video in videos)
    counts = {name: 0 for name in BUCKETS}
    decayed = 0.0
    for score in scores:
        if score.bucket is None:
            continue
        counts[score.bucket] += 1
        if score.bucket == "N_mega_excl":
            decayed += score.mega_decay
    index = saturation_index(decayed, counts["N_recent_excl"], counts["N_14d_excl"])
    return SaturationReport(
        scores=scores,
        counts=counts,
        n_mega_decayed=decayed,
        saturation_index=index,
    )


def poll_uploads(corpus: Mapping[str, object]) -> NightlyPoll:
    """Nightly poll uses playlist items and videos.list only. search.list stays at 0."""
    methods: list[str] = []
    kept: list[str] = []
    shorts: list[str] = []
    details = corpus["video_details"]
    if not isinstance(details, Mapping):
        raise TypeError("video_details must be an object")
    channels = corpus["channels"]
    if not isinstance(channels, Sequence):
        raise TypeError("channels must be a list")
    for channel in channels:
        if not isinstance(channel, Mapping):
            raise TypeError("channel must be an object")
        methods.append("playlistItems.list")
        items = channel["playlist_items"]
        if not isinstance(items, Sequence):
            raise TypeError("playlist_items must be a list")
        ids = [str(item["video_id"]) for item in items if isinstance(item, Mapping)]
        for start in range(0, len(ids), 50):
            methods.append("videos.list")
            for video_id in ids[start : start + 50]:
                detail = details[video_id]
                if not isinstance(detail, Mapping):
                    raise TypeError("video detail must be an object")
                duration = int(detail["duration_sec"])  # type: ignore[arg-type]
                title = str(detail.get("title") or "")
                if duration < 600 or "#shorts" in title.casefold():
                    shorts.append(video_id)
                    continue
                kept.append(video_id)
    return NightlyPoll(
        methods=tuple(methods),
        search_list_calls=methods.count("search.list"),
        video_ids=tuple(kept),
        excluded_shorts=tuple(shorts),
    )


def inspect_restricted_xray(
    recorded: Mapping[str, object],
    download: Callable[[str], None] | None = None,
) -> XrayInspection:
    """Age-restricted playback falls back to metadata and comments.

    captions.download and mp4 retrieval are never invoked. `download` is
    the fetcher a caller can spy on; this path does not call it.
    """
    if not age_restricted(recorded):
        raise ValueError("x-ray record is not age-restricted")
    del download
    metadata = recorded.get("metadata")
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be an object")
    comments = recorded.get("comments") or []
    if not isinstance(comments, Sequence) or isinstance(comments, (str, bytes)):
        raise TypeError("comments must be a list")
    tags = metadata.get("tags") or []
    if not isinstance(tags, Sequence) or isinstance(tags, (str, bytes)):
        raise TypeError("tags must be a list")
    return XrayInspection(
        fallback="authorized_metadata",
        playback=str(recorded.get("playback") or "PLAYBACK_RESTRICTED"),
        methods=("videos.list", "commentThreads.list"),
        caption_downloads=0,
        mp4_downloads=0,
        title=str(metadata.get("title") or ""),
        description=str(metadata.get("description") or ""),
        tags=tuple(str(tag) for tag in tags),
        comment_leads=tuple(str(comment) for comment in comments),
        lead_classification=LEAD_ONLY,
    )


def select_slate(corpus: Mapping[str, object]) -> SlateSelection:
    """When every Track A candidate dies on the 90-day rule, return Track B."""
    track_a = corpus["track_a"]
    track_b = corpus["track_b"]
    if not isinstance(track_a, Sequence) or not isinstance(track_b, Sequence):
        raise TypeError("track lists must be arrays")
    killed: list[str] = []
    survivors: list[str] = []
    for row in track_a:
        if not isinstance(row, Mapping):
            raise TypeError("track A row must be an object")
        views = int(row["views"])  # type: ignore[arg-type]
        age = int(row["age_days"])  # type: ignore[arg-type]
        candidate_id = str(row["candidate_id"])
        if recent_demand_exhausted(views, age):
            killed.append(candidate_id)
        else:
            survivors.append(candidate_id)
    winners: list[TrackWinner] = []
    if not survivors:
        for row in track_b:
            if not isinstance(row, Mapping):
                raise TypeError("track B row must be an object")
            if not is_track_b_winner(row):
                continue
            winners.append(
                TrackWinner(
                    candidate_id=str(row["candidate_id"]),
                    track=str(row["track"]),
                    source=str(row.get("source") or ""),
                )
            )
    return SlateSelection(
        track_a_killed=tuple(killed),
        track_a_survivors=tuple(survivors),
        winners=tuple(winners),
    )


class Agent1ScoutService:
    """Recorded-corpus scout. Reads local fixtures and applies the trap rules."""

    def __init__(self, fixtures: Path | str) -> None:
        self.fixtures = Path(fixtures)

    def _read(self, name: str) -> dict[str, object]:
        return load_json(self.fixtures / name)

    def nightly_poll(self, name: str = "nightly_poll.json") -> NightlyPoll:
        return poll_uploads(self._read(name))

    def score_saturation(self, name: str) -> SaturationReport:
        corpus = self._read(name)
        videos = corpus["videos"]
        if not isinstance(videos, Sequence):
            raise TypeError("videos must be a list")
        today = parse_day(str(corpus["as_of"])) if "as_of" in corpus else None
        rows = [video for video in videos if isinstance(video, Mapping)]
        return score_corpus(rows, today)

    def inspect_xray(
        self,
        name: str = "age_restricted_xray.json",
        download: Callable[[str], None] | None = None,
    ) -> XrayInspection:
        return inspect_restricted_xray(self._read(name), download)

    def clean_room(
        self,
        transcript_buffer: bytearray | list[object],
        name: str = "clean_room.json",
    ) -> dict[str, object]:
        fixture = self._read(name)
        leads = fixture["leads"]
        if not isinstance(leads, Mapping):
            raise TypeError("leads must be an object")
        return seal_seed_packet(leads, transcript_buffer)

    def safe_title_ctr_ok(self, title: str) -> int:
        return safe_title_ok(title)

    def purge_expired_payloads(self, name: str = "ttl_purge.json") -> dict[str, PurgedRecord]:
        fixture = self._read(name)
        as_of = parse_day(str(fixture["as_of"]))
        records = fixture["records"]
        if not isinstance(records, Sequence):
            raise TypeError("records must be a list")
        purged: dict[str, PurgedRecord] = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise TypeError("record must be an object")
            row = purge_yt_payload(record, as_of)
            seed = row["seed_packet_json"]
            if not isinstance(seed, dict):
                raise TypeError("seed packet must be an object")
            item = PurgedRecord(
                record_id=str(row["record_id"]),
                age_days=int(row["age_days"]),  # type: ignore[arg-type]
                status=str(row["status"]),
                raw_yt_payload_json=row["raw_yt_payload_json"],
                views_count=row["views_count"],
                outlier_ratio=row["outlier_ratio"],
                seed_packet_json=seed,
            )
            purged[item.record_id] = item
        return purged

    def recheck_sunk_cost(self, name: str = "sunk_cost.json") -> tuple[SunkCostDecision, ...]:
        fixture = self._read(name)
        scenarios = fixture["scenarios"]
        if not isinstance(scenarios, Sequence):
            raise TypeError("scenarios must be a list")
        decisions: list[SunkCostDecision] = []
        for scenario in scenarios:
            if not isinstance(scenario, Mapping):
                raise TypeError("scenario must be an object")
            row = evaluate_sunk_cost(scenario)
            decisions.append(
                SunkCostDecision(
                    scenario_id=str(row["scenario_id"]),
                    shift_day=int(row["shift_day"]),  # type: ignore[arg-type]
                    spent_credits_pct=float(row["spent_credits_pct"]),  # type: ignore[arg-type]
                    n_14d_wave=int(row["n_14d_wave"]),  # type: ignore[arg-type]
                    tier1_hit=bool(row["tier1_hit"]),
                    decision=str(row["decision"]),
                    sunk_cost_override=int(row["sunk_cost_override"]),  # type: ignore[arg-type]
                )
            )
        return tuple(decisions)

    def scout(self, name: str = "track_b_fallback.json") -> SlateSelection:
        return select_slate(self._read(name))


__all__ = [
    "ABORTED_COPYCAT_WAVE",
    "Agent1ScoutService",
    "FINISH",
    "KILL_90D",
    "SI_HARD_KILL",
    "SI_SWEET_SPOT",
    "TRACK_B",
]
