import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from integration_bridge.live_adapter import LivePart2RenderAdapter, StubPart2RenderAdapter, acquire_lease, open_locked


def test_stub_and_live_share_the_protocol_and_one_writer(tmp_path: Path):
    scene = {"scene_id": "sc_slice", "motif_component": "StickmanStage"}
    stub = StubPart2RenderAdapter().render_scene(scene)
    live = LivePart2RenderAdapter().render_scene(scene, str(tmp_path))
    assert stub["spend_usd"] == 0.0
    assert live["spend_usd"] == 0.0
    assert live["safety_passed"] is True
    assert live["start_frame"] is None
    assert live["sfx_hz"] == 48000
    assert len(LivePart2RenderAdapter().supported_motifs()) == 12
    db = tmp_path / "pipeline.db"
    first = open_locked(str(db))
    second = open_locked(str(db))
    assert acquire_lease(first, "ep_slice", "overnight") is True
    assert acquire_lease(second, "ep_slice", "desk") is False
