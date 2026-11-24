import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "flow_adapter" / "src"))
desk = importlib.import_module("flow_adapter.batch_desk_backend")


def test_three_slots_fifo_and_sunk_cost():
    cards = [
        desk.EpisodeCard("ep_c", 3000),
        desk.EpisodeCard("ep_a", 1000),
        desk.EpisodeCard("ep_b", 2000),
        desk.EpisodeCard("ep_d", 4000, status="SCOUTED"),
        desk.EpisodeCard("ep_e", 5000, status="EVIDENCE_AND_2K_LOCKED"),
    ]
    slots = desk.next_slots(cards)
    assert [card.episode_id for card in slots] == ["ep_a", "ep_b", "ep_c"]
    assert desk.saturation_decision(0.35, 4) == "ABORT"
    assert desk.saturation_decision(0.68, 4) == "FINISH"
    freed = [card for card in cards if card.episode_id != "ep_b"]
    waiting = desk.next_slots(freed)
    assert waiting[0].episode_id == "ep_a"
    assert len(waiting) == 2
