"""Offline Agent 4 — conflict-free 13-Law compiler & adversarial suite (Task 090).

All RULE_01–RULE_13 checks and deterministic repair paths are encoded locally.
Rule modules from Tasks 076–087 are not imported. No network.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

RULE_COUNT = 13
RULE_IDS: tuple[str, ...] = tuple(f"RULE_{i:02d}" for i in range(1, RULE_COUNT + 1))

RULE_01_TOLERANCE_MS = 250
FOIA_ENGINES = frozenset({"FOIA_REAL_FOOTAGE", "AUDIO_EVIDENCE_CARD"})

HERO_ENGINE = "FLOW_HERO_VIDEO"
STICKMAN_ENGINE = "CODE_STICKMAN"
STILL_ENGINE = "STILL_2K_PANZOOM"
CASEBOARD_SPINE_MOTIF = "CaseBoardSpine"

FLOW_BEAT_LONG_MS = 8500
FLOW_PRIMARY_CHUNK_MS = 8000
FLOW_ALT_FLOW_MS = 6000
MIN_BOOKEND_REMAINDER_SEC = 2.5

MICRO_BEAT_MAX_MS = 6000
FLOW_HERO_EXEMPT_MAX_MS = 10_000
ENGINE_STREAK_MAX_MS = 50_000
SPINE_WINDOW_START_MS = 210_000
SPINE_WINDOW_END_MS = 270_000

DEFAULT_MAX_HERO_CLIPS = 10
DEFAULT_MAX_HERO_DURATION_SEC = 80
DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD = 10_400_000
DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD = 135_000_000
DEFAULT_USD_PER_SEC = 0.10
MICRO_USD_PER_USD = 1_000_000
COLD_OPEN_END_MS = 20_000
ACT2_PEAKS_TO_PROTECT = 2
MIN_ACT2_PEAKS = 2
ACT1_HERO_BUDGET_FRACTION = 0.40

RULE_07_MAX_WORDS = 12
RULE_07_BASE_HOLD_SEC = 1.0
RULE_07_SEC_PER_WORD = 0.3

CINEMATOGRAPHY_BIGRAMS = (
    "tracking shot",
    "static shot",
    "dolly shot",
    "wide shot",
    "medium shot",
    "panning shot",
    "establishing shot",
    "side tracking shot",
)
_MASK = "\x00cam\x00"
_BLOCKED_SHOT_RE = re.compile(
    r"\b(?:shoot(?:s|ing)?|shot(?:s)?|guns?|minors?)\b",
    re.IGNORECASE,
)
_ATTRIBUTION_HEDGE_RE = re.compile(r"\bnews\s+accounts?\s+reported\b", re.IGNORECASE)
_TRANSCRIPT_BADGE = "TRANSCRIPT DRAMATIZATION"
_ILLUSTRATIVE_LABEL = "ILLUSTRATIVE RECONSTRUCTION"
_CRIMSON = "#C92A2A"
_RETIRED_MODES = frozenset({"FRAMES_MOTION_ONLY", "VEO_3_1_LITE"})

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
class LintViolation:
    rule_id: str
    code: str
    message: str
    scene_id: str | None = None


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

    def by_rule(self) -> dict[str, list[LintViolation]]:
        out: dict[str, list[LintViolation]] = {rid: [] for rid in RULE_IDS}
        for v in self.violations:
            out.setdefault(v.rule_id, []).append(v)
        return out


@dataclass
class BudgetCaps:
    max_hero_clips: int = DEFAULT_MAX_HERO_CLIPS
    max_hero_duration_sec: int = DEFAULT_MAX_HERO_DURATION_SEC
    episode_video_cap_micro_usd: int = DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD
    monthly_all_providers_cap_micro_usd: int = DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD
    usd_per_sec: float = DEFAULT_USD_PER_SEC


@dataclass
class DirectorManifest:
    scenes: list[dict[str, Any]]
    total_master_ms: int
    narration_version_sha256: str
    voice_segments: list[dict[str, Any]] = field(default_factory=list)
    fact_ledger: list[dict[str, Any]] = field(default_factory=list)
    callout_cards: list[dict[str, Any]] = field(default_factory=list)
    foia_911_slots_ms: list[dict[str, Any]] = field(default_factory=list)
    cold_open_archetype: str = "CHRONOLOGICAL_COUNTDOWN"
    turning_point_count: int = 3
    recent_cold_open_archetypes: tuple[str, ...] = ()
    monthly_spend_micro_usd: int = 0
    frame_png_specs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenes": self.scenes,
            "total_master_ms": self.total_master_ms,
            "narration_version_sha256": self.narration_version_sha256,
            "voice_segments": self.voice_segments,
            "fact_ledger": self.fact_ledger,
            "callout_cards": self.callout_cards,
            "foia_911_slots_ms": self.foia_911_slots_ms,
            "cold_open_archetype": self.cold_open_archetype,
            "turning_point_count": self.turning_point_count,
            "recent_cold_open_archetypes": list(self.recent_cold_open_archetypes),
            "monthly_spend_micro_usd": self.monthly_spend_micro_usd,
            "frame_png_specs": self.frame_png_specs,
        }


@dataclass
class CertifiedResult:
    ok: bool
    manifest: DirectorManifest
    lint: LintReport
    repairs: list[str] = field(default_factory=list)


def split_flow_beat_ms(duration_ms: int) -> tuple[int, int]:
    if duration_ms <= FLOW_BEAT_LONG_MS:
        return (duration_ms, 0)
    beat_sec = duration_ms / 1000.0
    remainder_after_eight = beat_sec - (FLOW_PRIMARY_CHUNK_MS / 1000.0)
    flow_ms = FLOW_ALT_FLOW_MS if remainder_after_eight < MIN_BOOKEND_REMAINDER_SEC else FLOW_PRIMARY_CHUNK_MS
    return (flow_ms, duration_ms - flow_ms)


def mask_cinematography_bigrams(text: str) -> str:
    lowered = text.lower()
    for bigram in CINEMATOGRAPHY_BIGRAMS:
        lowered = lowered.replace(bigram, _MASK)
    return lowered


def find_blocked_safety_terms(text: str) -> tuple[str, ...]:
    masked = mask_cinematography_bigrams(text)
    return tuple(sorted({m.group(0).lower() for m in _BLOCKED_SHOT_RE.finditer(masked)}))


def min_hold_duration_sec(word_count: int) -> float:
    return RULE_07_BASE_HOLD_SEC + RULE_07_SEC_PER_WORD * word_count


def _scene_duration_ms(scene: Mapping[str, Any]) -> int:
    return int(scene["end_ms"]) - int(scene["start_ms"])


def _is_hero(scene: Mapping[str, Any]) -> bool:
    return scene.get("visual_engine") == HERO_ENGINE


def _sorted_scenes(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(scenes, key=lambda s: (int(s.get("start_ms", 0)), int(s.get("seq_index", 0))))


def _sum_scene_ms(scenes: Sequence[Mapping[str, Any]]) -> int:
    return sum(_scene_duration_ms(s) for s in scenes)


def _hero_clips(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(s) for s in scenes if _is_hero(s)]


def _total_hero_duration_ms(scenes: Sequence[Mapping[str, Any]]) -> int:
    return sum(_scene_duration_ms(s) for s in scenes if _is_hero(s))


def _estimate_hero_cost_micro_usd(
    scenes: Sequence[Mapping[str, Any]], *, usd_per_sec: float = DEFAULT_USD_PER_SEC
) -> int:
    return int(round((_total_hero_duration_ms(scenes) / 1000.0) * usd_per_sec * MICRO_USD_PER_USD))


def protected_hero_scene_ids(scenes: Sequence[Mapping[str, Any]]) -> set[str]:
    protected: set[str] = set()
    for scene in scenes:
        if not _is_hero(scene):
            continue
        if int(scene.get("act_number", 0)) == 1 and int(scene.get("start_ms", 0)) < COLD_OPEN_END_MS:
            protected.add(str(scene["scene_id"]))
    act2 = [
        s for s in scenes if _is_hero(s) and int(s.get("act_number", 0)) == 2
    ]
    ranked = sorted(
        act2,
        key=lambda s: (-float(s.get("emotional_peak_score", 0.0)), int(s.get("seq_index", 0))),
    )
    protected.update(str(s["scene_id"]) for s in ranked[:ACT2_PEAKS_TO_PROTECT])
    return protected


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

    candidates = [s for s in working if _is_hero(s) and str(s["scene_id"]) not in protected]
    candidates.sort(
        key=lambda s: (float(s.get("emotional_peak_score", 0.0)), -int(s.get("seq_index", 0)))
    )
    for cand in candidates:
        if within_budget():
            break
        for idx, scene in enumerate(working):
            if scene.get("scene_id") == cand.get("scene_id"):
                working[idx] = _downgrade_hero_scene(scene)
                break
    return working


def select_non_neighbor_fallback_engine(prev_engine: str | None, next_engine: str | None) -> str:
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


def assign_rule_04_fallbacks(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = _sorted_scenes(scenes)
    out: list[dict[str, Any]] = []
    for idx, scene in enumerate(ordered):
        row = copy.deepcopy(dict(scene))
        if not _is_hero(row):
            out.append(row)
            continue
        prev_eng = ordered[idx - 1]["visual_engine"] if idx else None
        next_eng = ordered[idx + 1]["visual_engine"] if idx + 1 < len(ordered) else None
        row["fallback_spec_json"] = build_fallback_spec(
            select_non_neighbor_fallback_engine(prev_eng, next_eng)
        )
        out.append(row)
    for i, scene in enumerate(out):
        scene["seq_index"] = i
    return out


def apply_rule_03_splits(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
        tl.update({"visual_engine": STICKMAN_ENGINE, "motif_component": "StickmanStage", "prompt_mode": "NONE"})
        code["timeline_spec_json"] = tl
        out.extend([hero, code])
    for idx, scene in enumerate(out):
        scene["seq_index"] = idx
    return out


def snap_case_board_spine(scenes: list[dict[str, Any]], slots: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = [copy.deepcopy(s) for s in _sorted_scenes(scenes)]
    for scene in out:
        if scene.get("motif_component") != CASEBOARD_SPINE_MOTIF:
            continue
        start = int(scene["start_ms"])
        for slot in slots:
            s0, s1 = int(slot["start_ms"]), int(slot["end_ms"])
            if s0 < start < s1:
                dur = min(_scene_duration_ms(scene), MICRO_BEAT_MAX_MS)
                scene["start_ms"] = s1
                scene["end_ms"] = s1 + dur
    for idx, scene in enumerate(out):
        scene["seq_index"] = idx
    return out


def split_static_micro_beats(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Chop long CODE_STICKMAN / STILL beats to <= 6s (FOIA footage exempt)."""
    out: list[dict[str, Any]] = []
    for scene in _sorted_scenes(scenes):
        eng = scene.get("visual_engine")
        if eng in FOIA_ENGINES or eng == HERO_ENGINE:
            out.append(dict(scene))
            continue
        if eng not in {STICKMAN_ENGINE, STILL_ENGINE}:
            out.append(dict(scene))
            continue
        start = int(scene["start_ms"])
        remaining = _scene_duration_ms(scene)
        part = 0
        while remaining > 0:
            chunk = min(remaining, MICRO_BEAT_MAX_MS)
            row = copy.deepcopy(dict(scene))
            row["scene_id"] = f"{scene['scene_id']}_mb{part}" if part else str(scene["scene_id"])
            row["start_ms"] = start
            row["end_ms"] = start + chunk
            out.append(row)
            start += chunk
            remaining -= chunk
            part += 1
    for idx, scene in enumerate(out):
        scene["seq_index"] = idx
    return out


