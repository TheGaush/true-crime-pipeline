"""LAW_06: L-cut lead-ins, music ducking, twist pads, and merge anti-pumping."""

from __future__ import annotations

from agent4_director.rules.law_06_audio import (
    ADJACENT_FOIA_MERGE_GAP_MS,
    L_CUT_MAX_MS,
    L_CUT_MIN_MS,
    Law06AudioGraph,
    Law06FoiaScene,
    Law06FoiaSlot,
    Law06MusicDuck,
    Law06TwistPad,
    clamp_l_cut_start,
    expected_foia_slot_bounds,
    lead_in_duck_window,
    merge_foia_duck_regions,
    validate_law_06,
)


def _foia_scene(
    scene_id: str,
    visual_start: int,
    duration: int,
    *,
    l_cut_ms: int | None,
    asset: str = "foia_a",
) -> Law06FoiaScene:
    return Law06FoiaScene(
        scene_id=scene_id,
        visual_engine="FOIA_REAL_FOOTAGE",
        visual_start_ms=visual_start,
        visual_end_ms=visual_start + duration,
        foia_asset_id=asset,
        l_cut_ms=l_cut_ms,
    )


def _slot_for_scene(scene: Law06FoiaScene) -> Law06FoiaSlot:
    assert scene.l_cut_ms is not None
    start, end = expected_foia_slot_bounds(
        scene.visual_start_ms,
        scene.visual_end_ms,
        scene.l_cut_ms,
    )
    return Law06FoiaSlot(start_ms=start, end_ms=end, foia_asset_id=scene.foia_asset_id)


def _duck_lead_in(scene: Law06FoiaScene) -> Law06MusicDuck:
    assert scene.l_cut_ms is not None
    start, end = lead_in_duck_window(scene.visual_start_ms, scene.l_cut_ms)
    return Law06MusicDuck(start_ms=start, end_ms=end)


def _twist_for_duck(scene: Law06FoiaScene, pad_id: str = "tw1") -> Law06TwistPad:
    assert scene.l_cut_ms is not None
    start, end = lead_in_duck_window(scene.visual_start_ms, scene.l_cut_ms)
    mid = (start + end) // 2
    return Law06TwistPad(start_ms=start, end_ms=mid, pad_id=pad_id)


def _graph_for_scenes(scenes: list[Law06FoiaScene]) -> Law06AudioGraph:
    ducks = [_duck_lead_in(s) for s in scenes if s.l_cut_ms is not None]
    return Law06AudioGraph(
        foia_scenes=scenes,
        foia_slots=[_slot_for_scene(s) for s in scenes if s.l_cut_ms is not None],
        twist_pads=[_twist_for_duck(s, f"tw_{s.scene_id}") for s in scenes if s.l_cut_ms],
        music_ducks=ducks,
    )


def test_clamp_l_cut_at_timeline_origin() -> None:
    assert clamp_l_cut_start(500, 800) == 0


def test_expected_slot_includes_l_cut_prelap() -> None:
    assert expected_foia_slot_bounds(10_000, 22_000, 800) == (9200, 22_000)


def test_l_cut_min_max_constants() -> None:
    assert L_CUT_MIN_MS == 600
    assert L_CUT_MAX_MS == 1_000
    assert ADJACENT_FOIA_MERGE_GAP_MS == 500


def test_valid_single_foia_passes() -> None:
    scene = _foia_scene("f1", 10_000, 12_000, l_cut_ms=800)
    graph = _graph_for_scenes([scene])
    result = validate_law_06(graph)
    assert result.ok


def test_missing_l_cut_fails() -> None:
    scene = _foia_scene("f1", 10_000, 12_000, l_cut_ms=None)
    graph = Law06AudioGraph(
        foia_scenes=[scene],
        foia_slots=[],
        twist_pads=[],
        music_ducks=[],
    )
    result = validate_law_06(graph)
    assert not result.ok
    assert any(v.code == "MISSING_L_CUT" for v in result.violations)


def test_l_cut_out_of_range_fails() -> None:
    scene = _foia_scene("f1", 10_000, 12_000, l_cut_ms=500)
    graph = _graph_for_scenes([scene])
    result = validate_law_06(graph)
    assert any(v.code == "L_CUT_OUT_OF_RANGE" for v in result.violations)


