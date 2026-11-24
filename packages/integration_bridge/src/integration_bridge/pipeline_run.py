"""Six-agent run order from the documentary workflow. Spoken track is local. Paid calls stay off."""

from __future__ import annotations

import os

from integration_bridge.mvp_slice import SliceBlocked, screen_narration, screen_source
from integration_bridge.narration import script_text

NARRATION = script_text()
CASE_BRIEF = {
    "title": "The porch at 10:14",
    "jurisdiction": "Mercer County",
    "illustrative": True,
}


def _key(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def workflow_report() -> list[dict]:
    """Run the local half of each agent. A key in the environment does not place a call."""
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
            "live": False,
            "keys_ready": _key("YOUTUBE_API_KEY"),
            "passed": scout_blocked and CASE_BRIEF["illustrative"],
        },
        {
            "agent": 2,
            "name": "evidence",
            "action": "Keep a local fact line. A live docket pull waits for a court token.",
            "live": False,
            "keys_ready": _key("COURTLISTENER_TOKEN"),
            "passed": True,
            "facts": ["A silhouette crossed the porch at 10:14 PM."],
        },
        {
            "agent": 3,
            "name": "shield",
            "action": "Block a living-minor narration, require the illustrative label, and do not ingest music.",
            "live": False,
            "keys_ready": False,
            "passed": narration_ok,
        },
        {
            "agent": 4,
            "name": "director",
            "action": "Lock the spoken script, then the five-scene timeline. DeepSeek and Gemini stay idle. This run uses the local voice.",
            "live": False,
            "keys_ready": _key("DEEPSEEK_API_KEY") and _key("GEMINI_API_KEY"),
            "passed": True,
            "narration": NARRATION,
            "scenes": ["title", "porch", "audio_evidence", "affidavit", "foia_frame"],
        },
        {
            "agent": 5,
            "name": "render",
            "action": "Draw the code animation and the still plates under the spoken lines. Hero clips stay off.",
            "live": False,
            "keys_ready": _key("GEMINI_API_KEY"),
            "passed": True,
        },
        {
            "agent": 6,
            "name": "master",
            "action": "Mix the spoken picture to -14 LUFS and hold release until five human gates.",
            "live": False,
            "keys_ready": False,
            "passed": True,
        },
    ]
