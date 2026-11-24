"""RULE_05: static micro-beats, engine streaks, and CaseBoardSpine placement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RULE_ID = "RULE_05"

MICRO_BEAT_MAX_MS = 6_000
FLOW_HERO_EXEMPT_MAX_MS = 10_000
ENGINE_STREAK_MAX_MS = 50_000
CASEBOARD_SPINE_WINDOW_START_MS = 210_000
CASEBOARD_SPINE_WINDOW_END_MS = 270_000

STATIC_MICRO_BEAT_ENGINES = frozenset({"CODE_STICKMAN", "STILL_2K_PANZOOM"})
FLOW_HERO_ENGINE = "FLOW_HERO_VIDEO"
CASEBOARD_SPINE_MOTIF = "CaseBoardSpine"

BoundaryKind = Literal["scene_end", "sentence_end"]


@dataclass(frozen=True, slots=True)
class Rule05Scene:
    scene_id: str
    visual_engine: str
    motif_component: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class Foia911Slot:
    start_ms: int
    end_ms: int
    slot_id: str = "911_CALL"


@dataclass(slots=True)
class Rule05Timeline:
    scenes: list[Rule05Scene]
    sentence_boundaries_ms: list[int] = field(default_factory=list)
    foia_911_slots_ms: list[Foia911Slot] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Rule05Violation:
    code: str
    message: str
    scene_id: str | None = None
    rule_id: str = RULE_ID


@dataclass(slots=True)
class Rule05Result:
    violations: list[Rule05Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def is_flow_motion_exempt(scene: Rule05Scene) -> bool:
    """Continuous Hero clips up to 10s skip the static 6s micro-beat clock."""
    return (
        scene.visual_engine == FLOW_HERO_ENGINE
        and scene.duration_ms <= FLOW_HERO_EXEMPT_MAX_MS
    )


def _check_micro_beats(scenes: list[Rule05Scene]) -> list[Rule05Violation]:
    violations: list[Rule05Violation] = []
    for scene in scenes:
        if scene.visual_engine not in STATIC_MICRO_BEAT_ENGINES:
            continue
        if scene.duration_ms > MICRO_BEAT_MAX_MS:
            violations.append(
                Rule05Violation(
                    code="MICRO_BEAT_EXCEEDED",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} {scene.visual_engine} beat "
                        f"{scene.duration_ms}ms exceeds {MICRO_BEAT_MAX_MS}ms static clock"
                    ),
                )
            )
    return violations


def _check_engine_streaks(scenes: list[Rule05Scene]) -> list[Rule05Violation]:
    if not scenes:
        return []
    violations: list[Rule05Violation] = []
    run_engine = scenes[0].visual_engine
    run_ms = scenes[0].duration_ms
    run_scene_ids = [scenes[0].scene_id]

    def flush() -> None:
        if run_ms > ENGINE_STREAK_MAX_MS:
            violations.append(
                Rule05Violation(
                    code="ENGINE_STREAK_EXCEEDED",
                    scene_id=run_scene_ids[0],
                    message=(
                        f"engine streak {run_engine} {run_ms}ms exceeds "
                        f"{ENGINE_STREAK_MAX_MS}ms"
                    ),
                )
            )

    for scene in scenes[1:]:
        if scene.visual_engine == run_engine:
            run_ms += scene.duration_ms
            run_scene_ids.append(scene.scene_id)
        else:
            flush()
            run_engine = scene.visual_engine
            run_ms = scene.duration_ms
            run_scene_ids = [scene.scene_id]
    flush()
    return violations


def _completed_boundaries_ms(timeline: Rule05Timeline) -> set[int]:
    """Timestamps where narration may safely cut (never mid-scene)."""
    bounds: set[int] = set(timeline.sentence_boundaries_ms)
    for scene in timeline.scenes:
        bounds.add(scene.end_ms)
    for slot in timeline.foia_911_slots_ms:
        bounds.add(slot.end_ms)
    return bounds


def _is_mid_911(start_ms: int, slots: list[Foia911Slot]) -> Foia911Slot | None:
    for slot in slots:
        if slot.start_ms < start_ms < slot.end_ms:
            return slot
    return None


def _check_case_board_spine(timeline: Rule05Timeline) -> list[Rule05Violation]:
    violations: list[Rule05Violation] = []
    legal = _completed_boundaries_ms(timeline)
    for scene in timeline.scenes:
        if scene.motif_component != CASEBOARD_SPINE_MOTIF:
            continue
        start = scene.start_ms
        if start < CASEBOARD_SPINE_WINDOW_START_MS or start > CASEBOARD_SPINE_WINDOW_END_MS:
            violations.append(
                Rule05Violation(
                    code="SPINE_WINDOW",
                    scene_id=scene.scene_id,
                    message=(
                        f"CaseBoardSpine {scene.scene_id} at {start}ms outside "
                        f"{CASEBOARD_SPINE_WINDOW_START_MS}-{CASEBOARD_SPINE_WINDOW_END_MS}ms"
                    ),
                )
            )
        if start not in legal:
            violations.append(
                Rule05Violation(
                    code="SPINE_BOUNDARY",
                    scene_id=scene.scene_id,
                    message=(
                        f"CaseBoardSpine {scene.scene_id} at {start}ms is not on a "
                        "completed scene or sentence boundary"
                    ),
                )
            )
        mid = _is_mid_911(start, timeline.foia_911_slots_ms)
        if mid is not None:
            violations.append(
                Rule05Violation(
                    code="SPINE_MID_911",
                    scene_id=scene.scene_id,
                    message=(
                        f"CaseBoardSpine {scene.scene_id} at {start}ms chops "
                        f"911 slot {mid.slot_id} ({mid.start_ms}-{mid.end_ms}ms)"
                    ),
                )
            )
    return violations


def validate_rule_05(timeline: Rule05Timeline) -> Rule05Result:
    """Run all RULE_05 checks on a timeline snapshot."""
    violations: list[Rule05Violation] = []
    violations.extend(_check_micro_beats(timeline.scenes))
    violations.extend(_check_engine_streaks(timeline.scenes))
    violations.extend(_check_case_board_spine(timeline))
    return Rule05Result(violations=violations)