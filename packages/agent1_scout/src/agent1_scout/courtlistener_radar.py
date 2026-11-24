"""Track B CourtListener appellate radar.

Polls criminal appellate opinions through an injected fetcher. The scout
share is 62 requests, floor of 50% of the 125/day CourtListener cap, so
later verification keeps the rest of the bucket. Primary holdings that are
REVERSED or REMANDED are dropped before a seed is emitted. An AFFIRMED
murder (or other primary) count is kept when a minor count is REVERSED;
that seed is marked ``mixed_disposition`` for the later disposition gate.

Fetched payloads are stored in ``courtlistener_cache`` (schema/pipeline.sql).
A later poll of the same opinion id reads that row and does not call the
fetcher again until ``expires_at``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

COURTLISTENER_DAILY_CAP = 125
# 125 * 0.5 == 62.5. Stay at 62 so this poller never rounds into the
# verification reserve (125 - 62 == 63 requests left).
SCOUT_REQUEST_BUDGET = 62
MIN_OPINION_WORDS = 3000
CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000
TRACK_B = "TRACK_B_FOIA_RADAR"
CONTRACT_VERSION = "v4"

SKIP_PRIMARY_REVERSED = "PRIMARY_REVERSED"
SKIP_PRIMARY_REMANDED = "PRIMARY_REMANDED"
SKIP_NOT_AFFIRMED = "NOT_AFFIRMED"
SKIP_NOT_CRIMINAL = "NOT_CRIMINAL"
SKIP_NOT_APPELLATE = "NOT_APPELLATE"
SKIP_BELOW_WORD_MINIMUM = "BELOW_WORD_MINIMUM"
SKIP_INCOMPLETE_SEED = "INCOMPLETE_SEED"

_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)?")
_MURDER = re.compile(r"\bmurder\b", re.IGNORECASE)
_DOCKET_CR = re.compile(r"(?:^|[^A-Z0-9])CR(?:[^A-Z0-9]|$)")
_ENTITY_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_VERSUS = re.compile(r"\bv\.?\s+(.+)$", re.IGNORECASE)

_DISPOSITION_WORDS = {
    "AFFIRM": "AFFIRMED",
    "AFFIRMED": "AFFIRMED",
    "REVERSE": "REVERSED",
    "REVERSED": "REVERSED",
    "REVERSAL": "REVERSED",
    "REMAND": "REMANDED",
    "REMANDED": "REMANDED",
    "VACATE": "VACATED",
    "VACATED": "VACATED",
    "ACQUIT": "ACQUITTED",
    "ACQUITTED": "ACQUITTED",
    "PENDING": "PENDING",
}

_SEED_KEYS = (
    "contract_version",
    "track",
    "lead_classification",
    "suspect_names",
    "victim_names",
    "incident_date_or_year",
    "county_state",
    "docket_ids",
    "unanswered_comment_questions",
)

OpinionFetcher = Callable[[str], Mapping[str, Any]]


class CourtListenerCacheError(RuntimeError):
    """Raised when ``courtlistener_cache`` is not available on the connection."""


@dataclass(frozen=True, slots=True)
class EmittedOpinion:
    opinion_id: str
    seed: Mapping[str, Any]
    mixed_disposition: bool
    word_count: int
    primary_disposition: str
    primary_count: str | None


@dataclass(frozen=True, slots=True)
class SkippedOpinion:
    opinion_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RadarPollResult:
    seeds: tuple[EmittedOpinion, ...]
    skipped: tuple[SkippedOpinion, ...]
    deferred_opinion_ids: tuple[str, ...]
    requests_used: int
    cache_hits: int
    request_budget: int


@dataclass(frozen=True, slots=True)
class _Holding:
    primary_disposition: str
    mixed_disposition: bool
    primary_count: str | None


def normalize_disposition(value: object) -> str:
    """Map a single disposition label to AFFIRMED / REVERSED / REMANDED / ….

    A string that names more than one disposition (``AFFIRMED in part and
    REVERSED in part``) is ambiguous and returns ``""``. Count tags are the
    source of truth for that posture.
    """
    if not isinstance(value, str):
        return ""
    tokens = re.findall(r"[A-Za-z]+", value.upper())
    found: list[str] = []
    for token in tokens:
        mapped = _DISPOSITION_WORDS.get(token)
        if mapped and mapped not in found:
            found.append(mapped)
    if len(found) == 1:
        return found[0]
    return ""


class CourtListenerRadar:
    """Fetch, cache, and pre-filter criminal appellate opinions."""

    def __init__(
        self,
        fetcher: OpinionFetcher,
        connection: sqlite3.Connection,
        *,
        now_ms: int,
        ttl_ms: int = CACHE_TTL_MS,
    ) -> None:
        if now_ms < 0:
            raise ValueError("now_ms must be >= 0")
        if ttl_ms <= 0:
            raise ValueError("ttl_ms must be > 0")
        self._fetcher = fetcher
        self._conn = connection
        self._now_ms = now_ms
        self._ttl_ms = ttl_ms
        self._requests_used = 0
        _require_cache_table(connection)

    @property
    def requests_used(self) -> int:
        """Fetcher calls spent by this poller instance (the 62-request budget)."""
        return self._requests_used

    @property
    def now_ms(self) -> int:
        return self._now_ms

    def poll(self, opinion_ids: Sequence[object]) -> RadarPollResult:
        """Poll ``opinion_ids`` in order, spending at most 62 uncached fetches.

        Cache hits do not count against the budget. Uncached ids past the
        budget are returned in ``deferred_opinion_ids`` and are not fetched.
        Duplicate ids are fetched at most once.
        """
        spent_before = self._requests_used
        seeds: list[EmittedOpinion] = []
        skipped: list[SkippedOpinion] = []
        deferred: list[str] = []
        cache_hits = 0
        seen: set[str] = set()

        for raw_id in opinion_ids:
            opinion_id = str(raw_id).strip()
            if not opinion_id:
                raise ValueError("opinion id must be non-empty")
            if opinion_id in seen:
                continue
            seen.add(opinion_id)

            cached = self._read_cache(opinion_id)
            if cached is not None:
                cache_hits += 1
                payload = cached
            elif self._requests_used >= SCOUT_REQUEST_BUDGET:
                deferred.append(opinion_id)
                continue
            else:
                fetched = self._fetcher(opinion_id)
                if not isinstance(fetched, Mapping):
                    raise TypeError("opinion fetcher must return a mapping")
                payload = dict(fetched)
                payload.setdefault("id", opinion_id)
                self._requests_used += 1
                self._write_cache(opinion_id, payload)

            emitted, rejection = _evaluate(opinion_id, payload)
            if rejection is not None:
                skipped.append(rejection)
            elif emitted is not None:
                seeds.append(emitted)

        return RadarPollResult(
            seeds=tuple(seeds),
            skipped=tuple(skipped),
            deferred_opinion_ids=tuple(deferred),
            requests_used=self._requests_used - spent_before,
            cache_hits=cache_hits,
            request_budget=SCOUT_REQUEST_BUDGET,
        )

    def _read_cache(self, opinion_id: str) -> Mapping[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT payload_json, expires_at
            FROM courtlistener_cache
            WHERE cache_key = ?
            """,
            (opinion_id,),
        ).fetchone()
        if row is None:
            return None
        payload_json, expires_at = row[0], row[1]
        if int(expires_at) <= self._now_ms:
            return None
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            return None
        return payload

    def _write_cache(self, opinion_id: str, payload: Mapping[str, Any]) -> None:
        body = dict(payload)
        body.setdefault("id", opinion_id)
        docket_id = _raw_docket(body)
        self._conn.execute(
            """
            INSERT INTO courtlistener_cache (
                cache_key, docket_id, payload_json, fetched_at, expires_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                docket_id = excluded.docket_id,
                payload_json = excluded.payload_json,
                fetched_at = excluded.fetched_at,
                expires_at = excluded.expires_at
            """,
            (
                opinion_id,
                docket_id,
                json.dumps(body, sort_keys=True, ensure_ascii=False),
                self._now_ms,
                self._now_ms + self._ttl_ms,
            ),
        )
        self._conn.commit()