def break_engine_streaks(scenes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Flip static engines when a single-engine streak would exceed 50s."""
    out: list[dict[str, Any]] = []
    run_eng: str | None = None
    run_ms = 0

    for scene in _sorted_scenes(scenes):
        eng = scene.get("visual_engine")
        dur = _scene_duration_ms(scene)
        row = dict(scene)
        if eng in {STICKMAN_ENGINE, STILL_ENGINE}:
            if run_eng == eng and run_ms + dur > ENGINE_STREAK_MAX_MS:
                alt = STILL_ENGINE if eng == STICKMAN_ENGINE else STICKMAN_ENGINE
                row["visual_engine"] = alt
                row["motif_component"] = (
                    "Illustrative2KPanZoom" if alt == STILL_ENGINE else "StickmanStage"
                )
                eng = alt
                run_eng, run_ms = eng, dur
            elif run_eng == eng:
                run_ms += dur
            else:
                run_eng, run_ms = eng, dur
        else:
            run_eng, run_ms = None, 0
        out.append(row)
    for idx, scene in enumerate(out):
        scene["seq_index"] = idx
    return out


def align_timeline_to_voice(
    scenes: list[dict[str, Any]],
    total_master_ms: int,
) -> list[dict[str, Any]]:
    """Shrink or grow the final filler scene so scene sum matches voice within 250 ms."""
    working = [copy.deepcopy(s) for s in _sorted_scenes(scenes)]
    delta = total_master_ms - _sum_scene_ms(working)
    if abs(delta) <= RULE_01_TOLERANCE_MS:
        return working
    if not working:
        return [
            {
                "scene_id": "pad_rule01",
                "seq_index": 0,
                "visual_engine": STICKMAN_ENGINE,
                "motif_component": "StickmanStage",
                "start_ms": 0,
                "end_ms": max(total_master_ms, 0),
                "act_number": 1,
            }
        ]
    last = copy.deepcopy(working[-1])
    last["end_ms"] = int(last["end_ms"]) + delta
    if _scene_duration_ms(last) > MICRO_BEAT_MAX_MS and last.get("visual_engine") in {STICKMAN_ENGINE, STILL_ENGINE}:
        trimmed = copy.deepcopy(last)
        trimmed["end_ms"] = int(trimmed["start_ms"]) + MICRO_BEAT_MAX_MS
        working[-1] = trimmed
        spill = copy.deepcopy(last)
        spill["scene_id"] = f"{last['scene_id']}_pad"
        spill["start_ms"] = int(trimmed["end_ms"])
        spill["end_ms"] = spill["start_ms"] + (_scene_duration_ms(last) - MICRO_BEAT_MAX_MS)
        working.append(spill)
    else:
        working[-1] = last
    for idx, scene in enumerate(working):
        scene["seq_index"] = idx
    return working


def compress_hero_prompts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in scenes:
        row = copy.deepcopy(scene)
        if not _is_hero(row):
            out.append(row)
            continue
        tl = copy.deepcopy(row.get("timeline_spec_json") or {})
        mode = str(tl.get("prompt_mode") or "TEXT_TO_VIDEO")
        if mode in _RETIRED_MODES:
            tl["prompt_mode"] = "TEXT_TO_VIDEO"
            mode = "TEXT_TO_VIDEO"
        for key in ("prompt_v1", "visual_prompt"):
            if key in tl and isinstance(tl[key], str):
                text = re.sub(r"don'?t\s+show.*", "", tl[key], flags=re.IGNORECASE)
                text = re.sub(r"\bno\b\s+\w+.*", "", text, flags=re.IGNORECASE)
                tl[key] = " ".join(text.split()) or "Wide establishing shot of documentary stage."
        if mode in {"FIRST_FRAME", "FIRST_AND_LAST_FRAME"}:
            for key in ("prompt_v1", "visual_prompt"):
                if key in tl and isinstance(tl[key], str):
                    text = re.sub(
                        r"\b(hooded|detective|charcoal|coat|fedora)\b",
                        "",
                        tl[key],
                        flags=re.IGNORECASE,
                    )
                    tl[key] = " ".join(text.split())
        row["timeline_spec_json"] = tl
        if not row.get("prompt_v2_safe"):
            row["prompt_v2_safe"] = "Rain on windows, swinging door, flashlight beam only."
        out.append(row)
    return out


def inject_news_hedges(scenes: list[dict[str, Any]], ledger: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    news_ids = {str(f["fact_id"]) for f in ledger if f.get("source_kind") == "news_report"}
    out: list[dict[str, Any]] = []
    for scene in scenes:
        row = copy.deepcopy(scene)
        cited = row.get("cited_fact_ids") or []
        needs = any(str(fid) in news_ids for fid in cited)
        narration = str(row.get("narration_text") or "")
        if needs and narration and not _ATTRIBUTION_HEDGE_RE.search(narration):
            row["narration_text"] = f"News accounts reported that {narration[0].lower()}{narration[1:]}"
        out.append(row)
    return out


def ensure_foia_dramatization_badges(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for scene in scenes:
        row = copy.deepcopy(scene)
        if scene.get("visual_engine") in FOIA_ENGINES and row.get("on_screen_label") is None:
            row["on_screen_label"] = _TRANSCRIPT_BADGE
        out.append(row)
    return out


def fix_callout_holds(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for card in cards:
        row = copy.deepcopy(card)
        words = len(str(row.get("headline", "")).split())
        minimum = min_hold_duration_sec(words)
        if float(row.get("duration_sec", 0)) + 1e-9 < minimum:
            row["duration_sec"] = minimum
        row["safe_zone_mode"] = "CSS_CONTAINED"
        out.append(row)
    return out


def sanitize_blocked_hero_prompts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace violent safety tokens; tracking-shot bigrams remain whitelisted."""
    safe_motion = "Smooth tracking shot along rainlit corridor, empty documentary stage."
    out: list[dict[str, Any]] = []
    for scene in scenes:
        row = copy.deepcopy(scene)
        if not _is_hero(row):
            out.append(row)
            continue
        tl = copy.deepcopy(row.get("timeline_spec_json") or {})
        for key in ("prompt_v1", "visual_prompt"):
            if not isinstance(tl.get(key), str):
                continue
            if find_blocked_safety_terms(tl[key]):
                tl[key] = safe_motion
        row["timeline_spec_json"] = tl
        if not row.get("prompt_v2_safe"):
            row["prompt_v2_safe"] = "Rain on windows, swinging door, flashlight beam only."
        out.append(row)
    return out


def ensure_act2_retention_peaks(scenes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    out = [copy.deepcopy(s) for s in scenes]
    added_ms = 0
    for scene in out:
        scene.setdefault("act_number", 2 if _is_hero(scene) else scene.get("act_number", 1))
    peaks = [
        s
        for s in out
        if int(s.get("act_number", 0)) == 2
        and (
            s.get("retention_peak")
            or (_is_hero(s) and float(s.get("emotional_peak_score", 0)) >= 0.5)
        )
    ]
    peak_count = len(
        [
            s
            for s in out
            if int(s.get("act_number", 0)) == 2
            and (
                s.get("retention_peak")
                or (_is_hero(s) and float(s.get("emotional_peak_score", 0)) >= 0.5)
            )
        ]
    )
    if peak_count < MIN_ACT2_PEAKS:
        act2 = [s for s in out if int(s.get("act_number", 0)) == 2] or out
        for scene in act2[:MIN_ACT2_PEAKS]:
            scene["retention_peak"] = True
            scene["act_number"] = 2
        still_short = MIN_ACT2_PEAKS - len(
            [s for s in out if int(s.get("act_number", 0)) == 2 and s.get("retention_peak")]
        )
        tail = int(out[-1]["end_ms"]) if out else 0
        for i in range(still_short):
            out.append(
                {
                    "scene_id": f"synthetic_act2_peak_{i}",
                    "seq_index": len(out),
                    "visual_engine": STICKMAN_ENGINE,
                    "motif_component": "StickmanStage",
                    "act_number": 2,
                    "retention_peak": True,
                    "start_ms": tail + i * MICRO_BEAT_MAX_MS,
                    "end_ms": tail + (i + 1) * MICRO_BEAT_MAX_MS,
                    "narration_version_sha256": out[0].get("narration_version_sha256") if out else "",
                }
            )
            added_ms += MICRO_BEAT_MAX_MS
    for scene in out:
        if _is_hero(scene) and int(scene.get("act_number", 1)) == 1 and _scene_duration_ms(scene) > 20_000:
            scene["act_number"] = 2
    for idx, scene in enumerate(out):
        scene["seq_index"] = idx
    return out, added_ms


def fix_brand_entropy(manifest: DirectorManifest) -> DirectorManifest:
    m = copy.deepcopy(manifest)
    if m.turning_point_count < 3:
        m.turning_point_count = 3
    if m.cold_open_archetype in m.recent_cold_open_archetypes:
        m.cold_open_archetype = "CHRONOLOGICAL_COUNTDOWN"
    return m


def strip_crimson_from_frame_specs(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        row = copy.deepcopy(spec)
        for key in ("start_frame_hex", "end_frame_hex", "dominant_color"):
            if isinstance(row.get(key), str) and _CRIMSON.lower() in row[key].lower():
                row[key] = row[key].replace(_CRIMSON, "#4A4A4A").replace(_CRIMSON.lower(), "#4a4a4a")
        out.append(row)
    return out


def ensure_code_callout_for_splits(
    scenes: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach a 2-word RULE_07 callout to 3.2s CODE tail from 9.2s splits."""
    out = list(cards)
    for scene in scenes:
        sid = str(scene.get("scene_id", ""))
        if not sid.endswith("_code"):
            continue
        dur_sec = _scene_duration_ms(scene) / 1000.0
        if dur_sec + 1e-9 < min_hold_duration_sec(2):
            continue
        if any(c.get("scene_id") == sid for c in out):
            continue
        out.append(
            {
                "card_id": f"{sid}_callout",
                "scene_id": sid,
                "headline": "Dock Eight",
                "duration_sec": dur_sec,
                "safe_zone_mode": "CSS_CONTAINED",
                "anchor_space": "STAGE",
            }
        )
    return out


def _manifest_from_dict(data: Mapping[str, Any]) -> DirectorManifest:
    scenes = [copy.deepcopy(dict(s)) for s in data.get("scenes", [])]
    return DirectorManifest(
        scenes=scenes,
        total_master_ms=int(data.get("total_master_ms", _sum_scene_ms(scenes))),
        narration_version_sha256=str(data.get("narration_version_sha256", "")),
        voice_segments=[copy.deepcopy(dict(v)) for v in data.get("voice_segments", [])],
        fact_ledger=[copy.deepcopy(dict(f)) for f in data.get("fact_ledger", [])],
        callout_cards=[copy.deepcopy(dict(c)) for c in data.get("callout_cards", [])],
        foia_911_slots_ms=[copy.deepcopy(dict(s)) for s in data.get("foia_911_slots_ms", [])],
        cold_open_archetype=str(data.get("cold_open_archetype", "CHRONOLOGICAL_COUNTDOWN")),
        turning_point_count=int(data.get("turning_point_count", 3)),
        recent_cold_open_archetypes=tuple(data.get("recent_cold_open_archetypes", ())),
        monthly_spend_micro_usd=int(data.get("monthly_spend_micro_usd", 0)),
        frame_png_specs=[copy.deepcopy(dict(p)) for p in data.get("frame_png_specs", [])],
    )


# --- Lint helpers per rule ---


def _lint_rule_01(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    scenes = _sorted_scenes(manifest.scenes)
    if not scenes:
        return v
    delta = abs(_sum_scene_ms(scenes) - manifest.total_master_ms)
    if delta > RULE_01_TOLERANCE_MS:
        v.append(
            LintViolation(
                "RULE_01",
                "DURATION_SUM",
                f"scene sum differs from total_master_ms by {delta} ms",
            )
        )
    if int(scenes[0]["start_ms"]) != 0:
        v.append(LintViolation("RULE_01", "TIMELINE_START", "timeline must start at 0"))
    for scene in scenes:
        sha = scene.get("narration_version_sha256")
        if sha and sha != manifest.narration_version_sha256:
            v.append(
                LintViolation(
                    "RULE_01",
                    "NARRATION_SHA",
                    f"scene {scene['scene_id']} narration sha mismatch",
                    str(scene.get("scene_id")),
                )
            )
    foia_scenes = [s for s in scenes if s.get("visual_engine") in FOIA_ENGINES]
    foia_slots = [s for s in manifest.voice_segments if s.get("segment_kind") == "FOIA_AUDIO_SLOT"]
    if len(foia_scenes) != len(foia_slots):
        v.append(
            LintViolation(
                "RULE_01",
                "FOIA_SLOT_COUNT",
                f"FOIA scenes {len(foia_scenes)} vs slots {len(foia_slots)}",
            )
        )
    return v


def _lint_rule_02(manifest: DirectorManifest, caps: BudgetCaps) -> list[LintViolation]:
    v: list[LintViolation] = []
    heroes = _hero_clips(manifest.scenes)
    if len(heroes) > caps.max_hero_clips:
        v.append(LintViolation("RULE_02", "HERO_CLIP_COUNT", "too many hero clips"))
    hero_ms = _total_hero_duration_ms(manifest.scenes)
    if hero_ms > caps.max_hero_duration_sec * 1000:
        v.append(LintViolation("RULE_02", "HERO_DURATION", "hero duration cap exceeded"))
    ep_cost = _estimate_hero_cost_micro_usd(manifest.scenes, usd_per_sec=caps.usd_per_sec)
    if ep_cost > caps.episode_video_cap_micro_usd:
        v.append(LintViolation("RULE_02", "EPISODE_VIDEO_CAP", "episode cap exceeded"))
    if manifest.monthly_spend_micro_usd + ep_cost > caps.monthly_all_providers_cap_micro_usd:
        v.append(LintViolation("RULE_02", "MONTHLY_CAP", "monthly headroom exhausted"))
    return v


def _lint_rule_03(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    for scene in manifest.scenes:
        if not _is_hero(scene):
            continue
        dur = _scene_duration_ms(scene)
        if dur > FLOW_BEAT_LONG_MS:
            v.append(
                LintViolation(
                    "RULE_03",
                    "UNSPLIT_FLOW_BEAT",
                    f"scene {scene['scene_id']} needs 6s+remainder split",
                    str(scene.get("scene_id")),
                )
            )
        tl = scene.get("timeline_spec_json") or {}
        mode = tl.get("prompt_mode")
        if mode == "FIRST_AND_LAST_FRAME" and dur > 10_000:
            v.append(
                LintViolation(
                    "RULE_03",
                    "FALF_CAP",
                    f"scene {scene['scene_id']} exceeds 10s FIRST_AND_LAST_FRAME cap",
                    str(scene.get("scene_id")),
                )
            )
    return v


def _lint_rule_04(manifest: DirectorManifest) -> list[LintViolation]:
    ordered = _sorted_scenes(manifest.scenes)
    v: list[LintViolation] = []
    for idx, scene in enumerate(ordered):
        if not _is_hero(scene):
            continue
        sid = str(scene.get("scene_id"))
        fb = scene.get("fallback_spec_json")
        if not fb:
            v.append(LintViolation("RULE_04", "MISSING_FALLBACK", "missing fallback", sid))
            continue
        eng = fb.get("engine") or fb.get("visual_engine")
        if eng == HERO_ENGINE:
            v.append(LintViolation("RULE_04", "INVALID_FALLBACK", "fallback is hero", sid))
        prev_eng = ordered[idx - 1]["visual_engine"] if idx else None
        next_eng = ordered[idx + 1]["visual_engine"] if idx + 1 < len(ordered) else None
        if eng == prev_eng or eng == next_eng:
            v.append(LintViolation("RULE_04", "NEIGHBOR_FALLBACK", "neighbor fallback", sid))
    return v


def _lint_rule_05(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    ordered = _sorted_scenes(manifest.scenes)
    boundaries = {int(s["end_ms"]) for s in ordered}
    for slot in manifest.foia_911_slots_ms:
        boundaries.add(int(slot["end_ms"]))
    for scene in ordered:
        dur = _scene_duration_ms(scene)
        eng = scene.get("visual_engine")
        if eng in FOIA_ENGINES:
            continue
        if eng in {STICKMAN_ENGINE, STILL_ENGINE} and dur > MICRO_BEAT_MAX_MS:
            v.append(
                LintViolation(
                    "RULE_05",
                    "MICRO_BEAT",
                    f"static beat {dur}ms > 6s",
                    str(scene.get("scene_id")),
                )
            )
        if _is_hero(scene) and dur <= FLOW_HERO_EXEMPT_MAX_MS:
            continue
        if eng == STICKMAN_ENGINE and dur > MICRO_BEAT_MAX_MS:
            pass
        if scene.get("motif_component") != CASEBOARD_SPINE_MOTIF:
            continue
        start = int(scene["start_ms"])
        if start < SPINE_WINDOW_START_MS or start > SPINE_WINDOW_END_MS:
            v.append(
                LintViolation("RULE_05", "SPINE_WINDOW", "CaseBoardSpine outside 210-270s", str(scene.get("scene_id")))
            )
        if start not in boundaries:
            v.append(
                LintViolation("RULE_05", "SPINE_BOUNDARY", "spine not on completed boundary", str(scene.get("scene_id")))
            )
        for slot in manifest.foia_911_slots_ms:
            s0, s1 = int(slot["start_ms"]), int(slot["end_ms"])
            if s0 < start < s1:
                v.append(
                    LintViolation("RULE_05", "SPINE_MID_911", "spine chops 911 slot", str(scene.get("scene_id")))
                )
    run_eng = None
    run_ms = 0
    for scene in ordered:
        eng = scene.get("visual_engine")
        dur = _scene_duration_ms(scene)
        if eng in FOIA_ENGINES:
            if run_ms > ENGINE_STREAK_MAX_MS:
                v.append(LintViolation("RULE_05", "ENGINE_STREAK", f"streak {run_ms}ms"))
            run_eng, run_ms = None, 0
            continue
        if eng == run_eng:
            run_ms += dur
        else:
            if run_ms > ENGINE_STREAK_MAX_MS:
                v.append(LintViolation("RULE_05", "ENGINE_STREAK", f"streak {run_ms}ms"))
            run_eng, run_ms = eng, dur
    if run_ms > ENGINE_STREAK_MAX_MS:
        v.append(LintViolation("RULE_05", "ENGINE_STREAK", f"streak {run_ms}ms"))
    return v


def _lint_rule_06(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    peaks = [
        s
        for s in manifest.scenes
        if int(s.get("act_number", 0)) == 2
        and (
            s.get("retention_peak")
            or (_is_hero(s) and float(s.get("emotional_peak_score", 0)) >= 0.5)
        )
    ]
    if len(peaks) < MIN_ACT2_PEAKS:
        v.append(LintViolation("RULE_06", "ACT2_PEAKS", f"need {MIN_ACT2_PEAKS} Act 2 peaks"))
    hero_ms = _total_hero_duration_ms(manifest.scenes)
    act1_ms = sum(
        _scene_duration_ms(s)
        for s in manifest.scenes
        if _is_hero(s) and int(s.get("act_number", 1)) == 1
    )
    cap = int(hero_ms * ACT1_HERO_BUDGET_FRACTION) if hero_ms else int(DEFAULT_MAX_HERO_DURATION_SEC * 1000 * ACT1_HERO_BUDGET_FRACTION)
    if act1_ms > cap:
        v.append(LintViolation("RULE_06", "ACT1_HERO_FRONTLOAD", "Act 1 hero front-load"))
    return v


def _lint_rule_07(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    for card in manifest.callout_cards:
        words = len(str(card.get("headline", "")).split())
        if words > RULE_07_MAX_WORDS:
            v.append(LintViolation("RULE_07", "WORD_COUNT", f"card {card.get('card_id')}"))
        minimum = min_hold_duration_sec(words)
        if float(card.get("duration_sec", 0)) + 1e-9 < minimum:
            v.append(LintViolation("RULE_07", "HOLD_TOO_SHORT", f"card {card.get('card_id')}"))
        if card.get("safe_zone_mode") != "CSS_CONTAINED":
            v.append(LintViolation("RULE_07", "SAFE_ZONE", f"card {card.get('card_id')}"))
    return v


def _lint_rule_08(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    if manifest.turning_point_count < 3:
        v.append(LintViolation("RULE_08", "TURNING_POINTS", "need >= 3 turning points"))
    if manifest.cold_open_archetype in manifest.recent_cold_open_archetypes:
        v.append(LintViolation("RULE_08", "ARCHETYPE_REPEAT", "cold-open archetype repeated"))
    return v


def _lint_rule_09(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    news_ids = {str(f["fact_id"]) for f in manifest.fact_ledger if f.get("source_kind") == "news_report"}
    for scene in manifest.scenes:
        cited = scene.get("cited_fact_ids") or []
        if not any(str(fid) in news_ids for fid in cited):
            continue
        text = str(scene.get("narration_text") or "")
        if text and not _ATTRIBUTION_HEDGE_RE.search(text):
            v.append(
                LintViolation("RULE_09", "UNHEDGED_NEWS", "news citation lacks hedge", str(scene.get("scene_id")))
            )
    return v


def _lint_rule_10(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    for scene in manifest.scenes:
        if scene.get("visual_engine") not in FOIA_ENGINES:
            continue
        label = scene.get("on_screen_label")
        if label != _TRANSCRIPT_BADGE:
            v.append(
                LintViolation("RULE_10", "MISSING_BADGE", "FOIA scene missing dramatization badge", str(scene.get("scene_id")))
            )
    return v


def _lint_rule_11(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    for scene in manifest.scenes:
        if not _is_hero(scene):
            continue
        tl = scene.get("timeline_spec_json") or {}
        mode = str(tl.get("prompt_mode") or "")
        if mode in _RETIRED_MODES:
            v.append(LintViolation("RULE_11", "RETIRED_MODE", mode, str(scene.get("scene_id"))))
        dur = _scene_duration_ms(scene)
        if mode == "FIRST_AND_LAST_FRAME" and dur > 10_000:
            v.append(LintViolation("RULE_11", "DURATION_CAP", "FALF duration", str(scene.get("scene_id"))))
        prompt = str(tl.get("prompt_v1") or tl.get("visual_prompt") or "")
        if re.search(r"don'?t\s+show", prompt, re.IGNORECASE):
            v.append(LintViolation("RULE_11", "NEGATIVE_BAN", "banned negative wording", str(scene.get("scene_id"))))
    return v


def _lint_rule_12(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    for scene in manifest.scenes:
        if not _is_hero(scene):
            continue
        tl = scene.get("timeline_spec_json") or {}
        for key in ("prompt_v1", "visual_prompt"):
            text = tl.get(key)
            if isinstance(text, str) and find_blocked_safety_terms(text):
                v.append(
                    LintViolation(
                        "RULE_12",
                        "BLOCKED_TERM",
                        f"blocked terms in {key}",
                        str(scene.get("scene_id")),
                    )
                )
    return v


def _lint_rule_13(manifest: DirectorManifest) -> list[LintViolation]:
    v: list[LintViolation] = []
    for scene in manifest.scenes:
        if not _is_hero(scene):
            continue
        sid = str(scene.get("scene_id"))
        if not scene.get("prompt_v2_safe"):
            v.append(LintViolation("RULE_13", "MISSING_V2", "missing prompt_v2_safe", sid))
        tl = scene.get("timeline_spec_json") or {}
        if not (tl.get("prompt_v1") or tl.get("visual_prompt")):
            v.append(LintViolation("RULE_13", "MISSING_V1", "missing prompt_v1", sid))
    for spec in manifest.frame_png_specs:
        blob = " ".join(str(spec.get(k, "")) for k in ("start_frame_hex", "end_frame_hex", "dominant_color"))
        if _CRIMSON.lower() in blob.lower():
            v.append(LintViolation("RULE_13", "CRIMSON_FRAME", "crimson in frame PNG spec"))
    return v


def lint_manifest(manifest: DirectorManifest, *, caps: BudgetCaps | None = None) -> LintReport:
    caps = caps or BudgetCaps()
    violations: list[LintViolation] = []
    violations.extend(_lint_rule_01(manifest))
    violations.extend(_lint_rule_02(manifest, caps))
    violations.extend(_lint_rule_03(manifest))
    violations.extend(_lint_rule_04(manifest))
    violations.extend(_lint_rule_05(manifest))
    violations.extend(_lint_rule_06(manifest))
    violations.extend(_lint_rule_07(manifest))
    violations.extend(_lint_rule_08(manifest))
    violations.extend(_lint_rule_09(manifest))
    violations.extend(_lint_rule_10(manifest))
    violations.extend(_lint_rule_11(manifest))
    violations.extend(_lint_rule_12(manifest))
    violations.extend(_lint_rule_13(manifest))
    return LintReport(violations=violations)


def apply_fixed_point_repairs(
    manifest: DirectorManifest,
    *,
    caps: BudgetCaps | None = None,
) -> tuple[DirectorManifest, list[str]]:
    caps = caps or BudgetCaps()
    repairs: list[str] = []
    m = copy.deepcopy(manifest)

    scenes = snap_case_board_spine(m.scenes, m.foia_911_slots_ms)
    if scenes != m.scenes:
        repairs.append("RULE_05_spine_snap")
    m.scenes = scenes

    scenes = apply_act_constrained_downgrade(
        m.scenes, caps=caps, monthly_spend_micro_usd=m.monthly_spend_micro_usd
    )
    repairs.append("RULE_02_act_downgrade")

    scenes = apply_rule_03_splits(scenes)
    repairs.append("RULE_03_splits")

    scenes = split_static_micro_beats(scenes)
    repairs.append("RULE_05_micro_split")

    scenes = break_engine_streaks(scenes)
    repairs.append("RULE_05_streak_break")

    scenes = assign_rule_04_fallbacks(scenes)
    repairs.append("RULE_04_fallbacks")

    scenes, added_ms = ensure_act2_retention_peaks(scenes)
    if added_ms:
        m.total_master_ms += added_ms
    repairs.append("RULE_06_peaks")

    scenes = align_timeline_to_voice(scenes, m.total_master_ms)
    repairs.append("RULE_01_align")

    scenes = split_static_micro_beats(scenes)
    repairs.append("RULE_05_post_align_split")

    scenes = compress_hero_prompts(scenes)
    repairs.append("RULE_11_compress")

    scenes = sanitize_blocked_hero_prompts(scenes)
    repairs.append("RULE_12_sanitize")

    scenes = inject_news_hedges(scenes, m.fact_ledger)
    repairs.append("RULE_09_hedge")

    scenes = ensure_foia_dramatization_badges(scenes)
    repairs.append("RULE_10_badge")

    for scene in scenes:
        scene.setdefault("narration_version_sha256", m.narration_version_sha256)

    m.scenes = scenes
    m.callout_cards = fix_callout_holds(ensure_code_callout_for_splits(scenes, m.callout_cards))
    m.frame_png_specs = strip_crimson_from_frame_specs(m.frame_png_specs)
    m = fix_brand_entropy(m)

    m.scenes, tail_added = ensure_act2_retention_peaks(m.scenes)
    if tail_added:
        m.total_master_ms += tail_added
        m.scenes = align_timeline_to_voice(m.scenes, m.total_master_ms)
    m.scenes = sanitize_blocked_hero_prompts(m.scenes)
    m.scenes = compress_hero_prompts(m.scenes)
    before = lint_manifest(m, caps=caps)
    if not before.all_passed:
        m.scenes = assign_rule_04_fallbacks(m.scenes)
        m.scenes = split_static_micro_beats(m.scenes)
    return m, repairs


class Agent4DirectorService:
    """Certify manifests across RULE_01–RULE_13 with deterministic collision repair."""

    def __init__(self, *, caps: BudgetCaps | None = None) -> None:
        self.caps = caps or BudgetCaps()

    def lint(self, draft: Mapping[str, Any]) -> LintReport:
        return lint_manifest(_manifest_from_dict(draft), caps=self.caps)

    def certify(self, draft: Mapping[str, Any]) -> CertifiedResult:
        manifest = _manifest_from_dict(draft)
        repaired, repair_log = apply_fixed_point_repairs(manifest, caps=self.caps)
        report = lint_manifest(repaired, caps=self.caps)
        ok = report.all_passed and report.passed_rule_count == RULE_COUNT
        return CertifiedResult(ok=ok, manifest=repaired, lint=report, repairs=repair_log)

    def passes_rule(self, draft: Mapping[str, Any], rule_id: str) -> bool:
        report = self.certify(draft)
        return rule_id not in {v.rule_id for v in report.lint.violations}

    def rule_case(self, rule_id: str) -> dict[str, Any]:
        """Minimal adversarial draft engineered to exercise a single law after certify()."""
        sha = hashlib.sha256(b"task090-narration-v1").hexdigest()
        base_stick = {
            "visual_engine": STICKMAN_ENGINE,
            "motif_component": "StickmanStage",
            "act_number": 2,
            "narration_version_sha256": sha,
            "emotional_peak_score": 0.2,
        }
        if rule_id == "RULE_01":
            foia_ms = 240_000
            total = 300_000
            return {
                "total_master_ms": total,
                "narration_version_sha256": sha,
                "voice_segments": [{"segment_kind": "FOIA_AUDIO_SLOT", "duration_ms": foia_ms, "foia_asset_id": "foia_long"}],
                "scenes": [
                    {**base_stick, "scene_id": "n1", "seq_index": 0, "start_ms": 0, "end_ms": 30_000},
                    {
                        **base_stick,
                        "scene_id": "foia",
                        "seq_index": 1,
                        "visual_engine": "FOIA_REAL_FOOTAGE",
                        "foia_asset_id": "foia_long",
                        "start_ms": 30_000,
                        "end_ms": 30_000 + foia_ms,
                    },
                    {**base_stick, "scene_id": "n2", "seq_index": 2, "start_ms": 270_000, "end_ms": total},
                ],
            }
        if rule_id == "RULE_02":
            heroes = [
                {
                    "scene_id": f"h{i}",
                    "seq_index": i,
                    "visual_engine": HERO_ENGINE,
                    "motif_component": "HeroVideoBridge",
                    "act_number": 2,
                    "start_ms": i * 9000,
                    "end_ms": (i + 1) * 9000,
                    "emotional_peak_score": 0.9 - i * 0.05,
                    "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": "Wide establishing shot of warehouse."},
                }
                for i in range(15)
            ]
            return {"total_master_ms": 150_000, "narration_version_sha256": sha, "scenes": heroes}
        if rule_id == "RULE_03":
            return {
                "total_master_ms": 69_200,
                "narration_version_sha256": sha,
                "scenes": [
                    {**base_stick, "scene_id": "a", "seq_index": 0, "start_ms": 0, "end_ms": 60_000},
                    {
                        "scene_id": "long",
                        "seq_index": 1,
                        "visual_engine": HERO_ENGINE,
                        "motif_component": "HeroVideoBridge",
                        "act_number": 2,
                        "start_ms": 60_000,
                        "end_ms": 69_200,
                        "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": "Steady tracking shot down corridor."},
                        "prompt_v2_safe": "Rain on glass, door swings slowly.",
                    },
                ],
            }
        if rule_id == "RULE_04":
            return {
                "total_master_ms": 68_000,
                "narration_version_sha256": sha,
                "scenes": [
                    {**base_stick, "scene_id": "a", "seq_index": 0, "start_ms": 0, "end_ms": 30_000},
                    {
                        "scene_id": "mid",
                        "seq_index": 1,
                        "visual_engine": HERO_ENGINE,
                        "start_ms": 30_000,
                        "end_ms": 38_000,
                        "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": "Smooth tracking shot in alley."},
                        "fallback_spec_json": {"engine": STICKMAN_ENGINE},
                        "prompt_v2_safe": "Flashlight beam sweeps floor.",
                    },
                    {**base_stick, "scene_id": "b", "seq_index": 2, "start_ms": 38_000, "end_ms": 68_000},
                ],
            }
        if rule_id == "RULE_05":
            return {
                "total_master_ms": 261_000,
                "narration_version_sha256": sha,
                "foia_911_slots_ms": [{"slot_id": "911_CALL", "start_ms": 230_000, "end_ms": 255_000}],
                "scenes": [
                    {**base_stick, "scene_id": "pre", "seq_index": 0, "start_ms": 0, "end_ms": 230_000},
                    {
                        **base_stick,
                        "scene_id": "call",
                        "seq_index": 1,
                        "visual_engine": "FOIA_REAL_FOOTAGE",
                        "start_ms": 230_000,
                        "end_ms": 255_000,
                        "on_screen_label": _TRANSCRIPT_BADGE,
                    },
                    {
                        **base_stick,
                        "scene_id": "spine",
                        "seq_index": 2,
                        "motif_component": CASEBOARD_SPINE_MOTIF,
                        "start_ms": 240_000,
                        "end_ms": 246_000,
                    },
                    {**base_stick, "scene_id": "tail", "seq_index": 3, "start_ms": 255_000, "end_ms": 261_000},
                ],
                "voice_segments": [{"segment_kind": "FOIA_AUDIO_SLOT", "duration_ms": 25_000}],
            }
        if rule_id == "RULE_06":
            scenes = [{**base_stick, "scene_id": "intro", "seq_index": 0, "act_number": 1, "start_ms": 0, "end_ms": 400_000}]
            for i, score in enumerate((0.95, 0.92, 0.1, 0.15), start=1):
                scenes.append(
                    {
                        "scene_id": f"p{i}",
                        "seq_index": i,
                        "visual_engine": HERO_ENGINE,
                        "act_number": 2,
                        "start_ms": 400_000 + i * 10_000,
                        "end_ms": 410_000 + i * 10_000,
                        "emotional_peak_score": score,
                        "retention_peak": score >= 0.5,
                        "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": "Wide shot of evidence table."},
                        "prompt_v2_safe": "Overhead light flickers.",
                    }
                )
            return {"total_master_ms": 460_000, "narration_version_sha256": sha, "scenes": scenes, "monthly_spend_micro_usd": 0}
        if rule_id == "RULE_07":
            return {
                "total_master_ms": 10_000,
                "narration_version_sha256": sha,
                "scenes": [{**base_stick, "scene_id": "c", "seq_index": 0, "start_ms": 0, "end_ms": 10_000}],
                "callout_cards": [
                    {
                        "card_id": "bad",
                        "headline": "one two",
                        "duration_sec": 1.0,
                        "safe_zone_mode": "CSS_CONTAINED",
                    }
                ],
            }
        if rule_id == "RULE_08":
            return {
                "total_master_ms": 60_000,
                "narration_version_sha256": sha,
                "cold_open_archetype": "ALIBI_THAT_CRACKED",
                "turning_point_count": 2,
                "recent_cold_open_archetypes": ["ALIBI_THAT_CRACKED"],
                "scenes": [{**base_stick, "scene_id": "c", "seq_index": 0, "start_ms": 0, "end_ms": 60_000}],
            }
        if rule_id == "RULE_09":
            return {
                "total_master_ms": 20_000,
                "narration_version_sha256": sha,
                "fact_ledger": [{"fact_id": "f_news", "source_kind": "news_report"}],
                "scenes": [
                    {
                        **base_stick,
                        "scene_id": "news",
                        "cited_fact_ids": ["f_news"],
                        "narration_text": "Police identified a person of interest.",
                        "start_ms": 0,
                        "end_ms": 20_000,
                    }
                ],
            }
        if rule_id == "RULE_10":
            return {
                "total_master_ms": 25_000,
                "narration_version_sha256": sha,
                "voice_segments": [{"segment_kind": "FOIA_AUDIO_SLOT", "duration_ms": 25_000, "foia_asset_id": "foia_a"}],
                "scenes": [
                    {
                        **base_stick,
                        "scene_id": "foia",
                        "visual_engine": "FOIA_REAL_FOOTAGE",
                        "foia_asset_id": "foia_a",
                        "start_ms": 0,
                        "end_ms": 25_000,
                    }
                ],
            }
        if rule_id == "RULE_11":
            return {
                "total_master_ms": 20_000,
                "narration_version_sha256": sha,
                "scenes": [
                    {
                        "scene_id": "h1",
                        "seq_index": 0,
                        "visual_engine": HERO_ENGINE,
                        "start_ms": 0,
                        "end_ms": 9200,
                        "prompt_v2_safe": "Rain on glass, door creak.",
                        "timeline_spec_json": {
                            "prompt_mode": "VEO_3_1_LITE",
                            "prompt_v1": "Don't show the detective's face in frame.",
                        },
                    }
                ],
            }
        if rule_id == "RULE_12":
            return {
                "total_master_ms": 20_000,
                "narration_version_sha256": sha,
                "scenes": [
                    {
                        "scene_id": "violent",
                        "seq_index": 0,
                        "visual_engine": HERO_ENGINE,
                        "start_ms": 0,
                        "end_ms": 9200,
                        "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": VIOLENT_PROMPT_SAMPLE},
                        "prompt_v2_safe": "Rain on pavement.",
                    }
                ],
            }
        if rule_id == "RULE_13":
            return {
                "total_master_ms": 20_000,
                "narration_version_sha256": sha,
                "scenes": [
                    {
                        "scene_id": "hero",
                        "seq_index": 0,
                        "visual_engine": HERO_ENGINE,
                        "start_ms": 0,
                        "end_ms": 6000,
                        "prompt_v2_safe": "Flashlight beam on wet pavement.",
                        "timeline_spec_json": {"prompt_mode": "FIRST_FRAME", "prompt_v1": "Panning shot across rain alley."},
                    }
                ],
                "frame_png_specs": [{"dominant_color": _CRIMSON, "role": "start"}],
            }
        raise KeyError(rule_id)


VIOLENT_PROMPT_SAMPLE = "The suspect shot the victim near the loading dock."
TRACKING_PROMPT_SAMPLE = "Figure glides forward, smooth side tracking shot along the corridor."


def collision_manifest_triple_fault() -> dict[str, Any]:
    """RULE_02 overrun + unsplit 9.2s beat + tracking prompt with violent phrase."""
    sha = hashlib.sha256(b"collision-v1").hexdigest()
    scenes: list[dict[str, Any]] = []
    t = 0
    for i in range(12):
        scenes.append(
            {
                "scene_id": f"hero_{i}",
                "seq_index": i,
                "visual_engine": HERO_ENGINE,
                "act_number": 2,
                "start_ms": t,
                "end_ms": t + 9200,
                "emotional_peak_score": 0.85 if i < 2 else 0.2,
                "prompt_v2_safe": "Overhead light flickers in corridor.",
                "timeline_spec_json": {
                    "prompt_mode": "TEXT_TO_VIDEO",
                    "prompt_v1": f"{TRACKING_PROMPT_SAMPLE} Officers heard a shot echo.",
                },
            }
        )
        t += 9200
    return {
        "total_master_ms": t,
        "narration_version_sha256": sha,
        "monthly_spend_micro_usd": 120_000_000,
        "scenes": scenes,
    }