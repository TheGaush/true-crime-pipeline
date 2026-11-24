"""Granular provenance enforcer for Agent 3 FOIA media clearance.

Replaces naive domain whitelisting with per-asset rights fields aligned to
``foia_media_assets`` in ``schema/pipeline.sql``. No network I/O; Wikimedia
license checks accept injected ``extmetadata`` JSON.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

LicenseBasis = Literal[
    "US_FED_EMPLOYEE_17USC105",
    "STATE_PUBLIC_RECORD_PERMITTED",
    "CC0_PUBLIC_DOMAIN",
    "EXPLICIT_LICENSE_GRANT",
    "FAIR_USE_REVIEW_REQUIRED",
    "RESTRICTED_NO_REUSE",
]

RightsReviewStatus = Literal["NOT_STARTED", "IN_REVIEW", "APPROVED", "REJECTED"]

DEFAULT_RIGHTS_REVIEW_STATUS: RightsReviewStatus = "NOT_STARTED"

STATE_FOIA_STATUTE_BY_JURISDICTION: dict[str, str] = {
    "FL": "FL_SUNSHINE",
    "WA": "WA_PRA",
    "OH": "OH_PRA",
}

_FEDERAL_GOV_SUFFIXES = (
    ".gov",
    ".mil",
)

_STATE_TLD_EXEMPT_FEDERAL = frozenset(
    {
        "fbi.gov",
        "justice.gov",
        "usdoj.gov",
        "dhs.gov",
        "ice.gov",
        "dea.gov",
        "atf.gov",
        "usmarshals.gov",
        "uscourts.gov",
        "nps.gov",
        "usgs.gov",
        "cisa.gov",
        "secretservice.gov",
    }
)

_NEWS_DOMAIN_MARKERS = (
    "cnn.com",
    "foxnews.com",
    "nytimes.com",
    "washingtonpost.com",
    "reuters.com",
    "apnews.com",
    "usatoday.com",
    "nbcnews.com",
    "abcnews.go.com",
    "cbsnews.com",
    "huffpost.com",
    "dailymail.co.uk",
    "patch.com",
    "news.",
    "newspaper",
    "gazette.com",
    "herald.com",
    "tribune.com",
    "chronicle.com",
)

_YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})

_THIRD_PARTY_FILENAME = re.compile(
    r"(?:"
    r"ring[_\s-]?(?:doorbell)?|"
    r"doorbell[_\s-]?(?:neighbor|cctv)?|"
    r"walmart[_\s-]?(?:lobby[_\s-]?)?cam|"
    r"store[_\s-]?(?:security|camera|cctv)|"
    r"lobby[_\s-]?cam|"
    r"contractor[_\s-](?:media|footage|produced)|"
    r"gazette[_\s-]?scan|newspaper[_\s-]?scan|local[_\s-]?gazette"
    r")",
    re.IGNORECASE,
)

_THIRD_PARTY_ORIGIN_HINTS = re.compile(
    r"(?:ring|doorbell|walmart|store\s*cctv|contractor[-\s]produced|newspaper\s*scan)",
    re.IGNORECASE,
)

_911_DEATH_OR_PRIVATE_RESIDENCE = re.compile(
    r"(?:death|deceased|fatal|coroner|private[_\s-]?residence|"
    r"home[_\s-]?address|residential[_\s-]?911)",
    re.IGNORECASE,
)

_WIKIMEDIA_ALLOWED = frozenset(
    {
        "cc0",
        "cc0 1.0",
        "cc0 1.0 universal",
        "public domain",
        "pd",
        "pd-self",
        "cc-zero",
    }
)

_WIKIMEDIA_RESTRICTED_MARKERS = ("by-nc", "by-sa", "by-nc-nd", "by-nc-sa")


@dataclass(frozen=True, slots=True)
class ProvenanceBlock:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class AssetProvenanceRecord:
    """Component-level provenance row suitable for ``foia_media_assets``."""

    source_domain: str
    source_url: str
    creator_entity: str
    rights_holder: str
    license_basis: LicenseBasis
    permitted_uses_json: str
    contains_third_party_attach: int
    rights_review_status: RightsReviewStatus
    media_kind: str
    raw_path: str
    block: ProvenanceBlock | None = None

    @property
    def cleared_for_ingest(self) -> bool:
        return self.block is None and self.license_basis != "RESTRICTED_NO_REUSE"


@dataclass(frozen=True, slots=True)
class WikimediaLicenseVerdict:
    admitted: bool
    license_basis: LicenseBasis | None
    license_short_name: str
    block: ProvenanceBlock | None = None


def _host_from_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return (parsed.hostname or "").lower().strip(".")


def _normalize_domain(source_domain: str, source_url: str) -> str:
    domain = source_domain.lower().strip()
    if not domain:
        domain = _host_from_url(source_url)
    return domain.strip(".")


_STATE_GOV_SUFFIXES = (".wa.gov", ".fl.gov", ".ohio.gov", ".oh.gov")


def _is_federal_gov_host(host: str) -> bool:
    if host in _STATE_TLD_EXEMPT_FEDERAL:
        return True
    if not host.endswith(".gov"):
        return False
    if any(host.endswith(suffix) for suffix in _STATE_GOV_SUFFIXES):
        return False
    if host.startswith(("florida", "washington", "ohio")) and host.endswith(".gov"):
        return False
    return True


_STATE_US_HOST = re.compile(r"\.state\.[a-z]{2}\.us$", re.IGNORECASE)


def _is_state_gov_host(host: str) -> bool:
    if _is_federal_gov_host(host):
        return False
    if host.endswith(".gov"):
        return True
    return _STATE_US_HOST.search(host) is not None


def _domain_blocked(source_domain: str, source_url: str) -> ProvenanceBlock | None:
    host = _normalize_domain(source_domain, source_url)
    if host in _YOUTUBE_HOSTS or host.endswith(".youtube.com"):
        return ProvenanceBlock(
            code="PROVENANCE_THIRD_PARTY_YOUTUBE_BLOCKED",
            detail="Third-party YouTube URLs are metadata-only leads; media bytes blocked.",
        )
    if any(marker in host for marker in _NEWS_DOMAIN_MARKERS):
        return ProvenanceBlock(
            code="PROVENANCE_NEWS_DOMAIN_BLOCKED",
            detail=f"News domain {host!r} cannot supply cleared media bytes.",
        )
    return None


def _detect_third_party_attachment(
    *,
    filename: str,
    origin_label: str = "",
    creator_entity: str = "",
    attachment_tags: tuple[str, ...] = (),
) -> bool:
    joined_tags = " ".join(attachment_tags)
    if _THIRD_PARTY_FILENAME.search(filename):
        return True
    if origin_label and _THIRD_PARTY_ORIGIN_HINTS.search(origin_label):
        return True
    if joined_tags and _THIRD_PARTY_ORIGIN_HINTS.search(joined_tags):
        return True
    lowered_creator = creator_entity.lower()
    if "private citizen" in lowered_creator and ("ring" in lowered_creator or "cctv" in lowered_creator):
        return True
    if "contractor" in lowered_creator and "federal" not in lowered_creator:
        return True
    return False


def _restricted_attachment_record(
    *,
    source_domain: str,
    source_url: str,
    filename: str,
    media_kind: str,
    creator_entity: str,
    detail: str,
) -> AssetProvenanceRecord:
    return AssetProvenanceRecord(
        source_domain=source_domain,
        source_url=source_url,
        creator_entity=creator_entity,
        rights_holder="Private Rights Holder",
        license_basis="RESTRICTED_NO_REUSE",
        permitted_uses_json=json.dumps([]),
        contains_third_party_attach=1,
        rights_review_status=DEFAULT_RIGHTS_REVIEW_STATUS,
        media_kind=media_kind,
        raw_path=filename,
        block=ProvenanceBlock(code="PROVENANCE_THIRD_PARTY_ATTACHMENT", detail=detail),
    )


def evaluate_wikimedia_license(extmetadata: dict[str, Any]) -> WikimediaLicenseVerdict:
    """Admit only CC0 / Public Domain Wikimedia assets (injected metadata)."""
    license_entry = extmetadata.get("LicenseShortName") or extmetadata.get("License")
    if isinstance(license_entry, dict):
        raw = str(license_entry.get("value", "")).strip()
    else:
        raw = str(license_entry or "").strip()
    normalized = " ".join(raw.lower().split())

    if not normalized:
        return WikimediaLicenseVerdict(
            admitted=False,
            license_basis=None,
            license_short_name=raw,
            block=ProvenanceBlock(
                code="PROVENANCE_LICENSE_RESTRICTED",
                detail="Missing Wikimedia LicenseShortName.",
            ),
        )

    if any(marker in normalized for marker in _WIKIMEDIA_RESTRICTED_MARKERS):
        return WikimediaLicenseVerdict(
            admitted=False,
            license_basis=None,
            license_short_name=raw,
            block=ProvenanceBlock(
                code="PROVENANCE_LICENSE_RESTRICTED",
                detail=f"Wikimedia license {raw!r} is not CC0/Public Domain.",
            ),
        )

    if normalized in _WIKIMEDIA_ALLOWED or normalized.startswith("cc0"):
        return WikimediaLicenseVerdict(
            admitted=True,
            license_basis="CC0_PUBLIC_DOMAIN",
            license_short_name=raw,
            block=None,
        )

    if "public domain" in normalized:
        return WikimediaLicenseVerdict(
            admitted=True,
            license_basis="CC0_PUBLIC_DOMAIN",
            license_short_name=raw,
            block=None,
        )

    return WikimediaLicenseVerdict(
        admitted=False,
        license_basis=None,
        license_short_name=raw,
        block=ProvenanceBlock(
            code="PROVENANCE_LICENSE_RESTRICTED",
            detail=f"Wikimedia license {raw!r} is not CC0/Public Domain.",
        ),
    )


def can_advance_rights_review(
    current: RightsReviewStatus,
    target: RightsReviewStatus,
    *,
    license_basis: LicenseBasis,
    reviewed_by: str | None,
    reviewed_at: int | None,
) -> bool:
    """Mirror SQLite CHECK: RESTRICTED_NO_REUSE can never reach APPROVED."""
    if target == "APPROVED" and license_basis == "RESTRICTED_NO_REUSE":
        return False
    if target == "APPROVED" and (not reviewed_by or reviewed_at is None):
        return False
    allowed: dict[RightsReviewStatus, frozenset[RightsReviewStatus]] = {
        "NOT_STARTED": frozenset({"IN_REVIEW", "REJECTED"}),
        "IN_REVIEW": frozenset({"APPROVED", "REJECTED"}),
        "APPROVED": frozenset(),
        "REJECTED": frozenset({"IN_REVIEW"}),
    }
    return target in allowed.get(current, frozenset())


@dataclass(slots=True)
class GranularProvenanceEnforcer:
    """Classify staged FOIA / archival assets with component-level rights proof."""

    jurisdiction: str = ""

    def evaluate_wikimedia(self, extmetadata: dict[str, Any]) -> WikimediaLicenseVerdict:
        return evaluate_wikimedia_license(extmetadata)

    def evaluate_foia_attachment(
        self,
        *,
        source_domain: str,
        source_url: str,
        filename: str,
        media_kind: str,
        creator_entity: str = "",
        origin_label: str = "",
        is_federal_employee_official_duty: bool = False,
        attachment_tags: tuple[str, ...] = (),
        audio_descriptor: str = "",
    ) -> AssetProvenanceRecord:
        block = _domain_blocked(source_domain, source_url)
        if block is not None:
            return AssetProvenanceRecord(
                source_domain=_normalize_domain(source_domain, source_url),
                source_url=source_url,
                creator_entity=creator_entity or "Unknown",
                rights_holder="Blocked Source",
                license_basis="RESTRICTED_NO_REUSE",
                permitted_uses_json=json.dumps([]),
                contains_third_party_attach=0,
                rights_review_status=DEFAULT_RIGHTS_REVIEW_STATUS,
                media_kind=media_kind,
                raw_path=filename,
                block=block,
            )

        if _detect_third_party_attachment(
            filename=filename,
            origin_label=origin_label,
            creator_entity=creator_entity,
            attachment_tags=attachment_tags,
        ):
            return _restricted_attachment_record(
                source_domain=_normalize_domain(source_domain, source_url),
                source_url=source_url,
                filename=filename,
                media_kind=media_kind,
                creator_entity=creator_entity or "Third-Party Attachment",
                detail=f"Embedded third-party media {filename!r} is RESTRICTED_NO_REUSE.",
            )

        host = _normalize_domain(source_domain, source_url)
        permitted: list[str] = []
        license_basis: LicenseBasis = "FAIR_USE_REVIEW_REQUIRED"
        rights_holder = "Unknown"
        resolved_creator = creator_entity or "Unknown"

        if is_federal_employee_official_duty and _is_federal_gov_host(host):
            license_basis = "US_FED_EMPLOYEE_17USC105"
            resolved_creator = creator_entity or "US Federal Employee"
            rights_holder = "Public Domain (17 USC 105)"
            permitted = ["documentary_excerpt", "transformative_commentary"]
        elif self.jurisdiction.upper() in STATE_FOIA_STATUTE_BY_JURISDICTION and _is_state_gov_host(host):
            statute = STATE_FOIA_STATUTE_BY_JURISDICTION[self.jurisdiction.upper()]
            descriptor = f"{filename} {audio_descriptor}".strip()
            if media_kind == "call_911_wav" and _911_DEATH_OR_PRIVATE_RESIDENCE.search(descriptor):
                license_basis = "FAIR_USE_REVIEW_REQUIRED"
                permitted = [statute, "911_death_or_private_residence_review_required"]
            else:
                license_basis = "STATE_PUBLIC_RECORD_PERMITTED"
                permitted = [statute, "public_record_reuse_subject_to_statute"]

        return AssetProvenanceRecord(
            source_domain=host,
            source_url=source_url,
            creator_entity=resolved_creator,
            rights_holder=rights_holder,
            license_basis=license_basis,
            permitted_uses_json=json.dumps(permitted),
            contains_third_party_attach=0,
            rights_review_status=DEFAULT_RIGHTS_REVIEW_STATUS,
            media_kind=media_kind,
            raw_path=filename,
            block=None,
        )