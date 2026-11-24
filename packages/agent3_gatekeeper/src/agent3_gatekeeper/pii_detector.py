"""Visual + spoken PII detector for FOIA bodycam and 911 ASR.

Per-frame vision hits are injected at call sites (no OpenCV, no YOLO, no network).
Spoken PII is scanned from word-timestamped ASR using regex heuristics and a lightweight
name tagger. Temporal IOU smoothing merges the same bystander face, plate, or house
number box across frames into one blur track.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

IOU_TRACK_THRESHOLD = 0.5

VISUAL_BYSTANDER_FACE = "bystander_face"
VISUAL_LICENSE_PLATE = "license_plate"
VISUAL_HOUSE_NUMBER = "house_number"

SPOKEN_PHONE = "phone"
SPOKEN_STREET_ADDRESS = "street_address"
SPOKEN_DOB = "dob"
SPOKEN_PERSON = "person"
SPOKEN_JUVENILE = "juvenile"

_VISUAL_KINDS = {
    VISUAL_BYSTANDER_FACE,
    VISUAL_LICENSE_PLATE,
    VISUAL_HOUSE_NUMBER,
}

_STREET_SUFFIXES = frozenset(
    {
        "street",
        "st",
        "avenue",
        "ave",
        "road",
        "rd",
        "lane",
        "ln",
        "drive",
        "dr",
        "court",
        "ct",
        "boulevard",
        "blvd",
        "way",
        "place",
        "pl",
        "circle",
        "cir",
    }
)

_NAME_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "at",
        "my",
        "your",
        "his",
        "her",
        "their",
        "our",
        "caller",
        "dispatch",
        "officer",
        "says",
        "said",
        "please",
        "home",
        "address",
        "phone",
        "number",
        "callback",
        "born",
        "birthday",
        "date",
        "of",
        "on",
        "in",
        "to",
        "is",
        "are",
        "was",
        "were",
        "i",
        "we",
        "you",
        "he",
        "she",
        "they",
        "it",
        "a",
        "an",
        "dash",
        "hyphen",
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "oh",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "january",
        "february",
    }
)

_DIGIT_WORDS: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

_MONTH_NAMES = frozenset(
    {
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)

_PHONE_LITERAL_RE = re.compile(
    r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)"
)
_DOB_SLASH_RE = re.compile(r"\b(0?[1-9]|1[0-2])/(0?[1-9]|[12]\d|3[01])/(19|20)\d{2}\b")
_TOKEN_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


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
class BoundingBox:
    """Axis-aligned box in pixel coordinates."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        if self.w <= 0 or self.h <= 0:
            raise ValueError("box width and height must be positive")

    @property
    def area(self) -> float:
        return self.w * self.h

    def union(self, other: BoundingBox) -> BoundingBox:
        x1 = min(self.x, other.x)
        y1 = min(self.y, other.y)
        x2 = max(self.x + self.w, other.x + other.w)
        y2 = max(self.y + self.h, other.y + other.h)
        return BoundingBox(x=x1, y=y1, w=x2 - x1, h=y2 - y1)

    def iou(self, other: BoundingBox) -> float:
        ax2 = self.x + self.w
        ay2 = self.y + self.h
        bx2 = other.x + other.w
        by2 = other.y + other.h
        ix1 = max(self.x, other.x)
        iy1 = max(self.y, other.y)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter = (ix2 - ix1) * (iy2 - iy1)
        union = self.area + other.area - inter
        if union <= 0:
            return 0.0
        return inter / union


@dataclass(frozen=True)
class FrameVisualDetection:
    """Single-frame injected vision hit (simulates YOLO output)."""

    frame_index: int
    timestamp_ms: int
    kind: str
    bbox: BoundingBox
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.kind not in _VISUAL_KINDS:
            raise ValueError(f"unexpected visual kind {self.kind!r}")


