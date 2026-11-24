"""LAW_06: segmented L-cut lead-ins, music ducking, and twist-pad alignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

LAW_ID = "LAW_06"

L_CUT_MIN_MS = 600
L_CUT_MAX_MS = 1_000
ADJACENT_FOIA_MERGE_GAP_MS = 500

MUSIC_BASE_LUFS = -22.0
MUSIC_DUCK_LUFS = -36.0
LUFS_TOLERANCE = 0.05

FOIA_VISUAL_ENGINES = frozenset({"FOIA_REAL_FOOTAGE", "AUDIO_EVIDENCE_CARD"})


@dataclass(frozen=True, slots=True)
class Law06FoiaScene:
    scene_id: str
    visual_engine: str
    visual_start_ms: int
    visual_end_ms: int
    foia_asset_id: str
    l_cut_ms: int | None = None

    @property
    def duration_ms(self) -> int:
        return self.visual_end_ms - self.visual_start_ms


@dataclass(frozen=True, slots=True)
class Law06FoiaSlot:
    start_ms: int
    end_ms: int
    foia_asset_id: str


@dataclass(frozen=True, slots=True)
class Law06TwistPad:
    start_ms: int
    end_ms: int
    pad_id: str = ""


@dataclass(frozen=True, slots=True)
class Law06MusicDuck:
    start_ms: int
    end_ms: int
    from_lufs: float = MUSIC_BASE_LUFS
    to_lufs: float = MUSIC_DUCK_LUFS


@dataclass(slots=True)
class Law06AudioGraph:
    foia_scenes: list[Law06FoiaScene] = field(default_factory=list)
    foia_slots: list[Law06FoiaSlot] = field(default_factory=list)
    twist_pads: list[Law06TwistPad] = field(default_factory=list)
    music_ducks: list[Law06MusicDuck] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Law06Violation:
    code: str
    message: str
    scene_id: str | None = None
    rule_id: str = LAW_ID


@dataclass(slots=True)
class Law06Result:
    violations: list[Law06Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def clamp_l_cut_start(visual_start_ms: int, l_cut_ms: int) -> int:
    """Law 6 cannot pre-lap before t=0."""
    return max(0, visual_start_ms - l_cut_ms)


def expected_foia_slot_bounds(
    visual_start_ms: int,
    visual_end_ms: int,
    l_cut_ms: int,
) -> tuple[int, int]:
    """FOIA audio slots include the L-cut pre-roll on Track 2."""
    return (clamp_l_cut_start(visual_start_ms, l_cut_ms), visual_end_ms)


def lead_in_duck_window(visual_start_ms: int, l_cut_ms: int) -> tuple[int, int]:
    """Music bed ducks from -22 to -36 across the L-cut lead-in window."""
    return (clamp_l_cut_start(visual_start_ms, l_cut_ms), visual_start_ms)


def _lufs_close(a: float, b: float) -> bool:
    return abs(a - b) <= LUFS_TOLERANCE


def merge_foia_duck_regions(
    scenes: Sequence[Law06FoiaScene],
    *,
    merge_gap_ms: int = ADJACENT_FOIA_MERGE_GAP_MS,
) -> list[tuple[int, int]]:
    """Merge adjacent FOIA duck envelopes when clips are < 500 ms apart."""
    ordered = sorted(scenes, key=lambda s: s.visual_start_ms)
    regions: list[list[int]] = []

    for scene in ordered:
        if scene.l_cut_ms is None:
            continue
        region_start = clamp_l_cut_start(scene.visual_start_ms, scene.l_cut_ms)
        region_end = scene.visual_end_ms
        if (
            regions
            and scene.visual_start_ms - regions[-1][1] < merge_gap_ms
        ):
            regions[-1][1] = max(regions[-1][1], region_end)
        else:
            regions.append([region_start, region_end])

    return [(start, end) for start, end in regions]


def _find_slot_for_scene(
    scene: Law06FoiaScene,
    slots: Sequence[Law06FoiaSlot],
    slot_start: int,
    slot_end: int,
) -> Law06FoiaSlot | None:
    for slot in slots:
        if slot.foia_asset_id != scene.foia_asset_id:
            continue
        if slot.start_ms == slot_start and slot.end_ms == slot_end:
            return slot
    return None


def _twist_aligns_with_duck(
    twist: Law06TwistPad,
    duck_start: int,
    duck_end: int,
) -> bool:
    """Twist pad must sit inside the duck lead-in window."""
    return twist.start_ms >= duck_start and twist.end_ms <= duck_end


def _music_ducked_at(ducks: Sequence[Law06MusicDuck], t_ms: int) -> bool:
    """True when the bed is already at (or ramping to) -36 LUFS at t_ms."""
    for duck in ducks:
        if not (duck.start_ms <= t_ms < duck.end_ms):
            continue
        if _lufs_close(duck.from_lufs, MUSIC_DUCK_LUFS) and _lufs_close(
            duck.to_lufs, MUSIC_DUCK_LUFS
        ):
            return True
        if _lufs_close(duck.to_lufs, MUSIC_DUCK_LUFS):
            return True
    return False


def _duck_covers_lead_in(
    ducks: Sequence[Law06MusicDuck],
    duck_start: int,
    duck_end: int,
) -> bool:
    for duck in ducks:
        if duck.start_ms != duck_start or duck.end_ms != duck_end:
            continue
        if not _lufs_close(duck.from_lufs, MUSIC_BASE_LUFS):
            continue
        if not _lufs_close(duck.to_lufs, MUSIC_DUCK_LUFS):
            continue
        return True
    return False


def _region_covered_without_pumping(
    ducks: Sequence[Law06MusicDuck],
    region_start: int,
    region_end: int,
) -> bool:
    """Continuous -36 LUFS cover for merged FOIA regions (no -22 bounce)."""
    relevant = [
        duck
        for duck in ducks
        if duck.end_ms > region_start and duck.start_ms < region_end
    ]
    if not relevant:
        return False

    for duck in relevant:
        if duck.start_ms == region_start:
            continue
        if _lufs_close(duck.from_lufs, MUSIC_BASE_LUFS):
            return False

    ramp = next(
        (
            duck
            for duck in relevant
            if duck.start_ms == region_start
            and _lufs_close(duck.from_lufs, MUSIC_BASE_LUFS)
            and _lufs_close(duck.to_lufs, MUSIC_DUCK_LUFS)
        ),
        None,
    )
    if ramp is None:
        return False

    hold_segments = [
        duck
        for duck in relevant
        if duck is not ramp
        and _lufs_close(duck.from_lufs, MUSIC_DUCK_LUFS)
        and _lufs_close(duck.to_lufs, MUSIC_DUCK_LUFS)
    ]
    covered_until = ramp.end_ms
    for hold in sorted(hold_segments, key=lambda d: d.start_ms):
        if hold.start_ms > covered_until:
            return False
        covered_until = max(covered_until, hold.end_ms)

    return covered_until >= region_end


def validate_law_06(graph: Law06AudioGraph) -> Law06Result:
    violations: list[Law06Violation] = []

    foia_scenes = [
        scene
        for scene in graph.foia_scenes
        if scene.visual_engine in FOIA_VISUAL_ENGINES
    ]

    for scene in foia_scenes:
        if scene.l_cut_ms is None:
            violations.append(
                Law06Violation(
                    code="MISSING_L_CUT",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} FOIA scene missing Law 6 L-cut lead-in"
                    ),
                )
            )
            continue

        if not (L_CUT_MIN_MS <= scene.l_cut_ms <= L_CUT_MAX_MS):
            violations.append(
                Law06Violation(
                    code="L_CUT_OUT_OF_RANGE",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} L-cut {scene.l_cut_ms}ms outside "
                        f"{L_CUT_MIN_MS}–{L_CUT_MAX_MS} ms"
                    ),
                )
            )
            continue

        slot_start, slot_end = expected_foia_slot_bounds(
            scene.visual_start_ms,
            scene.visual_end_ms,
            scene.l_cut_ms,
        )
        slot = _find_slot_for_scene(scene, graph.foia_slots, slot_start, slot_end)
        if slot is None:
            violations.append(
                Law06Violation(
                    code="FOIA_SLOT_MISMATCH",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} FOIA_AUDIO_SLOT expected "
                        f"[{slot_start}, {slot_end}) for asset {scene.foia_asset_id!r}"
                    ),
                )
            )

        duck_start, duck_end = lead_in_duck_window(
            scene.visual_start_ms,
            scene.l_cut_ms,
        )
        if duck_end <= duck_start:
            violations.append(
                Law06Violation(
                    code="L_CUT_CLAMPD_TO_ZERO",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} L-cut window collapsed at timeline origin"
                    ),
                )
            )
            continue

        if not _duck_covers_lead_in(
            graph.music_ducks, duck_start, duck_end
        ) and not _music_ducked_at(graph.music_ducks, duck_start):
            violations.append(
                Law06Violation(
                    code="MUSIC_DUCK_MISMATCH",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} missing -22→-36 LUFS duck on "
                        f"[{duck_start}, {duck_end})"
                    ),
                )
            )

        aligned_twist = any(
            _twist_aligns_with_duck(pad, duck_start, duck_end)
            for pad in graph.twist_pads
        )
        if not aligned_twist:
            violations.append(
                Law06Violation(
                    code="TWIST_PAD_NOT_ALIGNED",
                    scene_id=scene.scene_id,
                    message=(
                        f"{scene.scene_id} requires TWIST_PAD aligned to duck "
                        f"[{duck_start}, {duck_end})"
                    ),
                )
            )

    valid_foia = [
        scene
        for scene in foia_scenes
        if scene.l_cut_ms is not None
        and L_CUT_MIN_MS <= scene.l_cut_ms <= L_CUT_MAX_MS
    ]
    merged_regions = merge_foia_duck_regions(valid_foia)
    if len(merged_regions) < len(valid_foia):
        for region_start, region_end in merged_regions:
            if not _region_covered_without_pumping(
                graph.music_ducks,
                region_start,
                region_end,
            ):
                violations.append(
                    Law06Violation(
                        code="DUCK_PUMPING",
                        message=(
                            f"merged FOIA duck [{region_start}, {region_end}) "
                            "must stay at -36 LUFS without pumping"
                        ),
                    )
                )

    return Law06Result(violations=violations)