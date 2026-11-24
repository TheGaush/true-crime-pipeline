"""Act-constrained RULE_02 budget caps and RULE_04 non-neighbor fallbacks (Task 077).

Offline-only: loads numeric caps from a local ``providers.yaml`` when present;
never opens a socket.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

HERO_ENGINE = "FLOW_HERO_VIDEO"
STICKMAN_ENGINE = "CODE_STICKMAN"
STILL_ENGINE = "STILL_2K_PANZOOM"

DEFAULT_MAX_HERO_CLIPS = 10
DEFAULT_MAX_HERO_DURATION_SEC = 80
DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD = 10_400_000
DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD = 135_000_000
DEFAULT_USD_PER_SEC = 0.10
MICRO_USD_PER_USD = 1_000_000

MAX_ENGINE_STREAK_MS = 50_000
COLD_OPEN_END_MS = 20_000
ACT2_PEAKS_TO_PROTECT = 2

RULE_02 = "RULE_02"
RULE_04 = "RULE_04"

DOWNGRADE_TARGET_ENGINE = STICKMAN_ENGINE
DOWNGRADE_TARGET_MOTIF = "StickmanStage"

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


@dataclass(frozen=True)
class BudgetCaps:
    max_hero_clips: int = DEFAULT_MAX_HERO_CLIPS
    max_hero_duration_sec: int = DEFAULT_MAX_HERO_DURATION_SEC
    episode_video_cap_micro_usd: int = DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD
    monthly_all_providers_cap_micro_usd: int = DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD
    usd_per_sec: float = DEFAULT_USD_PER_SEC


@dataclass
class RuleViolation:
    rule: str
    code: str
    message: str
    scene_id: str | None = None


@dataclass
class RuleCheckResult:
    rule: str
    passed: bool
    violations: list[RuleViolation] = field(default_factory=list)
    scenes: list[dict[str, Any]] | None = None


def load_budget_caps(providers_path: Path | None = None) -> BudgetCaps:
    """Read caps from ``providers.yaml`` without network I/O."""
    path = providers_path
    if path is None:
        path = Path(__file__).resolve().parents[5] / "providers.yaml"
    if not path.is_file():
        return BudgetCaps()

    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return BudgetCaps()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    budgets = raw.get("budgets", {})
    video = raw.get("video", {}).get("primary", {})
    return BudgetCaps(
        max_hero_clips=int(video.get("max_hero_clips", DEFAULT_MAX_HERO_CLIPS)),
        max_hero_duration_sec=int(
            video.get("max_hero_duration_sec", DEFAULT_MAX_HERO_DURATION_SEC)
        ),
        episode_video_cap_micro_usd=int(
            budgets.get(
                "per_episode_video_cap_micro_usd", DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD
            )
        ),
        monthly_all_providers_cap_micro_usd=int(
            budgets.get(
                "all_providers_monthly_cap_micro_usd",
                DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD,
            )
        ),
        usd_per_sec=float(video.get("usd_per_sec", DEFAULT_USD_PER_SEC)),
    )


def _scene_duration_ms(scene: Mapping[str, Any]) -> int:
    return int(scene["end_ms"]) - int(scene["start_ms"])


def _is_hero(scene: Mapping[str, Any]) -> bool:
    return scene.get("visual_engine") == HERO_ENGINE


def hero_clips(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(s) for s in scenes if _is_hero(s)]


def total_hero_duration_ms(scenes: Sequence[Mapping[str, Any]]) -> int:
    return sum(_scene_duration_ms(s) for s in scenes if _is_hero(s))


def estimate_hero_cost_micro_usd(
    scenes: Sequence[Mapping[str, Any]],
    *,
    usd_per_sec: float = DEFAULT_USD_PER_SEC,
    flow_jobs: Sequence[Mapping[str, Any]] | None = None,
) -> int:
    if flow_jobs:
        return sum(int(j.get("estimated_micro_usd", 0)) for j in flow_jobs)
    total_ms = total_hero_duration_ms(scenes)
    return int(round((total_ms / 1000.0) * usd_per_sec * MICRO_USD_PER_USD))


def _cold_open_protected_hero_ids(
    scenes: Sequence[Mapping[str, Any]],
) -> set[str]:
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
        s
        for s in scenes
        if _is_hero(s) and int(s.get("act_number", 0)) == 2
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
    cold = _cold_open_protected_hero_ids(scenes)
    peaks = _act2_top_hero_peak_ids(scenes)
    return cold | peaks


def _downgrade_hero_scene(scene: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(scene)
    out["visual_engine"] = DOWNGRADE_TARGET_ENGINE
    out["motif_component"] = DOWNGRADE_TARGET_MOTIF
    out["fallback_spec_json"] = None
    tl = copy.deepcopy(out.get("timeline_spec_json") or {})
    tl["visual_engine"] = DOWNGRADE_TARGET_ENGINE
    tl["motif_component"] = DOWNGRADE_TARGET_MOTIF
    tl["prompt_mode"] = "NONE"
    out["timeline_spec_json"] = tl
    return out


def apply_act_constrained_downgrade(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps | None = None,
    monthly_spend_micro_usd: int = 0,
) -> list[dict[str, Any]]:
    """Deterministically downgrade excess hero clips; protect cold open + Act 2 top peaks."""
    caps = caps or BudgetCaps()
    protected = protected_hero_scene_ids(scenes)
    working = [dict(s) for s in scenes]

    def within_budget() -> bool:
        heroes = [s for s in working if _is_hero(s)]
        if len(heroes) > caps.max_hero_clips:
            return False
        if total_hero_duration_ms(working) > caps.max_hero_duration_sec * 1000:
            return False
        ep_cost = estimate_hero_cost_micro_usd(working, usd_per_sec=caps.usd_per_sec)
        if ep_cost > caps.episode_video_cap_micro_usd:
            return False
        if monthly_spend_micro_usd + ep_cost > caps.monthly_all_providers_cap_micro_usd:
            return False
        return True

    if within_budget():
        return working

    candidates = [
        s
        for s in working
        if _is_hero(s) and str(s["scene_id"]) not in protected
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


def validate_rule_02(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps | None = None,
    monthly_spend_micro_usd: int = 0,
    auto_downgrade: bool = True,
    flow_jobs: Sequence[Mapping[str, Any]] | None = None,
) -> RuleCheckResult:
    caps = caps or BudgetCaps()
    working = (
        apply_act_constrained_downgrade(
            scenes, caps=caps, monthly_spend_micro_usd=monthly_spend_micro_usd
        )
        if auto_downgrade
        else [dict(s) for s in scenes]
    )
    violations: list[RuleViolation] = []
    heroes = hero_clips(working)

    if len(heroes) > caps.max_hero_clips:
        violations.append(
            RuleViolation(
                RULE_02,
                "HERO_CLIP_COUNT",
                f"hero_clip_count {len(heroes)} exceeds max {caps.max_hero_clips}",
            )
        )

    hero_ms = total_hero_duration_ms(working)
    max_ms = caps.max_hero_duration_sec * 1000
    if hero_ms > max_ms:
        violations.append(
            RuleViolation(
                RULE_02,
                "HERO_DURATION",
                f"hero_duration_ms {hero_ms} exceeds cap {max_ms}",
            )
        )

    ep_cost = estimate_hero_cost_micro_usd(
        working, usd_per_sec=caps.usd_per_sec, flow_jobs=flow_jobs
    )
    if ep_cost > caps.episode_video_cap_micro_usd:
        violations.append(
            RuleViolation(
                RULE_02,
                "EPISODE_VIDEO_CAP",
                f"episode hero estimate {ep_cost} micro-USD exceeds "
                f"{caps.episode_video_cap_micro_usd}",
            )
        )

    if monthly_spend_micro_usd + ep_cost > caps.monthly_all_providers_cap_micro_usd:
        violations.append(
            RuleViolation(
                RULE_02,
                "MONTHLY_ALL_PROVIDERS",
                "monthly ALL_PROVIDERS headroom exhausted",
            )
        )

    input_act2_heroes = [
        s for s in scenes if _is_hero(s) and int(s.get("act_number", 0)) == 2
    ]
    if len(input_act2_heroes) >= ACT2_PEAKS_TO_PROTECT:
        act2_heroes = [s for s in working if _is_hero(s) and int(s.get("act_number", 0)) == 2]
        if len(act2_heroes) < ACT2_PEAKS_TO_PROTECT:
            violations.append(
                RuleViolation(
                    RULE_02,
                    "ACT2_HERO_PEAKS",
                    f"Act 2 retains only {len(act2_heroes)} hero peaks; need "
                    f"{ACT2_PEAKS_TO_PROTECT}",
                )
            )

    return RuleCheckResult(
        rule=RULE_02,
        passed=not violations,
        violations=violations,
        scenes=working,
    )


def _fallback_engine(spec: Mapping[str, Any] | None) -> str | None:
    if not spec:
        return None
    return spec.get("engine") or spec.get("visual_engine")


def select_non_neighbor_fallback_engine(
    prev_engine: str | None,
    next_engine: str | None,
) -> str:
    """Pick a fallback engine distinct from both neighbors (RULE_04)."""
    if prev_engine == STICKMAN_ENGINE and next_engine == STICKMAN_ENGINE:
        return STILL_ENGINE

    forbidden = {e for e in (prev_engine, next_engine, HERO_ENGINE) if e}
    for candidate in FALLBACK_CANDIDATES:
        if candidate not in forbidden:
            return candidate
    return STILL_ENGINE


def build_fallback_spec(
    engine: str,
    *,
    reason: str = "RULE_04 non-neighbor fallback",
    still_2k_id: str | None = None,
    anchor_id: str | None = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "engine": engine,
        "motif_component": MOTIF_FOR_ENGINE.get(engine, "StickmanStage"),
        "rule": RULE_04,
        "reason": reason,
    }
    if still_2k_id:
        spec["still_2k_id"] = still_2k_id
    if anchor_id:
        spec["anchor_id"] = anchor_id
    return spec


def assign_rule_04_fallbacks(
    scenes: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Assign neighbor-safe ``fallback_spec_json`` on every hero scene."""
    ordered = sorted(scenes, key=lambda s: int(s.get("seq_index", 0)))
    out: list[dict[str, Any]] = []
    for idx, scene in enumerate(ordered):
        row = copy.deepcopy(dict(scene))
        if not _is_hero(row):
            out.append(row)
            continue
        prev_eng = ordered[idx - 1]["visual_engine"] if idx else None
        next_eng = (
            ordered[idx + 1]["visual_engine"] if idx + 1 < len(ordered) else None
        )
        engine = select_non_neighbor_fallback_engine(prev_eng, next_eng)
        existing = row.get("fallback_spec_json") or {}
        row["fallback_spec_json"] = build_fallback_spec(
            engine,
            still_2k_id=existing.get("still_2k_id"),
            anchor_id=existing.get("anchor_id"),
        )
        out.append(row)
    return out


