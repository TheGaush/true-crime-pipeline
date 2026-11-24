"""Tests for music-gated Demucs bypass and honest ASR metrics (Task 047)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent3_gatekeeper.demucs_stripper import (
    DISAGREEMENT_REVIEW_THRESHOLD,
    MusicGatedDemucsIsolator,
    asr_hypothesis_disagreement,
    is_911_telephony_bypass,
    labeled_corpus_wer,
)

CORPUS = Path(__file__).resolve().parent / "audio_corpus" / "bodycam_reference.json"

ASSET_911 = {
    "asset_id": "foia_911_fixture",
    "media_kind": "call_911_wav",
    "raw_path": "fixtures/synthetic_media/911_8khz_distorted.wav",
    "sample_rate_hz": 8000,
}

ASSET_PURE_SPEECH = {
    "asset_id": "foia_pure_speech",
    "media_kind": "interview_wav",
    "raw_path": "fixtures/synthetic_media/witness_interview_48k.wav",
    "sample_rate_hz": 48000,
}

ASSET_BODYCAM = {
    "asset_id": "foia_bodycam",
    "media_kind": "bodycam_mp4",
    "raw_path": "fixtures/synthetic_media/bodycam_440hz_music_042profanity.mp4",
    "sample_rate_hz": 8000,
}


def test_911_8khz_distorted_bypasses_music_detection_and_demucs() -> None:
    def detector(_: dict) -> int:
        raise AssertionError("music detector must not run on 8 kHz 911 bypass")

    isolator = MusicGatedDemucsIsolator(music_detector=detector)
    result = isolator.process(
        ASSET_911,
        pre_demucs_hypothesis="help someone is breaking in",
        post_demucs_hypothesis="help someone is breaking in",
    )
    assert is_911_telephony_bypass(ASSET_911)
    assert result.music_detected == 0
    assert result.demucs_applied == 0
    assert result.asr_hypothesis_disagreement == 0.0
    assert result.human_audio_review_required == 0


def test_pure_speech_bypasses_demucs_when_detector_reports_no_music() -> None:
    isolator = MusicGatedDemucsIsolator(music_detector=lambda _: 0)
    result = isolator.process(
        ASSET_PURE_SPEECH,
        pre_demucs_hypothesis="the porch light was still on when I left",
        post_demucs_hypothesis="the porch light was still on when I left",
    )
    assert result.music_detected == 0
    assert result.demucs_applied == 0
    assert result.asr_hypothesis_disagreement == 0.0
    assert result.human_audio_review_required == 0


def test_bodycam_music_triggers_demucs_and_music_flag() -> None:
    demucs_ran: list[str] = []

    def detector(asset: dict) -> int:
        assert "440hz_music" in asset["raw_path"]
        return 1

    def demucs_stub(asset: dict) -> None:
        demucs_ran.append(asset["asset_id"])

    isolator = MusicGatedDemucsIsolator(
        music_detector=detector,
        demucs_runner=demucs_stub,
    )
    result = isolator.process(
        ASSET_BODYCAM,
        pre_demucs_hypothesis="officer stay back suspect is armed",
        post_demucs_hypothesis="officer stay back suspect is armed",
    )
    assert result.music_detected == 1
    assert result.demucs_applied == 1
    assert demucs_ran == ["foia_bodycam"]
    assert result.asr_hypothesis_disagreement == 0.0
    assert result.human_audio_review_required == 0


def test_asr_hypothesis_disagreement_is_token_ratio_not_wer() -> None:
    pre = "alpha beta gamma delta"
    post = "alpha beta zeta delta"
    disagreement = asr_hypothesis_disagreement(pre, post)
    assert disagreement == pytest.approx(1 / 4)

    longer = "alpha beta gamma delta echo"
    shorter = "alpha beta gamma"
    disagreement_asym = asr_hypothesis_disagreement(longer, shorter)
    wer_vs_reference = labeled_corpus_wer(longer, shorter)
    assert disagreement_asym == pytest.approx(2 / 5)
    assert wer_vs_reference == pytest.approx(2 / 3)
    assert disagreement_asym != wer_vs_reference


def test_high_disagreement_sets_human_audio_review_required() -> None:
    isolator = MusicGatedDemucsIsolator(music_detector=lambda _: 1)
    result = isolator.process(
        ASSET_BODYCAM,
        pre_demucs_hypothesis="one two three four five six",
        post_demucs_hypothesis="alpha bravo charlie delta echo foxtrot",
    )
    assert result.asr_hypothesis_disagreement > DISAGREEMENT_REVIEW_THRESHOLD
    assert result.human_audio_review_required == 1


def test_low_disagreement_skips_human_review_when_confidence_ok() -> None:
    isolator = MusicGatedDemucsIsolator(music_detector=lambda _: 1)
    result = isolator.process(
        ASSET_BODYCAM,
        pre_demucs_hypothesis="officer stay back",
        post_demucs_hypothesis="officer stay back",
        asr_confidence=0.92,
    )
    assert result.asr_hypothesis_disagreement == 0.0
    assert result.human_audio_review_required == 0


def test_low_asr_confidence_sets_human_audio_review_required() -> None:
    isolator = MusicGatedDemucsIsolator(music_detector=lambda _: 0)
    result = isolator.process(
        ASSET_PURE_SPEECH,
        pre_demucs_hypothesis="witness saw a dark sedan",
        post_demucs_hypothesis="witness saw a dark sedan",
        asr_confidence=0.70,
    )
    assert result.asr_hypothesis_disagreement == 0.0
    assert result.human_audio_review_required == 1


def test_labeled_corpus_wer_against_offline_reference_corpus() -> None:
    payload = json.loads(CORPUS.read_text(encoding="utf-8"))
    reference = payload["human_reference_transcript"]
    perfect = labeled_corpus_wer(payload["regression_hypothesis"], reference)
    assert perfect == 0.0
    degraded = labeled_corpus_wer(
        "officer stay back suspect has armed drop weapon now", reference
    )
    assert 0.0 < degraded < 1.0
    assert labeled_corpus_wer("", reference) == pytest.approx(1.0)


def test_injected_asr_provider_used_when_music_detected() -> None:
    calls: list[bool] = []

    def asr_provider(asset: dict, demucs_applied: bool) -> tuple[str, float]:
        calls.append(demucs_applied)
        if demucs_applied:
            return ("officer stay back suspect armed", 0.9)
        return ("officer stay back suspect is armed", 0.91)

    isolator = MusicGatedDemucsIsolator(
        music_detector=lambda _: 1,
        asr_provider=asr_provider,
    )
    result = isolator.process(ASSET_BODYCAM)
    assert calls == [False, True]
    assert result.demucs_applied == 1
    assert result.asr_hypothesis_disagreement == pytest.approx(1 / 6)
    assert result.human_audio_review_required == 1