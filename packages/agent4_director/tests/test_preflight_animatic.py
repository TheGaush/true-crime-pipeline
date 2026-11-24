"""Pre-flight 480p animatic dry-run planner tests (Task 089)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent4_director.preflight_animatic import (
    ANIMATIC_HEIGHT,
    ANIMATIC_WIDTH,
    PLAN_TIME_BUDGET_SEC,
    VOICE_KIND_ORDER,
    assert_voice_concat_order,
    plan_preflight_animatic_dry_run,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PACK = REPO_ROOT / "fixtures/golden_manifests/ep_golden_01_20min/pack.json"


@pytest.fixture(scope="module")
def golden_pack() -> dict:
    return json.loads(GOLDEN_PACK.read_text(encoding="utf-8"))


def test_golden_20min_plan_under_15s_and_zero_flow_spend(golden_pack: dict) -> None:
    plan = plan_preflight_animatic_dry_run(golden_pack)
    assert plan.elapsed_sec < PLAN_TIME_BUDGET_SEC
    assert plan.flow_spend_micro_usd == 0
    assert plan.ffmpeg.flow_spend_micro_usd == 0
    assert plan.total_master_ms == 1_200_000
    assert len(plan.scenes) == len(golden_pack["timeline_spec"]["scenes"])


def test_diagnostic_frames_are_854x480_with_required_overlays(golden_pack: dict) -> None:
    plan = plan_preflight_animatic_dry_run(golden_pack)
    for scene in plan.scenes:
        frame = scene.frame
        assert frame.width == ANIMATIC_WIDTH
        assert frame.height == ANIMATIC_HEIGHT
        assert frame.engine
        assert frame.safe_zone_guide.style == "dashed"
        assert frame.safe_zone_guide.width > 0
        assert set(frame.labels) >= {
            "engine",
            "cost",
            "open_loop",
            "safe_zone_guide",
            "zoom_box",
        }


def test_global_voice_concat_order_narration_foia_twist_pad(golden_pack: dict) -> None:
    plan = plan_preflight_animatic_dry_run(golden_pack)
    kinds = [clip.segment_kind for clip in plan.global_voice_concat]
    assert kinds.count("NARRATION") == 33
    assert kinds.count("FOIA_AUDIO_SLOT") == 3
    assert kinds.count("TWIST_PAD") == 3
    assert kinds == sorted(
        kinds,
        key=lambda kind: (VOICE_KIND_ORDER.index(kind),),
    )
    last_rank = -1
    for clip in plan.global_voice_concat:
        rank = VOICE_KIND_ORDER.index(clip.segment_kind)
        assert rank >= last_rank
        last_rank = rank
    assert_voice_concat_order(plan.global_voice_concat)


def test_flow_hero_frames_carry_cost_and_fallback_zoom(golden_pack: dict) -> None:
    plan = plan_preflight_animatic_dry_run(golden_pack)
    heroes = [s for s in plan.scenes if s.frame.engine == "FLOW_HERO_VIDEO"]
    assert heroes
    for scene in heroes:
        assert scene.frame.cost_micro_usd == 800_000
        assert scene.frame.zoom_box is not None
        assert scene.frame.zoom_box.grid_cell


def test_per_scene_voice_slices_respect_concat_priority(golden_pack: dict) -> None:
    plan = plan_preflight_animatic_dry_run(golden_pack)
    for scene in plan.scenes:
        if not scene.voice_concat:
            continue
        assert_voice_concat_order(scene.voice_concat)


def test_ffmpeg_plan_is_dry_run_without_mp4_decode(golden_pack: dict) -> None:
    plan = plan_preflight_animatic_dry_run(golden_pack)
    payload = plan.as_dict()
    assert payload["ffmpeg"]["dry_run"] is True
    assert payload["ffmpeg"]["flow_spend_micro_usd"] == 0
    assert "854x480" in payload["ffmpeg"]["output_mp4"]
    assert payload["ffmpeg"]["ffmpeg_concat_lines"]