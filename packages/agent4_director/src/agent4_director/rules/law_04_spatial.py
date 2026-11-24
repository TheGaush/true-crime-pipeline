"""LAW_04: pre-locked spatial anchors and pursuit travel_axis continuity (Task 083)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

LAW_ID = "LAW_04"
STILL_ENGINE = "STILL_2K_PANZOOM"
MOVEMENT_AXES = frozenset({"L_TO_R", "R_TO_L"})


@dataclass(frozen=True, slots=True)
class Law04Violation:
    code: str
    message: str
    law_id: str = LAW_ID
    scene_id: str | None = None
    anchor_id: str | None = None


@dataclass(slots=True)
class Law04Result:
    violations: list[Law04Violation] = field(default_factory=list)
    missing_anchor_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations and not self.missing_anchor_ids


def _anchor_index(
    spatial_anchors: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    return {str(a["anchor_id"]): a for a in spatial_anchors}


def _still_index(
    still_assets: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    return {str(s["still_2k_id"]): s for s in still_assets}


def _scene_anchor_id(scene: Mapping[str, Any]) -> str | None:
    tl = scene.get("timeline_spec_json") or {}
    anchor = tl.get("anchor_id")
    if anchor:
        return str(anchor)
    fb = scene.get("fallback_spec_json") or {}
    if scene.get("visual_engine") == STILL_ENGINE:
        fb_anchor = fb.get("anchor_id")
        if fb_anchor:
            return str(fb_anchor)
    return None


def _scene_travel_axis(scene: Mapping[str, Any]) -> str | None:
    tl = scene.get("timeline_spec_json") or {}
    axis = tl.get("travel_axis")
    return str(axis) if axis else None


def _is_pursuit_scene(scene: Mapping[str, Any]) -> bool:
    axis = _scene_travel_axis(scene)
    if axis in MOVEMENT_AXES:
        return True
    tl = scene.get("timeline_spec_json") or {}
    return bool(tl.get("pursuit_scene"))


def _record_missing_anchor(result: Law04Result, anchor_id: str, scene_id: str) -> None:
    if anchor_id not in result.missing_anchor_ids:
        result.missing_anchor_ids.append(anchor_id)
    result.violations.append(
        Law04Violation(
            code="MISSING_ANCHOR",
            message=f"spatial anchor {anchor_id} is not pre-locked",
            scene_id=scene_id,
            anchor_id=anchor_id,
        )
    )


def _validate_still_clue(
    scene: Mapping[str, Any],
    *,
    anchors: dict[str, Mapping[str, Any]],
    stills: dict[str, Mapping[str, Any]],
    result: Law04Result,
) -> None:
    scene_id = str(scene.get("scene_id", ""))
    anchor_id = _scene_anchor_id(scene)
    if not anchor_id:
        result.violations.append(
            Law04Violation(
                code="MISSING_ANCHOR_REF",
                message="STILL_2K_PANZOOM scene requires anchor_id",
                scene_id=scene_id,
            )
        )
        return

    anchor = anchors.get(anchor_id)
    if anchor is None:
        _record_missing_anchor(result, anchor_id, scene_id)
        return

    if anchor.get("lock_status") != "LOCKED":
        result.violations.append(
            Law04Violation(
                code="ANCHOR_NOT_LOCKED",
                message=f"anchor {anchor_id} lock_status must be LOCKED",
                scene_id=scene_id,
                anchor_id=anchor_id,
            )
        )

    span_cols = anchor.get("span_cols")
    span_rows = anchor.get("span_rows")
    if span_cols is None or span_rows is None:
        result.violations.append(
            Law04Violation(
                code="ANCHOR_SPAN_MISSING",
                message=f"anchor {anchor_id} requires span_cols and span_rows",
                scene_id=scene_id,
                anchor_id=anchor_id,
            )
        )
    elif float(span_cols) <= 0 or float(span_rows) <= 0:
        result.violations.append(
            Law04Violation(
                code="ANCHOR_SPAN_INVALID",
                message=f"anchor {anchor_id} span_cols and span_rows must be positive",
                scene_id=scene_id,
                anchor_id=anchor_id,
            )
        )

    still_id = str(anchor.get("still_2k_id", ""))
    still = stills.get(still_id)
    if still is None:
        result.violations.append(
            Law04Violation(
                code="MISSING_STILL_ASSET",
                message=f"anchor {anchor_id} references unknown still_2k_id {still_id}",
                scene_id=scene_id,
                anchor_id=anchor_id,
            )
        )
        return

    illustrative = still.get("is_illustrative_reconstruction")
    if illustrative not in (1, True):
        result.violations.append(
            Law04Violation(
                code="STILL_NOT_ILLUSTRATIVE",
                message=f"still {still_id} must have is_illustrative_reconstruction=1",
                scene_id=scene_id,
                anchor_id=anchor_id,
            )
        )


def _validate_travel_axis_continuity(
    scenes: Sequence[Mapping[str, Any]],
    result: Law04Result,
) -> None:
    ordered = sorted(scenes, key=lambda s: int(s.get("seq_index", 0)))
    prev_pursuit_id: str | None = None
    prev_axis: str | None = None
    prev_was_pursuit = False

    for scene in ordered:
        if not _is_pursuit_scene(scene):
            prev_was_pursuit = False
            continue

        axis = _scene_travel_axis(scene)
        scene_id = str(scene.get("scene_id", ""))
        if axis not in MOVEMENT_AXES:
            result.violations.append(
                Law04Violation(
                    code="PURSUIT_AXIS_MISSING",
                    message="pursuit scene requires travel_axis L_TO_R or R_TO_L",
                    scene_id=scene_id,
                )
            )
            prev_was_pursuit = False
            continue

        if prev_was_pursuit and prev_axis is not None and prev_axis != axis:
            result.violations.append(
                Law04Violation(
                    code="TRAVEL_AXIS_FLIP",
                    message=(
                        f"consecutive pursuit scenes {prev_pursuit_id} ({prev_axis}) "
                        f"then {scene_id} ({axis}) flip travel_axis"
                    ),
                    scene_id=scene_id,
                )
            )

        prev_was_pursuit = True
        prev_pursuit_id = scene_id
        prev_axis = axis


def validate_law_04(
    scenes: Sequence[Mapping[str, Any]],
    spatial_anchors: Sequence[Mapping[str, Any]],
    still_assets: Sequence[Mapping[str, Any]],
) -> Law04Result:
    """Validate LAW_04 spatial truth and screen-axis continuity."""
    result = Law04Result()
    anchors = _anchor_index(spatial_anchors)
    stills = _still_index(still_assets)

    for scene in scenes:
        if scene.get("visual_engine") != STILL_ENGINE:
            continue
        _validate_still_clue(scene, anchors=anchors, stills=stills, result=result)

    _validate_travel_axis_continuity(scenes, result)
    return result