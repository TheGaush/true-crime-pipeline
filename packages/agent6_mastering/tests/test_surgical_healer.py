import importlib.util
import sys
import time
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "surgical_healer.py"
_SPEC = importlib.util.spec_from_file_location("tc171_heal", _PATH)
assert _SPEC and _SPEC.loader
heal = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = heal
_SPEC.loader.exec_module(heal)


def test_two_passes_keep_frames_and_spend_nothing(tmp_path: Path):
    calls = {"n": 0}

    def scan(scene):
        calls["n"] += 1
        return ["bottom"] if calls["n"] < 3 else []

    started = time.perf_counter()
    scene = {"scene_id": "s1", "visual_engine": "CODE_STICKMAN", "duration_sec": 0.4}
    result = heal.heal(scene, str(tmp_path), scan)
    assert time.perf_counter() - started < 5.0
    assert result.passes == 2
    assert result.nb_frames == 12
    assert result.flow_spend_usd == 0.0
    assert result.human_review is False
    assert "render-catalog --scene s1" in (tmp_path / "s1.command").read_text(encoding="utf8")
    hero = {"scene_id": "h1", "visual_engine": "FLOW_HERO_VIDEO", "duration_sec": 0.2, "fallback_engine": "STILL_2K_PANZOOM"}
    blocked = heal.heal(hero, str(tmp_path), lambda _scene: ["still"])
    assert blocked.passes == 2
    assert blocked.human_review is True
    assert blocked.flow_spend_usd == 0.0
