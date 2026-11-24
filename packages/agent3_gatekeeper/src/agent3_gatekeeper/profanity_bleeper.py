"""Whole-clip profanity map and episode 0:00-0:30 slice auto-bleeper.

Word-timestamped ASR is injected at call sites (no live ASR, no network).
The mapper scans the full clip duration, persists ``profanity_intervals_json``,
and plans 1000 Hz tone bleeps with mute for severe slurs everywhere plus any
profanity whose source time lies inside a FOIA slice routed to the cold open.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

BLEEP_HZ = 1000
EPISODE_INTRO_END_MS = 30_000

SEVERE = "severe"
MODERATE = "moderate"
MILD = "mild"

_REASON_SEVERE_EVERYWHERE = "severe_everywhere"
_REASON_INTRO_SLICE = "intro_slice"

_SEVERE_WORDS: frozenset[str] = frozenset(
    {
        "nigger",
        "nigga",
        "faggot",
        "fag",
        "kike",
        "spic",
        "chink",
        "wetback",
        "retard",
        "tranny",
    }
)

_HARD_EXPLICIT: frozenset[str] = frozenset(
    {
        "fuck",
        "fucking",
        "fucked",
        "fucker",
        "shit",
        "shitty",
        "bitch",
        "bastard",
        "asshole",
        "dick",
        "cock",
        "pussy",
        "whore",
        "slut",
    }
)

_MILD_PROFANITY: frozenset[str] = frozenset(
    {
        "damn",
        "hell",
        "crap",
        "piss",
    }
)

_PROFANITY_WORDS: frozenset[str] = _HARD_EXPLICIT | _MILD_PROFANITY | _SEVERE_WORDS

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class WordTimestamp:
    """One ASR token with source-timeline millisecond bounds."""

    word: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")


@dataclass(frozen=True)
class ProfanityInterval:
    """Source-timeline profanity span stored in ``profanity_intervals_json``."""

    start_ms: int
    end_ms: int
    severity: str

    def __post_init__(self) -> None:
        if self.severity not in {SEVERE, MODERATE, MILD}:
            raise ValueError(f"unexpected severity {self.severity!r}")
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class FoiaTimelineSlice:
    """Maps a source FOIA window onto an episode-timeline window."""

    source_start_ms: int
    source_end_ms: int
    episode_start_ms: int
    episode_end_ms: int

    def __post_init__(self) -> None:
        if self.source_end_ms < self.source_start_ms:
            raise ValueError("source_end_ms must be >= source_start_ms")
        if self.episode_end_ms < self.episode_start_ms:
            raise ValueError("episode_end_ms must be >= episode_start_ms")

    @property
    def source_duration_ms(self) -> int:
        return self.source_end_ms - self.source_start_ms

    @property
    def episode_duration_ms(self) -> int:
        return self.episode_end_ms - self.episode_start_ms

    def map_source_to_episode(self, source_ms: int) -> int:
        """Linear map from source time to episode time inside this slice."""
        offset = source_ms - self.source_start_ms
        if self.source_duration_ms <= 0:
            return self.episode_start_ms
        ratio = offset / self.source_duration_ms
        mapped = self.episode_start_ms + int(ratio * self.episode_duration_ms)
        return max(self.episode_start_ms, min(mapped, self.episode_end_ms))

    def overlaps_intro(self, intro_end_ms: int = EPISODE_INTRO_END_MS) -> bool:
        return self.episode_start_ms < intro_end_ms and self.episode_end_ms > 0


@dataclass(frozen=True)
class BleepInterval:
    """A single 1000 Hz bleep window on the episode timeline."""

    episode_start_ms: int
    episode_end_ms: int
    source_start_ms: int
    source_end_ms: int
    severity: str
    reason: str
    bleep_hz: int = BLEEP_HZ
    mute: bool = True

    def to_dict(self) -> dict[str, int | str | bool]:
        return {
            "episode_start_ms": self.episode_start_ms,
            "episode_end_ms": self.episode_end_ms,
            "source_start_ms": self.source_start_ms,
            "source_end_ms": self.source_end_ms,
            "severity": self.severity,
            "reason": self.reason,
            "bleep_hz": self.bleep_hz,
            "mute": self.mute,
        }


@dataclass
class ProfanityMapResult:
    """Output of a whole-clip profanity scan."""

    duration_ms: int
    intervals: list[ProfanityInterval] = field(default_factory=list)

    @property
    def profanity_intervals_json(self) -> list[dict[str, int | str]]:
        return [interval.to_dict() for interval in self.intervals]


def _normalize_token(word: str) -> str:
    return _TOKEN_RE.sub("", word.strip().lower())


def classify_word(word: str) -> str | None:
    """Return severity for a profane token, or None if clean."""
    token = _normalize_token(word)
    if not token:
        return None
    if token in _SEVERE_WORDS or token in _HARD_EXPLICIT:
        return SEVERE
    if token in _MILD_PROFANITY:
        return MODERATE
    return None


def _coerce_word_timestamps(
    words: Sequence[WordTimestamp | Mapping[str, Any]],
) -> list[WordTimestamp]:
    out: list[WordTimestamp] = []
    for item in words:
        if isinstance(item, WordTimestamp):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            out.append(
                WordTimestamp(
                    word=str(item["word"]),
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                )
            )
            continue
        raise TypeError("word timestamps must be WordTimestamp or mapping")
    return out


def scan_whole_clip(
    word_timestamps: Sequence[WordTimestamp | Mapping[str, Any]],
    duration_ms: int,
    *,
    scan_cap_ms: int | None = None,
) -> ProfanityMapResult:
    """Index profanity across the full clip (not capped at the first 15 seconds).

    ``scan_cap_ms`` exists only for regression tests that prove we do not default
    to a 15-second window. Production callers should omit it.
    """
    if duration_ms <= 0:
        raise ValueError("duration_ms must be positive")

    tokens = _coerce_word_timestamps(word_timestamps)
    intervals: list[ProfanityInterval] = []
    for token in tokens:
        if token.start_ms > duration_ms:
            continue
        if scan_cap_ms is not None and token.start_ms >= scan_cap_ms:
            continue
        severity = classify_word(token.word)
        if severity is None:
            continue
        intervals.append(
            ProfanityInterval(
                start_ms=token.start_ms,
                end_ms=token.end_ms,
                severity=severity,
            )
        )
    intervals.sort(key=lambda item: (item.start_ms, item.end_ms))
    return ProfanityMapResult(duration_ms=duration_ms, intervals=intervals)


def serialize_profanity_intervals(
    intervals: Iterable[ProfanityInterval | Mapping[str, Any]],
) -> str:
    """Serialize intervals for ``foia_media_assets.profanity_intervals_json``."""
    payload: list[dict[str, int | str]] = []
    for item in intervals:
        if isinstance(item, ProfanityInterval):
            payload.append(item.to_dict())
        elif isinstance(item, Mapping):
            payload.append(
                {
                    "start_ms": int(item["start_ms"]),
                    "end_ms": int(item["end_ms"]),
                    "severity": str(item["severity"]),
                }
            )
        else:
            raise TypeError("interval must be ProfanityInterval or mapping")
    return json.dumps(payload, separators=(",", ":"))


def _interval_overlaps_slice(
    interval: ProfanityInterval,
    slice_: FoiaTimelineSlice,
) -> bool:
    return (
        interval.start_ms < slice_.source_end_ms
        and interval.end_ms > slice_.source_start_ms
    )


def _word_in_slice(interval: ProfanityInterval, slice_: FoiaTimelineSlice) -> bool:
    """True when the profanity source span falls inside the slice source window."""
    return (
        interval.start_ms >= slice_.source_start_ms
        and interval.start_ms < slice_.source_end_ms
    )


def plan_bleeps(
    profanity_intervals: Sequence[ProfanityInterval | Mapping[str, Any]],
    timeline_slices: Sequence[FoiaTimelineSlice],
    *,
    intro_end_ms: int = EPISODE_INTRO_END_MS,
) -> list[BleepInterval]:
    """Plan episode bleeps: severe everywhere a slice uses the source span; intro slice rule."""
    intervals: list[ProfanityInterval] = []
    for item in profanity_intervals:
        if isinstance(item, ProfanityInterval):
            intervals.append(item)
        elif isinstance(item, Mapping):
            intervals.append(
                ProfanityInterval(
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                    severity=str(item["severity"]),
                )
            )
        else:
            raise TypeError("profanity interval must be ProfanityInterval or mapping")

    planned: list[BleepInterval] = []
    seen: set[tuple[int, int, int, str]] = set()

    for slice_ in timeline_slices:
        for interval in intervals:
            if not _interval_overlaps_slice(interval, slice_):
                continue
            force = interval.severity == SEVERE or (
                slice_.overlaps_intro(intro_end_ms)
                and _word_in_slice(interval, slice_)
            )
            if not force:
                continue
            ep_start = slice_.map_source_to_episode(interval.start_ms)
            ep_end = slice_.map_source_to_episode(interval.end_ms)
            if ep_end <= ep_start:
                ep_end = ep_start + max(1, interval.end_ms - interval.start_ms)
            reason = (
                _REASON_SEVERE_EVERYWHERE
                if interval.severity == SEVERE
                else _REASON_INTRO_SLICE
            )
            key = (slice_.episode_start_ms, ep_start, interval.start_ms, reason)
            if key in seen:
                continue
            seen.add(key)
            planned.append(
                BleepInterval(
                    episode_start_ms=ep_start,
                    episode_end_ms=ep_end,
                    source_start_ms=interval.start_ms,
                    source_end_ms=interval.end_ms,
                    severity=interval.severity,
                    reason=reason,
                )
            )

    planned.sort(key=lambda item: (item.episode_start_ms, item.source_start_ms))
    return planned


WordTimestampProvider = Callable[[], Sequence[WordTimestamp | Mapping[str, Any]]]


@dataclass
class WholeClipProfanityMapper:
    """High-level façade: inject ASR word timestamps, scan, plan bleeps."""

    word_timestamps: Sequence[WordTimestamp | Mapping[str, Any]] | None = None
    word_timestamps_provider: WordTimestampProvider | None = None

    def _resolve_words(self) -> list[WordTimestamp]:
        if self.word_timestamps_provider is not None:
            return _coerce_word_timestamps(self.word_timestamps_provider())
        if self.word_timestamps is not None:
            return _coerce_word_timestamps(self.word_timestamps)
        return []

    def scan(self, duration_ms: int, **scan_kwargs: Any) -> ProfanityMapResult:
        return scan_whole_clip(self._resolve_words(), duration_ms, **scan_kwargs)

    def plan(
        self,
        scan_result: ProfanityMapResult,
        timeline_slices: Sequence[FoiaTimelineSlice],
        *,
        intro_end_ms: int = EPISODE_INTRO_END_MS,
    ) -> list[BleepInterval]:
        return plan_bleeps(scan_result.intervals, timeline_slices, intro_end_ms=intro_end_ms)


def profanity_in_intro_window(
    profanity_intervals: Sequence[ProfanityInterval | Mapping[str, Any]],
    timeline_slices: Sequence[FoiaTimelineSlice],
    *,
    intro_end_ms: int = EPISODE_INTRO_END_MS,
) -> list[ProfanityInterval]:
    """Return profanity that would be exposed unbleeped in episode 0:00–intro_end_ms."""
    intervals: list[ProfanityInterval] = []
    for item in profanity_intervals:
        if isinstance(item, ProfanityInterval):
            intervals.append(item)
        elif isinstance(item, Mapping):
            intervals.append(
                ProfanityInterval(
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                    severity=str(item["severity"]),
                )
            )
    bleeps = plan_bleeps(intervals, timeline_slices, intro_end_ms=intro_end_ms)
    bleeped_sources = {b.source_start_ms for b in bleeps}
    leaks: list[ProfanityInterval] = []
    for slice_ in timeline_slices:
        if not slice_.overlaps_intro(intro_end_ms):
            continue
        for interval in intervals:
            if not _word_in_slice(interval, slice_):
                continue
            if interval.start_ms not in bleeped_sources:
                leaks.append(interval)
    return leaks