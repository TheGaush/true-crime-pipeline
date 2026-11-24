"""Offline granular provenance enforcer tests (Tasks 045)."""

from __future__ import annotations

import json

import pytest

from agent3_gatekeeper.provenance_whitelist import (
    DEFAULT_RIGHTS_REVIEW_STATUS,
    GranularProvenanceEnforcer,
    STATE_FOIA_STATUTE_BY_JURISDICTION,
    can_advance_rights_review,
    evaluate_wikimedia_license,
)


@pytest.fixture
def enforcer() -> GranularProvenanceEnforcer:
    return GranularProvenanceEnforcer()


# --- 1) Federal 17 USC § 105 narrowed ---


def test_federal_employee_official_duty_gets_17usc105_not_auto_approved(
    enforcer: GranularProvenanceEnforcer,
) -> None:
    record = enforcer.evaluate_foia_attachment(
        source_domain="fbi.gov",
        source_url="https://fbi.gov/releases/bwc_01.mp4",
        filename="officer_bodycam.mp4",
        media_kind="bodycam_mp4",
        creator_entity="US Federal Employee",
        is_federal_employee_official_duty=True,
    )

    assert record.license_basis == "US_FED_EMPLOYEE_17USC105"
    assert record.rights_review_status == DEFAULT_RIGHTS_REVIEW_STATUS
    assert record.rights_review_status != "APPROVED"
    assert record.contains_third_party_attach == 0
    assert record.cleared_for_ingest is True


def test_state_gov_host_does_not_inherit_federal_17usc105(
    enforcer: GranularProvenanceEnforcer,
) -> None:
    fl_enforcer = GranularProvenanceEnforcer(jurisdiction="FL")
    record = fl_enforcer.evaluate_foia_attachment(
        source_domain="fdle.state.fl.us",
        source_url="https://fdle.state.fl.us/media/bwc.mp4",
        filename="state_troop_bwc.mp4",
        media_kind="bodycam_mp4",
        creator_entity="State Agency Officer",
        is_federal_employee_official_duty=False,
    )

    assert record.license_basis == "STATE_PUBLIC_RECORD_PERMITTED"
    assert "FL_SUNSHINE" in json.loads(record.permitted_uses_json)
    assert record.license_basis != "US_FED_EMPLOYEE_17USC105"


def test_federal_gov_url_without_employee_duty_is_not_17usc105(
    enforcer: GranularProvenanceEnforcer,
) -> None:
    record = enforcer.evaluate_foia_attachment(
        source_domain="fbi.gov",
        source_url="https://fbi.gov/contractor_clip.mp4",
        filename="contractor_b_roll.mp4",
        media_kind="bodycam_mp4",
        creator_entity="Private Contractor",
        is_federal_employee_official_duty=False,
    )

    assert record.license_basis == "RESTRICTED_NO_REUSE"
    assert record.contains_third_party_attach == 1


# --- 2) State FOIA statute matrix & 911 restrictions ---


@pytest.mark.parametrize(
    ("jurisdiction", "statute"),
    [
        ("FL", "FL_SUNSHINE"),
        ("WA", "WA_PRA"),
        ("OH", "OH_PRA"),
    ],
)
def test_state_foia_statute_config(jurisdiction: str, statute: str) -> None:
    assert STATE_FOIA_STATUTE_BY_JURISDICTION[jurisdiction] == statute

    enforcer = GranularProvenanceEnforcer(jurisdiction=jurisdiction)
    record = enforcer.evaluate_foia_attachment(
        source_domain=f"agency.{jurisdiction.lower()}.gov",
        source_url=f"https://agency.{jurisdiction.lower()}.gov/dispatch.wav",
        filename="routine_dispatch.wav",
        media_kind="call_911_wav",
        creator_entity="State Agency",
    )
    assert record.license_basis == "STATE_PUBLIC_RECORD_PERMITTED"
    assert statute in json.loads(record.permitted_uses_json)


def test_state_911_private_residence_not_cleared_by_gov_host() -> None:
    enforcer = GranularProvenanceEnforcer(jurisdiction="WA")
    record = enforcer.evaluate_foia_attachment(
        source_domain="kingcounty.wa.gov",
        source_url="https://kingcounty.wa.gov/911/private_residence_death_call.wav",
        filename="private_residence_911_death.wav",
        media_kind="call_911_wav",
        creator_entity="County Dispatcher",
        audio_descriptor="fatal injury private residence",
    )

    assert record.license_basis == "FAIR_USE_REVIEW_REQUIRED"
    assert record.rights_review_status == "NOT_STARTED"
    assert "911_death_or_private_residence_review_required" in json.loads(record.permitted_uses_json)


