"""RULE_01 (segmented voice timeline) and RULE_03 (6s+remainder Flow splits)."""

from __future__ import annotations

from typing import Sequence

from agent4_director.linter_types import LintFinding, LintScene, LintVoiceManifest

RULE_01_TOLERANCE_MS = 250
FOIA_VISUAL_ENGINES = frozenset({"FOIA_REAL_FOOTAGE", "AUDIO_EVIDENCE_CARD"})

FLOW_BEAT_LONG_MS = 8500
FLOW_PRIMARY_CHUNK_MS = 8000
FLOW_ALT_FLOW_MS = 6000
MIN_BOOKEND_REMAINDER_SEC = 2.5


def split_flow_beat_ms(duration_ms: int) -> tuple[int, int]:
    """Split a long Flow beat into Flow + Code durations in milliseconds.

  When the beat exceeds 8.5s and the remainder after an 8.0s Flow head would be
    under 2.5s, use 6.0s Flow + the rest as Code (e.g. 9.2s -> 6000 + 3200 ms).
    Otherwise use 8.0s Flow + the remainder as Code (e.g. 11.4s -> 8000 + 3400 ms).
    """
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


def _scene_duration_ms(scene: LintScene) -> int:
    return scene.end_ms - scene.start_ms


def _sum_scene_durations_ms(scenes: Sequence[LintScene]) -> int:
    return sum(_scene_duration_ms(scene) for scene in scenes)


def _foia_slots(manifest: LintVoiceManifest) -> list:
    return [seg for seg in manifest.segments if seg.segment_kind == "FOIA_AUDIO_SLOT"]


def check_rule_01(
    scenes: Sequence[LintScene],
    voice: LintVoiceManifest,
) -> list[LintFinding]:
    """RULE_01: scene durations sum to voice total within tolerance; FOIA scenes match slots."""
    findings: list[LintFinding] = []

    ordered = sorted(scenes, key=lambda scene: (scene.start_ms, scene.scene_id))
    scene_sum_ms = _sum_scene_durations_ms(ordered)
    delta = abs(scene_sum_ms - voice.total_master_ms)
    if delta > RULE_01_TOLERANCE_MS:
        findings.append(
            LintFinding(
                rule_id="RULE_01",
                message=(
                    f"scene duration sum {scene_sum_ms} ms differs from "
                    f"total_master_ms {voice.total_master_ms} by {delta} ms "
                    f"(limit {RULE_01_TOLERANCE_MS} ms)"
                ),
                severity="error",
            )
        )

    if ordered:
        if ordered[0].start_ms != 0:
            findings.append(
                LintFinding(
                    rule_id="RULE_01",
                    message=f"timeline must start at 0 ms, got {ordered[0].start_ms}",
                    severity="error",
                )
            )
        timeline_end = ordered[-1].end_ms
        end_delta = abs(timeline_end - voice.total_master_ms)
        if end_delta > RULE_01_TOLERANCE_MS:
            findings.append(
                LintFinding(
                    rule_id="RULE_01",
                    message=(
                        f"final scene ends at {timeline_end} ms but total_master_ms is "
                        f"{voice.total_master_ms} ms (delta {end_delta} ms)"
                    ),
                    severity="error",
                )
            )

    foia_scenes = [scene for scene in ordered if scene.visual_engine in FOIA_VISUAL_ENGINES]
    foia_slots = _foia_slots(voice)

    if len(foia_scenes) != len(foia_slots):
        findings.append(
            LintFinding(
                rule_id="RULE_01",
                message=(
                    f"FOIA scene count {len(foia_scenes)} does not match "
                    f"FOIA_AUDIO_SLOT count {len(foia_slots)}"
                ),
                severity="error",
            )
        )

    slots_by_asset: dict[str, list] = {}
    for slot in foia_slots:
        asset = slot.foia_asset_id or ""
        slots_by_asset.setdefault(asset, []).append(slot)

    for scene in foia_scenes:
        asset = scene.foia_asset_id or ""
        candidate_slots = slots_by_asset.get(asset)
        if candidate_slots:
            match = next(
                (
                    slot
                    for slot in candidate_slots
                    if slot.start_ms == scene.start_ms and slot.end_ms == scene.end_ms
                ),
                None,
            )
            if match is None:
                findings.append(
                    LintFinding(
                        rule_id="RULE_01",
                        message=(
                            f"FOIA scene {scene.scene_id} ({scene.visual_engine}) "
                            f"interval [{scene.start_ms}, {scene.end_ms}) does not match "
                            f"any FOIA_AUDIO_SLOT for asset {asset!r}"
                        ),
                        severity="error",
                    )
                )
            continue

        match = next(
            (
                slot
                for slot in foia_slots
                if slot.start_ms == scene.start_ms and slot.end_ms == scene.end_ms
            ),
            None,
        )
        if match is None:
            findings.append(
                LintFinding(
                    rule_id="RULE_01",
                    message=(
                        f"FOIA scene {scene.scene_id} ({scene.visual_engine}) "
                        f"interval [{scene.start_ms}, {scene.end_ms}) is not aligned "
                        "to a FOIA_AUDIO_SLOT"
                    ),
                    severity="error",
                )
            )

    return findings


def check_rule_03(scenes: Sequence[LintScene]) -> list[LintFinding]:
    """RULE_03: long Flow beats must be split so bookend remainders stay >= 2.5s."""
    findings: list[LintFinding] = []

    for scene in scenes:
        if scene.visual_engine != "FLOW_HERO_VIDEO":
            continue
        duration_ms = _scene_duration_ms(scene)
        if duration_ms <= FLOW_BEAT_LONG_MS:
            continue

        flow_ms, code_ms = split_flow_beat_ms(duration_ms)
        if code_ms == 0:
            continue

        findings.append(
            LintFinding(
                rule_id="RULE_03",
                message=(
                    f"FLOW_HERO_VIDEO scene {scene.scene_id} is {duration_ms} ms; "
                    f"split required as {flow_ms} ms Flow + {code_ms} ms Code"
                ),
                severity="error",
                context={
                    "scene_id": scene.scene_id,
                    "duration_ms": duration_ms,
                    "proposed_flow_ms": flow_ms,
                    "proposed_code_ms": code_ms,
                },
            )
        )

    return findings