def _require_cache_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'table' AND name = 'courtlistener_cache'
        """
    ).fetchone()
    if row is None:
        raise CourtListenerCacheError(
            "courtlistener_cache is missing. Apply the CREATE TABLE in "
            "schema/pipeline.sql before polling."
        )


def _evaluate(
    opinion_id: str, payload: Mapping[str, Any]
) -> tuple[EmittedOpinion | None, SkippedOpinion | None]:
    holding = _holding(payload)
    criminal, appellate = _case_posture(payload)
    words = _word_count(payload)
    reason = _skip_reason(holding.primary_disposition, criminal, appellate, words)
    if reason is not None:
        return None, SkippedOpinion(opinion_id, reason)
    try:
        seed = _seed_packet(payload)
    except ValueError:
        return None, SkippedOpinion(opinion_id, SKIP_INCOMPLETE_SEED)
    emitted = EmittedOpinion(
        opinion_id=opinion_id,
        seed=MappingProxyType(seed),
        mixed_disposition=holding.mixed_disposition,
        word_count=words,
        primary_disposition=holding.primary_disposition,
        primary_count=holding.primary_count,
    )
    return emitted, None


def _skip_reason(
    primary: str, criminal: bool, appellate: bool, words: int
) -> str | None:
    if primary == "REVERSED":
        return SKIP_PRIMARY_REVERSED
    if primary == "REMANDED":
        return SKIP_PRIMARY_REMANDED
    if primary != "AFFIRMED":
        return SKIP_NOT_AFFIRMED
    if not criminal:
        return SKIP_NOT_CRIMINAL
    if not appellate:
        return SKIP_NOT_APPELLATE
    if words < MIN_OPINION_WORDS:
        return SKIP_BELOW_WORD_MINIMUM
    return None


def _holding(opinion: Mapping[str, Any]) -> _Holding:
    counts = _count_rows(opinion)
    if counts:
        primary = _primary_count(counts)
        primary_disposition = normalize_disposition(
            primary.get("disposition", primary.get("result"))
        )
        label = _count_label(primary)
        mixed = primary_disposition == "AFFIRMED" and any(
            normalize_disposition(count.get("disposition", count.get("result"))) == "REVERSED"
            for count in counts
            if count is not primary
        )
        return _Holding(primary_disposition, mixed, label or None)
    scalar = ""
    for key in ("primary_disposition", "majority_disposition", "disposition"):
        scalar = normalize_disposition(_meta(opinion, key))
        if scalar:
            break
    return _Holding(scalar, False, None)


def _count_rows(opinion: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = opinion.get("dispositions")
    if raw is None:
        raw = opinion.get("counts")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, Mapping)]


def _count_label(count: Mapping[str, Any]) -> str:
    for key in ("count", "charge", "label"):
        value = count.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_primary_flag(count: Mapping[str, Any]) -> bool:
    if count.get("primary") is True:
        return True
    role = str(count.get("role") or count.get("rank") or "").casefold()
    return role in {"primary", "lead", "principal"}


def _primary_count(counts: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    murders = [count for count in counts if _MURDER.search(_count_label(count))]
    pool = murders or list(counts)
    for count in pool:
        if _is_primary_flag(count):
            return count
    return pool[0]


def _case_posture(opinion: Mapping[str, Any]) -> tuple[bool, bool]:
    criminal = _explicit_bool(opinion.get("criminal"))
    if criminal is None:
        nature = str(_meta(opinion, "nature_of_suit") or _meta(opinion, "case_type") or "")
        folded = nature.casefold()
        if "criminal" in folded:
            criminal = True
        elif "civil" in folded:
            criminal = False
        else:
            docket = str(_raw_docket(opinion) or "").upper()
            criminal = bool(_DOCKET_CR.search(docket) or "CRIM" in docket)
    appellate = _explicit_bool(opinion.get("appellate"))
    if appellate is None:
        court = str(_meta(opinion, "court") or "").casefold()
        appellate = any(
            token in court
            for token in (
                "appellate",
                "court of appeals",
                "court of criminal appeals",
                "supreme court",
            )
        )
    return bool(criminal), bool(appellate)


def _explicit_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _word_count(opinion: Mapping[str, Any]) -> int:
    if "word_count" in opinion and opinion["word_count"] is not None:
        return int(opinion["word_count"])
    for key in ("plain_text", "html_lawbox", "html_with_citations", "html"):
        text = opinion.get(key)
        if isinstance(text, str) and text.strip():
            return len(_WORD.findall(text))
    return 0


def _meta(opinion: Mapping[str, Any], key: str) -> object:
    value = opinion.get(key)
    if value not in (None, ""):
        return value
    cluster = opinion.get("cluster")
    if isinstance(cluster, Mapping):
        nested = cluster.get(key)
        if nested not in (None, ""):
            return nested
    return None


def _raw_docket(opinion: Mapping[str, Any]) -> str | None:
    raw = _meta(opinion, "docket_number")
    if raw in (None, ""):
        raw = _meta(opinion, "docket_id")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _docket_ids(opinion: Mapping[str, Any]) -> list[str]:
    raw = _meta(opinion, "docket_number")
    if raw in (None, ""):
        raw = _meta(opinion, "docket_id")
    parts: list[object]
    if isinstance(raw, list):
        parts = list(raw)
    elif raw in (None, ""):
        parts = []
    else:
        parts = [raw]
    cleaned: list[str] = []
    for part in parts:
        token = re.sub(r"[^A-Za-z0-9_-]", "", str(part))
        if token and token not in cleaned and _ENTITY_ID.fullmatch(token):
            cleaned.append(token[:128])
    return cleaned


def _name_list(opinion: Mapping[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = opinion.get(key)
        if isinstance(value, str) and value.strip():
            return [value.strip()[:200]]
        if isinstance(value, list):
            names = [str(item).strip()[:200] for item in value if str(item).strip()]
            if names:
                return names[:8]
    return []


def _suspect_names(opinion: Mapping[str, Any]) -> list[str]:
    names = _name_list(opinion, "defendant", "defendant_name", "suspect_names")
    if names:
        return names
    case_name = str(_meta(opinion, "case_name") or "")
    match = _VERSUS.search(case_name)
    if not match:
        return []
    name = match.group(1).strip().rstrip(".")
    if not name:
        return []
    return [name[:200]]


def _incident_date_or_year(opinion: Mapping[str, Any]) -> str:
    for key in ("incident_date_or_year", "incident_year", "incident_date"):
        value = opinion.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()[:200]
    filed = str(_meta(opinion, "date_filed") or "")
    if len(filed) >= 4 and filed[:4].isdigit():
        return filed[:4]
    return ""


def _county_state(opinion: Mapping[str, Any]) -> str:
    value = _meta(opinion, "county_state")
    if isinstance(value, str) and value.strip():
        return value.strip()[:200]
    return ""


def _seed_packet(opinion: Mapping[str, Any]) -> dict[str, Any]:
    suspects = _suspect_names(opinion)
    victims = _name_list(opinion, "victim", "victim_names")
    dockets = _docket_ids(opinion)
    incident = _incident_date_or_year(opinion)
    county = _county_state(opinion)
    if not incident or not county:
        raise ValueError("seed is missing incident year or county")
    if not (suspects or victims or dockets):
        raise ValueError("seed is missing a lookup key")
    for name in (*suspects, *victims):
        if not name or len(name) > 200:
            raise ValueError("seed name is empty or too long")
    seed = {
        "contract_version": CONTRACT_VERSION,
        "track": TRACK_B,
        "lead_classification": "LEAD_ONLY",
        "suspect_names": suspects,
        "victim_names": victims,
        "incident_date_or_year": incident,
        "county_state": county,
        "docket_ids": dockets,
        "unanswered_comment_questions": [],
    }
    if tuple(seed) != _SEED_KEYS:
        raise ValueError("seed keys drifted from SeedPacket")
    return seed