@dataclass(frozen=True)
class VisualPiiTrack:
    """Temporally smoothed visual PII blur window."""

    kind: str
    start_ms: int
    end_ms: int
    bbox: BoundingBox
    track_id: int

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "kind": self.kind,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "track_id": self.track_id,
            "bbox_x": self.bbox.x,
            "bbox_y": self.bbox.y,
            "bbox_w": self.bbox.w,
            "bbox_h": self.bbox.h,
        }


@dataclass(frozen=True)
class SpokenPiiInterval:
    """Spoken PII mute/bleep window on the source timeline."""

    start_ms: int
    end_ms: int
    kind: str
    text: str = ""

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "kind": self.kind,
            "text": self.text,
        }


@dataclass(frozen=True)
class CaseRecord:
    """Case metadata used to suppress convicted-defendant spoken name hits."""

    defendant_name: str
    juvenile_names: frozenset[str] = frozenset()


@dataclass
class SpokenPiiScanResult:
    duration_ms: int
    intervals: list[SpokenPiiInterval] = field(default_factory=list)

    @property
    def spoken_pii_intervals_json(self) -> list[dict[str, int | str]]:
        return [interval.to_dict() for interval in self.intervals]


@dataclass
class VisualPiiScanResult:
    duration_ms: int
    tracks: list[VisualPiiTrack] = field(default_factory=list)

    @property
    def visual_pii_tracks_json(self) -> list[dict[str, int | float | str]]:
        return [track.to_dict() for track in self.tracks]


@dataclass
class PiiScanResult:
    """Combined visual + spoken PII index for one FOIA asset."""

    duration_ms: int
    visual_tracks: list[VisualPiiTrack] = field(default_factory=list)
    spoken_intervals: list[SpokenPiiInterval] = field(default_factory=list)


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


def _coerce_bbox(item: BoundingBox | Mapping[str, Any]) -> BoundingBox:
    if isinstance(item, BoundingBox):
        return item
    if isinstance(item, Mapping):
        return BoundingBox(
            x=float(item["x"]),
            y=float(item["y"]),
            w=float(item["w"]),
            h=float(item["h"]),
        )
    raise TypeError("bbox must be BoundingBox or mapping")


def _coerce_frame_detections(
    detections: Sequence[FrameVisualDetection | Mapping[str, Any]],
) -> list[FrameVisualDetection]:
    out: list[FrameVisualDetection] = []
    for item in detections:
        if isinstance(item, FrameVisualDetection):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            out.append(
                FrameVisualDetection(
                    frame_index=int(item["frame_index"]),
                    timestamp_ms=int(item["timestamp_ms"]),
                    kind=str(item["kind"]),
                    bbox=_coerce_bbox(item["bbox"]),
                    confidence=float(item.get("confidence", 1.0)),
                )
            )
            continue
        raise TypeError("detections must be FrameVisualDetection or mapping")
    return out


def accept_injected_visual_detections(
    detections: Sequence[FrameVisualDetection | Mapping[str, Any]],
) -> list[FrameVisualDetection]:
    """Return injected per-frame vision hits unchanged (no model inference)."""
    hits = _coerce_frame_detections(detections)
    return sorted(hits, key=lambda item: (item.timestamp_ms, item.frame_index, item.kind))


