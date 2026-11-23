"""Law 6 L-cut schedule for the four documentary audio tracks."""

from __future__ import annotations

from dataclasses import dataclass

EVIDENCE = {"FOIA_REAL_FOOTAGE", "AUDIO_EVIDENCE_CARD"}


@dataclass(frozen=True)
class MixPlan:
    total_master_timeline_ms: int
    track1: tuple[dict, ...]
    track2: tuple[dict, ...]
    track3: dict
    track4: tuple[dict, ...]


def schedule(scenes: list[dict], cues: list[dict] | None = None, l_cut_ms: int = 800) -> MixPlan:
    if not 600 <= l_cut_ms <= 1000:
        raise ValueError("L-cut must sit between 600 and 1000 ms")
    cursor = 0
    narration = []
    evidence = []
    for scene in scenes:
        start = cursor
        duration = int(scene["duration_ms"])
        end = start + duration
        engine = scene.get("visual_engine", "CODE_STICKMAN")
        if engine in EVIDENCE:
            evidence.append({"scene_id": scene["scene_id"], "start_ms": max(0, start - l_cut_ms), "end_ms": end, "mute_track1": True})
        else:
            narration.append({"scene_id": scene["scene_id"], "start_ms": start, "end_ms": end, "gain": 1.0})
        cursor = end
    placed = []
    for cue in cues or []:
        placed.append({"cue_id": cue["cue_id"], "start_ms": int(cue["start_ms"]), "sample_rate_hz": 48000})
    total = sum(int(scene["duration_ms"]) for scene in scenes)
    if abs(total - cursor) > 1:
        raise ValueError("timeline drifted")
    return MixPlan(total, tuple(narration), tuple(evidence), {"start_ms": 0, "end_ms": total, "duck_during": [row["scene_id"] for row in evidence]}, tuple(placed))