def fallback_streak_ms_if_activated(
    scenes: Sequence[Mapping[str, Any]],
    hero_index: int,
) -> int:
    """Longest same-engine run if this hero's two-strike fallback fires."""
    hero = scenes[hero_index]
    fb_engine = _fallback_engine(hero.get("fallback_spec_json"))
    if not fb_engine:
        return 0

    duration = _scene_duration_ms(hero)
    streak = duration

    for i in range(hero_index - 1, -1, -1):
        eng = scenes[i]["visual_engine"]
        if eng == fb_engine:
            streak += _scene_duration_ms(scenes[i])
        else:
            break

    for i in range(hero_index + 1, len(scenes)):
        eng = scenes[i]["visual_engine"]
        if eng == fb_engine:
            streak += _scene_duration_ms(scenes[i])
        else:
            break

    return streak


def validate_rule_04(
    scenes: Sequence[Mapping[str, Any]],
    *,
    auto_assign: bool = True,
) -> RuleCheckResult:
    ordered = sorted(scenes, key=lambda s: int(s.get("seq_index", 0)))
    working = assign_rule_04_fallbacks(ordered) if auto_assign else [dict(s) for s in ordered]
    violations: list[RuleViolation] = []

    for idx, scene in enumerate(working):
        if not _is_hero(scene):
            continue
        fb = scene.get("fallback_spec_json")
        if not fb:
            violations.append(
                RuleViolation(
                    RULE_04,
                    "MISSING_FALLBACK",
                    "FLOW_HERO_VIDEO requires fallback_spec_json",
                    str(scene.get("scene_id")),
                )
            )
            continue

        fb_engine = _fallback_engine(fb)
        if not fb_engine or fb_engine == HERO_ENGINE:
            violations.append(
                RuleViolation(
                    RULE_04,
                    "INVALID_FALLBACK_ENGINE",
                    "fallback must not be FLOW_HERO_VIDEO",
                    str(scene.get("scene_id")),
                )
            )
            continue

        prev_eng = working[idx - 1]["visual_engine"] if idx else None
        next_eng = working[idx + 1]["visual_engine"] if idx + 1 < len(working) else None

        if prev_eng and fb_engine == prev_eng:
            violations.append(
                RuleViolation(
                    RULE_04,
                    "NEIGHBOR_PREV",
                    f"fallback engine {fb_engine} matches previous scene",
                    str(scene.get("scene_id")),
                )
            )
        if next_eng and fb_engine == next_eng:
            violations.append(
                RuleViolation(
                    RULE_04,
                    "NEIGHBOR_NEXT",
                    f"fallback engine {fb_engine} matches next scene",
                    str(scene.get("scene_id")),
                )
            )

        if (
            prev_eng == STICKMAN_ENGINE
            and next_eng == STICKMAN_ENGINE
            and fb_engine != STILL_ENGINE
        ):
            violations.append(
                RuleViolation(
                    RULE_04,
                    "STICKMAN_SANDWICH",
                    "hero between CODE_STICKMAN neighbors must fallback to STILL_2K_PANZOOM",
                    str(scene.get("scene_id")),
                )
            )

        streak = fallback_streak_ms_if_activated(working, idx)
        if streak > MAX_ENGINE_STREAK_MS:
            violations.append(
                RuleViolation(
                    RULE_04,
                    "FALLBACK_STREAK",
                    f"two-strike fallback would create {streak}ms streak (> {MAX_ENGINE_STREAK_MS})",
                    str(scene.get("scene_id")),
                )
            )

    return RuleCheckResult(
        rule=RULE_04,
        passed=not violations,
        violations=violations,
        scenes=working,
    )


def validate_rule_02_and_04(
    scenes: Sequence[Mapping[str, Any]],
    *,
    caps: BudgetCaps | None = None,
    monthly_spend_micro_usd: int = 0,
    flow_jobs: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[RuleCheckResult, RuleCheckResult]:
    r02 = validate_rule_02(
        scenes,
        caps=caps,
        monthly_spend_micro_usd=monthly_spend_micro_usd,
        auto_downgrade=True,
        flow_jobs=flow_jobs,
    )
    base = r02.scenes or [dict(s) for s in scenes]
    r04 = validate_rule_04(base, auto_assign=True)
    return r02, r04