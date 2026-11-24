"""LLM diff-repair loop with deterministic downgrade (Task 088).

Embeds a minimal offline linter for RULE_02, RULE_03, and RULE_04 fix paths;
RULE_05–RULE_13 are checked only when explicit failure markers are present.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

MAX_REPAIR_PASSES = 3
RULE_COUNT = 13

HERO_ENGINE = "FLOW_HERO_VIDEO"
STICKMAN_ENGINE = "CODE_STICKMAN"
STILL_ENGINE = "STILL_2K_PANZOOM"

FLOW_BEAT_LONG_MS = 8500
FLOW_PRIMARY_CHUNK_MS = 8000
FLOW_ALT_FLOW_MS = 6000
MIN_BOOKEND_REMAINDER_SEC = 2.5

DEFAULT_MAX_HERO_CLIPS = 10
DEFAULT_MAX_HERO_DURATION_SEC = 80
DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD = 10_400_000
DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD = 135_000_000
DEFAULT_USD_PER_SEC = 0.10
MICRO_USD_PER_USD = 1_000_000

COLD_OPEN_END_MS = 20_000
ACT2_PEAKS_TO_PROTECT = 2

FALLBACK_CANDIDATES: tuple[str, ...] = (
    STILL_ENGINE,
    STICKMAN_ENGINE,
    "AUDIO_EVIDENCE_CARD",
    "FOIA_REAL_FOOTAGE",
)

MOTIF_FOR_ENGINE: dict[str, str] = {
    STILL_ENGINE: "Illustrative2KPanZoom",
    STICKMAN_ENGINE: "StickmanStage",
    "AUDIO_EVIDENCE_CARD": "AudioEvidenceCard",
    "FOIA_REAL_FOOTAGE": "FoiaFootageFrame",
}

RepairFn = Callable[[list[dict[str, Any]], list["LintViolation"], int], list[dict[str, Any]]]
ProposeFn = Callable[[Any], list[dict[str, Any]]]


@dataclass(frozen=True)
class LintViolation:
    rule_id: str
    code: str
    message: str
    scene_id: str | None = None
    context: dict[str, Any] | None = None


@dataclass
class LintReport:
    violations: list[LintViolation] = field(default_factory=list)

    @property
    def passed_rule_count(self) -> int:
        failing = {v.rule_id for v in self.violations}
        return RULE_COUNT - len(failing)

    @property
    def all_passed(self) -> bool:
        return len(self.violations) == 0

    @property
    def rules_summary(self) -> str:
        return f"{self.passed_rule_count}/{RULE_COUNT}"


@dataclass
class BudgetCaps:
    max_hero_clips: int = DEFAULT_MAX_HERO_CLIPS
    max_hero_duration_sec: int = DEFAULT_MAX_HERO_DURATION_SEC
    episode_video_cap_micro_usd: int = DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD
    monthly_all_providers_cap_micro_usd: int = DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD
    usd_per_sec: float = DEFAULT_USD_PER_SEC


@dataclass
class CompileResult:
    ok: bool
    scenes: list[dict[str, Any]]
    repair_attempts: int
    used_downgrade: bool
    final_lint: LintReport
    passes: list[str] = field(default_factory=list)


def split_flow_beat_ms(duration_ms: int) -> tuple[int, int]:
    """RULE_03 split: 9.2s -> 6000 ms Flow + 3200 ms Code."""
    if duration_ms <= FLOW_BEAT_LONG_MS:
        return (duration_ms, 0)

    beat_sec = duration_ms / 1000.0
    remainder_after_eight = beat_sec - (FLOW_PRIMARY_CHUNK_MS / 1000.0)
    if remainder_after_eight < MIN_BOOKEND_REMAINDER_SEC:
        flow_ms = FLOW_ALT_FLOW_MS
    else:
        flow_ms = FLOW_PRIMARY_CHUNK_MS
    code_ms = duration_ms - flow_ms
    return (flow_ms, code_ms)


def _scene_duration_ms(scene: Mapping[str, Any]) -> int:
    return int(scene["end_ms"]) - int(scene["start_ms"])


def _is_hero(scene: Mapping[str, Any]) -> bool:
    return scene.get("visual_engine") == HERO_ENGINE


def _fallback_engine(spec: Mapping[str, Any] | None) -> str | None:
    if not spec:
        return None
    return spec.get("engine") or spec.get("visual_engine")


def _sorted_scenes(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(scenes, key=lambda s: int(s.get("seq_index", 0)))


def _hero_clips(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(s) for s in scenes if _is_hero(s)]


def _total_hero_duration_ms(scenes: Sequence[Mapping[str, Any]]) -> int:
    return sum(_scene_duration_ms(s) for s in scenes if _is_hero(s))


def _estimate_hero_cost_micro_usd(
    scenes: Sequence[Mapping[str, Any]], *, usd_per_sec: float = DEFAULT_USD_PER_SEC
) -> int:
    total_ms = _total_hero_duration_ms(scenes)
    return int(round((total_ms / 1000.0) * usd_per_sec * MICRO_USD_PER_USD))


def _cold_open_protected_hero_ids(scenes: Sequence[Mapping[str, Any]]) -> set[str]:
    protected: set[str] = set()
    for scene in scenes:
        if not _is_hero(scene):
            continue
        if int(scene.get("act_number", 0)) == 1 and int(scene.get("start_ms", 0)) < COLD_OPEN_END_MS:
            protected.add(str(scene["scene_id"]))
    return protected


def _act2_top_hero_peak_ids(
    scenes: Sequence[Mapping[str, Any]],
    *,
    count: int = ACT2_PEAKS_TO_PROTECT,
) -> set[str]:
    act2_heroes = [
        s for s in scenes if _is_hero(s) and int(s.get("act_number", 0)) == 2
    ]
    ranked = sorted(
        act2_heroes,
        key=lambda s: (
            -float(s.get("emotional_peak_score", 0.0)),
            int(s.get("seq_index", 0)),
        ),
    )
    return {str(s["scene_id"]) for s in ranked[:count]}


def protected_hero_scene_ids(scenes: Sequence[Mapping[str, Any]]) -> set[str]:
    return _cold_open_protected_hero_ids(scenes) | _act2_top_hero_peak_ids(scenes)


def _downgrade_hero_scene(scene: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(scene)
    out["visual_engine"] = STICKMAN_ENGINE
    out["motif_component"] = "StickmanStage"
    out["fallback_spec_json"] = None
    tl = copy.deepcopy(out.get("timeline_spec_json") or {})
    tl["visual_engine"] = STICKMAN_ENGINE
    tl["motif_component"] = "StickmanStage"
    tl["prompt_mode"] = "NONE"
    out["timeline_spec_json"] = tl
    return out


def apply_act_constrained_downgrade(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps | None = None,
    monthly_spend_micro_usd: int = 0,
) -> list[dict[str, Any]]:
    caps = caps or BudgetCaps()
    protected = protected_hero_scene_ids(scenes)
    working = [dict(s) for s in scenes]

    def within_budget() -> bool:
        heroes = [s for s in working if _is_hero(s)]
        if len(heroes) > caps.max_hero_clips:
            return False
        if _total_hero_duration_ms(working) > caps.max_hero_duration_sec * 1000:
            return False
        ep_cost = _estimate_hero_cost_micro_usd(working, usd_per_sec=caps.usd_per_sec)
        if ep_cost > caps.episode_video_cap_micro_usd:
            return False
        if monthly_spend_micro_usd + ep_cost > caps.monthly_all_providers_cap_micro_usd:
            return False
        return True

    if within_budget():
        return working

    candidates = [
        s for s in working if _is_hero(s) and str(s["scene_id"]) not in protected
    ]
    candidates.sort(
        key=lambda s: (
            float(s.get("emotional_peak_score", 0.0)),
            -int(s.get("seq_index", 0)),
        )
    )

    for cand in candidates:
        if within_budget():
            break
        for idx, scene in enumerate(working):
            if scene.get("scene_id") == cand.get("scene_id"):
                working[idx] = _downgrade_hero_scene(scene)
                break

    return working


def select_non_neighbor_fallback_engine(
    prev_engine: str | None,
    next_engine: str | None,
) -> str:
    if prev_engine == STICKMAN_ENGINE and next_engine == STICKMAN_ENGINE:
        return STILL_ENGINE
    forbidden = {e for e in (prev_engine, next_engine, HERO_ENGINE) if e}
    for candidate in FALLBACK_CANDIDATES:
        if candidate not in forbidden:
            return candidate
    return STILL_ENGINE


def build_fallback_spec(engine: str) -> dict[str, Any]:
    return {
        "engine": engine,
        "motif_component": MOTIF_FOR_ENGINE.get(engine, "StickmanStage"),
        "rule": "RULE_04",
        "reason": "RULE_04 non-neighbor fallback",
    }


def assign_rule_04_fallbacks(
    scenes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    ordered = _sorted_scenes(scenes)
    out: list[dict[str, Any]] = []
    for idx, scene in enumerate(ordered):
        row = copy.deepcopy(dict(scene))
        if not _is_hero(row):
            out.append(row)
            continue
        prev_eng = ordered[idx - 1]["visual_engine"] if idx else None
        next_eng = ordered[idx + 1]["visual_engine"] if idx + 1 < len(ordered) else None
        engine = select_non_neighbor_fallback_engine(prev_eng, next_eng)
        row["fallback_spec_json"] = build_fallback_spec(engine)
        out.append(row)
    return out


def apply_rule_03_splits(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Split long FLOW_HERO_VIDEO beats into Flow + CODE_STICKMAN pair."""
    out: list[dict[str, Any]] = []
    for scene in _sorted_scenes(scenes):
        row = dict(scene)
        if not _is_hero(row):
            out.append(row)
            continue
        duration_ms = _scene_duration_ms(row)
        flow_ms, code_ms = split_flow_beat_ms(duration_ms)
        if code_ms == 0:
            out.append(row)
            continue

        start_ms = int(row["start_ms"])
        hero = copy.deepcopy(row)
        hero["end_ms"] = start_ms + flow_ms
        hero["scene_id"] = f"{row['scene_id']}_flow"

        code = copy.deepcopy(row)
        code["scene_id"] = f"{row['scene_id']}_code"
        code["visual_engine"] = STICKMAN_ENGINE
        code["motif_component"] = "StickmanStage"
        code["start_ms"] = start_ms + flow_ms
        code["end_ms"] = start_ms + flow_ms + code_ms
        code["fallback_spec_json"] = None
        tl = copy.deepcopy(code.get("timeline_spec_json") or {})
        tl["visual_engine"] = STICKMAN_ENGINE
        tl["motif_component"] = "StickmanStage"
        tl["prompt_mode"] = "NONE"
        code["timeline_spec_json"] = tl

        out.extend([hero, code])

    for idx, scene in enumerate(out):
        scene["seq_index"] = idx
    return out


