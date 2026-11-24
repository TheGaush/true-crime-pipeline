"""Mandatory ``news_report`` attribution hedging verifier for script beats.

Cross-checks each beat's ``cited_fact_ids`` against a ``fact_ledger``. Any beat
that cites a ``news_report`` fact must carry explicit attribution hedging (for
example ``News accounts reported that``). ``court_ruling`` and
``police_affidavit`` citations alone do not require that hedge. Mixed beats
that cite both tiers must hedge the news clause, not the court holding.

Missing hedges yield a failure with a suggested rewritten narration line. This
module does not open a database or edit ``schema/pipeline.sql``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

SourceType = Literal["court_ruling", "police_affidavit", "news_report"]

VERIFIER_ID = "hedging-verifier@1"

NEWS_ATTRIBUTION_PREFIX = "News accounts reported that "
RULE_09_CODE = "RULE_09_UNHEDGED_NEWS_CITATION"
UNKNOWN_FACT_CODE = "UNKNOWN_FACT_ID"

_ATTRIBUTION_HEDGE_RE = re.compile(r"\bnews\s+accounts?\s+reported\b", re.IGNORECASE)
_EXISTING_PREFIX_RE = re.compile(r"^News accounts reported that\s+", re.IGNORECASE)

_CLAUSE_SPLITS: tuple[re.Pattern[str], ...] = (
    re.compile(r";\s*however,\s*", re.IGNORECASE),
    re.compile(r";\s*but\s+", re.IGNORECASE),
    re.compile(r"\.\s+Meanwhile,\s+", re.IGNORECASE),
    re.compile(r",\s*but\s+", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class ScriptBeat:
    """One narration beat with cited ``fact_ledger`` IDs."""

    beat_id: str
    narration_text: str
    cited_fact_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HedgingFailure:
    beat_id: str
    code: str
    message: str
    suggested_line: str | None = None


@dataclass(frozen=True, slots=True)
class HedgingVerdict:
    """Outcome of hedging verification across script beats."""

    passed: bool
    failures: tuple[HedgingFailure, ...]


def index_fact_ledger(
    ledger: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    """Build a ``fact_id`` -> row map from a ledger sequence or dict."""
    if isinstance(ledger, Mapping):
        if ledger and all(isinstance(k, str) for k in ledger):
            first = next(iter(ledger.values()), None)
            if first is not None and isinstance(first, Mapping) and "fact_id" in first:
                return {str(row["fact_id"]): row for row in ledger.values()}
            return dict(ledger)
    out: dict[str, Mapping[str, Any]] = {}
    for row in ledger:
        out[str(row["fact_id"])] = row
    return out


def beat_from_mapping(raw: Mapping[str, Any]) -> ScriptBeat:
    cited = raw.get("cited_fact_ids")
    if cited is None:
        cited = raw.get("cited_fact_ids_json", [])
    narration = (
        raw.get("narration_text")
        or raw.get("approved_narration_text")
        or raw.get("line")
        or ""
    )
    beat_id = str(
        raw.get("beat_id") or raw.get("scene_plan_id") or raw.get("plan_id") or "beat"
    )
    return ScriptBeat(
        beat_id=beat_id,
        narration_text=str(narration),
        cited_fact_ids=tuple(str(x) for x in cited),
    )


def has_attribution_hedge(text: str) -> bool:
    """Return True when *text* contains an approved news attribution hedge."""
    return bool(_ATTRIBUTION_HEDGE_RE.search(text))


def prefix_attribution(clause: str) -> str:
    """Prefix a clause with the standard news attribution hedge (idempotent)."""
    text = clause.strip()
    if not text:
        return NEWS_ATTRIBUTION_PREFIX.rstrip()
    if _EXISTING_PREFIX_RE.match(text):
        return text[0].upper() + text[1:] if text else text
    body = text[0].lower() + text[1:] if len(text) > 1 else text.lower()
    return f"{NEWS_ATTRIBUTION_PREFIX}{body}"


@dataclass(frozen=True, slots=True)
class _ClauseSplit:
    court_clause: str
    separator: str
    news_clause: str


def _split_mixed_narration(text: str) -> _ClauseSplit | None:
    for pattern in _CLAUSE_SPLITS:
        match = pattern.search(text)
        if match is None:
            continue
        left, right = pattern.split(text, maxsplit=1)
        left, right = left.strip(), right.strip()
        if left and right:
            return _ClauseSplit(left, match.group(0), right)
    return None


def _suggest_news_only(line: str) -> str:
    return prefix_attribution(line)


def _suggest_mixed(split: _ClauseSplit) -> str:
    hedged_news = prefix_attribution(split.news_clause)
    return f"{split.court_clause}{split.separator}{hedged_news}"


def _cited_source_types(
    cited_fact_ids: Sequence[str],
    facts_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, bool, tuple[str, ...]]:
    cites_news = False
    cites_primary = False
    missing: list[str] = []
    for fact_id in cited_fact_ids:
        row = facts_by_id.get(fact_id)
        if row is None:
            missing.append(fact_id)
            continue
        source = row.get("source_type")
        if source == "news_report":
            cites_news = True
        elif source in ("court_ruling", "police_affidavit"):
            cites_primary = True
        else:
            cites_primary = True
    return cites_news, cites_primary, tuple(missing)


def verify_beat_hedging(
    beat: ScriptBeat | Mapping[str, Any],
    fact_ledger: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> HedgingFailure | None:
    """Verify one beat. Return ``None`` when hedging requirements are satisfied."""
    if not isinstance(beat, ScriptBeat):
        beat = beat_from_mapping(beat)
    facts_by_id = index_fact_ledger(fact_ledger)
    cites_news, cites_primary, missing = _cited_source_types(
        beat.cited_fact_ids, facts_by_id
    )
    if missing:
        return HedgingFailure(
            beat_id=beat.beat_id,
            code=UNKNOWN_FACT_CODE,
            message=f"Unknown cited fact id(s): {', '.join(missing)}",
            suggested_line=None,
        )
    if not cites_news:
        return None

    line = beat.narration_text.strip()
    if cites_primary:
        split = _split_mixed_narration(line)
        if split is not None:
            if has_attribution_hedge(split.news_clause):
                return None
            return HedgingFailure(
                beat_id=beat.beat_id,
                code=RULE_09_CODE,
                message=(
                    "Mixed court/affidavit and news_report beat must hedge the "
                    "news clause with explicit attribution."
                ),
                suggested_line=_suggest_mixed(split),
            )

    if has_attribution_hedge(line):
        return None

    return HedgingFailure(
        beat_id=beat.beat_id,
        code=RULE_09_CODE,
        message=(
            "Beat cites news_report fact(s) but narration lacks explicit "
            "news attribution hedging."
        ),
        suggested_line=_suggest_news_only(line),
    )


def verify_beats_hedging(
    beats: Sequence[ScriptBeat | Mapping[str, Any]],
    fact_ledger: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> HedgingVerdict:
    """Verify every beat in *beats* against *fact_ledger*."""
    failures: list[HedgingFailure] = []
    for raw in beats:
        failure = verify_beat_hedging(raw, fact_ledger)
        if failure is not None:
            failures.append(failure)
    return HedgingVerdict(passed=not failures, failures=tuple(failures))