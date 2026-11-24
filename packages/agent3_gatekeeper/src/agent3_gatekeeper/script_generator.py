"""Fact-grounded, topology-safe documentary script compiler (Task 052).

Consumes a temporal fact ledger, turning-point beats, craft rubric guidance, and
pre-locked spatial anchors. Produces per-scene plan rows with cited narration
before voice synthesis or visual creation. No sockets or paid APIs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

TOTAL_MASTER_SEC = 1200
NARRATION_WPM = 145

EPISODE_STATUS_SCENE_PLAN_APPROVED = "SCENE_PLAN_APPROVED"

REJECTED_UNLOCKED_ANCHORS = "REJECTED_UNLOCKED_SPATIAL_ANCHORS"
REJECTED_UNKNOWN_FACT_CITE = "REJECTED_UNKNOWN_FACT_CITATION"
REJECTED_MISSING_SCENE_FIELDS = "REJECTED_INCOMPLETE_SCENE_PLAN"
REJECTED_LOW_BEAT_COUNT = "REJECTED_INSUFFICIENT_BEATS"

CompilationStatus = Literal["OK", "REJECTED"]

_FACT_ID_IN_TEXT = re.compile(r"\b(fact_[A-Za-z0-9_-]+)\b")
_BRACKETED_FACT = re.compile(r"\[([A-Za-z0-9_-]+)\]")


def compute_target_narration_words(foia_total_sec: float) -> float:
    """FOIA-aware narration word budget for a 20-minute master timeline."""
    if foia_total_sec < 0:
        raise ValueError("foia_total_sec must be non-negative")
    if foia_total_sec > TOTAL_MASTER_SEC:
        raise ValueError("foia_total_sec cannot exceed total master duration")
    narration_sec = TOTAL_MASTER_SEC - foia_total_sec
    return narration_sec / 60.0 * NARRATION_WPM


def narration_version_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_words(text: str) -> int:
    return len(text.split())


def extract_asserted_fact_ids(narration_text: str) -> frozenset[str]:
    """Fact ids explicitly named in narration (bare or bracketed)."""
    found: set[str] = set(_FACT_ID_IN_TEXT.findall(narration_text))
    for token in _BRACKETED_FACT.findall(narration_text):
        if token.startswith("fact_"):
            found.add(token)
    return frozenset(found)


def topology_safe_clause(
    *,
    event_summary: str,
    source_type: str,
    citation_locator: str,
    clue_name: str | None = None,
) -> str:
    """Record-anchored phrasing that does not imply measured room geometry."""
    source_phrase = {
        "police_affidavit": "the affidavit",
        "court_ruling": "the court record",
        "news_report": "contemporaneous reporting",
    }.get(source_type, "the primary record")
    anchor = (
        f" According to {source_phrase} ({citation_locator}), "
        f"an illustrative reconstruction marks {clue_name} on the plate"
        if clue_name
        else f" According to {source_phrase} ({citation_locator}),"
    )
    return f"{anchor} {event_summary.rstrip('.')}. The view is illustrative, not a measured layout."


@dataclass(frozen=True, slots=True)
class BeatInput:
    beat_id: str
    fact_id: str
    datetime_iso: str
    citation_locator: str
    source_type: str
    record_anchor: str
    editorial_analysis: str = ""


@dataclass(frozen=True, slots=True)
class AnchorInput:
    anchor_id: str
    lock_status: str
    clue_name: str
    cited_fact_id: str | None = None
    grid_cell: str = "A1"


@dataclass(frozen=True, slots=True)
class FactInput:
    fact_id: str
    event_summary: str
    source_type: str
    citation_locator: str
    datetime_iso: str = "2020-01-01T12:00:00Z"


@dataclass(frozen=True, slots=True)
class CompiledScenePlan:
    scene_plan_id: str
    scene_id: str
    seq_index: int
    story_purpose: str
    intended_audience_effect: str
    approved_narration_text: str
    narration_version_sha256: str
    cited_fact_ids: tuple[str, ...]
    anchor_id: str | None = None

    def stage1_fields_complete(self) -> bool:
        return bool(
            self.story_purpose.strip()
            and self.intended_audience_effect.strip()
            and self.approved_narration_text.strip()
            and self.narration_version_sha256
            and len(self.cited_fact_ids) >= 1
            and self.narration_version_sha256
            == narration_version_sha256(self.approved_narration_text)
        )


def scene_plan_stage1_approved(plan: CompiledScenePlan) -> bool:
    return plan.stage1_fields_complete()


@dataclass(frozen=True, slots=True)
class ScriptCompileResult:
    status: CompilationStatus
    reason: str | None
    episode_status: str | None
    target_narration_words: float
    narration_word_count: int
    scene_plans: tuple[CompiledScenePlan, ...] = field(default_factory=tuple)

    @property
    def accepted(self) -> bool:
        return self.status == "OK"


def _all_anchors_locked(anchors: Sequence[AnchorInput]) -> bool:
    if not anchors:
        return False
    return all(anchor.lock_status == "LOCKED" for anchor in anchors)


def _validate_narration_facts(
    narration_text: str,
    cited_fact_ids: Sequence[str],
    allowed_fact_ids: frozenset[str],
) -> str | None:
    unknown_in_citations = [fid for fid in cited_fact_ids if fid not in allowed_fact_ids]
    if unknown_in_citations:
        return REJECTED_UNKNOWN_FACT_CITE
    asserted = extract_asserted_fact_ids(narration_text)
    unknown_in_text = sorted(asserted - allowed_fact_ids)
    if unknown_in_text:
        return REJECTED_UNKNOWN_FACT_CITE
    missing_from_citations = sorted(asserted - frozenset(cited_fact_ids))
    if missing_from_citations:
        return REJECTED_UNKNOWN_FACT_CITE
    return None


def _fact_lookup(facts: Sequence[FactInput]) -> dict[str, FactInput]:
    return {fact.fact_id: fact for fact in facts}


def _pick_anchor_for_fact(
    fact_id: str,
    anchors: Sequence[AnchorInput],
    index: int,
) -> AnchorInput:
    for anchor in anchors:
        if anchor.cited_fact_id == fact_id:
            return anchor
    return anchors[index % len(anchors)]


class GroundedScriptGenerator:
    """Compile topology-safe scene narration bound to locked spatial anchors."""

    def __init__(self, *, craft_rubric: Mapping[str, Any] | None = None) -> None:
        self._craft_rubric = craft_rubric or {}

    def compile(
        self,
        *,
        episode_id: str,
        foia_total_sec: float,
        facts: Sequence[FactInput],
        beats: Sequence[BeatInput],
        spatial_anchors: Sequence[AnchorInput],
    ) -> ScriptCompileResult:
        target_words = compute_target_narration_words(foia_total_sec)
        if len(beats) < 1:
            return ScriptCompileResult(
                status="REJECTED",
                reason=REJECTED_LOW_BEAT_COUNT,
                episode_status=None,
                target_narration_words=target_words,
                narration_word_count=0,
            )
        if not _all_anchors_locked(spatial_anchors):
            return ScriptCompileResult(
                status="REJECTED",
                reason=REJECTED_UNLOCKED_ANCHORS,
                episode_status=None,
                target_narration_words=target_words,
                narration_word_count=0,
            )

        allowed_ids = frozenset(fact.fact_id for fact in facts)
        by_id = _fact_lookup(facts)
        compiled: list[CompiledScenePlan] = []

        for seq_index, beat in enumerate(beats, start=1):
            if beat.fact_id not in allowed_ids:
                return ScriptCompileResult(
                    status="REJECTED",
                    reason=REJECTED_UNKNOWN_FACT_CITE,
                    episode_status=None,
                    target_narration_words=target_words,
                    narration_word_count=0,
                )
            fact = by_id[beat.fact_id]
            anchor = _pick_anchor_for_fact(beat.fact_id, spatial_anchors, seq_index - 1)
            narration = topology_safe_clause(
                event_summary=fact.event_summary,
                source_type=fact.source_type,
                citation_locator=beat.citation_locator or fact.citation_locator,
                clue_name=anchor.clue_name,
            )
            narration = f"{narration} [fact:{beat.fact_id}]"
            cited = (beat.fact_id,)
            cite_error = _validate_narration_facts(narration, cited, allowed_ids)
            if cite_error:
                return ScriptCompileResult(
                    status="REJECTED",
                    reason=cite_error,
                    episode_status=None,
                    target_narration_words=target_words,
                    narration_word_count=0,
                )
            plan = CompiledScenePlan(
                scene_plan_id=f"plan_{episode_id}_{seq_index}",
                scene_id=f"scene_{episode_id}_{seq_index}",
                seq_index=seq_index,
                story_purpose=beat.record_anchor,
                intended_audience_effect=beat.editorial_analysis or beat.record_anchor,
                approved_narration_text=narration,
                narration_version_sha256=narration_version_sha256(narration),
                cited_fact_ids=cited,
                anchor_id=anchor.anchor_id,
            )
            if not scene_plan_stage1_approved(plan):
                return ScriptCompileResult(
                    status="REJECTED",
                    reason=REJECTED_MISSING_SCENE_FIELDS,
                    episode_status=None,
                    target_narration_words=target_words,
                    narration_word_count=0,
                )
            compiled.append(plan)

        word_count = sum(count_words(p.approved_narration_text) for p in compiled)
        return ScriptCompileResult(
            status="OK",
            reason=None,
            episode_status=EPISODE_STATUS_SCENE_PLAN_APPROVED,
            target_narration_words=target_words,
            narration_word_count=word_count,
            scene_plans=tuple(compiled),
        )

    def apply_external_narration(
        self,
        *,
        scene_plan_id: str,
        scene_id: str,
        seq_index: int,
        story_purpose: str,
        intended_audience_effect: str,
        approved_narration_text: str,
        cited_fact_ids: Sequence[str],
        allowed_fact_ids: frozenset[str],
        anchor_id: str | None = None,
    ) -> CompiledScenePlan | ScriptCompileResult:
        """Validate externally supplied narration (mocked LLM output in tests)."""
        cite_error = _validate_narration_facts(
            approved_narration_text,
            cited_fact_ids,
            allowed_fact_ids,
        )
        if cite_error:
            return ScriptCompileResult(
                status="REJECTED",
                reason=cite_error,
                episode_status=None,
                target_narration_words=0.0,
                narration_word_count=0,
            )
        plan = CompiledScenePlan(
            scene_plan_id=scene_plan_id,
            scene_id=scene_id,
            seq_index=seq_index,
            story_purpose=story_purpose,
            intended_audience_effect=intended_audience_effect,
            approved_narration_text=approved_narration_text,
            narration_version_sha256=narration_version_sha256(approved_narration_text),
            cited_fact_ids=tuple(cited_fact_ids),
            anchor_id=anchor_id,
        )
        if not scene_plan_stage1_approved(plan):
            return ScriptCompileResult(
                status="REJECTED",
                reason=REJECTED_MISSING_SCENE_FIELDS,
                episode_status=None,
                target_narration_words=0.0,
                narration_word_count=0,
            )
        return plan