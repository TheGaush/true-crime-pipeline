"""Config-driven canonical search alias expansion (`alias-expander@1`)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

CONTRACT_ID = "alias-expander@1"
MAX_ALIASES = 4
MIN_ALIASES = 3

DEFER_REASON_YOUTUBE_XRAY = "waiting for youtube-xray name extraction"

LLMCallable = Callable[[str, str], str]

_TITLE_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "he",
        "her",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "she",
        "that",
        "the",
        "their",
        "them",
        "they",
        "them",
        "this",
        "to",
        "want",
        "know",
        "don",
        "dont",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
        # common true-crime clickbait openers
        "disturbing",
        "shocking",
        "unbelievable",
        "unsolved",
        "mystery",
        "story",
        "case",
        "truth",
        "real",
        "scariest",
        "creepiest",
        "gone",
        "missing",
        "solved",
        "never",
        "finally",
        "updated",
        "part",
        "episode",
    }
)

_PERSON_NAME_RE = re.compile(
    r"\b([A-Z][a-z]+(?:['-][A-Z]?[a-z]+)?)(?:\s+([A-Z][a-z]+(?:['-][A-Z]?[a-z]+)?))+\b"
)
_PLACE_HINT_RE = re.compile(
    r"\b(?:county|parish|township|borough)\b",
    re.IGNORECASE,
)
_STATE_ABBREV_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?\s+[A-Z]{2}\b")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\s]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class CaseFacts:
    """Factual lookup keys available before or after metadata lead extraction."""

    title: str
    suspect_full_name: str | None = None
    incident_year: str | int | None = None
    victim_name: str | None = None
    crime_type: str | None = None
    city: str | None = None
    case_nickname: str | None = None
    forensic_detail: str | None = None


@dataclass(frozen=True, slots=True)
class AliasExpansionReady:
    aliases: tuple[str, ...]
    model_id: str
    status: Literal["ready"] = "ready"
    contract_id: str = CONTRACT_ID


@dataclass(frozen=True, slots=True)
class AliasExpansionDeferred:
    reason: str
    status: Literal["deferred"] = "deferred"
    contract_id: str = CONTRACT_ID


AliasExpansionOutcome = AliasExpansionReady | AliasExpansionDeferred


def default_model_id(provider_config: Mapping[str, Any]) -> str:
    """Resolve the default model for ``alias-expander@1`` from a providers-shaped dict."""

    contracts = provider_config.get("prompt_contracts", provider_config)
    if isinstance(contracts, Mapping):
        entry = contracts.get(CONTRACT_ID)
        if isinstance(entry, Mapping) and (model_id := entry.get("model_id")):
            return str(model_id)

    providers = provider_config.get("providers", {})
    if isinstance(providers, Mapping):
        for provider in providers.values():
            if not isinstance(provider, Mapping):
                continue
            for model in provider.get("models", ()):
                if not isinstance(model, Mapping):
                    continue
                roles = model.get("roles", ())
                if "alias_expansion" in roles:
                    return str(model["id"])

    roles = provider_config.get("roles", ())
    if isinstance(roles, Mapping) and (model_id := roles.get("alias_expansion")):
        return str(model_id)

    raise KeyError(
        f"No model routing found for {CONTRACT_ID!r} or role 'alias_expansion' in provider_config"
    )


def normalize_alias_query(query: str) -> str:
    folded = query.casefold()
    stripped = _PUNCTUATION_RE.sub(" ", folded)
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def dedupe_queries(queries: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw in queries:
        normalized = normalize_alias_query(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
        if len(unique) >= MAX_ALIASES:
            break
    return tuple(unique)


def _name_like_tokens(fragment: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", fragment)
    return [
        token
        for token in raw_tokens
        if token.casefold() not in _TITLE_STOPWORDS and len(token) >= 4
    ]


def title_has_person_or_place_name(title: str) -> bool:
    if _PLACE_HINT_RE.search(title) or _STATE_ABBREV_RE.search(title):
        return True

    for match in _PERSON_NAME_RE.finditer(title):
        tokens = _name_like_tokens(match.group(0))
        if len(tokens) >= 2:
            return True
    return False


def _non_empty(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def available_alias_slots(facts: CaseFacts) -> dict[str, str]:
    """Map canonical slot labels to grounded values; omit slots with missing inputs."""

    slots: dict[str, str] = {}

    suspect = _non_empty(facts.suspect_full_name)
    year = _non_empty(facts.incident_year)
    if suspect and year:
        slots["suspect_full_name_year"] = f"{suspect} {year}"

    victim = _non_empty(facts.victim_name)
    crime = _non_empty(facts.crime_type)
    if victim and crime:
        slots["victim_name_crime"] = f"{victim} {crime}"

    city = _non_empty(facts.city)
    nickname = _non_empty(facts.case_nickname)
    if city and nickname:
        slots["city_case_nickname"] = f"{city} {nickname}"

    forensic = _non_empty(facts.forensic_detail)
    if forensic:
        slots["unique_forensic_detail"] = forensic

    return slots


def _wrap_data_envelope(payload: Mapping[str, Any]) -> str:
    body = json.dumps(payload, indent=2, sort_keys=True)
    return f"<data>\n{body}\n</data>"


def _build_prompt(slots: Mapping[str, str], facts: CaseFacts) -> str:
    instructions = (
        "You are the alias-expander@1 LEAD_ONLY extractor. "
        "Return a JSON array of 3 to 4 YouTube search query strings. "
        "Use ONLY the grounded slot values provided. "
        "Do not invent names, places, or forensic details. "
        "Each array element must correspond to one provided slot value "
        "(you may lightly reorder words but must keep the same entities)."
    )
    envelope = _wrap_data_envelope(
        {
            "contract_id": CONTRACT_ID,
            "title": facts.title,
            "canonical_slots": dict(slots),
            "rules": {
                "max_aliases": MAX_ALIASES,
                "min_aliases": MIN_ALIASES,
                "omit_missing_slots": True,
            },
        }
    )
    return f"{instructions}\n\n{envelope}"


def parse_alias_response(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []

    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return [line.strip() for line in text.splitlines() if line.strip()]

    if isinstance(decoded, list):
        return [str(item).strip() for item in decoded if str(item).strip()]
    if isinstance(decoded, Mapping) and isinstance(decoded.get("aliases"), list):
        return [str(item).strip() for item in decoded["aliases"] if str(item).strip()]
    return []


class CanonicalAliasExpander:
    """Expand grounded case facts into at most four deduplicated YouTube search aliases."""

    def __init__(
        self,
        *,
        llm: LLMCallable,
        provider_config: Mapping[str, Any],
        model_id: str | None = None,
    ) -> None:
        self._llm = llm
        self._provider_config = provider_config
        self._model_id = model_id if model_id is not None else default_model_id(provider_config)

    @property
    def model_id(self) -> str:
        return self._model_id

    def expand(self, facts: CaseFacts) -> AliasExpansionOutcome:
        if not title_has_person_or_place_name(facts.title):
            return AliasExpansionDeferred(reason=DEFER_REASON_YOUTUBE_XRAY)

        slots = available_alias_slots(facts)
        if not slots:
            return AliasExpansionDeferred(reason=DEFER_REASON_YOUTUBE_XRAY)

        prompt = _build_prompt(slots, facts)
        raw = self._llm(self._model_id, prompt)
        parsed = parse_alias_response(raw)
        aliases = dedupe_queries(parsed)
        if len(aliases) < MIN_ALIASES:
            # Fall back to grounded slot strings if the model returned too few unique lines.
            aliases = dedupe_queries([*parsed, *slots.values()])

        return AliasExpansionReady(aliases=aliases, model_id=self._model_id)