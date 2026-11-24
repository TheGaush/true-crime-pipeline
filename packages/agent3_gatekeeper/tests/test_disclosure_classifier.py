"""Disclosure and TRANSCRIPT DRAMATIZATION badge classifier tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent3_gatekeeper.disclosure_classifier import (
    TRANSCRIPT_DRAMATIZATION_BADGE,
    DisclosureClassifier,
    SceneDisclosureBeat,
    altered_content_disclosure_for_beat,
    classify_episode_disclosure,
    classify_scene_disclosure,
    dramatization_badge_label,
    has_realistic_reconstruction_tag,
    is_stylized_stick_figure,
    requires_dramatization_badge,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "disclosure_classifier.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}

_STICKMAN = SceneDisclosureBeat(
    visual_engine="CODE_STICKMAN",
    motif_component="StickmanStage",
)
_REALISTIC = SceneDisclosureBeat(
    visual_engine="CODE_STICKMAN",
    motif_component="StickmanStage",
    content_tags=frozenset({"REALISTIC_RECONSTRUCTION"}),
)
_TTS_911_CARD = SceneDisclosureBeat(
    visual_engine="AUDIO_EVIDENCE_CARD",
    motif_component="AudioEvidenceCard",
    quote_kind="911",
    audio_delivery="TTS",
    is_verbatim_quote=True,
)
_ARCHIVAL_911_CARD = SceneDisclosureBeat(
    visual_engine="AUDIO_EVIDENCE_CARD",
    motif_component="AudioEvidenceCard",
    quote_kind="911",
    audio_delivery="ARCHIVAL_WAV",
    is_verbatim_quote=True,
)


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_stylized_stick_figure_skips_altered_content_disclosure() -> None:
    assert is_stylized_stick_figure("CODE_STICKMAN", "StickmanStage")
    assert altered_content_disclosure_for_beat(_STICKMAN) is False
    result = classify_scene_disclosure(_STICKMAN)
    assert result.altered_content_disclosure is False
    assert result.requires_dramatization_badge is False


@pytest.mark.parametrize(
    "tag",
    [
        "REALISTIC_RECONSTRUCTION",
        "realistic reconstruction",
        "PHOTOREALISTIC_RECONSTRUCTION",
    ],
)
def test_realistic_reconstruction_tag_requires_altered_disclosure(tag: str) -> None:
    assert has_realistic_reconstruction_tag([tag])
    beat = SceneDisclosureBeat(
        visual_engine="CODE_STICKMAN",
        motif_component="StickmanStage",
        content_tags=frozenset({tag}),
    )
    assert altered_content_disclosure_for_beat(beat) is True


@pytest.mark.parametrize("quote_kind", ["suspect", "witness", "911"])
def test_tts_verbatim_quote_on_audio_card_requires_dramatization_badge(
    quote_kind: str,
) -> None:
    beat = SceneDisclosureBeat(
        visual_engine="AUDIO_EVIDENCE_CARD",
        motif_component="AudioEvidenceCard",
        quote_kind=quote_kind,  # type: ignore[arg-type]
        audio_delivery="TTS",
        is_verbatim_quote=True,
    )
    assert requires_dramatization_badge(beat) is True
    result = classify_scene_disclosure(beat)
    assert result.requires_dramatization_badge is True
    assert result.dramatization_badge_label == TRANSCRIPT_DRAMATIZATION_BADGE
    assert dramatization_badge_label(True) == TRANSCRIPT_DRAMATIZATION_BADGE


def test_tts_verbatim_quote_on_redacted_doc_reveal_requires_badge() -> None:
    beat = SceneDisclosureBeat(
        visual_engine="CODE_STICKMAN",
        motif_component="RedactedDocReveal",
        quote_kind="witness",
        audio_delivery="TTS",
        is_verbatim_quote=True,
    )
    assert requires_dramatization_badge(beat) is True
    assert classify_scene_disclosure(beat).dramatization_badge_label == (
        TRANSCRIPT_DRAMATIZATION_BADGE
    )


def test_archival_wav_911_on_audio_card_skips_dramatization_badge() -> None:
    assert requires_dramatization_badge(_ARCHIVAL_911_CARD) is False
    result = classify_scene_disclosure(_ARCHIVAL_911_CARD)
    assert result.requires_dramatization_badge is False
    assert result.dramatization_badge_label is None


def test_tts_quote_on_stickman_stage_skips_dramatization_badge() -> None:
    beat = SceneDisclosureBeat(
        visual_engine="CODE_STICKMAN",
        motif_component="StickmanStage",
        quote_kind="suspect",
        audio_delivery="TTS",
        is_verbatim_quote=True,
    )
    assert requires_dramatization_badge(beat) is False


def test_episode_rollups_stickman_plus_realistic_tag() -> None:
    episode = classify_episode_disclosure([_STICKMAN, _REALISTIC])
    assert episode.altered_content_disclosure is True
    assert len(episode.scene_results) == 2
    assert episode.scene_results[0].altered_content_disclosure is False
    assert episode.scene_results[1].altered_content_disclosure is True


def test_episode_rollups_dramatization_on_tts_card_only() -> None:
    episode = classify_episode_disclosure([_STICKMAN, _TTS_911_CARD, _ARCHIVAL_911_CARD])
    assert episode.altered_content_disclosure is False
    assert episode.scene_results[1].requires_dramatization_badge is True
    assert episode.scene_results[2].requires_dramatization_badge is False


def test_disclosure_classifier_facade_matches_functions() -> None:
    classifier = DisclosureClassifier()
    assert classifier.classify_scene(_TTS_911_CARD) == classify_scene_disclosure(_TTS_911_CARD)
    assert classifier.classify_episode([_STICKMAN, _REALISTIC]) == classify_episode_disclosure(
        [_STICKMAN, _REALISTIC]
    )