def test_foia_slot_mismatch_fails() -> None:
    scene = _foia_scene("f1", 10_000, 22_000, l_cut_ms=800)
    bad_slot = Law06FoiaSlot(
        start_ms=10_000,
        end_ms=22_000,
        foia_asset_id="foia_a",
    )
    graph = Law06AudioGraph(
        foia_scenes=[scene],
        foia_slots=[bad_slot],
        twist_pads=[_twist_for_duck(scene)],
        music_ducks=[_duck_lead_in(scene)],
    )
    result = validate_law_06(graph)
    assert any(v.code == "FOIA_SLOT_MISMATCH" for v in result.violations)


def test_missing_music_duck_fails() -> None:
    scene = _foia_scene("f1", 10_000, 22_000, l_cut_ms=800)
    graph = Law06AudioGraph(
        foia_scenes=[scene],
        foia_slots=[_slot_for_scene(scene)],
        twist_pads=[_twist_for_duck(scene)],
        music_ducks=[],
    )
    result = validate_law_06(graph)
    assert any(v.code == "MUSIC_DUCK_MISMATCH" for v in result.violations)


def test_missing_twist_pad_fails() -> None:
    scene = _foia_scene("f1", 10_000, 22_000, l_cut_ms=800)
    graph = Law06AudioGraph(
        foia_scenes=[scene],
        foia_slots=[_slot_for_scene(scene)],
        twist_pads=[],
        music_ducks=[_duck_lead_in(scene)],
    )
    result = validate_law_06(graph)
    assert any(v.code == "TWIST_PAD_NOT_ALIGNED" for v in result.violations)


def test_merge_duck_regions_when_gap_under_500ms() -> None:
    scenes = [
        _foia_scene("f1", 10_000, 5_000, l_cut_ms=800),
        _foia_scene("f2", 15_200, 8_000, l_cut_ms=600),
    ]
    regions = merge_foia_duck_regions(scenes)
    assert len(regions) == 1
    assert regions[0] == (9200, 23_200)


def test_merged_foia_requires_continuous_duck_hold() -> None:
    s1 = _foia_scene("f1", 10_000, 5_000, l_cut_ms=800)
    s2 = _foia_scene("f2", 15_200, 8_000, l_cut_ms=600)
    merged_hold = Law06MusicDuck(
        start_ms=10_000,
        end_ms=23_200,
        from_lufs=-36.0,
        to_lufs=-36.0,
    )
    graph = Law06AudioGraph(
        foia_scenes=[s1, s2],
        foia_slots=[_slot_for_scene(s1), _slot_for_scene(s2)],
        twist_pads=[_twist_for_duck(s1, "t1"), _twist_for_duck(s2, "t2")],
        music_ducks=[_duck_lead_in(s1), merged_hold],
    )
    result = validate_law_06(graph)
    assert result.ok


def test_merged_foia_pumping_without_hold_fails() -> None:
    s1 = _foia_scene("f1", 10_000, 5_000, l_cut_ms=800)
    s2 = _foia_scene("f2", 15_200, 8_000, l_cut_ms=600)
    graph = Law06AudioGraph(
        foia_scenes=[s1, s2],
        foia_slots=[_slot_for_scene(s1), _slot_for_scene(s2)],
        twist_pads=[_twist_for_duck(s1), _twist_for_duck(s2)],
        music_ducks=[_duck_lead_in(s1), _duck_lead_in(s2)],
    )
    result = validate_law_06(graph)
    assert any(v.code == "DUCK_PUMPING" for v in result.violations)


def test_audio_evidence_card_engine_supported() -> None:
    scene = Law06FoiaScene(
        scene_id="card1",
        visual_engine="AUDIO_EVIDENCE_CARD",
        visual_start_ms=5_000,
        visual_end_ms=11_000,
        foia_asset_id="911_a",
        l_cut_ms=700,
    )
    graph = Law06AudioGraph(
        foia_scenes=[scene],
        foia_slots=[_slot_for_scene(scene)],
        twist_pads=[_twist_for_duck(scene)],
        music_ducks=[_duck_lead_in(scene)],
    )
    assert validate_law_06(graph).ok