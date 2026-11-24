"""CourtListener appellate opinion harvester for Agent 2.

Fetches opinion payloads through an injected ``fetch_opinion`` callable,
keeps a simple in-process cache (task 008's persistent rate limiter is not
required here), splits majority from concurring and dissenting sections, and
emits ``primary_documents``-shaped metadata plus normalized text suitable for
``fact_ledger`` citation locators (``p. 12``, ``para. 3``, …).

Dissenting sections are explicitly tagged and never marked as holdings so
downstream extraction cannot treat speculative dissent arguments as established
law.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

OpinionFetcher = Callable[[str], Mapping[str, Any]]

SectionRole = Literal["majority", "concurring", "dissent"]

_CITATION_LOCATOR = re.compile(
    r"\b(?:"
    r"(?:p\.|pp\.)\s*\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*para\.\s*\d+)?|"
    r"para\.\s*\d+|"
    r"paragraph\s+\d+|"
    r"¶\s*\d+"
    r")\b",
    re.IGNORECASE,
)
_BLOCK_BREAK = re.compile(r"</?(?:p|div|br|h[1-6]|li|tr|blockquote)[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", re.IGNORECASE | re.DOTALL)

_PLAIN_SECTION_HEAD = re.compile(
    r"(?im)^\s*(?:"
    r"OPINION OF THE COURT|Opinion of the Court|PER CURIAM|"
    r"CONCURRING(?:\s+OPINION)?|Concurring(?:\s+Opinion)?|"
    r"DISSENT(?:ING)?(?:\s+OPINION)?|Dissenting(?:\s+Opinion)?"
    r")\s*:?\s*$"
)

_HTML_SECTION_HEAD = re.compile(
    r"(?is)<h[1-4][^>]*>\s*("
    r"OPINION OF THE COURT|Opinion of the Court|PER CURIAM|"
    r"CONCURRING(?:\s+OPINION)?|Concurring(?:\s+Opinion)?|"
    r"DISSENT(?:ING)?(?:\s+OPINION)?|Dissenting(?:\s+Opinion)?"
    r")\s*</h[1-4]>"
)

_ROLE_FROM_LABEL: list[tuple[re.Pattern[str], SectionRole]] = [
    (re.compile(r"^OPINION OF THE COURT$", re.I), "majority"),
    (re.compile(r"^Opinion of the Court$", re.I), "majority"),
    (re.compile(r"^PER CURIAM$", re.I), "majority"),
    (re.compile(r"^CONCURRING", re.I), "concurring"),
    (re.compile(r"^Concurring", re.I), "concurring"),
    (re.compile(r"^DISSENT", re.I), "dissent"),
    (re.compile(r"^Dissenting", re.I), "dissent"),
]


class CourtListenerHarvesterError(ValueError):
    """Raised when an opinion payload cannot be normalized."""


@dataclass(frozen=True, slots=True)
class OpinionSection:
    section_id: str
    role: SectionRole
    is_holding: bool
    heading: str
    text: str
    citation_locators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HarvestedOpinion:
    opinion_id: str
    case_name: str
    sections: tuple[OpinionSection, ...]
    majority_text: str
    full_normalized_text: str
    citation_locators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HarvestResult:
    harvested: HarvestedOpinion
    primary_document: dict[str, Any]
    cache_hit: bool


def _role_for_heading(label: str) -> SectionRole:
    trimmed = label.strip()
    for pattern, role in _ROLE_FROM_LABEL:
        if pattern.search(trimmed):
            return role
    return "majority"


def _is_holding(role: SectionRole) -> bool:
    return role == "majority"


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    cleaned: list[str] = []
    prior_blank = False
    for line in lines:
        if not line:
            if not prior_blank and cleaned:
                cleaned.append("")
            prior_blank = True
            continue
        cleaned.append(line)
        prior_blank = False
    return "\n".join(cleaned).strip()


def _html_to_text(fragment: str) -> str:
    without_embedded = _SCRIPT_STYLE.sub("", fragment)
    with_breaks = _BLOCK_BREAK.sub("\n", without_embedded)
    bare = _TAG.sub("", with_breaks)
    return _normalize_whitespace(html_lib.unescape(bare))


def _extract_citation_locators(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for match in _CITATION_LOCATOR.finditer(text):
        token = match.group(0)
        if token not in seen:
            seen.append(token)
    return tuple(seen)


def _split_html_sections(html: str) -> list[tuple[str, str]]:
    matches = list(_HTML_SECTION_HEAD.finditer(html))
    if not matches:
        body = _html_to_text(html)
        if body:
            return [("Opinion of the Court", body)]
        return []

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        prefix = _html_to_text(html[: matches[0].start()])
        if prefix:
            sections.append(("Opinion of the Court", prefix))

    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        sections.append((heading, _html_to_text(html[start:end])))
    return sections


def _split_plain_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = "Opinion of the Court"
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        joined = _normalize_whitespace("\n".join(buffer))
        if joined:
            sections.append((current_heading, joined))
        buffer = []

    for line in lines:
        if _PLAIN_SECTION_HEAD.match(line):
            flush()
            current_heading = line.strip().rstrip(":")
            continue
        buffer.append(line)
    flush()

    if not sections and text.strip():
        return [("Opinion of the Court", _normalize_whitespace(text))]
    return sections


def _opinion_body(payload: Mapping[str, Any]) -> tuple[str, bool]:
    for key in ("html_with_citations", "html", "html_lawbox"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value, True
    plain = payload.get("plain_text")
    if isinstance(plain, str) and plain.strip():
        return plain, False
    raise CourtListenerHarvesterError("opinion payload has no html or plain_text")


def _parse_sections(raw: str, *, from_html: bool) -> list[tuple[str, str]]:
    if from_html:
        sections = _split_html_sections(raw)
        if sections:
            return sections
    if from_html:
        text = _html_to_text(raw)
    else:
        text = _normalize_whitespace(raw)
    return _split_plain_sections(text)


def _section_tag(role: SectionRole) -> str:
    return {
        "majority": "MAJORITY",
        "concurring": "CONCURRING",
        "dissent": "DISSENT",
    }[role]


def _build_full_text(sections: Sequence[OpinionSection]) -> str:
    blocks: list[str] = []
    for section in sections:
        blocks.append(f"[{_section_tag(section.role)}]")
        blocks.append(section.text)
    return "\n\n".join(blocks).strip()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_domain(absolute_url: str) -> str:
    parsed = urlparse(absolute_url)
    return parsed.netloc or "courtlistener.com"


class CourtListenerHarvester:
    """Fetch, cache, split, and normalize a single CourtListener opinion."""

    def __init__(self, fetch_opinion: OpinionFetcher) -> None:
        self._fetch_opinion = fetch_opinion
        self._cache: dict[str, Mapping[str, Any]] = {}
        self.fetch_call_count = 0

    def clear_cache(self) -> None:
        self._cache.clear()

    def harvest(
        self,
        opinion_id: str,
        *,
        case_id: str,
        fetched_at: int,
        local_text_path: str | None = None,
    ) -> HarvestResult:
        if not opinion_id:
            raise ValueError("opinion_id is required")
        if not case_id:
            raise ValueError("case_id is required")
        if fetched_at < 0:
            raise ValueError("fetched_at must be >= 0")

        cache_hit = opinion_id in self._cache
        if cache_hit:
            payload = self._cache[opinion_id]
        else:
            fetched = self._fetch_opinion(opinion_id)
            if not isinstance(fetched, Mapping):
                raise TypeError("fetch_opinion must return a mapping")
            payload = fetched
            self._cache[opinion_id] = payload
            self.fetch_call_count += 1

        body, from_html = _opinion_body(payload)
        raw_sections = _parse_sections(body, from_html=from_html)
        if not raw_sections:
            raise CourtListenerHarvesterError(f"opinion {opinion_id} has no extractable text")

        opinion_sections: list[OpinionSection] = []
        for index, (heading, text) in enumerate(raw_sections, start=1):
            role = _role_for_heading(heading)
            locators = _extract_citation_locators(text)
            opinion_sections.append(
                OpinionSection(
                    section_id=f"{opinion_id}-s{index}",
                    role=role,
                    is_holding=_is_holding(role),
                    heading=heading,
                    text=text,
                    citation_locators=locators,
                )
            )

        sections_tuple = tuple(opinion_sections)
        majority_parts = [s.text for s in sections_tuple if s.role == "majority"]
        majority_text = "\n\n".join(majority_parts).strip()
        full_text = _build_full_text(sections_tuple)
        all_locators: list[str] = []
        for section in sections_tuple:
            for loc in section.citation_locators:
                if loc not in all_locators:
                    all_locators.append(loc)

        case_name = str(payload.get("case_name") or "Unknown Case")
        absolute_url = str(
            payload.get("absolute_url")
            or f"https://www.courtlistener.com/opinion/{opinion_id}/"
        )
        text_path = local_text_path or f"raw_courtlistener/{case_id}/opinion_{opinion_id}.txt"

        harvested = HarvestedOpinion(
            opinion_id=str(payload.get("id", opinion_id)),
            case_name=case_name,
            sections=sections_tuple,
            majority_text=majority_text,
            full_normalized_text=full_text,
            citation_locators=tuple(all_locators),
        )

        primary_document = {
            "doc_id": f"{case_id}_doc_cl_{opinion_id}",
            "case_id": case_id,
            "source_domain": _source_domain(absolute_url),
            "source_url": absolute_url,
            "doc_type": "court_ruling",
            "raw_text_sha256": _sha256(full_text),
            "local_text_path": text_path,
            "fetched_at": fetched_at,
        }

        return HarvestResult(
            harvested=harvested,
            primary_document=primary_document,
            cache_hit=cache_hit,
        )