"""Deterministic visual Gaussian blur and spoken PII tone-mute scrub planner.

No real video encoder and no network: persist a JSON scrub plan under
``scrubbed_foia/`` and run a post-scrub audit on simulated mask state.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MIN_GAUSSIAN_SIGMA = 25
SPOKEN_TONE_DBFS = -24
STATUS_BLURRED = "blurred"
STATUS_CRISP = "crisp"
STATUS_MUTED = "muted"
STATUS_UNMUTED = "unmuted"

_AUDIO_EXTENSIONS = frozenset({".wav", ".flac", ".mp3", ".m4a", ".aac"})
_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".m4v"})


@dataclass(frozen=True)
class VisualPiiBox:
    """Axis-aligned visual PII region on the source timeline."""

    box_id: str
    x: int
    y: int
    width: int
    height: int
    start_ms: int = 0
    end_ms: int = 0

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.end_ms and self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")

    def to_dict(self) -> dict[str, int | str]:
        return {
            "box_id": self.box_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }


@dataclass(frozen=True)
class SpokenPiiInterval:
    """Spoken PII span on the source audio timeline."""

    start_ms: int
    end_ms: int
    kind: str = "pii"

    def __post_init__(self) -> None:
        if self.end_ms < self.start_ms:
            raise ValueError("end_ms must be >= start_ms")

    @property
    def interval_key(self) -> str:
        return f"{self.start_ms}:{self.end_ms}"

    def to_dict(self) -> dict[str, int | str]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class BlurOperation:
    """Planned Gaussian blur over one visual box."""

    box_id: str
    sigma: float
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        if self.sigma < MIN_GAUSSIAN_SIGMA:
            raise ValueError(f"sigma must be >= {MIN_GAUSSIAN_SIGMA}")

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "box_id": self.box_id,
            "sigma": self.sigma,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }


@dataclass(frozen=True)
class MuteOperation:
    """Planned -24 dBFS tone overlay replacing spoken PII audio."""

    start_ms: int
    end_ms: int
    tone_dbfs: float
    interval_key: str

    def __post_init__(self) -> None:
        if self.tone_dbfs != SPOKEN_TONE_DBFS:
            raise ValueError(f"tone_dbfs must be {SPOKEN_TONE_DBFS}")

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "tone_dbfs": self.tone_dbfs,
            "interval_key": self.interval_key,
        }


@dataclass
class ScrubPlan:
    """JSON-serializable scrub plan (not a rendered media file)."""

    asset_id: str
    source_path: str
    has_video_track: bool
    blur_operations: list[BlurOperation] = field(default_factory=list)
    mute_operations: list[MuteOperation] = field(default_factory=list)
    visual_pii_blurred: int = 0
    spoken_pii_bleeped: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source_path": self.source_path,
            "has_video_track": self.has_video_track,
            "visual_pii_blurred": self.visual_pii_blurred,
            "spoken_pii_bleeped": self.spoken_pii_bleeped,
            "blur_operations": [op.to_dict() for op in self.blur_operations],
            "mute_operations": [op.to_dict() for op in self.mute_operations],
        }


@dataclass
class ScrubState:
    """Simulated post-render mask state for offline audit."""

    box_status: dict[str, str] = field(default_factory=dict)
    interval_status: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ScrubAuditResult:
    """Outcome of a post-scrub residual PII audit."""

    passed: bool
    visual_pii_blurred: int
    spoken_pii_bleeped: int
    crisp_boxes: tuple[str, ...] = ()
    unmuted_intervals: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "visual_pii_blurred": self.visual_pii_blurred,
            "spoken_pii_bleeped": self.spoken_pii_bleeped,
            "crisp_boxes": list(self.crisp_boxes),
            "unmuted_intervals": list(self.unmuted_intervals),
        }


def media_has_video_track(source_path: Path | str) -> bool:
    """Infer whether the source asset carries a video track from its extension."""
    suffix = Path(source_path).suffix.lower()
    if suffix in _AUDIO_EXTENSIONS:
        return False
    if suffix in _VIDEO_EXTENSIONS:
        return True
    raise ValueError(f"unsupported FOIA media extension: {suffix!r}")


def _coerce_visual_boxes(
    boxes: Sequence[VisualPiiBox | Mapping[str, Any]],
) -> list[VisualPiiBox]:
    out: list[VisualPiiBox] = []
    for item in boxes:
        if isinstance(item, VisualPiiBox):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            out.append(
                VisualPiiBox(
                    box_id=str(item["box_id"]),
                    x=int(item["x"]),
                    y=int(item["y"]),
                    width=int(item["width"]),
                    height=int(item["height"]),
                    start_ms=int(item.get("start_ms", 0)),
                    end_ms=int(item.get("end_ms", 0)),
                )
            )
            continue
        raise TypeError("visual box must be VisualPiiBox or mapping")
    return out


def _coerce_spoken_intervals(
    intervals: Sequence[SpokenPiiInterval | Mapping[str, Any]],
) -> list[SpokenPiiInterval]:
    out: list[SpokenPiiInterval] = []
    for item in intervals:
        if isinstance(item, SpokenPiiInterval):
            out.append(item)
            continue
        if isinstance(item, Mapping):
            out.append(
                SpokenPiiInterval(
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                    kind=str(item.get("kind", "pii")),
                )
            )
            continue
        raise TypeError("spoken interval must be SpokenPiiInterval or mapping")
    return out


def plan_pii_scrub(
    visual_boxes: Sequence[VisualPiiBox | Mapping[str, Any]],
    spoken_intervals: Sequence[SpokenPiiInterval | Mapping[str, Any]],
    *,
    asset_id: str,
    source_path: Path | str,
    blur_sigma: float = MIN_GAUSSIAN_SIGMA,
) -> ScrubPlan:
    """Plan blur and tone-mute operations for every detected PII region."""
    if blur_sigma < MIN_GAUSSIAN_SIGMA:
        raise ValueError(f"blur_sigma must be >= {MIN_GAUSSIAN_SIGMA}")

    boxes = _coerce_visual_boxes(visual_boxes)
    intervals = _coerce_spoken_intervals(spoken_intervals)
    has_video = media_has_video_track(source_path)

    if not has_video and boxes:
        raise ValueError("audio-only source cannot carry visual PII boxes")

    blur_ops = [
        BlurOperation(
            box_id=box.box_id,
            sigma=blur_sigma,
            start_ms=box.start_ms,
            end_ms=box.end_ms,
        )
        for box in boxes
    ]
    mute_ops = [
        MuteOperation(
            start_ms=ival.start_ms,
            end_ms=ival.end_ms,
            tone_dbfs=SPOKEN_TONE_DBFS,
            interval_key=ival.interval_key,
        )
        for ival in intervals
    ]

    visual_flag = 1 if (not boxes or len(blur_ops) == len(boxes)) else 0
    spoken_flag = 1 if (not intervals or len(mute_ops) == len(intervals)) else 0

    return ScrubPlan(
        asset_id=asset_id,
        source_path=str(source_path),
        has_video_track=has_video,
        blur_operations=blur_ops,
        mute_operations=mute_ops,
        visual_pii_blurred=visual_flag,
        spoken_pii_bleeped=spoken_flag,
    )


def apply_scrub_plan(plan: ScrubPlan) -> ScrubState:
    """Apply the plan to simulated mask state (no ffmpeg / encoder)."""
    state = ScrubState()
    for op in plan.blur_operations:
        state.box_status[op.box_id] = STATUS_BLURRED
    for op in plan.mute_operations:
        state.interval_status[op.interval_key] = STATUS_MUTED
    return state


def audit_post_scrub(
    state: ScrubState,
    visual_boxes: Sequence[VisualPiiBox | Mapping[str, Any]],
    spoken_intervals: Sequence[SpokenPiiInterval | Mapping[str, Any]],
) -> ScrubAuditResult:
    """Fail when any original box is still crisp or any interval is still unmuted."""
    boxes = _coerce_visual_boxes(visual_boxes)
    intervals = _coerce_spoken_intervals(spoken_intervals)

    crisp: list[str] = []
    for box in boxes:
        status = state.box_status.get(box.box_id, STATUS_CRISP)
        if status != STATUS_BLURRED:
            crisp.append(box.box_id)

    unmuted: list[str] = []
    for ival in intervals:
        status = state.interval_status.get(ival.interval_key, STATUS_UNMUTED)
        if status != STATUS_MUTED:
            unmuted.append(ival.interval_key)

    visual_ok = len(crisp) == 0
    spoken_ok = len(unmuted) == 0
    passed = visual_ok and spoken_ok

    return ScrubAuditResult(
        passed=passed,
        visual_pii_blurred=1 if visual_ok else 0,
        spoken_pii_bleeped=1 if spoken_ok else 0,
        crisp_boxes=tuple(crisp),
        unmuted_intervals=tuple(unmuted),
    )


def default_scrubbed_foia_dir() -> Path:
    """Return a temp ``scrubbed_foia`` directory (created if missing)."""
    base = Path(tempfile.gettempdir()) / "scrubbed_foia"
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_scrub_plan_json(
    plan: ScrubPlan,
    *,
    scrubbed_foia_dir: Path | str | None = None,
) -> Path:
    """Persist the scrub plan as JSON under ``scrubbed_foia/``."""
    out_dir = Path(scrubbed_foia_dir) if scrubbed_foia_dir else default_scrubbed_foia_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{plan.asset_id}.scrub_plan.json"
    out_path.write_text(
        json.dumps(plan.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return out_path


@dataclass
class PiiBlurRenderer:
    """High-level façade: plan, simulate apply, audit, and write JSON."""

    def render(
        self,
        visual_boxes: Sequence[VisualPiiBox | Mapping[str, Any]],
        spoken_intervals: Sequence[SpokenPiiInterval | Mapping[str, Any]],
        *,
        asset_id: str,
        source_path: Path | str,
        scrubbed_foia_dir: Path | str | None = None,
    ) -> tuple[ScrubPlan, ScrubState, ScrubAuditResult, Path]:
        plan = plan_pii_scrub(
            visual_boxes,
            spoken_intervals,
            asset_id=asset_id,
            source_path=source_path,
        )
        state = apply_scrub_plan(plan)
        audit = audit_post_scrub(state, visual_boxes, spoken_intervals)
        plan.visual_pii_blurred = audit.visual_pii_blurred
        plan.spoken_pii_bleeped = audit.spoken_pii_bleeped
        out_path = write_scrub_plan_json(plan, scrubbed_foia_dir=scrubbed_foia_dir)
        return plan, state, audit, out_path