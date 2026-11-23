import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "flow_adapter" / "batch_desk_backend.py"
_SPEC = importlib.util.spec_from_file_location("tc155_desk", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
desk = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = desk
_SPEC.loader.exec_module(desk)


def test_independent_locks_fifo_and_sunk_cost():
    start = 1_700_000_000_000
    assert desk.next_reset_ms(start) - start == 86_700_000
    first = desk.Account("tab-1", first_spend_ms=start)
    second = desk.Account("tab-2", first_spend_ms=start + 11 * 60 * 1000)
    try:
        desk.checkout(first, start + 86_700_000 - 1)
        assert False
    except desk.AccountLockedError:
        pass
    assert desk.checkout(second, start + 11 * 60 * 1000 + 86_700_000) == "tab-2"
    fresh = desk.Account("tab-3")
    desk.reserve_credit(fresh, start)
    assert fresh.committed_credits == 0
    desk.commit_credit(fresh)
    assert fresh.committed_credits == 1
    cards = [
        desk.EpisodeCard("ep_c", 30),
        desk.EpisodeCard("ep_a", 10),
        desk.EpisodeCard("ep_b", 20),
        desk.EpisodeCard("ep_d", 40, status="READY"),
    ]
    assert [card.episode_id for card in desk.next_slots(cards)] == ["ep_a", "ep_b", "ep_c"]
    assert desk.saturation_decision(0.40, 4) == "ABORT"
    assert desk.saturation_decision(0.60, 5) == "FINISH"
    assert desk.tos_notice("human_batch_desk")
    assert desk.tos_notice("primary") is None
