"""Offline tests for the MuckRock completed-drop radar."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_PKG_SRC = Path(__file__).resolve().parents[1] / "src"
_CONTRACTS_SRC = Path(__file__).resolve().parents[2] / "shared_contracts" / "src"
for _path in (_PKG_SRC, _CONTRACTS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from agent1_scout.muckrock_radar import (  # noqa: E402
    MIN_SUBSTANTIVE_BYTES,
    MuckRockCompletedDropRadar,
    TRACK_B_FOIA_RADAR,
    attachment_needs_third_party_cctv_inspection,
    is_substantive_file,
)
from shared_contracts.models import SeedPacket  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "muckrock_completed.json"


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    return _load_fixture()


def _accept_all(seed: dict[str, Any]) -> dict[str, Any]:
    _ = seed
    return {"rejected": False, "reason": ""}


def _reject_saturated(seed: dict[str, Any]) -> dict[str, Any]:
    if seed.get("suspect_names") == ["Saturated Lead"]:
        return {"rejected": True, "reason": "HARD_KILL_RECENT_DEMAND_EXHAUSTED"}
    return {"rejected": False, "reason": ""}


def test_substantive_size_and_type_invariants():
    tiny = {"content_type": "application/pdf", "size_bytes": MIN_SUBSTANTIVE_BYTES - 1}
    assert is_substantive_file(tiny) is False
    denial = {
        "content_type": "application/pdf",
        "size_bytes": 9000,
        "attachment_kind": "denial_letter",
    }
    assert is_substantive_file(denial) is False
    good = {"content_type": "application/pdf", "size_bytes": MIN_SUBSTANTIVE_BYTES}
    assert is_substantive_file(good) is True


def test_cctv_pre_tag_on_video_attachment():
    video = {
        "filename": "release_clip.mp4",
        "content_type": "video/mp4",
        "size_bytes": 50_000,
    }
    assert attachment_needs_third_party_cctv_inspection(video) is True
    pdf = {
        "filename": "affidavit.pdf",
        "content_type": "application/pdf",
        "size_bytes": 50_000,
    }
    assert attachment_needs_third_party_cctv_inspection(pdf) is False


def test_poll_filters_empty_denial_and_fee_waiver_only(recorded: dict[str, Any]):
    radar = MuckRockCompletedDropRadar(lambda: recorded, _reject_saturated)
    seeds = radar.poll()
    suspects = {tuple(s["suspect_names"]) for s in seeds}
    assert ("Ghost Suspect",) not in suspects
    assert ("Denied Subject",) not in suspects
    assert ("Fee Target",) not in suspects


def test_poll_emits_track_b_seed_packets(recorded: dict[str, Any]):
    radar = MuckRockCompletedDropRadar(lambda: recorded, _accept_all)
    seeds = radar.poll()
    assert len(seeds) == 3
    by_suspect = {s["suspect_names"][0]: s for s in seeds if s["suspect_names"]}
    rivera = by_suspect["Alex Rivera"]
    assert rivera["track"] == TRACK_B_FOIA_RADAR
    assert rivera["needs_third_party_cctv_inspection"] is False
    SeedPacket.model_validate(
        {k: v for k, v in rivera.items() if k != "needs_third_party_cctv_inspection"}
    )

    saturated = by_suspect["Saturated Lead"]
    assert saturated["needs_third_party_cctv_inspection"] is False


def test_poll_tags_cctv_drop(recorded: dict[str, Any]):
    radar = MuckRockCompletedDropRadar(lambda: recorded, _accept_all)
    seeds = radar.poll()
    hale = next(s for s in seeds if s["victim_names"] == ["Jordan Hale"])
    assert hale["needs_third_party_cctv_inspection"] is True


def test_saturation_rejection_suppresses_emit(recorded: dict[str, Any]):
    radar = MuckRockCompletedDropRadar(lambda: recorded, _reject_saturated)
    seeds = radar.poll()
    suspects = {tuple(s["suspect_names"]) for s in seeds}
    assert ("Saturated Lead",) not in suspects
    assert len(seeds) == 2