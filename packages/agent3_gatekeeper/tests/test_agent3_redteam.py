"""Offline Agent 3 red-team trap suite (Task 059). Fixtures only. No network."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent3_gatekeeper.pipeline import (
    DISAGREEMENT_REVIEW_THRESHOLD,
    EPISODE_INTRO_END_MS,
    NINE_TRAP_IDS,
    RULE_09_CODE,
    Agent3GatekeeperService,
    TRAP_BODYCAM_MUSIC_ASR,
    TRAP_NEWS_HEDGING,
    TRAP_PROFANITY_COLD_OPEN,
    TRAP_RING_CCTV,
    TRAP_SCRIPT_POLICY,
    TRAP_SPOKEN_PII,
    TRAP_VISUAL_COMPLIANCE,
    TRAP_WIKIMEDIA_BY_NC,
    TRAP_911_DEMUCS_BYPASS,
    asr_hypothesis_disagreement,
    evaluate_ring_cctv_in_foia_zip,
    evaluate_wikimedia_license,
    is_911_telephony_bypass,
    labeled_corpus_wer,
    post_scrub_asr_clean,
    profanity_in_source_window,
)

REPO = Path(__file__).resolve().parents[3]
SYNTHETIC = REPO / "fixtures" / "synthetic_media"
SERVICE = Agent3GatekeeperService(REPO)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "pipeline.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


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


def test_ring_cctv_in_muckrock_zip_is_restricted_no_reuse() -> None:
    verdict = SERVICE.trap_ring_cctv()
    record = evaluate_ring_cctv_in_foia_zip(
        source_url="https://muckrock.com/foia/zip/ring-bundle",
        filename="ring_doorbell_neighbor.mp4",
    )
    assert record.license_basis == "RESTRICTED_NO_REUSE"
    assert verdict.trap_id == TRAP_RING_CCTV
    assert verdict.defended is True


def test_wikimedia_cc_by_nc_is_rejected() -> None:
    verdict = SERVICE.trap_wikimedia_by_nc()
    license_verdict = evaluate_wikimedia_license({"LicenseShortName": "CC BY-NC 4.0"})
    assert license_verdict.admitted is False
    assert verdict.trap_id == TRAP_WIKIMEDIA_BY_NC
    assert verdict.defended is True


def test_8khz_911_skips_demucs() -> None:
    verdict = SERVICE.trap_911_demucs_bypass()
    asset = {
        "media_kind": "call_911_wav",
        "raw_path": str(SYNTHETIC / "911_8khz_distorted.wav"),
        "sample_rate_hz": 8000,
    }
    assert is_911_telephony_bypass(asset)
    assert verdict.trap_id == TRAP_911_DEMUCS_BYPASS
    assert verdict.defended is True
    assert verdict.evidence["demucs_applied"] == 0


def test_bodycam_music_tracks_disagreement_and_labeled_wer_separately() -> None:
    verdict = SERVICE.trap_bodycam_music_asr()
    pre = "officer stay back suspect is armed drop weapon now"
    post = "officer stay back suspect is armed drop the weapon now"
    reference = "officer stay back suspect is armed drop the weapon now"
    disagreement = asr_hypothesis_disagreement(pre, post)
    wer = labeled_corpus_wer(post, reference)
    assert disagreement <= DISAGREEMENT_REVIEW_THRESHOLD
    assert disagreement != wer
    assert verdict.trap_id == TRAP_BODYCAM_MUSIC_ASR
    assert verdict.defended is True
    assert verdict.evidence["labeled_corpus_wer"] == 0.0


def test_profanity_at_42s_mapped_to_open_is_bleeped() -> None:
    notes = SERVICE._media_notes()
    profanity = [notes["profanity_source_timeline_ms"]]
    hits = profanity_in_source_window(profanity, 40_000, 52_000)
    assert len(hits) == 1
    assert hits[0].start_ms == 42_000

    verdict = SERVICE.trap_profanity_cold_open_bleep()
    assert verdict.trap_id == TRAP_PROFANITY_COLD_OPEN
    assert verdict.defended is True
    assert verdict.evidence["mute_count"] >= 1


def test_post_scrub_asr_fails_when_profanity_not_bleeped() -> None:
    from agent3_gatekeeper.pipeline import TimelineInterval, plan_intro_mutes

    notes = SERVICE._media_notes()
    mutes = plan_intro_mutes(
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=EPISODE_INTRO_END_MS,
        profanity_intervals=[notes["profanity_source_timeline_ms"]],
        spoken_pii_intervals=[],
    )
    assert post_scrub_asr_clean("officer said shit on tape", mutes) is False
    assert post_scrub_asr_clean("officer said on tape", mutes) is True


def test_spoken_phone_and_address_are_muted() -> None:
    verdict = SERVICE.trap_spoken_pii_muted()
    transcript = SERVICE._911_transcript()
    kinds = {span["kind"] for span in transcript["pii_spans"]}
    assert "phone" in kinds
    assert "street" in kinds
    assert verdict.trap_id == TRAP_SPOKEN_PII
    assert verdict.defended is True


def test_tv_logo_and_bystander_face_fail_compliance() -> None:
    verdict = SERVICE.trap_visual_compliance()
    assert verdict.trap_id == TRAP_VISUAL_COMPLIANCE
    assert verdict.defended is True
    assert verdict.evidence["watermark_clean"] == 0


def test_graphic_how_and_legal_advice_rewritten() -> None:
    verdict = SERVICE.trap_script_policy()
    assert verdict.trap_id == TRAP_SCRIPT_POLICY
    assert verdict.defended is True
    assert "you should" not in verdict.evidence["legal_rewritten"].casefold()
    assert "how the suspect killed" not in verdict.evidence["graphic_rewritten"].casefold()


def test_unhedged_news_report_fails() -> None:
    verdict = SERVICE.trap_news_hedging()
    assert verdict.trap_id == TRAP_NEWS_HEDGING
    assert verdict.defended is True
    assert verdict.detail == RULE_09_CODE


def test_overlapping_spoken_pii_and_profanity_both_muted() -> None:
    verdict = SERVICE.trap_overlap_pii_profanity()
    assert verdict.defended is True
    assert "phone+profanity" in verdict.detail or "+" in verdict.detail


def test_full_redteam_suite_passes_all_nine_traps() -> None:
    report = SERVICE.run_redteam_suite()
    trap_map = {t.trap_id: t for t in report.traps}
    for trap_id in NINE_TRAP_IDS:
        assert trap_id in trap_map, trap_id
        assert trap_map[trap_id].defended, trap_map[trap_id].code
    assert report.defended_count >= len(NINE_TRAP_IDS)
    assert report.passed is True