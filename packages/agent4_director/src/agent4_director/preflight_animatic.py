"""Pre-flight 480p animatic dry-run planner (Task 089).

Plans one 854×480 diagnostic frame per timeline scene plus an FFmpeg concat
script for segmented voice audio. Does not invoke FFmpeg or spend Flow credits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

ANIMATIC_WIDTH = 854
ANIMATIC_HEIGHT = 480
PLATE_WIDTH = 2560
PLATE_HEIGHT = 1440
FPS_DEFAULT = 30
PLAN_TIME_BUDGET_SEC = 15.0

VOICE_KIND_ORDER = ("NARRATION", "FOIA_AUDIO_SLOT", "TWIST_PAD")

SAFE_ZONE_INSET_PX = 48


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int
    style: str = "solid"

    def as_dict(self) -> dict[str, int | str]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "style": self.style,
        }


@dataclass(frozen=True, slots=True)
class ZoomBoxOverlay:
    """2K illustrative crop projected into animatic pixel space."""

    anchor_id: str | None
    grid_cell: str | None
    rect: Rect

    def as_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "grid_cell": self.grid_cell,
            "rect": self.rect.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticFrameSpec:
    scene_id: str
    width: int
    height: int
    engine: str
    cost_usd: float
    cost_micro_usd: int
    open_loop: bool
    open_loop_label: str
    safe_zone_guide: Rect
    zoom_box: ZoomBoxOverlay | None
    labels: tuple[str, ...] = (
        "engine",
        "cost",
        "open_loop",
        "safe_zone_guide",
        "zoom_box",
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "width": self.width,
            "height": self.height,
            "engine": self.engine,
            "cost_usd": self.cost_usd,
            "cost_micro_usd": self.cost_micro_usd,
            "open_loop": self.open_loop,
            "open_loop_label": self.open_loop_label,
            "safe_zone_guide": self.safe_zone_guide.as_dict(),
            "zoom_box": None if self.zoom_box is None else self.zoom_box.as_dict(),
            "diagnostic_png": (
                f"artifacts/preflight/{self.scene_id}_854x480_diag.png"
            ),
            "overlay_fields": list(self.labels),
        }


@dataclass(frozen=True, slots=True)
class VoiceConcatClip:
    segment_id: str
    segment_kind: str
    start_ms: int
    end_ms: int
    audio_ref: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "segment_kind": self.segment_kind,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "audio_ref": self.audio_ref,
        }


@dataclass(frozen=True, slots=True)
class SceneAnimaticSlice:
    scene_id: str
    seq_index: int
    start_ms: int
    end_ms: int
    duration_ms: int
    frame: DiagnosticFrameSpec
    voice_concat: tuple[VoiceConcatClip, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "seq_index": self.seq_index,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "frame": self.frame.as_dict(),
            "voice_concat": [clip.as_dict() for clip in self.voice_concat],
        }


@dataclass(frozen=True, slots=True)
class FfmpegDryRunScript:
    """Concat demuxer lines only; execution is out of scope for dry-run."""

    output_mp4: str
    frame_list_path: str
    audio_concat_path: str
    video_filter: str
    flow_spend_micro_usd: int
    lines: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_mp4": self.output_mp4,
            "frame_list_path": self.frame_list_path,
            "audio_concat_path": self.audio_concat_path,
            "video_filter": self.video_filter,
            "flow_spend_micro_usd": self.flow_spend_micro_usd,
            "ffmpeg_concat_lines": list(self.lines),
            "dry_run": True,
        }


@dataclass(frozen=True, slots=True)
class PreflightAnimaticPlan:
    episode_id: str
    total_master_ms: int
    width: int
    height: int
    elapsed_sec: float
    flow_spend_micro_usd: int
    scenes: tuple[SceneAnimaticSlice, ...]
    global_voice_concat: tuple[VoiceConcatClip, ...]
    ffmpeg: FfmpegDryRunScript

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "total_master_ms": self.total_master_ms,
            "width": self.width,
            "height": self.height,
            "elapsed_sec": self.elapsed_sec,
            "flow_spend_micro_usd": self.flow_spend_micro_usd,
            "scene_count": len(self.scenes),
            "scenes": [scene.as_dict() for scene in self.scenes],
            "global_voice_concat": [clip.as_dict() for clip in self.global_voice_concat],
            "ffmpeg": self.ffmpeg.as_dict(),
        }


def _safe_zone_rect() -> Rect:
    inset = SAFE_ZONE_INSET_PX
    return Rect(
        x=inset,
        y=inset,
        width=ANIMATIC_WIDTH - 2 * inset,
        height=ANIMATIC_HEIGHT - 2 * inset,
        style="dashed",
    )


def _scale_to_animatic(x_px: int, y_px: int, span_cols: float, span_rows: float) -> Rect:
    """Project a 2K plate focal point into animatic coordinates."""
    sx = ANIMATIC_WIDTH / PLATE_WIDTH
    sy = ANIMATIC_HEIGHT / PLATE_HEIGHT
    cx = int(round(x_px * sx))
    cy = int(round(y_px * sy))
    half_w = max(12, int(round((PLATE_WIDTH / max(span_cols, 0.5)) * sx / 6)))
    half_h = max(12, int(round((PLATE_HEIGHT / max(span_rows, 0.5)) * sy / 6)))
    x0 = max(0, cx - half_w)
    y0 = max(0, cy - half_h)
    w = min(ANIMATIC_WIDTH - x0, half_w * 2)
    h = min(ANIMATIC_HEIGHT - y0, half_h * 2)
    return Rect(x=x0, y=y0, width=w, height=h, style="solid")


def _open_loop_label(scene_plan: Mapping[str, Any] | None) -> tuple[bool, str]:
    if scene_plan is None:
        return False, ""
    narration = str(scene_plan.get("approved_narration_text") or "").strip()
    story = str(scene_plan.get("story_purpose") or "").strip()
    if narration.endswith("?"):
        return True, narration
    if "?" in story:
        return True, story.split("?", 1)[0].strip() + "?"
    if story:
        return True, story[:120]
    return False, ""


def _scene_cost_micro(
    engine: str,
    scene_id: str,
    flow_by_scene: Mapping[str, Mapping[str, Any]],
) -> int:
    if engine != "FLOW_HERO_VIDEO":
        return 0
    card = flow_by_scene.get(scene_id)
    if card is None:
        return 0
    return int(card.get("estimated_micro_usd") or 0)


def _resolve_zoom_box(
    engine: str,
    scene_id: str,
    flow_by_scene: Mapping[str, Mapping[str, Any]],
    anchors_by_id: Mapping[str, Mapping[str, Any]],
    anchors_by_still: Mapping[str, Mapping[str, Any]],
) -> ZoomBoxOverlay | None:
    anchor: Mapping[str, Any] | None = None
    card = flow_by_scene.get(scene_id)
    if card is not None:
        fallback = card.get("fallback_spec_json") or {}
        anchor_id = fallback.get("anchor_id")
        if anchor_id:
            anchor = anchors_by_id.get(str(anchor_id))
        elif fallback.get("still_2k_id"):
            anchor = anchors_by_still.get(str(fallback["still_2k_id"]))
    if anchor is None and engine == "STILL_2K_PANZOOM":
        # Golden packs align the first locked anchor per illustrative still.
        for row in anchors_by_still.values():
            anchor = row
            break
    if anchor is None:
        return None
    rect = _scale_to_animatic(
        int(anchor.get("x_px") or 0),
        int(anchor.get("y_px") or 0),
        float(anchor.get("span_cols") or 1.0),
        float(anchor.get("span_rows") or 1.0),
    )
    return ZoomBoxOverlay(
        anchor_id=str(anchor.get("anchor_id")),
        grid_cell=str(anchor.get("grid_cell")) if anchor.get("grid_cell") else None,
        rect=rect,
    )


def _voice_ref(segment: Mapping[str, Any]) -> str | None:
    audio_path = segment.get("audio_path")
    if audio_path:
        return str(audio_path)
    foia = segment.get("foia_asset_id")
    if foia:
        return f"foia://{foia}"
    return None


def _sort_voice_clips(clips: Sequence[VoiceConcatClip]) -> tuple[VoiceConcatClip, ...]:
    order = {kind: index for index, kind in enumerate(VOICE_KIND_ORDER)}

    def key(clip: VoiceConcatClip) -> tuple[int, int, str]:
        return (order.get(clip.segment_kind, 99), clip.start_ms, clip.segment_id)

    return tuple(sorted(clips, key=key))


def _collect_overlapping_voice(
    start_ms: int,
    end_ms: int,
    segments: Sequence[Mapping[str, Any]],
) -> tuple[VoiceConcatClip, ...]:
    clips: list[VoiceConcatClip] = []
    for segment in segments:
        seg_start = int(segment["start_ms"])
        seg_end = int(segment["end_ms"])
        if seg_start >= end_ms or seg_end <= start_ms:
            continue
        clips.append(
            VoiceConcatClip(
                segment_id=str(segment["segment_id"]),
                segment_kind=str(segment["segment_kind"]),
                start_ms=seg_start,
                end_ms=seg_end,
                audio_ref=_voice_ref(segment),
            )
        )
    return _sort_voice_clips(clips)


def _global_voice_concat(segments: Sequence[Mapping[str, Any]]) -> tuple[VoiceConcatClip, ...]:
    clips = [
        VoiceConcatClip(
            segment_id=str(segment["segment_id"]),
            segment_kind=str(segment["segment_kind"]),
            start_ms=int(segment["start_ms"]),
            end_ms=int(segment["end_ms"]),
            audio_ref=_voice_ref(segment),
        )
        for segment in segments
    ]
    return _sort_voice_clips(clips)


def _build_ffmpeg_script(
    episode_id: str,
    slices: Sequence[SceneAnimaticSlice],
    global_voice: Sequence[VoiceConcatClip],
) -> FfmpegDryRunScript:
    lines: list[str] = []
    for clip in global_voice:
        ref = clip.audio_ref or f"silence://{clip.segment_id}"
        lines.append(f"file '{ref}'")
    filter_chain = (
        f"scale={ANIMATIC_WIDTH}:{ANIMATIC_HEIGHT},fps={FPS_DEFAULT},"
        "format=yuv420p"
    )
    return FfmpegDryRunScript(
        output_mp4=f"artifacts/preflight/{episode_id}_854x480_dryrun.mp4",
        frame_list_path=f"artifacts/preflight/{episode_id}_frames.txt",
        audio_concat_path=f"artifacts/preflight/{episode_id}_voice_concat.txt",
        video_filter=filter_chain,
        flow_spend_micro_usd=0,
        lines=tuple(lines),
    )


def plan_preflight_animatic_dry_run(pack: Mapping[str, Any]) -> PreflightAnimaticPlan:
    """Build a zero-Flow-spend animatic plan for a ReadyToUpload-style pack dict."""
    started = time.perf_counter()

    timeline = pack.get("timeline_spec") or {}
    voice = pack.get("voice_track_manifest") or {}
    scene_plans_raw = pack.get("scene_plans") or []
    flow_cards = pack.get("flow_job_cards") or []
    anchors = pack.get("spatial_anchors") or []

    fps = int(timeline.get("fps") or FPS_DEFAULT)
    ms_per_frame = 1000 / fps

    scene_plans = {str(row["scene_id"]): row for row in scene_plans_raw}
    flow_by_scene = {str(row["scene_id"]): row for row in flow_cards}
    anchors_by_id = {str(row["anchor_id"]): row for row in anchors}
    anchors_by_still: dict[str, Mapping[str, Any]] = {}
    for row in anchors:
        still_id = str(row.get("still_2k_id") or "")
        if still_id and still_id not in anchors_by_still:
            anchors_by_still[still_id] = row
    segments = list(voice.get("segments") or [])
    timeline_scenes = list(timeline.get("scenes") or [])

    episode_id = str(
        voice.get("episode_id")
        or pack.get("episode", {}).get("episode_id")
        or pack.get("pack_id")
        or "episode"
    )
    total_master_ms = int(
        voice.get("total_master_ms")
        or timeline.get("total_master_ms")
        or (timeline_scenes[-1]["start_frame"] + timeline_scenes[-1]["duration_frames"])
        * ms_per_frame
        if timeline_scenes
        else 0
    )

    safe_zone = _safe_zone_rect()
    slices: list[SceneAnimaticSlice] = []

    for scene in timeline_scenes:
        scene_id = str(scene["scene_id"])
        start_ms = int(round(int(scene["start_frame"]) * ms_per_frame))
        duration_ms = int(round(int(scene["duration_frames"]) * ms_per_frame))
        end_ms = start_ms + duration_ms
        engine = str(scene.get("visual_engine") or "CODE_STICKMAN")
        plan_row = scene_plans.get(scene_id)
        open_loop, open_label = _open_loop_label(plan_row)
        cost_micro = _scene_cost_micro(engine, scene_id, flow_by_scene)
        zoom = _resolve_zoom_box(
            engine, scene_id, flow_by_scene, anchors_by_id, anchors_by_still
        )
        frame = DiagnosticFrameSpec(
            scene_id=scene_id,
            width=ANIMATIC_WIDTH,
            height=ANIMATIC_HEIGHT,
            engine=engine,
            cost_usd=round(cost_micro / 1_000_000, 6),
            cost_micro_usd=cost_micro,
            open_loop=open_loop,
            open_loop_label=open_label,
            safe_zone_guide=safe_zone,
            zoom_box=zoom,
        )
        voice_concat = _collect_overlapping_voice(start_ms, end_ms, segments)
        slices.append(
            SceneAnimaticSlice(
                scene_id=scene_id,
                seq_index=int(scene.get("seq_index") or 0),
                start_ms=start_ms,
                end_ms=end_ms,
                duration_ms=duration_ms,
                frame=frame,
                voice_concat=voice_concat,
            )
        )

    global_voice = _global_voice_concat(segments)
    ffmpeg = _build_ffmpeg_script(episode_id, slices, global_voice)
    elapsed = time.perf_counter() - started

    return PreflightAnimaticPlan(
        episode_id=episode_id,
        total_master_ms=total_master_ms,
        width=ANIMATIC_WIDTH,
        height=ANIMATIC_HEIGHT,
        elapsed_sec=elapsed,
        flow_spend_micro_usd=0,
        scenes=tuple(slices),
        global_voice_concat=global_voice,
        ffmpeg=ffmpeg,
    )


def assert_voice_concat_order(clips: Sequence[VoiceConcatClip]) -> None:
    """Raise if concat clips violate narration → FOIA → twist pad ordering."""
    order = {kind: index for index, kind in enumerate(VOICE_KIND_ORDER)}
    last_kind_rank = -1
    last_start = -1
    for clip in clips:
        rank = order.get(clip.segment_kind)
        if rank is None:
            raise ValueError(f"unknown segment kind {clip.segment_kind!r}")
        if rank < last_kind_rank:
            raise ValueError("voice concat violates narration → FOIA → twist pad order")
        if rank == last_kind_rank and clip.start_ms < last_start:
            raise ValueError("voice concat start_ms must be non-decreasing within a kind")
        last_kind_rank = rank
        last_start = clip.start_ms