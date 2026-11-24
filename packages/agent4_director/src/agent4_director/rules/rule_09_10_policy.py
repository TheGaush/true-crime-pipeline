"""RULE_09 & RULE_10: news hedging, graphic label blocks, dramatization badges."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

RULE_09 = "RULE_09"
RULE_10 = "RULE_10"

AUDIO_EVIDENCE_CARD = "AUDIO_EVIDENCE_CARD"
TRANSCRIPT_DRAMATIZATION_BADGE = "TRANSCRIPT DRAMATIZATION"

RULE_09_UNHEDGED_NEWS = "RULE_09_UNHEDGED_NEWS_CITATION"
RULE_09_GRAPHIC_DISTRESS_LABEL = "RULE_09_GRAPHIC_DISTRESS_LABEL"
RULE_09_UNKNOWN_FACT = "RULE_09_UNKNOWN_FACT_ID"

RULE_10_MISSING_BADGE = "RULE_10_MISSING_DRAMATIZATION_BADGE"
RULE_10_WRONG_LABEL = "RULE_10_WRONG_DRAMATIZATION_LABEL"

_ATTRIBUTION_HEDGE_RE = re.compile(r"\bnews\s+accounts?\s+reported\b", re.IGNORECASE)

_CLAUSE_SPLITS: tuple[re.Pattern[str], ...] = (
    re.compile(r";\s*however,\s*", re.IGNORECASE),
    re.compile(r";\s*but\s+", re.IGNORECASE),
    re.compile(r"\.\s+Meanwhile,\s+", re.IGNORECASE),
    re.compile(r",\s*but\s+", re.IGNORECASE),
)

_GRAPHIC_DISTRESS_LABELS: frozenset[str] = frozenset(
    {
        "gore_visible",
        "blood_pool",
        "graphic_injury",
        "distressed_victim_audio",
        "mutilation",
        "shocking_visual",
        "corpse_visible",
        "gunshot_wound",
        "stab_wound",
        "gore",
        "gory",
        "bloodbath",
        "mutilation",
        "graphic injury",
        "screaming victim",
    }
)

_VERBATIM_QUOTE_KINDS: frozenset[str] = frozenset({"suspect", "witness", "911"})


@dataclass(frozen=True, slots=True)
class Rule0910Violation:
    rule_id: str
    code: str
    message: str
    scene_id: str | None = None


@dataclass(frozen=True, slots=True)
class Rule0910Repair:
    rule_id: str
    scene_id: str
    code: str
    message: str


@dataclass(slots=True)
class Rule0910Result:
    violations: list[Rule0910Violation] = field(default_factory=list)
    repairs: list[Rule0910Repair] = field(default_factory=list)
    scenes: list[dict[str, Any]] | None = None

    @property
    def ok(self) -> bool:
        return not self.violations


def index_fact_ledger(
    ledger: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
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


def has_attribution_hedge(text: str) -> bool:
    return bool(_ATTRIBUTION_HEDGE_RE.search(text))


def _normalize_label(raw: str) -> str:
    return " ".join(raw.strip().split()).lower()


def _scene_id(scene: Mapping[str, Any]) -> str:
    return str(scene.get("scene_id") or scene.get("scene_plan_id") or "scene")


def _narration_text(scene: Mapping[str, Any]) -> str:
    return str(
        scene.get("approved_narration_text")
        or scene.get("narration_text")
        or scene.get("line")
        or ""
    )


def _cited_fact_ids(scene: Mapping[str, Any]) -> tuple[str, ...]:
    cited = scene.get("cited_fact_ids_json")
    if cited is None:
        cited = scene.get("cited_fact_ids", [])
    return tuple(str(x) for x in cited or ())


def _collect_on_screen_labels(scene: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    for key in ("on_screen_labels", "on_screen_labels_json", "screen_labels"):
        raw = scene.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            labels.append(raw)
        else:
            labels.extend(str(x) for x in raw)
    tags = scene.get("content_tags") or scene.get("graphic_distress_tags") or ()
    if isinstance(tags, str):
        labels.append(tags)
    else:
        labels.extend(str(x) for x in tags)
    return labels


def find_graphic_distress_labels(labels: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for raw in labels:
        norm = _normalize_label(raw)
        norm_underscore = norm.replace(" ", "_")
        if norm in _GRAPHIC_DISTRESS_LABELS or norm_underscore in _GRAPHIC_DISTRESS_LABELS:
            hits.append(raw)
        else:
            for banned in _GRAPHIC_DISTRESS_LABELS:
                if banned in norm or banned.replace("_", " ") in norm:
                    hits.append(raw)
                    break
    return hits


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


def _cited_source_flags(
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
    return cites_news, cites_primary, tuple(missing)


def check_scene_news_hedging(
    scene: Mapping[str, Any],
    facts_by_id: Mapping[str, Mapping[str, Any]],
) -> Rule0910Violation | None:
    cited = _cited_fact_ids(scene)
    if not cited:
        return None
    cites_news, cites_primary, missing = _cited_source_flags(cited, facts_by_id)
    scene_id = _scene_id(scene)
    if missing:
        return Rule0910Violation(
            RULE_09,
            RULE_09_UNKNOWN_FACT,
            f"Unknown cited fact id(s): {', '.join(missing)}",
            scene_id,
        )
    if not cites_news:
        return None

    line = _narration_text(scene).strip()
    if cites_primary:
        split = _split_mixed_narration(line)
        if split is not None:
            if has_attribution_hedge(split.news_clause):
                return None
            return Rule0910Violation(
                RULE_09,
                RULE_09_UNHEDGED_NEWS,
                "Mixed court/affidavit and news_report beat must hedge the news clause",
                scene_id,
            )

    if has_attribution_hedge(line):
        return None

    return Rule0910Violation(
        RULE_09,
        RULE_09_UNHEDGED_NEWS,
        "Beat cites news_report fact(s) but narration lacks explicit news attribution hedging",
        scene_id,
    )


def check_scene_graphic_distress_labels(
    scene: Mapping[str, Any],
) -> Rule0910Violation | None:
    labels = _collect_on_screen_labels(scene)
    hits = find_graphic_distress_labels(labels)
    if not hits:
        return None
    return Rule0910Violation(
        RULE_09,
        RULE_09_GRAPHIC_DISTRESS_LABEL,
        f"On-screen label blocked for graphic distress policy: {hits[0]!r}",
        _scene_id(scene),
    )


def scene_requires_dramatization_badge(scene: Mapping[str, Any]) -> bool:
    if scene.get("visual_engine") != AUDIO_EVIDENCE_CARD:
        return False
    if not scene.get("is_verbatim_quote"):
        return False
    if scene.get("quote_kind") not in _VERBATIM_QUOTE_KINDS:
        return False
    return scene.get("audio_delivery", "NARRATION") == "TTS"


def apply_rule_10_dramatization_badges(
    scenes: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[Rule0910Repair]]:
    """Ensure TTS verbatim quote cards expose the TRANSCRIPT DRAMATIZATION badge."""
    out: list[dict[str, Any]] = []
    repairs: list[Rule0910Repair] = []
    for raw in scenes:
        row = copy.deepcopy(dict(raw))
        if not scene_requires_dramatization_badge(row):
            out.append(row)
            continue

        scene_id = _scene_id(row)
        needs_badge = row.get("show_dramatization_badge") is not True
        label = row.get("dramatization_badge_label") or row.get("disclosure_badge_label")

        if needs_badge:
            row["show_dramatization_badge"] = True
            repairs.append(
                Rule0910Repair(
                    RULE_10,
                    scene_id,
                    RULE_10_MISSING_BADGE,
                    "Set show_dramatization_badge=true for TTS verbatim quote",
                )
            )

        if label != TRANSCRIPT_DRAMATIZATION_BADGE:
            row["dramatization_badge_label"] = TRANSCRIPT_DRAMATIZATION_BADGE
            repairs.append(
                Rule0910Repair(
                    RULE_10,
                    scene_id,
                    RULE_10_WRONG_LABEL,
                    f"Required dramatization badge label {TRANSCRIPT_DRAMATIZATION_BADGE!r}",
                )
            )

        out.append(row)
    return out, repairs


def validate_rule_09(
    scenes: Sequence[Mapping[str, Any]],
    fact_ledger: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
) -> Rule0910Result:
    facts_by_id = index_fact_ledger(fact_ledger)
    violations: list[Rule0910Violation] = []
    for scene in scenes:
        hedge_v = check_scene_news_hedging(scene, facts_by_id)
        if hedge_v is not None:
            violations.append(hedge_v)
        graphic_v = check_scene_graphic_distress_labels(scene)
        if graphic_v is not None:
            violations.append(graphic_v)
    return Rule0910Result(violations=violations, scenes=[dict(s) for s in scenes])


def validate_rule_10(
    scenes: Sequence[Mapping[str, Any]],
    *,
    auto_fix: bool = True,
) -> Rule0910Result:
    if not auto_fix:
        violations: list[Rule0910Violation] = []
        for scene in scenes:
            if not scene_requires_dramatization_badge(scene):
                continue
            scene_id = _scene_id(scene)
            if scene.get("show_dramatization_badge") is not True:
                violations.append(
                    Rule0910Violation(
                        RULE_10,
                        RULE_10_MISSING_BADGE,
                        "AUDIO_EVIDENCE_CARD TTS verbatim quote requires show_dramatization_badge",
                        scene_id,
                    )
                )
            label = scene.get("dramatization_badge_label") or scene.get(
                "disclosure_badge_label"
            )
            if label != TRANSCRIPT_DRAMATIZATION_BADGE:
                violations.append(
                    Rule0910Violation(
                        RULE_10,
                        RULE_10_WRONG_LABEL,
                        f"Badge label must be {TRANSCRIPT_DRAMATIZATION_BADGE!r}",
                        scene_id,
                    )
                )
        return Rule0910Result(
            violations=violations, scenes=[dict(s) for s in scenes]
        )

    fixed, repairs = apply_rule_10_dramatization_badges(scenes)
    return Rule0910Result(repairs=repairs, scenes=fixed)


def validate_rule_09_10(
    scenes: Sequence[Mapping[str, Any]],
    fact_ledger: Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]],
    *,
    auto_fix_rule_10: bool = True,
) -> Rule0910Result:
    r09 = validate_rule_09(scenes, fact_ledger)
    r10 = validate_rule_10(scenes, auto_fix=auto_fix_rule_10)
    working = r10.scenes or [dict(s) for s in scenes]
    violations = list(r09.violations)
    if not auto_fix_rule_10:
        violations.extend(r10.violations)
    return Rule0910Result(
        violations=violations,
        repairs=r10.repairs,
        scenes=working,
    )