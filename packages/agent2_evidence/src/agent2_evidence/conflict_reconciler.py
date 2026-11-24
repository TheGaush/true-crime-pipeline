"""Conflict and alibi reconciler (`evidence-conflict-reconciler@1`).

Overlapping timeline claims are routed to the injected reasoning client using
the ``contradiction_reasoning`` model id from ``providers.yaml``. This module
does not open sockets, call tools, or write SQLite.

Judicial hierarchy: ``court_ruling`` > ``police_affidavit`` > ``news_report``.
When two facts at the same tier still conflict, both are kept and marked
disputed rather than guessing a winner. A discredited alibi is linked to the
fact that discredits it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared_contracts.models import TemporalFact, TemporalFactLedger
from shared_contracts.version import CONTRACT_VERSION

PROMPT_CONTRACT_ID = "evidence-conflict-reconciler@1"
TOOLS_ENABLED = False
WRITES_DATABASE = False

_SOURCE_TYPES = ("court_ruling", "police_affidavit", "news_report")
_TIER_RANK = {name: index for index, name in enumerate(_SOURCE_TYPES)}
_ENTITY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_ID_LINE = re.compile(r"^- id:\s*(\S+)\s*$")
_ROLES_LINE = re.compile(r"^roles:\s*\[([^\]]*)\]\s*$")

ReasoningClient = Callable[[str, str], str]


class ConflictReconciliationError(ValueError):
    """The ledger could not be reconciled from model output."""


@dataclass(frozen=True)
class ReconciledFact:
    """One ledger fact plus reconciliation metadata (not a DB row)."""

    fact: TemporalFact
    disputed: bool = False
    discredited_alibi: bool = False
    discredited_by: str | None = None


@dataclass(frozen=True)
class ConflictReconciliation:
    """Reconciled ledger and audit metadata."""

    prompt_contract_id: str
    model_id: str
    case_id: str
    facts: tuple[ReconciledFact, ...]
    disputed_fact_ids: tuple[str, ...]
    discredited_alibi_links: Mapping[str, str]
    tools_enabled: bool = False
    writes_database: bool = False

    @property
    def ledger(self) -> TemporalFactLedger:
        return TemporalFactLedger(
            contract_version=CONTRACT_VERSION,
            case_id=self.case_id,
            facts=[item.fact for item in self.facts],
        )


def default_providers_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "providers.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("providers.yaml")


def load_reasoning_model_id(path: str | Path | None = None, *, role: str = "contradiction_reasoning") -> str:
    """Return the sole model id in ``providers.yaml`` that lists ``role``."""

    source = Path(path) if path is not None else default_providers_path()
    text = source.read_text(encoding="utf-8")
    pending: str | None = None
    matches: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        id_match = _ID_LINE.match(line)
        if id_match:
            pending = id_match.group(1).strip("'\"")
            continue
        roles_match = _ROLES_LINE.match(line)
        if roles_match and pending is not None:
            roles = [
                part.strip().strip("'\"")
                for part in roles_match.group(1).split(",")
                if part.strip()
            ]
            if role in roles:
                matches.append(pending)
            pending = None
            continue
        pending = None
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise LookupError(f"expected exactly one model id for role {role}, found {unique}")
    return unique[0]


def _tier(source_type: str) -> int:
    try:
        return _TIER_RANK[source_type]
    except KeyError as exc:
        raise ConflictReconciliationError(f"unsupported source_type: {source_type}") from exc


def _entity_id(value: Any, label: str) -> str:
    token = str(value)
    if _ENTITY_RE.fullmatch(token) is None or len(token) > 128:
        raise ConflictReconciliationError(f"{label} must be a valid fact id")
    return token


def _parse_model_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ConflictReconciliationError("reasoning client returned empty text")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        if start < 0:
            raise ConflictReconciliationError("reasoning client did not return JSON") from None
        payload = json.loads(stripped[start:])
    if not isinstance(payload, dict):
        raise ConflictReconciliationError("reasoning payload must be a JSON object")
    return payload


def _conflict_groups(payload: Mapping[str, Any], known_ids: frozenset[str]) -> list[dict[str, Any]]:
    raw = payload.get("conflict_groups", [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConflictReconciliationError("conflict_groups must be a list")
    groups: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ConflictReconciliationError("each conflict group must be an object")
        fact_ids_raw = item.get("fact_ids")
        if not isinstance(fact_ids_raw, list) or len(fact_ids_raw) < 2:
            raise ConflictReconciliationError("conflict group requires at least two fact_ids")
        fact_ids = tuple(_entity_id(value, "fact_ids entry") for value in fact_ids_raw)
        for fact_id in fact_ids:
            if fact_id not in known_ids:
                raise ConflictReconciliationError(f"unknown fact_id in model output: {fact_id}")
        if len(set(fact_ids)) != len(fact_ids):
            raise ConflictReconciliationError("duplicate fact_id inside a conflict group")
        alibi_id = item.get("alibi_fact_id")
        discredit_id = item.get("discrediting_fact_id")
        parsed: dict[str, Any] = {"fact_ids": fact_ids}
        if alibi_id is not None:
            parsed["alibi_fact_id"] = _entity_id(alibi_id, "alibi_fact_id")
            if parsed["alibi_fact_id"] not in fact_ids:
                raise ConflictReconciliationError("alibi_fact_id must appear in fact_ids")
        if discredit_id is not None:
            parsed["discrediting_fact_id"] = _entity_id(discredit_id, "discrediting_fact_id")
            if parsed["discrediting_fact_id"] not in fact_ids:
                raise ConflictReconciliationError("discrediting_fact_id must appear in fact_ids")
        groups.append(parsed)
    return groups


def _build_prompt(ledger: TemporalFactLedger) -> str:
    compact = [
        {
            "fact_id": fact.fact_id,
            "source_type": fact.source_type,
            "datetime_iso": fact.datetime_iso,
            "event_summary": fact.event_summary,
            "location_text": fact.location_text,
        }
        for fact in ledger.facts
    ]
    rules = (
        "Identify timeline conflicts only among the given fact_id values.\n"
        "Return strict JSON: {\"conflict_groups\":[{\"fact_ids\":[\"...\"],"
        "\"alibi_fact_id\":null,\"discrediting_fact_id\":null}]}.\n"
        "Use alibi_fact_id and discrediting_fact_id when one fact is a suspect alibi "
        "and another primary-record fact discredits it.\n"
        "Do not invent fact_ids. If no conflicts exist, return {\"conflict_groups\":[]}.\n"
    )
    return rules + json.dumps({"case_id": ledger.case_id, "facts": compact}, ensure_ascii=False)


class ConflictReconciler:
    """Apply V4-Pro conflict reasoning with judicial source-tier precedence."""

    def __init__(
        self,
        providers_path: str | Path | None = None,
        *,
        model_client: ReasoningClient,
        model_id: str | None = None,
    ) -> None:
        if TOOLS_ENABLED or WRITES_DATABASE:
            raise ConflictReconciliationError("reconciler cannot enable tools or database writes")
        self._providers_path = Path(providers_path) if providers_path is not None else default_providers_path()
        self._model_client = model_client
        self._model_id = model_id or load_reasoning_model_id(self._providers_path)

    @property
    def model_id(self) -> str:
        return self._model_id

    def reconcile(self, ledger: TemporalFactLedger) -> ConflictReconciliation:
        if not isinstance(ledger, TemporalFactLedger):
            raise TypeError("ledger must be a TemporalFactLedger")
        known = {fact.fact_id: fact for fact in ledger.facts}
        prompt = _build_prompt(ledger)
        model_text = self._model_client(self._model_id, prompt)
        groups = _conflict_groups(_parse_model_payload(model_text), frozenset(known))
        return _apply_groups(ledger, groups, model_id=self._model_id)


def reconcile_conflicts(
    ledger: TemporalFactLedger,
    *,
    model_client: ReasoningClient,
    providers_path: str | Path | None = None,
) -> ConflictReconciliation:
    """Reconcile one ledger. See ``ConflictReconciler.reconcile``."""

    return ConflictReconciler(providers_path=providers_path, model_client=model_client).reconcile(ledger)


def _merge_contradicts(existing: Sequence[str], extra: Sequence[str]) -> list[str]:
    merged = list(existing)
    seen = set(existing)
    for item in extra:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


def _apply_groups(
    ledger: TemporalFactLedger,
    groups: Sequence[Mapping[str, Any]],
    *,
    model_id: str,
) -> ConflictReconciliation:
    by_id = {fact.fact_id: fact.model_copy(deep=True) for fact in ledger.facts}
    disputed: set[str] = set()
    alibi_links: dict[str, str] = {}
    meta: dict[str, dict[str, Any]] = {
        fact_id: {"disputed": False, "discredited_alibi": False, "discredited_by": None}
        for fact_id in by_id
    }

    for group in groups:
        fact_ids = group["fact_ids"]
        members = [by_id[fact_id] for fact_id in fact_ids]
        tiers = {_tier(member.source_type) for member in members}
        alibi_id = group.get("alibi_fact_id")
        discredit_id = group.get("discrediting_fact_id")

        if alibi_id and discredit_id:
            alibi_links[str(alibi_id)] = str(discredit_id)
            meta[str(alibi_id)]["discredited_alibi"] = True
            meta[str(alibi_id)]["discredited_by"] = str(discredit_id)
            by_id[str(alibi_id)] = by_id[str(alibi_id)].model_copy(
                update={
                    "contradicts_json": _merge_contradicts(
                        by_id[str(alibi_id)].contradicts_json,
                        (str(discredit_id),),
                    )
                }
            )

        if len(tiers) == 1:
            for fact_id in fact_ids:
                disputed.add(fact_id)
                meta[fact_id]["disputed"] = True
            for left in fact_ids:
                others = [other for other in fact_ids if other != left]
                by_id[left] = by_id[left].model_copy(
                    update={"contradicts_json": _merge_contradicts(by_id[left].contradicts_json, others)}
                )
            continue

        winner = min(members, key=lambda item: _tier(item.source_type))
        winner_id = winner.fact_id
        losers = [member.fact_id for member in members if member.fact_id != winner_id]
        for loser_id in losers:
            by_id[loser_id] = by_id[loser_id].model_copy(
                update={
                    "contradicts_json": _merge_contradicts(by_id[loser_id].contradicts_json, (winner_id,))
                }
            )
            if alibi_id == loser_id and discredit_id:
                by_id[loser_id] = by_id[loser_id].model_copy(
                    update={
                        "contradicts_json": _merge_contradicts(
                            by_id[loser_id].contradicts_json,
                            (str(discredit_id),),
                        )
                    }
                )

    ordered = tuple(
        ReconciledFact(
            fact=by_id[fact.fact_id],
            disputed=meta[fact.fact_id]["disputed"],
            discredited_alibi=meta[fact.fact_id]["discredited_alibi"],
            discredited_by=meta[fact.fact_id]["discredited_by"],
        )
        for fact in ledger.facts
    )
    return ConflictReconciliation(
        prompt_contract_id=PROMPT_CONTRACT_ID,
        model_id=model_id,
        case_id=ledger.case_id,
        facts=ordered,
        disputed_fact_ids=tuple(sorted(disputed)),
        discredited_alibi_links=alibi_links,
        tools_enabled=False,
        writes_database=False,
    )