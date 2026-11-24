"""RenderBackendPort contract and Part 2 import isolation."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ORCHESTRATOR_SRC = Path(__file__).resolve().parents[1] / "src"
SHARED_CONTRACTS_SRC = Path(__file__).resolve().parents[2] / "shared_contracts" / "src"
if str(ORCHESTRATOR_SRC) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_SRC))
if str(SHARED_CONTRACTS_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_CONTRACTS_SRC))

from orchestrator.render_port import (  # noqa: E402
    CodeSceneRequest,
    FlowJobDispatch,
    FORBIDDEN_PART2_ROOTS,
    MasterAssemblyRequest,
    MVP_MOTIF_NAMES_V1,
    PanZoom2KRequest,
    RENDER_CATALOG_MOTIF_NAMES_V1,
    RenderBackendPort,
    RenderSceneReceipt,
    _stable_digest,
)
from shared_contracts.motifs import MOTIF_CATALOG, MVP_MOTIF_NAMES  # noqa: E402

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_PY_FILES = tuple(PACKAGE_ROOT.rglob("*.py"))


def _import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


@pytest.mark.parametrize("path", ORCHESTRATOR_PY_FILES, ids=lambda p: p.name)
def test_orchestrator_package_has_no_part2_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = _import_roots(tree)
    leaked = sorted(roots & FORBIDDEN_PART2_ROOTS)
    assert not leaked, f"{path.relative_to(PACKAGE_ROOT)} imports forbidden Part 2 roots: {leaked}"


def test_render_port_protocol_methods_exist() -> None:
    required = {
        "render_code_scene",
        "render_2k_panzoom",
        "generate_flow_keyframes",
        "dispatch_flow_jobs",
        "assemble_master",
    }
    assert required.issubset(RenderBackendPort.__protocol_attrs__)


def test_catalog_constants_match_shared_contracts() -> None:
    render_catalog_twelve = tuple(
        entry.motif_component for entry in MOTIF_CATALOG if entry.owner_package == "render_catalog"
    )
    assert RENDER_CATALOG_MOTIF_NAMES_V1 == render_catalog_twelve
    assert len(RENDER_CATALOG_MOTIF_NAMES_V1) == 12
    assert MVP_MOTIF_NAMES_V1 == MVP_MOTIF_NAMES
    assert len(MVP_MOTIF_NAMES_V1) == 4


class FakeRenderBackend:
    """In-memory adapter for contract tests. No network, no Part 2 imports."""

    backend_name = "fake-render-backend"

    def render_code_scene(self, request: CodeSceneRequest) -> RenderSceneReceipt:
        digest = _stable_digest("code", request.motif_component, request.scene_id)
        return RenderSceneReceipt(
            backend_name=self.backend_name,
            episode_id=request.episode_id,
            scene_id=request.scene_id,
            output_relpath=f"renders/{request.episode_id}/{request.scene_id}_{request.motif_component}.mp4",
            sha256=digest,
        )

    def render_2k_panzoom(self, request: PanZoom2KRequest) -> RenderSceneReceipt:
        digest = _stable_digest("2k", request.still_asset_relpath, request.scene_id)
        return RenderSceneReceipt(
            backend_name=self.backend_name,
            episode_id=request.episode_id,
            scene_id=request.scene_id,
            output_relpath=f"renders/{request.episode_id}/{request.scene_id}_2k.mp4",
            sha256=digest,
        )

    def generate_flow_keyframes(
        self,
        flow_job_id: str,
        prompt_mode: str,
        visual_prompt: str,
    ):
        from orchestrator.render_port import FlowKeyframeRef, FlowKeyframeSet

        digest = _stable_digest(flow_job_id, prompt_mode, visual_prompt)
        keyframes = (
            FlowKeyframeRef(
                ref_id=f"{flow_job_id}_start",
                role="START",
                png_relpath=f"keyframes/{flow_job_id}/start.png",
                sha256=digest[:64],
            ),
        )
        if prompt_mode == "FIRST_AND_LAST_FRAME":
            keyframes = keyframes + (
                FlowKeyframeRef(
                    ref_id=f"{flow_job_id}_end",
                    role="END",
                    png_relpath=f"keyframes/{flow_job_id}/end.png",
                    sha256=_stable_digest(digest, "end"),
                ),
            )
        return FlowKeyframeSet(flow_job_id=flow_job_id, prompt_mode=prompt_mode, keyframes=keyframes)

    def dispatch_flow_jobs(self, jobs):
        from orchestrator.render_port import FlowJobDispatchReceipt

        receipts: list[FlowJobDispatchReceipt] = []
        for job in jobs:
            state = "QUEUED_BATCH_DESK" if job.provider_route == "HUMAN_BATCH_DESK" else "PENDING"
            receipts.append(
                FlowJobDispatchReceipt(
                    flow_job_id=job.flow_job_id,
                    provider_route=job.provider_route,
                    state=state,
                    estimated_micro_usd=0,
                )
            )
        return tuple(receipts)

    def assemble_master(self, request: MasterAssemblyRequest):
        from orchestrator.render_port import MasterAssemblyReceipt

        digest = _stable_digest(
            request.manifest_id,
            request.episode_id,
            *(receipt.sha256 for receipt in request.scene_receipts),
        )
        return MasterAssemblyReceipt(
            episode_id=request.episode_id,
            manifest_id=request.manifest_id,
            final_mp4_relpath=f"masters/{request.episode_id}/final_1080p30.mp4",
            integrated_lufs=request.target_lufs,
            scene_count=len(request.scene_receipts),
            sha256=digest,
        )


def test_fake_adapter_is_render_backend_port() -> None:
    backend = FakeRenderBackend()
    assert isinstance(backend, RenderBackendPort)


@pytest.mark.parametrize("motif", MVP_MOTIF_NAMES_V1)
def test_fake_adapter_renders_mvp_motifs(motif: str) -> None:
    backend = FakeRenderBackend()
    receipt = backend.render_code_scene(
        CodeSceneRequest(
            episode_id="ep_mvp",
            scene_id=f"scene_{motif}",
            motif_component=motif,
            duration_ms=4000,
        )
    )
    assert receipt.sha256
    assert motif in receipt.output_relpath


def test_fake_adapter_renders_twelve_motif_catalog() -> None:
    backend = FakeRenderBackend()
    receipts = [
        backend.render_code_scene(
            CodeSceneRequest(
                episode_id="ep_full",
                scene_id=f"scene_{idx:02d}",
                motif_component=motif,
                duration_ms=5000,
            )
        )
        for idx, motif in enumerate(RENDER_CATALOG_MOTIF_NAMES_V1, start=1)
    ]
    assert len(receipts) == 12
    assert len({r.output_relpath for r in receipts}) == 12
    master = backend.assemble_master(
        MasterAssemblyRequest(
            manifest_id="manifest_ep_full",
            episode_id="ep_full",
            scene_receipts=tuple(receipts),
        )
    )
    assert master.scene_count == 12
    assert master.integrated_lufs == pytest.approx(-14.0)


def test_fake_adapter_flow_and_2k_paths() -> None:
    backend = FakeRenderBackend()
    pan = backend.render_2k_panzoom(
        PanZoom2KRequest(
            episode_id="ep_2k",
            scene_id="scene_still",
            still_asset_relpath="plates/illustrative/plate_01.png",
            duration_ms=20000,
        )
    )
    assert pan.output_relpath.endswith("_2k.mp4")
    keyframes = backend.generate_flow_keyframes(
        "flow_job_1",
        "FIRST_AND_LAST_FRAME",
        "Rain-slick alley, monochrome keyframe",
    )
    assert len(keyframes.keyframes) == 2
    dispatch = backend.dispatch_flow_jobs(
        (
            FlowJobDispatch(
                flow_job_id="flow_job_1",
                episode_id="ep_2k",
                scene_id="scene_hero",
                idempotency_key="idem-flow-1",
                provider_route="GEMINI_OMNI_INTERACTIONS",
                prompt_mode="FIRST_AND_LAST_FRAME",
                prompt_v1="Hero prompt",
                prompt_v2_safe="Hero safe prompt",
                duration_bucket_sec=8,
            ),
        )
    )
    assert dispatch[0].estimated_micro_usd == 0