def smooth_visual_pii_tracks(
    detections: Sequence[FrameVisualDetection | Mapping[str, Any]],
    duration_ms: int,
    *,
    iou_threshold: float = IOU_TRACK_THRESHOLD,
) -> VisualPiiScanResult:
    """Merge overlapping same-kind boxes across consecutive frames into blur tracks."""
    if duration_ms <= 0:
        raise ValueError("duration_ms must be positive")

    hits = accept_injected_visual_detections(detections)
    if not hits:
        return VisualPiiScanResult(duration_ms=duration_ms, tracks=[])

    active: dict[tuple[str, int], dict[str, Any]] = {}
    finished: list[VisualPiiTrack] = []
    next_track_id = 1

    def flush(track_id: int, state: dict[str, Any]) -> None:
        finished.append(
            VisualPiiTrack(
                kind=state["kind"],
                start_ms=state["start_ms"],
                end_ms=state["end_ms"],
                bbox=state["bbox"],
                track_id=track_id,
            )
        )

    for hit in hits:
        matched_id: int | None = None
        for track_id, state in active.items():
            kind, _ = track_id
            if kind != hit.kind:
                continue
            if hit.timestamp_ms < state["last_ms"]:
                continue
            if hit.bbox.iou(state["bbox"]) >= iou_threshold:
                matched_id = track_id[1]
                state["end_ms"] = max(state["end_ms"], hit.timestamp_ms)
                state["last_ms"] = hit.timestamp_ms
                state["bbox"] = state["bbox"].union(hit.bbox)
                state["hits"] += 1
                break

        if matched_id is not None:
            continue

        active_key = (hit.kind, next_track_id)
        active[active_key] = {
            "kind": hit.kind,
            "start_ms": hit.timestamp_ms,
            "end_ms": hit.timestamp_ms,
            "last_ms": hit.timestamp_ms,
            "bbox": hit.bbox,
            "hits": 1,
        }
        next_track_id += 1

    for track_id, state in active.items():
        flush(track_id[1], state)

    finished.sort(key=lambda item: (item.start_ms, item.kind, item.track_id))
    return VisualPiiScanResult(duration_ms=duration_ms, tracks=finished)


def _normalize_token(word: str) -> str:
    return _TOKEN_NORMALIZE_RE.sub("", word.strip().lower())


def _is_name_token(word: str) -> bool:
    token = _normalize_token(word)
    if not token or token in _NAME_STOPWORDS:
        return False
    if not token.isalpha():
        return False
    return word[:1].isupper() or word.isupper()


def _defendant_tokens(defendant_name: str) -> frozenset[str]:
    parts = [p for p in re.split(r"\s+", defendant_name.strip()) if p]
    if not parts:
        return frozenset()
    tokens: set[str] = set()
    for index in range(len(parts)):
        for end in range(index + 1, len(parts) + 1):
            phrase = " ".join(parts[index:end]).lower()
            tokens.add(phrase)
            tokens.add(phrase.replace(" ", ""))
    return frozenset(tokens)


def _word_span_text(words: list[WordTimestamp], start: int, end: int) -> str:
    return " ".join(words[i].word for i in range(start, end))


def _emit_interval(
    intervals: list[SpokenPiiInterval],
    words: list[WordTimestamp],
    start: int,
    end: int,
    kind: str,
    *,
    text: str | None = None,
) -> None:
    if end <= start:
        return
    payload = text if text is not None else _word_span_text(words, start, end)
    interval = SpokenPiiInterval(
        start_ms=words[start].start_ms,
        end_ms=words[end - 1].end_ms,
        kind=kind,
        text=payload,
    )
    intervals.append(interval)


def _scan_literal_phones(
    intervals: list[SpokenPiiInterval],
    words: list[WordTimestamp],
) -> None:
    for index, token in enumerate(words):
        for match in _PHONE_LITERAL_RE.finditer(token.word):
            intervals.append(
                SpokenPiiInterval(
                    start_ms=token.start_ms,
                    end_ms=token.end_ms,
                    kind=SPOKEN_PHONE,
                    text=match.group(0),
                )
            )


def _phone_digit_for_word(word: str) -> str | None:
    token = _normalize_token(word)
    if token in _DIGIT_WORDS:
        return _DIGIT_WORDS[token]
    if token in {"dash", "hyphen", "-"}:
        return "-"
    if token.isdigit():
        return token
    return None


