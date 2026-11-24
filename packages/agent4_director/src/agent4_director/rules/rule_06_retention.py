"""RULE_06: mid-video retention — anti-front-loaded hero spend & open-loop cadence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

RULE_ID = "RULE_06"

HERO_ENGINE = "FLOW_HERO_VIDEO"
FOIA_ENGINE = "FOIA_REAL_FOOTAGE"
PEAK_ENGINES = frozenset({HERO_ENGINE, FOIA_ENGINE})

DEFAULT_EPISODE_HERO_BUDGET_MS = 80_000
ACT1_HERO_BUDGET_FRACTION = 0.40

ACT2_WINDOW_START_MS = 6 * 60 * 1000
ACT2_WINDOW_END_MS = 14 * 60 * 1000

OPEN_LOOP_MAX_GAP_MS = int(4.5 * 60 * 1000)
MIN_ACT2_PEAKS = 2

PEAK_SCORE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Rule06Violation:
    code: str
    message: str
    rule_id: str = RULE_ID
    scene_id: str | None = None


@dataclass(frozen=True, slots=True)
class HeroReallocation:
    """Moves excess Act 1 hero duration into Act 2 for intro-heavy manifests."""

    from_act: int
    to_act: int
    shift_ms: int
    scene_ids: tuple[str, ...]
    act1_hero_ms_before: int
    act1_cap_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_act": self.from_act,
            "to_act": self.to_act,
            "shift_ms": self.shift_ms,
            "scene_ids": list(self.scene_ids),
            "act1_hero_ms_before": self.act1_hero_ms_before,
            "act1_cap_ms": self.act1_cap_ms,
        }


@dataclass(slots=True)
class Rule06Result:
    violations: list[Rule06Violation] = field(default_factory=list)
    reallocation: HeroReallocation | None = None

    @property
    def ok(self) -> bool:
        return not self.violations


def _scene_duration_ms(scene: Mapping[str, Any]) -> int:
    return int(scene["end_ms"]) - int(scene["start_ms"])


def _is_hero(scene: Mapping[str, Any]) -> bool:
    return scene.get("visual_engine") == HERO_ENGINE


def act1_hero_spend_ms(scenes: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        _scene_duration_ms(s)
        for s in scenes
        if _is_hero(s) and int(s.get("act_number", 1)) == 1
    )


def total_hero_spend_ms(scenes: Sequence[Mapping[str, Any]]) -> int:
    return sum(_scene_duration_ms(s) for s in scenes if _is_hero(s))


def act1_hero_cap_ms(hero_budget_ms: int) -> int:
    return int(hero_budget_ms * ACT1_HERO_BUDGET_FRACTION)


def _interval_overlaps_act2(start_ms: int, end_ms: int) -> bool:
    return start_ms < ACT2_WINDOW_END_MS and end_ms > ACT2_WINDOW_START_MS


def _is_retention_peak(scene: Mapping[str, Any]) -> bool:
    if scene.get("retention_peak") is True:
        return True
    if scene.get("retention_peak") is False:
        return False
    if scene.get("visual_engine") not in PEAK_ENGINES:
        return False
    return float(scene.get("emotional_peak_score", 0.0)) >= PEAK_SCORE_THRESHOLD


def act2_retention_peaks(scenes: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    peaks: list[Mapping[str, Any]] = []
    for scene in scenes:
        if scene.get("visual_engine") not in PEAK_ENGINES:
            continue
        if not _is_retention_peak(scene):
            continue
        start = int(scene["start_ms"])
        end = int(scene["end_ms"])
        if _interval_overlaps_act2(start, end):
            peaks.append(scene)
    return peaks


def _open_loop_gaps_ms(open_loops_ms: Sequence[int]) -> list[int]:
    ordered = sorted(int(t) for t in open_loops_ms)
    if len(ordered) < 2:
        return []
    return [ordered[i] - ordered[i - 1] for i in range(1, len(ordered))]


def propose_act1_to_act2_reallocation(
    scenes: Sequence[Mapping[str, Any]],
    *,
    hero_budget_ms: int = DEFAULT_EPISODE_HERO_BUDGET_MS,
) -> HeroReallocation | None:
    """If Act 1 hero spend exceeds 40% of episode hero budget, propose Act 2 shift."""
    act1_ms = act1_hero_spend_ms(scenes)
    cap_ms = act1_hero_cap_ms(hero_budget_ms)
    if act1_ms <= cap_ms:
        return None

    excess_ms = act1_ms - cap_ms
    act1_heroes = sorted(
        (s for s in scenes if _is_hero(s) and int(s.get("act_number", 1)) == 1),
        key=lambda s: (
            float(s.get("emotional_peak_score", 0.0)),
            int(s.get("seq_index", 0)),
        ),
    )
    scene_ids: list[str] = []
    budget = 0
    for scene in act1_heroes:
        scene_ids.append(str(scene["scene_id"]))
        budget += _scene_duration_ms(scene)
        if budget >= excess_ms:
            break

    return HeroReallocation(
        from_act=1,
        to_act=2,
        shift_ms=excess_ms,
        scene_ids=tuple(scene_ids),
        act1_hero_ms_before=act1_ms,
        act1_cap_ms=cap_ms,
    )


def validate_rule_06(
    scenes: Sequence[Mapping[str, Any]],
    *,
    open_loops_ms: Sequence[int] | None = None,
    hero_budget_ms: int = DEFAULT_EPISODE_HERO_BUDGET_MS,
    emit_reallocation: bool = True,
) -> Rule06Result:
    """Validate RULE_06 retention constraints on scene plans and open-loop cadence."""
    violations: list[Rule06Violation] = []
    loops = list(open_loops_ms or [])

    act1_ms = act1_hero_spend_ms(scenes)
    cap_ms = act1_hero_cap_ms(hero_budget_ms)
    if act1_ms > cap_ms:
        violations.append(
            Rule06Violation(
                code="ACT1_HERO_BUDGET",
                message=(
                    f"Act 1 hero spend {act1_ms}ms exceeds "
                    f"{int(ACT1_HERO_BUDGET_FRACTION * 100)}% episode hero budget "
                    f"cap {cap_ms}ms"
                ),
            )
        )

    peaks = act2_retention_peaks(scenes)
    if len(peaks) < MIN_ACT2_PEAKS:
        violations.append(
            Rule06Violation(
                code="ACT2_PEAK_COUNT",
                message=(
                    f"Act 2 window {ACT2_WINDOW_START_MS}-{ACT2_WINDOW_END_MS}ms "
                    f"has {len(peaks)} hero/FOIA peaks; need {MIN_ACT2_PEAKS}"
                ),
            )
        )

    for gap in _open_loop_gaps_ms(loops):
        if gap > OPEN_LOOP_MAX_GAP_MS:
            violations.append(
                Rule06Violation(
                    code="OPEN_LOOP_GAP",
                    message=(
                        f"open loops {gap}ms apart exceed "
                        f"{OPEN_LOOP_MAX_GAP_MS}ms ({OPEN_LOOP_MAX_GAP_MS / 60_000:.1f}m) max"
                    ),
                )
            )

    reallocation = None
    if emit_reallocation and act1_ms > cap_ms:
        reallocation = propose_act1_to_act2_reallocation(
            scenes, hero_budget_ms=hero_budget_ms
        )

    return Rule06Result(violations=violations, reallocation=reallocation)