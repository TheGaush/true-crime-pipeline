import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "flow_adapter" / "circuit_breaker.py"
_SPEC = importlib.util.spec_from_file_location("tc158_breaker", _PATH)
assert _SPEC and _SPEC.loader
breaker = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = breaker
_SPEC.loader.exec_module(breaker)


def test_two_strikes_escrow_and_neighbor_rule():
    scene = breaker.SceneTicket("hero", "the figure runs down the hall and grabs the folder", 8)
    machine = breaker.CircuitBreaker(1.0)
    assert machine.fail(scene, None, None) == "RETRY"
    assert scene.attempt_count == 1
    assert "runs" not in scene.prompt.split()
    assert len(scene.prompt.split()) <= 10
    assert scene.alert.startswith("Strike 1")
    assert machine.fail(scene, None, None) == "fallback_triggered"
    assert scene.attempt_count <= 2
    dry = breaker.SceneTicket("next", "quiet room", 8)
    assert breaker.CircuitBreaker(0).fail(dry, None, None) == "fallback_triggered"
    crowded = breaker.SceneTicket("mid", "quiet", 20, fallback_engine="CODE_STICKMAN")
    left = breaker.Neighbor("CODE_STICKMAN", 20)
    right = breaker.Neighbor("CODE_STICKMAN", 20)
    machine.fail(crowded, left, right)
    assert machine.fail(crowded, left, right) == "fallback_triggered"
    assert crowded.fallback_engine == "STILL_2K_PANZOOM"