def _scan_spoken_phone_sequences(
    intervals: list[SpokenPiiInterval],
    words: list[WordTimestamp],
) -> None:
    index = 0
    while index < len(words):
        chunk_start: int | None = None
        digit_count = 0
        index_cursor = index
        while index_cursor < len(words):
            piece = _phone_digit_for_word(words[index_cursor].word)
            if piece is None:
                if digit_count >= 7 and chunk_start is not None:
                    _emit_interval(
                        intervals,
                        words,
                        chunk_start,
                        index_cursor,
                        SPOKEN_PHONE,
                    )
                break
            if chunk_start is None:
                chunk_start = index_cursor
            if piece != "-":
                digit_count += len(piece)
            index_cursor += 1
            if digit_count >= 10 and chunk_start is not None:
                _emit_interval(
                    intervals,
                    words,
                    chunk_start,
                    index_cursor,
                    SPOKEN_PHONE,
                )
                chunk_start = None
                digit_count = 0
        if chunk_start is not None and digit_count >= 7:
            _emit_interval(intervals, words, chunk_start, index_cursor, SPOKEN_PHONE)
        index = max(index + 1, index_cursor)


def _is_number_word(word: str) -> bool:
    token = _normalize_token(word)
    return token.isdigit() or token in _DIGIT_WORDS


def _scan_street_addresses(
    intervals: list[SpokenPiiInterval],
    words: list[WordTimestamp],
) -> None:
    for index, token in enumerate(words):
        suffix = _normalize_token(token.word)
        if suffix not in _STREET_SUFFIXES:
            continue

        end = index + 1
        start = index
        # Street name: walk back across capitalized tokens (e.g. Oak).
        while start > 0 and _is_name_token(words[start - 1].word):
            if _normalize_token(words[start - 1].word) in _STREET_SUFFIXES:
                break
            start -= 1

        # House number: digits or number words immediately before the street name.
        while start > 0 and _is_number_word(words[start - 1].word):
            start -= 1

        if start == end:
            continue
        _emit_interval(
            intervals,
            words,
            start,
            end,
            SPOKEN_STREET_ADDRESS,
        )


def _scan_dob_spans(
    intervals: list[SpokenPiiInterval],
    words: list[WordTimestamp],
) -> None:
    for index, token in enumerate(words):
        for match in _DOB_SLASH_RE.finditer(token.word):
            intervals.append(
                SpokenPiiInterval(
                    start_ms=token.start_ms,
                    end_ms=token.end_ms,
                    kind=SPOKEN_DOB,
                    text=match.group(0),
                )
            )

    index = 0
    while index < len(words):
        token = _normalize_token(words[index].word)
        if token not in _MONTH_NAMES:
            index += 1
            continue
        start = index
        end = index + 1
        if end < len(words) and re.fullmatch(r"\d{1,2}", _normalize_token(words[end].word)):
            end += 1
        if end < len(words) and re.fullmatch(r"(19|20)\d{2}", _normalize_token(words[end].word)):
            end += 1
            _emit_interval(intervals, words, start, end, SPOKEN_DOB)
            index = end
            continue
        index += 1


def _person_is_defendant(
    words: list[WordTimestamp],
    start: int,
    end: int,
    defendant_phrases: frozenset[str],
) -> bool:
    phrase = _word_span_text(words, start, end).lower()
    compact = phrase.replace(" ", "")
    return phrase in defendant_phrases or compact in defendant_phrases


def _juvenile_kind(
    words: list[WordTimestamp],
    start: int,
    end: int,
    juvenile_names: frozenset[str],
) -> bool:
    phrase = _word_span_text(words, start, end).lower()
    return phrase in juvenile_names


def _scan_person_names(
    intervals: list[SpokenPiiInterval],
    words: list[WordTimestamp],
    case: CaseRecord,
    *,
    ner_person_spans: Sequence[tuple[int, int]] | None = None,
) -> None:
    defendant_phrases = _defendant_tokens(case.defendant_name)

    if ner_person_spans:
        for start, end in ner_person_spans:
            if _person_is_defendant(words, start, end, defendant_phrases):
                continue
            kind = (
                SPOKEN_JUVENILE
                if _juvenile_kind(words, start, end, case.juvenile_names)
                else SPOKEN_PERSON
            )
            _emit_interval(intervals, words, start, end, kind)

    index = 0
    while index < len(words) - 1:
        if not _is_name_token(words[index].word):
            index += 1
            continue
        if not _is_name_token(words[index + 1].word):
            index += 1
            continue
        start = index
        end = index + 2
        if _person_is_defendant(words, start, end, defendant_phrases):
            index = end
            continue
        kind = (
            SPOKEN_JUVENILE
            if _juvenile_kind(words, start, end, case.juvenile_names)
            else SPOKEN_PERSON
        )
        _emit_interval(intervals, words, start, end, kind)
        index += 2