# --- 3) FOIA third-party attachment quarantine ---


@pytest.mark.parametrize(
    "filename",
    [
        "ring_doorbell_neighbor.mp4",
        "walmart_lobby_cam.mp4",
        "local_gazette_scan.pdf",
        "contractor_media_take003.mp4",
    ],
)
def test_third_party_attachments_restricted_no_reuse(
    enforcer: GranularProvenanceEnforcer,
    filename: str,
) -> None:
    record = enforcer.evaluate_foia_attachment(
        source_domain="muckrock.com",
        source_url="https://muckrock.com/foia/zip/123",
        filename=filename,
        media_kind="bodycam_mp4",
        creator_entity="Private Citizen",
        origin_label="muckrock:foia_zip",
    )

    assert record.license_basis == "RESTRICTED_NO_REUSE"
    assert record.contains_third_party_attach == 1
    assert record.cleared_for_ingest is False
    assert can_advance_rights_review(
        record.rights_review_status,
        "APPROVED",
        license_basis=record.license_basis,
        reviewed_by="rev_1",
        reviewed_at=1000,
    ) is False


# --- 4) Wikimedia extmetadata license gate ---


@pytest.mark.parametrize(
    "license_short",
    [
        "CC0",
        "CC0 1.0 Universal",
        "Public domain",
    ],
)
def test_wikimedia_admits_cc0_and_public_domain(license_short: str) -> None:
    verdict = evaluate_wikimedia_license(
        {"LicenseShortName": {"value": license_short}},
    )
    assert verdict.admitted is True
    assert verdict.license_basis == "CC0_PUBLIC_DOMAIN"
    assert verdict.block is None


@pytest.mark.parametrize(
    "license_short",
    [
        "CC BY-NC 4.0",
        "CC BY-SA 4.0",
        "CC BY-NC-ND 4.0",
    ],
)
def test_wikimedia_rejects_restricted_licenses(license_short: str) -> None:
    verdict = evaluate_wikimedia_license({"LicenseShortName": license_short})
    assert verdict.admitted is False
    assert verdict.block is not None
    assert verdict.block.code == "PROVENANCE_LICENSE_RESTRICTED"


def test_wikimedia_via_enforcer(enforcer: GranularProvenanceEnforcer) -> None:
    verdict = enforcer.evaluate_wikimedia(
        {"LicenseShortName": {"value": "CC BY-NC-ND 4.0"}}
    )
    assert verdict.admitted is False


# --- News / YouTube unconditional blocks ---


@pytest.mark.parametrize(
    "url",
    [
        "https://www.cnn.com/video/evidence.mp4",
        "https://foxnews.com/local/crime-clip",
    ],
)
def test_news_domains_blocked(enforcer: GranularProvenanceEnforcer, url: str) -> None:
    record = enforcer.evaluate_foia_attachment(
        source_domain="",
        source_url=url,
        filename="clip.mp4",
        media_kind="bodycam_mp4",
    )
    assert record.block is not None
    assert record.block.code == "PROVENANCE_NEWS_DOMAIN_BLOCKED"
    assert record.license_basis == "RESTRICTED_NO_REUSE"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
    ],
)
def test_third_party_youtube_blocked(enforcer: GranularProvenanceEnforcer, url: str) -> None:
    record = enforcer.evaluate_foia_attachment(
        source_domain="youtube.com",
        source_url=url,
        filename="mirror.mp4",
        media_kind="bodycam_mp4",
    )
    assert record.block is not None
    assert record.block.code == "PROVENANCE_THIRD_PARTY_YOUTUBE_BLOCKED"


def test_rights_review_never_defaults_to_approved(
    enforcer: GranularProvenanceEnforcer,
) -> None:
    record = enforcer.evaluate_foia_attachment(
        source_domain="fbi.gov",
        source_url="https://fbi.gov/1",
        filename="federal_bwc.mp4",
        media_kind="bodycam_mp4",
        creator_entity="US Federal Employee",
        is_federal_employee_official_duty=True,
    )
    assert record.rights_review_status == "NOT_STARTED"