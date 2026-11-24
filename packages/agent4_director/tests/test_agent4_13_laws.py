"""Task 090 — Agent 4 conflict-free 13-Law property & adversarial suite."""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parents[1]
SRC = PKG_ROOT / "src"
sys.path.insert(0, str(SRC))

from agent4_director.pipeline import (  # noqa: E402
    RULE_COUNT,
    RULE_IDS,
    RULE_01_TOLERANCE_MS,
    STICKMAN_ENGINE,
    TRACKING_PROMPT_SAMPLE,
    VIOLENT_PROMPT_SAMPLE,
    Agent4DirectorService,
    collision_manifest_triple_fault,
    find_blocked_safety_terms,
    min_hold_duration_sec,
    split_flow_beat_ms,
)

PIPELINE_SOURCE = SRC / "agent4_director" / "pipeline.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(PIPELINE_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in _BANNED_IMPORTS


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_certify_passes_each_rule_case(rule_id: str) -> None:
    service = Agent4DirectorService()
    draft = service.rule_case(rule_id)
    result = service.certify(draft)
    remaining = {v.rule_id for v in result.lint.violations}
    assert rule_id not in remaining, result.lint.violations
    assert result.lint.passed_rule_count == RULE_COUNT


def test_rule_01_four_minute_foia_sums_within_tolerance() -> None:
    service = Agent4DirectorService()
    result = service.certify(service.rule_case("RULE_01"))
    assert result.ok
    scene_sum = sum(int(s["end_ms"]) - int(s["start_ms"]) for s in result.manifest.scenes)
    delta = abs(scene_sum - result.manifest.total_master_ms)
    assert delta <= RULE_01_TOLERANCE_MS


def test_collision_tracking_shot_allowed_violent_shot_blocked() -> None:
    assert find_blocked_safety_terms(TRACKING_PROMPT_SAMPLE) == ()
    assert "shot" in find_blocked_safety_terms(VIOLENT_PROMPT_SAMPLE)
    service = Agent4DirectorService()
    bad = {
        "total_master_ms": 18_400,
        "narration_version_sha256": hashlib.sha256(b"x").hexdigest(),
        "scenes": [
            {
                "scene_id": "h",
                "seq_index": 0,
                "act_number": 2,
                "visual_engine": "FLOW_HERO_VIDEO",
                "start_ms": 0,
                "end_ms": 9200,
                "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": VIOLENT_PROMPT_SAMPLE},
                "prompt_v2_safe": "Rain on windows.",
            },
            {
                "scene_id": "ok",
                "seq_index": 1,
                "act_number": 2,
                "visual_engine": "FLOW_HERO_VIDEO",
                "start_ms": 9200,
                "end_ms": 18_400,
                "emotional_peak_score": 0.9,
                "timeline_spec_json": {"prompt_mode": "TEXT_TO_VIDEO", "prompt_v1": TRACKING_PROMPT_SAMPLE},
                "prompt_v2_safe": "Rain on windows.",
            },
        ],
    }
    result = service.certify(bad)
    prompts = [
        str(s.get("timeline_spec_json", {}).get("prompt_v1", ""))
        for s in result.manifest.scenes
        if s.get("visual_engine") == "FLOW_HERO_VIDEO"
    ]
    assert any("tracking shot" in p.lower() for p in prompts)
    assert all("shot the victim" not in p.lower() for p in prompts)
    assert result.ok


def test_collision_9_2s_split_meets_headline_minimum() -> None:
    flow_ms, code_ms = split_flow_beat_ms(9200)
    assert flow_ms == 6000
    assert code_ms == 3200
    service = Agent4DirectorService()
    result = service.certify(service.rule_case("RULE_03"))
    code_scenes = [s for s in result.manifest.scenes if str(s["scene_id"]).endswith("_code")]
    assert code_scenes
    assert _scene_ms(code_scenes[0]) == 3200
    cards = result.manifest.callout_cards
    headline_cards = [c for c in cards if c.get("headline")]
    assert headline_cards
    for card in headline_cards:
        words = len(str(card["headline"]).split())
        assert float(card["duration_sec"]) + 1e-9 >= min_hold_duration_sec(words)


def _scene_ms(scene: dict) -> int:
    return int(scene["end_ms"]) - int(scene["start_ms"])


def test_collision_act2_keeps_two_peaks() -> None:
    service = Agent4DirectorService()
    result = service.certify(service.rule_case("RULE_06"))
    heroes = [s for s in result.manifest.scenes if s.get("visual_engine") == "FLOW_HERO_VIDEO"]
    act2_heroes = [s for s in heroes if int(s.get("act_number", 0)) == 2]
    ranked = sorted(act2_heroes, key=lambda s: -float(s.get("emotional_peak_score", 0)))
    assert len(ranked) >= 2
    assert ranked[0]["scene_id"] in {s["scene_id"] for s in heroes}
    assert ranked[1]["scene_id"] in {s["scene_id"] for s in heroes}
    stickmen = [s for s in result.manifest.scenes if s.get("visual_engine") == STICKMAN_ENGINE]
    assert stickmen


def test_collision_fallback_not_neighbor_engine() -> None:
    service = Agent4DirectorService()
    result = service.certify(service.rule_case("RULE_04"))
    ordered = sorted(result.manifest.scenes, key=lambda s: int(s["seq_index"]))
    hero = next(s for s in ordered if s.get("visual_engine") == "FLOW_HERO_VIDEO")
    idx = ordered.index(hero)
    fb = hero["fallback_spec_json"]
    assert fb is not None
    eng = fb["engine"]
    if idx > 0:
        assert eng != ordered[idx - 1]["visual_engine"]
    if idx + 1 < len(ordered):
        assert eng != ordered[idx + 1]["visual_engine"]


def test_collision_911_slot_snaps_spine_to_255() -> None:
    service = Agent4DirectorService()
    result = service.certify(service.rule_case("RULE_05"))
    spine = next(s for s in result.manifest.scenes if s.get("motif_component") == "CaseBoardSpine")
    assert int(spine["start_ms"]) == 255_000


def test_collision_triple_fault_manifest_cleans() -> None:
    service = Agent4DirectorService()
    result = service.certify(collision_manifest_triple_fault())
    assert result.ok
    assert result.lint.violations == []
    assert result.lint.rules_summary == f"{RULE_COUNT}/{RULE_COUNT}"


def test_full_certify_reports_thirteen_of_thirteen() -> None:
    service = Agent4DirectorService()
    result = service.certify(service.rule_case("RULE_03"))
    assert result.lint.passed_rule_count == RULE_COUNT
    assert result.ok