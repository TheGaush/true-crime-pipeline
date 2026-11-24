"""Part 1 -> Part 2 render backend seam. No Part 2 package imports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence, runtime_checkable

FORBIDDEN_PART2_ROOTS: frozenset[str] = frozenset(
    {
        "render_catalog",
        "crime_scene_2k",
        "flow_adapter",
        "agent6_mastering",
    }
)

# Authoritative 12-motif @tc/render_catalog catalog (Motifs #1–#12 per MOTIF_REGISTRY).
RENDER_CATALOG_MOTIF_NAMES_V1: tuple[str, ...] = (
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
    "TimelineScrubber",
    "AnimatedMapRoute",
    "CellTowerTriangulation",
    "SplitScreenComparison",
    "CaseBoardSpine",
    "QuotePullout",
    "EvidenceGridMatrix",
    "ChapterSlateTransition",
)

MVP_MOTIF_NAMES_V1: tuple[str, ...] = RENDER_CATALOG_MOTIF_NAMES_V1[:4]

ScenePromptMode = Literal["NONE", "TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]
VideoPromptMode = Literal["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]
FlowBackendMode = Literal[
    "GEMINI_OMNI_INTERACTIONS",
    "VERTEX_VEO_ENTERPRISE",
    "HUMAN_BATCH_DESK",
]


@dataclass(frozen=True, slots=True)
class CodeSceneRequest:
    episode_id: str
    scene_id: str
    motif_component: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PanZoom2KRequest:
    episode_id: str
    scene_id: str
    still_asset_relpath: str
    duration_ms: int
    span_cols: float = 2.0
    span_rows: float = 2.0


@dataclass(frozen=True, slots=True)
class RenderSceneReceipt:
    backend_name: str
    episode_id: str
    scene_id: str
    output_relpath: str
    sha256: str
    fps: Literal[30] = 30


@dataclass(frozen=True, slots=True)
class FlowKeyframeRef:
    ref_id: str
    role: Literal["START", "END"]
    png_relpath: str
    sha256: str


@dataclass(frozen=True, slots=True)
class FlowKeyframeSet:
    flow_job_id: str
    prompt_mode: VideoPromptMode
    keyframes: tuple[FlowKeyframeRef, ...]


@dataclass(frozen=True, slots=True)
class FlowJobDispatch:
    flow_job_id: str
    episode_id: str
    scene_id: str
    idempotency_key: str
    provider_route: FlowBackendMode
    prompt_mode: VideoPromptMode
    prompt_v1: str
    prompt_v2_safe: str
    duration_bucket_sec: int


@dataclass(frozen=True, slots=True)
class FlowJobDispatchReceipt:
    flow_job_id: str
    provider_route: FlowBackendMode
    state: Literal["PENDING", "SUBMITTING", "QUEUED_BATCH_DESK"]
    estimated_micro_usd: int


@dataclass(frozen=True, slots=True)
class MasterAssemblyRequest:
    manifest_id: str
    episode_id: str
    scene_receipts: tuple[RenderSceneReceipt, ...]
    target_lufs: float = -14.0


@dataclass(frozen=True, slots=True)
class MasterAssemblyReceipt:
    episode_id: str
    manifest_id: str
    final_mp4_relpath: str
    integrated_lufs: float
    scene_count: int
    sha256: str


def _stable_digest(*parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@runtime_checkable
class RenderBackendPort(Protocol):
    """Adapter surface for Part 2 render, flow, and mastering backends."""

    def render_code_scene(self, request: CodeSceneRequest) -> RenderSceneReceipt:
        """Render a Remotion catalog motif clip."""

    def render_2k_panzoom(self, request: PanZoom2KRequest) -> RenderSceneReceipt:
        """Render an illustrative 2K pan/zoom segment."""

    def generate_flow_keyframes(
        self,
        flow_job_id: str,
        prompt_mode: VideoPromptMode,
        visual_prompt: str,
    ) -> FlowKeyframeSet:
        """Produce monochrome Start/End keyframe PNGs for a flow job."""

    def dispatch_flow_jobs(
        self,
        jobs: Sequence[FlowJobDispatch],
    ) -> tuple[FlowJobDispatchReceipt, ...]:
        """Submit or queue hero-video flow jobs."""

    def assemble_master(self, request: MasterAssemblyRequest) -> MasterAssemblyReceipt:
        """Stitch scene outputs into a single mastered episode master."""