def _merge_spoken_intervals(
    intervals: list[SpokenPiiInterval],
) -> list[SpokenPiiInterval]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda item: (item.kind, item.start_ms, item.end_ms))
    merged: list[SpokenPiiInterval] = []
    current = ordered[0]
    for nxt in ordered[1:]:
        if nxt.kind != current.kind:
            merged.append(current)
            current = nxt
            continue
        if nxt.start_ms <= current.end_ms:
            current = SpokenPiiInterval(
                start_ms=current.start_ms,
                end_ms=max(current.end_ms, nxt.end_ms),
                kind=current.kind,
                text=current.text or nxt.text,
            )
            continue
        merged.append(current)
        current = nxt
    merged.append(current)
    return merged


def scan_spoken_pii(
    word_timestamps: Sequence[WordTimestamp | Mapping[str, Any]],
    duration_ms: int,
    case: CaseRecord,
    *,
    ner_person_spans: Sequence[tuple[int, int]] | None = None,
) -> SpokenPiiScanResult:
    """Detect spoken PII mute intervals from FOIA ASR word timestamps."""
    if duration_ms <= 0:
        raise ValueError("duration_ms must be positive")

    words = _coerce_word_timestamps(word_timestamps)
    intervals: list[SpokenPiiInterval] = []

    _scan_literal_phones(intervals, words)
    _scan_spoken_phone_sequences(intervals, words)
    _scan_street_addresses(intervals, words)
    _scan_dob_spans(intervals, words)
    _scan_person_names(intervals, words, case, ner_person_spans=ner_person_spans)

    merged = _merge_spoken_intervals(intervals)
    merged.sort(key=lambda item: (item.start_ms, item.end_ms, item.kind))
    return SpokenPiiScanResult(duration_ms=duration_ms, intervals=merged)


def scan_pii(
    *,
    duration_ms: int,
    visual_detections: Sequence[FrameVisualDetection | Mapping[str, Any]] | None = None,
    word_timestamps: Sequence[WordTimestamp | Mapping[str, Any]] | None = None,
    case: CaseRecord | None = None,
    ner_person_spans: Sequence[tuple[int, int]] | None = None,
) -> PiiScanResult:
    """Run visual track smoothing and spoken PII scanning for one asset."""
    visual = smooth_visual_pii_tracks(visual_detections or [], duration_ms)
    spoken_case = case or CaseRecord(defendant_name="")
    spoken = scan_spoken_pii(
        word_timestamps or [],
        duration_ms,
        spoken_case,
        ner_person_spans=ner_person_spans,
    )
    return PiiScanResult(
        duration_ms=duration_ms,
        visual_tracks=visual.tracks,
        spoken_intervals=spoken.intervals,
    )


def serialize_spoken_pii_intervals(
    intervals: Iterable[SpokenPiiInterval | Mapping[str, Any]],
) -> list[dict[str, int | str]]:
    """Serialize spoken intervals for persistence on ``foia_media_assets``."""
    payload: list[dict[str, int | str]] = []
    for item in intervals:
        if isinstance(item, SpokenPiiInterval):
            payload.append(item.to_dict())
        elif isinstance(item, Mapping):
            payload.append(
                {
                    "start_ms": int(item["start_ms"]),
                    "end_ms": int(item["end_ms"]),
                    "kind": str(item["kind"]),
                    "text": str(item.get("text", "")),
                }
            )
        else:
            raise TypeError("interval must be SpokenPiiInterval or mapping")
    return payload