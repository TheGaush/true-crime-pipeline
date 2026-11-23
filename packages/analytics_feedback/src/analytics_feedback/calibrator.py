"""Bound calibration notes for topic choice and mid-roll pacing."""

from __future__ import annotations

import json
from pathlib import Path

SHIFT_CAP = 0.15


def calibrate(episodes: list[dict]) -> dict:
    if len(episodes) < 3:
        return {"adjustment": 0.0, "confidence": "insufficient_sample", "yellow_tags": [], "midroll": "hold", "thumbnails": []}
    yellow_tags: dict[str, int] = {}
    for episode in episodes:
        if episode.get("adsense_status") in {"limitedAds", "yellow_icon"}:
            for tag in episode.get("tags", []):
                yellow_tags[tag] = yellow_tags.get(tag, 0) + 1
    flagged = sorted(tag for tag, count in yellow_tags.items() if count >= 2)
    recent = episodes[-5:]
    dips = [episode for episode in recent if (episode.get("retention_min6_14_pct") or 100) < 50]
    shift = 0.0
    if flagged:
        shift -= 0.10
    if len(dips) >= 3:
        shift -= 0.05
    shift = max(-SHIFT_CAP, min(SHIFT_CAP, shift))
    ranks = {}
    for episode in episodes:
        name = episode.get("thumbnail_archetype")
        if name and episode.get("ctr_pct") is not None:
            ranks.setdefault(name, []).append(float(episode["ctr_pct"]))
    order = sorted(ranks, key=lambda name: sum(ranks[name]) / len(ranks[name]), reverse=True)
    return {
        "adjustment": shift,
        "confidence": "sample",
        "yellow_tags": flagged,
        "midroll": "tighten_pattern_interrupt" if len(dips) >= 3 else "hold",
        "thumbnails": order,
    }


def write_weights(path: str, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
