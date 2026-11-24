"""Offline adversarial tests for CleanRoomFirewall."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_PKG_SRC = Path(__file__).resolve().parents[1] / "src"
_CONTRACTS_SRC = Path(__file__).resolve().parents[2] / "shared_contracts" / "src"
for _path in (_PKG_SRC, _CONTRACTS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from agent1_scout.clean_room_firewall import (  # noqa: E402
    CleanRoomFirewall,
    CleanRoomFirewallError,
    MAX_FIELD_CHARS,
)
from shared_contracts.models import SeedPacket  # noqa: E402

VALID_SEED = {
    "track": "TRACK_A_OUTLIER",
    "suspect_names": ["Alex Rivera"],
    "victim_names": [],
    "incident_date_or_year": "2018",
    "county_state": "King County, WA",
    "docket_ids": [],
    "unanswered_comment_questions": ["Who signed the affidavit?"],
}


@pytest.fixture
def firewall() -> CleanRoomFirewall:
    return CleanRoomFirewall()


def test_emit_valid_factual_seed(firewall: CleanRoomFirewall) -> None:
    packet = firewall.emit_seed(VALID_SEED)
    assert isinstance(packet, SeedPacket)
    assert packet.suspect_names == ["Alex Rivera"]
    assert packet.lead_classification == "LEAD_ONLY"


@pytest.mark.parametrize(
    "field",
    ["narrative_outline", "beat_order", "creator_commentary"],
)
def test_rejects_forbidden_top_level_fields(firewall: CleanRoomFirewall, field: str) -> None:
    dirty = {**VALID_SEED, field: "smuggled"}
    with pytest.raises(CleanRoomFirewallError, match="forbidden narrative"):
        firewall.emit_seed(dirty)


def test_rejects_closed_schema_extra_fields(firewall: CleanRoomFirewall) -> None:
    dirty = {**VALID_SEED, "editorial_notes": "cold open hook"}
    with pytest.raises(CleanRoomFirewallError, match="closed SeedPacket"):
        firewall.emit_seed(dirty)


def test_rejects_string_field_over_200_chars(firewall: CleanRoomFirewall) -> None:
    dirty = {**VALID_SEED, "county_state": "A" * (MAX_FIELD_CHARS + 1)}
    with pytest.raises(CleanRoomFirewallError, match="exceeds 200"):
        firewall.emit_seed(dirty)


@pytest.mark.parametrize(
    "question",
    [
        "What happened. Then they left town?",
        "Who was there. She ran away?",
        "Not even a question",
        "A" * 180 + " why?",
    ],
)
def test_rejects_smuggled_comment_questions(firewall: CleanRoomFirewall, question: str) -> None:
    dirty = {**VALID_SEED, "unanswered_comment_questions": [question]}
    with pytest.raises(CleanRoomFirewallError):
        firewall.emit_seed(dirty)


def test_rejects_narrative_markers_in_lookup_fields(firewall: CleanRoomFirewall) -> None:
    dirty = {**VALID_SEED, "county_state": "King County three-act structure"}
    with pytest.raises(CleanRoomFirewallError, match="narrative outline"):
        firewall.emit_seed(dirty)


def test_rejects_deprecated_identifier(firewall: CleanRoomFirewall) -> None:
    dirty = {**VALID_SEED, "suspect_names": ["VEO_3_1_LITE"]}
    with pytest.raises(CleanRoomFirewallError, match="deprecated"):
        firewall.emit_seed(dirty)


def test_rejects_missing_lookup_key(firewall: CleanRoomFirewall) -> None:
    dirty = {
        **VALID_SEED,
        "suspect_names": [],
        "victim_names": [],
        "docket_ids": [],
    }
    with pytest.raises(CleanRoomFirewallError):
        firewall.emit_seed(dirty)


def test_wipe_transcript_deletes_file(firewall: CleanRoomFirewall, tmp_path: Path) -> None:
    transcript = tmp_path / "fallback_transcript.txt"
    secret = "CREATOR_FALLBACK_TRANSCRIPT_BYTES_UNIQUE"
    transcript.write_text(secret, encoding="utf-8")
    assert transcript.is_file()

    packet = firewall.emit_seed(VALID_SEED, transcript_buffer=transcript)

    assert not transcript.exists()
    joined = " ".join(
        [
            packet.incident_date_or_year,
            packet.county_state,
            *packet.suspect_names,
            *packet.victim_names,
            *packet.docket_ids,
            *packet.unanswered_comment_questions,
        ]
    )
    assert secret not in joined


def test_wipe_transcript_standalone(firewall: CleanRoomFirewall, tmp_path: Path) -> None:
    transcript = tmp_path / "buf.txt"
    transcript.write_text("purge me", encoding="utf-8")
    firewall.wipe_transcript(transcript)
    assert not transcript.exists()


def test_rejects_transcript_residue_before_wipe(firewall: CleanRoomFirewall, tmp_path: Path) -> None:
    transcript = tmp_path / "fallback_transcript.txt"
    secret = "SMUGGLED_TRANSCRIPT_FINGERPRINT_XYZ"
    transcript.write_text(secret, encoding="utf-8")
    dirty = {**VALID_SEED, "county_state": f"King County, WA — {secret}"}
    with pytest.raises(CleanRoomFirewallError, match="transcript buffer"):
        firewall.emit_seed(dirty, transcript_buffer=transcript)
    assert transcript.is_file()


def test_module_has_no_network_imports() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "agent1_scout" / "clean_room_firewall.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    banned_roots = {
        "http",
        "httpx",
        "requests",
        "socket",
        "ssl",
        "urllib",
        "aiohttp",
        "websockets",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in banned_roots
        if isinstance(node, ast.ImportFrom):
            assert node.module is not None
            root = node.module.split(".", 1)[0]
            assert root not in banned_roots