"""Part 1 standalone end-to-end certification (offline, $0.00)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.part1_cert import (
    MAX_BATCH_DESK_PARKED,
    MAX_HERO_CLIPS,
    MAX_HERO_DURATION_SEC,
    run_part1_certification,
    render_cert_report,
)

REPORT_PATH = Path(__file__).resolve().parents[1] / "PART1_CERT_REPORT.md"

REQUIRED_CHECK_IDS = frozenset(
    {
        "disposition.reversed_killed",
        "disposition.affirmed_passes",
        "compliance.anonymization_explicit",
        "evidence.2k_illustrative_locked",
        "gatekeeper.ring_restricted",
        "gatekeeper.8khz_no_demucs",
        "director.plan_before_voice",
        "voice_sync.past_foia_slot",
        "director.hero_limits",
        "orchestrator.stub_zero_spend",
        "flow.gemini_omni_interactions",
        "conveyor.batch_desk_park",
        "flow.human_batch_desk",
    }
)


def test_part1_three_episodes_zero_spend() -> None:
    cert = run_part1_certification()
    assert len(cert.episodes) == 3
    assert cert.total_spend_micro_usd == 0
    assert all(ep.spend_micro_usd == 0 for ep in cert.episodes)


def test_part1_gemini_omni_episode_present() -> None:
    cert = run_part1_certification()
    modes = {ep.flow_backend_mode for ep in cert.episodes}
    assert "GEMINI_OMNI_INTERACTIONS" in modes
    gemini_eps = [
        ep for ep in cert.episodes if ep.flow_backend_mode == "GEMINI_OMNI_INTERACTIONS"
    ]
    assert any(ep.completed for ep in gemini_eps)


def test_part1_human_batch_desk_parking_at_most_three() -> None:
    cert = run_part1_certification()
    batch = next(
        ep for ep in cert.episodes if ep.flow_backend_mode == "HUMAN_BATCH_DESK"
    )
    park = next(c for c in batch.checks if c.check_id == "conveyor.batch_desk_park")
    assert park.passed
    assert "parked=3" in park.detail
    assert MAX_BATCH_DESK_PARKED == 3


def test_part1_all_mandatory_path_checks_pass() -> None:
    cert = run_part1_certification()
    seen = {c.check_id for c in cert.all_checks if c.passed}
    assert REQUIRED_CHECK_IDS <= seen, sorted(REQUIRED_CHECK_IDS - seen)
    assert cert.certified


def test_part1_hero_clip_law_limits() -> None:
    cert = run_part1_certification()
    hero = next(c for c in cert.all_checks if c.check_id == "director.hero_limits")
    assert hero.passed
    assert str(MAX_HERO_CLIPS) in hero.title
    assert str(MAX_HERO_DURATION_SEC) in hero.title


def test_part1_cert_report_verdict_wording() -> None:
    cert = run_part1_certification()
    report = render_cert_report(cert)
    assert "Part 1 is certified only if every check passes" in report
    assert cert.certified
    assert "YES" in report.split("**Certified:**")[1].split("\n")[0]


@pytest.fixture(scope="session", autouse=True)
def _write_cert_report() -> None:
    cert = run_part1_certification()
    REPORT_PATH.write_text(render_cert_report(cert), encoding="utf-8")