def apply_deterministic_downgrade(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps | None = None,
    monthly_spend_micro_usd: int = 0,
) -> list[dict[str, Any]]:
    """RULE_02 downgrade, RULE_03 splits, RULE_04 fallbacks."""
    working = apply_act_constrained_downgrade(
        scenes, caps=caps, monthly_spend_micro_usd=monthly_spend_micro_usd
    )
    working = apply_rule_03_splits(working)
    return assign_rule_04_fallbacks(working)


def apply_repair_hints(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply linter-known fixes without budget downgrade."""
    working = apply_rule_03_splits(scenes)
    return assign_rule_04_fallbacks(working)


def _lint_rule_02(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps,
    monthly_spend_micro_usd: int,
) -> list[LintViolation]:
    violations: list[LintViolation] = []
    heroes = _hero_clips(scenes)
    if len(heroes) > caps.max_hero_clips:
        violations.append(
            LintViolation(
                "RULE_02",
                "HERO_CLIP_COUNT",
                f"hero_clip_count {len(heroes)} exceeds max {caps.max_hero_clips}",
            )
        )
    hero_ms = _total_hero_duration_ms(scenes)
    max_ms = caps.max_hero_duration_sec * 1000
    if hero_ms > max_ms:
        violations.append(
            LintViolation(
                "RULE_02",
                "HERO_DURATION",
                f"hero_duration_ms {hero_ms} exceeds cap {max_ms}",
            )
        )
    ep_cost = _estimate_hero_cost_micro_usd(scenes, usd_per_sec=caps.usd_per_sec)
    if ep_cost > caps.episode_video_cap_micro_usd:
        violations.append(
            LintViolation(
                "RULE_02",
                "EPISODE_VIDEO_CAP",
                f"episode hero estimate {ep_cost} micro-USD exceeds cap",
            )
        )
    if monthly_spend_micro_usd + ep_cost > caps.monthly_all_providers_cap_micro_usd:
        violations.append(
            LintViolation(
                "RULE_02",
                "MONTHLY_ALL_PROVIDERS",
                "monthly ALL_PROVIDERS headroom exhausted",
            )
        )
    return violations


def _lint_rule_03(scenes: Sequence[Mapping[str, Any]]) -> list[LintViolation]:
    violations: list[LintViolation] = []
    for scene in scenes:
        if not _is_hero(scene):
            continue
        duration_ms = _scene_duration_ms(scene)
        if duration_ms <= FLOW_BEAT_LONG_MS:
            continue
        flow_ms, code_ms = split_flow_beat_ms(duration_ms)
        if code_ms == 0:
            continue
        violations.append(
            LintViolation(
                "RULE_03",
                "UNSPLIT_FLOW_BEAT",
                f"scene {scene['scene_id']} duration {duration_ms} ms needs split",
                str(scene.get("scene_id")),
                {
                    "duration_ms": duration_ms,
                    "proposed_flow_ms": flow_ms,
                    "proposed_code_ms": code_ms,
                },
            )
        )
    return violations


def _lint_rule_04(scenes: Sequence[Mapping[str, Any]]) -> list[LintViolation]:
    ordered = _sorted_scenes(scenes)
    violations: list[LintViolation] = []
    for idx, scene in enumerate(ordered):
        if not _is_hero(scene):
            continue
        sid = str(scene.get("scene_id"))
        fb = scene.get("fallback_spec_json")
        if not fb:
            violations.append(
                LintViolation(
                    "RULE_04",
                    "MISSING_FALLBACK",
                    "FLOW_HERO_VIDEO requires fallback_spec_json",
                    sid,
                )
            )
            continue
        fb_engine = _fallback_engine(fb)
        if not fb_engine or fb_engine == HERO_ENGINE:
            violations.append(
                LintViolation(
                    "RULE_04",
                    "INVALID_FALLBACK_ENGINE",
                    "fallback must not be FLOW_HERO_VIDEO",
                    sid,
                )
            )
            continue
        prev_eng = ordered[idx - 1]["visual_engine"] if idx else None
        next_eng = ordered[idx + 1]["visual_engine"] if idx + 1 < len(ordered) else None
        if prev_eng and fb_engine == prev_eng:
            violations.append(
                LintViolation(
                    "RULE_04",
                    "NEIGHBOR_PREV",
                    f"fallback engine {fb_engine} matches previous scene",
                    sid,
                )
            )
        if next_eng and fb_engine == next_eng:
            violations.append(
                LintViolation(
                    "RULE_04",
                    "NEIGHBOR_NEXT",
                    f"fallback engine {fb_engine} matches next scene",
                    sid,
                )
            )
    return violations


def _lint_placeholder_rules(scenes: Sequence[Mapping[str, Any]]) -> list[LintViolation]:
    """RULE_05–RULE_13: only fail when explicit test markers are set."""
    violations: list[LintViolation] = []
    for scene in scenes:
        marker = scene.get("_force_rule_failure")
        if marker and str(marker).startswith("RULE_"):
            violations.append(
                LintViolation(
                    str(marker),
                    "FORCED_FAILURE",
                    f"scene {scene.get('scene_id')} forced failure for {marker}",
                    str(scene.get("scene_id")),
                )
            )
    return violations


def lint_manifest(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps | None = None,
    monthly_spend_micro_usd: int = 0,
) -> LintReport:
    caps = caps or BudgetCaps()
    violations: list[LintViolation] = []
    violations.extend(_lint_rule_02(scenes, caps=caps, monthly_spend_micro_usd=monthly_spend_micro_usd))
    violations.extend(_lint_rule_03(scenes))
    violations.extend(_lint_rule_04(scenes))
    violations.extend(_lint_placeholder_rules(scenes))
    return LintReport(violations=violations)


def propose_scenes(draft: Any) -> list[dict[str, Any]]:
    """Layer-1 proposal: shallow copy of draft scenes."""
    if isinstance(draft, Mapping) and "scenes" in draft:
        return [copy.deepcopy(dict(s)) for s in draft["scenes"]]
    if isinstance(draft, Sequence):
        return [copy.deepcopy(dict(s)) for s in draft]
    raise TypeError("draft must expose scenes sequence or mapping with 'scenes'")


class DirectorCompiler:
    """Propose -> lint -> <=3 repairs -> deterministic downgrade -> fixed-point lint."""

    def __init__(
        self,
        *,
        caps: BudgetCaps | None = None,
        monthly_spend_micro_usd: int = 0,
        proposer: ProposeFn | None = None,
        repair_fn: RepairFn | None = None,
    ) -> None:
        self.caps = caps or BudgetCaps()
        self.monthly_spend_micro_usd = monthly_spend_micro_usd
        self.proposer = proposer or propose_scenes
        self.repair_fn = repair_fn

    def compile(self, draft: Any) -> CompileResult:
        passes: list[str] = ["propose"]
        scenes = self.proposer(draft)

        report = lint_manifest(
            scenes, caps=self.caps, monthly_spend_micro_usd=self.monthly_spend_micro_usd
        )
        passes.append("lint")

        repair_attempts = 0
        used_downgrade = False

        while not report.all_passed and repair_attempts < MAX_REPAIR_PASSES:
            if self.repair_fn is None:
                break
            scenes = self.repair_fn(scenes, list(report.violations), repair_attempts)
            repair_attempts += 1
            passes.append(f"repair_{repair_attempts}")
            report = lint_manifest(
                scenes,
                caps=self.caps,
                monthly_spend_micro_usd=self.monthly_spend_micro_usd,
            )
            passes.append("lint")

        if not report.all_passed:
            scenes = apply_deterministic_downgrade(
                scenes,
                caps=self.caps,
                monthly_spend_micro_usd=self.monthly_spend_micro_usd,
            )
            used_downgrade = True
            passes.append("downgrade")
            report = lint_manifest(
                scenes,
                caps=self.caps,
                monthly_spend_micro_usd=self.monthly_spend_micro_usd,
            )
            passes.append("lint")

        verify = lint_manifest(
            scenes, caps=self.caps, monthly_spend_micro_usd=self.monthly_spend_micro_usd
        )
        passes.append("lint_verify")
        ok = verify.all_passed and verify.passed_rule_count == RULE_COUNT

        return CompileResult(
            ok=ok,
            scenes=scenes,
            repair_attempts=repair_attempts,
            used_downgrade=used_downgrade,
            final_lint=verify,
            passes=passes,
        )


def make_stubborn_repair_fn(
    fix_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> RepairFn:
    """Succeeds only on the third repair attempt (index 2)."""

    def _repair(
        scenes: list[dict[str, Any]],
        _violations: list[LintViolation],
        attempt: int,
    ) -> list[dict[str, Any]]:
        if attempt >= 2:
            return fix_fn(scenes)
        return [copy.deepcopy(s) for s in scenes]

    return _repair


def make_broken_repair_fn() -> RepairFn:
    """Never repairs; leaves manifest unchanged."""

    def _repair(
        scenes: list[dict[str, Any]],
        _violations: list[LintViolation],
        _attempt: int,
    ) -> list[dict[str, Any]]:
        return [copy.deepcopy(s) for s in scenes]

    return _repair