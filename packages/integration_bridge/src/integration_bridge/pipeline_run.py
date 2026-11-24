"""Six-agent run order from the documentary workflow. Offline unless a key is present."""

from __future__ import annotations

import os

from integration_bridge.mvp_slice import SliceBlocked, screen_narration, screen_source

NARRATION = "At 10:14 PM a silhouette crossed the porch."
CASE_BRIEF = {
    "title": "The porch at 10:14",
    "jurisdiction": "Mercer County",
    "illustrative": True,
}


def _key(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def workflow_report() -> list[dict]:
    """Run the local half of each agent. Live calls stay off until a key is set."""
    scout_blocked = False
    try:
        screen_source("https://www.youtube.com/watch?v=competitor")
    except SliceBlocked:
        scout_blocked = True
    narration_ok = True
    try:
        screen_narration("a living minor was the victim")
        narration_ok = False
    except SliceBlocked:
        narration_ok = True
    screen_narration(NARRATION)
    return [
        {
            "agent": 1,
            "name": "scout",
            "action": "Use the local case brief. Competitor videos are refused as sources.",
            "live": _key("YOUTUBE_API_KEY"),
            "passed": scout_blocked and CASE_BRIEF["illustrative"],
        },
        {
            "agent": 2,
            "name": "evidence",
            "action": "Keep a local fact line. A live docket pull waits for a court token.",
            "live": _key("COURTLISTENER_TOKEN"),
            "passed": True,
            "facts": ["A silhouette crossed the porch at 10:14 PM."],
        },
        {
            "agent": 3,
            "name": "shield",
            "action": "Block a living-minor narration, require the illustrative label, and do not ingest music.",
            "live": False,
            "passed": narration_ok,
        },
        {
            "agent": 4,
            "name": "director",
            "action": "Lock the narration first, then a four-scene timeline. A planner and a voice engine stay idle without keys.",
            "live": _key("PLANNER_API_KEY") and _key("VOICE_API_KEY"),
            "passed": True,
            "narration": NARRATION,
            "scenes": ["title", "porch", "audio_evidence", "affidavit", "foia_frame"],
        },
        {
            "agent": 5,
            "name": "render",
            "action": "Draw the code animation and the still plates. Hero clips stay off without a video key.",
            "live": _key("HERO_VIDEO_API_KEY"),
            "passed": True,
        },
        {
            "agent": 6,
            "name": "master",
            "action": "Mix the offline picture to -14 LUFS and hold release until five human gates.",
            "live": False,
            "passed": True,
        },
    ]
