import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from flow_adapter.orchestrator import FlowOrchestrator


class Transport:
    def __init__(self) -> None:
        self.created = []
        self.fail = {"lost"}
        self.empty = {"bad"}

    def create(self, scene_id, prompt_mode, duration):
        self.created.append(scene_id)
        if scene_id in self.fail:
            raise TimeoutError(scene_id)
        return {"id": f"op-{scene_id}", "output_tokens": 0 if scene_id in self.empty else 8, "mode": prompt_mode, "duration": duration}

    def poll(self, operation_id):
        return "SUCCEEDED"


def test_reconcile_strike_and_frame_lock(tmp_path: Path):
    manifest = {
        "episode_id": "ep_golden_01",
        "scenes": [
            {"scene_id": "ok", "visual_engine": "FLOW_HERO_VIDEO", "prompt_mode": "TEXT_TO_VIDEO", "duration_sec": 0.2},
            {"scene_id": "lost", "visual_engine": "FLOW_HERO_VIDEO", "prompt_mode": "FIRST_FRAME", "duration_sec": 0.2},
            {"scene_id": "bad", "visual_engine": "FLOW_HERO_VIDEO", "prompt_mode": "FIRST_AND_LAST_FRAME", "duration_sec": 0.2, "fallback_engine": "STILL_2K_PANZOOM"},
        ],
    }
    transport = Transport()
    db = tmp_path / "pipeline.db"
    first = FlowOrchestrator(str(db), str(tmp_path / "out"), transport).run(manifest)
    assert {row["state"] for row in first["scenes"]} == {"SUCCEEDED", "UNKNOWN_RECONCILE", "STRIKE_1"}
    assert first["nb_frames"] == 18
    again = FlowOrchestrator(str(db), str(tmp_path / "out"), transport).run(manifest)
    states = {row["scene_id"]: row["state"] for row in again["scenes"]}
    assert states["lost"] == "SUCCEEDED"
    assert states["bad"] == "FALLBACK"
    assert transport.created.count("lost") == 1
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,r_frame_rate", "-of", "json", str(tmp_path / "out" / "ok.mp4")],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["r_frame_rate"] == "30/1"
    assert int(stream["nb_frames"]) == 6
