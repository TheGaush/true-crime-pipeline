"""Byte-0 cross-episode prompt cache ordering tests. No network."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_PROVIDERS = _ROOT / "providers.yaml"
_SRC = Path(__file__).resolve().parents[1] / "src"
_CONTRACTS_SRC = _ROOT / "packages" / "shared_contracts" / "src"
for entry in (_SRC, _CONTRACTS_SRC):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from agent4_director.cached_director_client import (  # noqa: E402
    CachedDirectorClient,
    TIER2_DELIMITER,
    TIER3_DELIMITER,
    build_byte0_static_rules,
    byte0_prefix_sha256,
    leading_prefix_sha256,
    load_model_id_for_role,
)
from shared_contracts.models import CaseBible, SpatialAnchor, VoiceSegment, VoiceTrackManifest  # noqa: E402


def _case_bible(episode_id: str, *, suspect_color: str) -> CaseBible:
    return CaseBible.model_validate(
        {
            "episode_id": episode_id,
            "style_dna_json": {"flow_keyframe_safe_palette": ["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"]},
            "characters_json": [
                {"character_id": "detective_01", "prop": "notepad", "color_hex": "#3A4F66"},
                {"character_id": "suspect_01", "prop": "coat", "color_hex": suspect_color},
            ],
            "locked_at": 500,
        }
    )


def _anchor(episode_id: str, suffix: str) -> SpatialAnchor:
    return SpatialAnchor.model_validate(
        {
            "anchor_id": f"{episode_id}_anchor_{suffix}",
            "episode_id": episode_id,
            "still_2k_id": f"still_{suffix}",
            "clue_name": f"Clue {suffix}",
            "grid_cell": "A1",
            "x_px": 120,
            "y_px": 240,
            "lock_status": "LOCKED",
            "locked_by": "grid_test",
            "locked_at": 900,
            "still_asset_sha256": "a" * 64,
        }
    )


def _voice_manifest(episode_id: str, *, narration: str) -> VoiceTrackManifest:
    segment = VoiceSegment.model_validate(
        {
            "segment_id": f"{episode_id}_seg_1",
            "episode_id": episode_id,
            "seq_index": 1,
            "segment_kind": "NARRATION",
            "start_ms": 0,
            "end_ms": 4000,
            "audio_path": f"voice/{episode_id}.wav",
            "narration_version_sha256": "b" * 64,
        }
    )
    return VoiceTrackManifest.model_validate(
        {
            "episode_id": episode_id,
            "total_master_ms": 4000,
            "segments": [segment],
        }
    )


@pytest.fixture()
def client() -> CachedDirectorClient:
    return CachedDirectorClient(_PROVIDERS)


def test_model_id_loaded_from_providers_yaml(client: CachedDirectorClient) -> None:
    assert client.manifests_model_id == load_model_id_for_role(_PROVIDERS, "manifests")
    assert client.manifests_model_id == "DeepSeek-V4.1-Flash-1017"


def test_byte0_static_rules_use_sort_keys(client: CachedDirectorClient) -> None:
    text = client.byte0_static_rules
    parsed = json.loads(text)
    assert text == json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n"
    assert parsed["manifests_model_id"] == "DeepSeek-V4.1-Flash-1017"
    assert parsed["model_config"]["model_id"] == "gemini-omni-1.2-flash"
    assert len(parsed["thirteen_laws"]) == 13
    assert len(parsed["motif_catalog_v1"]) == 12


def test_prompt_tier_ordering(client: CachedDirectorClient) -> None:
    episode = _case_bible("ep_alpha", suspect_color="#C4A574")
    anchors = (_anchor("ep_alpha", "01"),)
    voice = _voice_manifest("ep_alpha", narration="Alpha narration line.")
    built = client.build_prompt(
        case_bible=episode,
        spatial_anchors=anchors,
        voice_track_manifest=voice,
        scene_id="scene_open",
    )
    assert built.text.startswith(client.byte0_static_rules)
    assert TIER2_DELIMITER in built.text
    assert TIER3_DELIMITER in built.text
    assert built.text.index(TIER2_DELIMITER) == len(client.byte0_static_rules)
    tier3_start = built.text.index(TIER3_DELIMITER)
    tier2_body = built.text[len(client.byte0_static_rules) + len(TIER2_DELIMITER) : tier3_start]
    assert json.loads(tier2_body.strip())["case_bible"]["episode_id"] == "ep_alpha"


def test_cross_episode_byte0_sha256_is_identical(client: CachedDirectorClient) -> None:
    one = client.build_prompt(
        case_bible=_case_bible("ep_one", suspect_color="#C4A574"),
        spatial_anchors=(_anchor("ep_one", "a"),),
        voice_track_manifest=_voice_manifest("ep_one", narration="Episode one hook."),
    )
    two = client.build_prompt(
        case_bible=_case_bible("ep_two", suspect_color="#8B7355"),
        spatial_anchors=(_anchor("ep_two", "b"), _anchor("ep_two", "c")),
        voice_track_manifest=_voice_manifest("ep_two", narration="Completely different episode."),
        scene_id="scene_mid",
    )
    assert one.byte0_sha256 == two.byte0_sha256
    assert byte0_prefix_sha256(one.text, byte0_text=client.byte0_static_rules) == one.byte0_sha256
    assert byte0_prefix_sha256(two.text, byte0_text=client.byte0_static_rules) == two.byte0_sha256
    assert one.text[: len(client.byte0_static_rules)] == two.text[: len(client.byte0_static_rules)]


def test_case_bible_first_breaks_cross_episode_byte0_hash(client: CachedDirectorClient) -> None:
    byte_count = len(client.byte0_static_rules.encode("utf-8"))
    bug_one = client.build_prompt_v1_bug(
        case_bible=_case_bible("ep_bug_one", suspect_color="#111111"),
        spatial_anchors=(_anchor("ep_bug_one", "x"),),
        voice_track_manifest=_voice_manifest("ep_bug_one", narration="Bug one."),
    )
    bug_two = client.build_prompt_v1_bug(
        case_bible=_case_bible("ep_bug_two", suspect_color="#222222"),
        spatial_anchors=(_anchor("ep_bug_two", "y"),),
        voice_track_manifest=_voice_manifest("ep_bug_two", narration="Bug two."),
    )
    assert bug_one.byte0_sha256 != bug_two.byte0_sha256
    assert leading_prefix_sha256(bug_one.text, byte_count=byte_count) != leading_prefix_sha256(
        bug_two.text, byte_count=byte_count
    )


def test_build_byte0_static_rules_is_stable_across_calls() -> None:
    first = build_byte0_static_rules(_PROVIDERS)
    second = build_byte0_static_rules(_PROVIDERS)
    assert first == second
    assert byte0_prefix_sha256(first + TIER2_DELIMITER, byte0_text=first) == byte0_prefix_sha256(
        second + TIER2_DELIMITER, byte0_text=second
    )