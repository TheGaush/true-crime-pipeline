"""Track B MuckRock completed-FOIA-drop radar.

Offline only: completed drops are supplied through an injected ``fetch_fn``.
No sockets or HTTP clients in this module.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from shared_contracts.models import SeedPacket
from shared_contracts.version import CONTRACT_VERSION

TRACK_B_FOIA_RADAR = "TRACK_B_FOIA_RADAR"
MIN_SUBSTANTIVE_BYTES = 2048

SaturationFn = Callable[[Mapping[str, Any]], Mapping[str, Any]]
FetchFn = Callable[[], Mapping[str, Any]]

_DENIAL_KINDS = frozenset({"denial", "denial_letter", "denial_only"})
_FEE_WAIVER_KINDS = frozenset({"fee_waiver", "fee_waiver_correspondence"})
_CCTV_HINTS = re.compile(
    r"(?:\bcctv\b|body[\s_-]?cam|body[\s_-]?worn|surveillance|dash[\s_-]?cam)",
    re.IGNORECASE,
)


def _coerce_files(drop: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = drop.get("files")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    out: list[Mapping[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            out.append(item)
    return out


def _attachment_kind(file: Mapping[str, Any]) -> str:
    for key in ("attachment_kind", "role", "kind"):
        value = file.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower().replace("-", "_")
    name = str(file.get("filename", "")).lower()
    if "denial" in name:
        return "denial_letter"
    if "fee" in name and "waiver" in name:
        return "fee_waiver_correspondence"
    return "records"


def _content_type(file: Mapping[str, Any]) -> str:
    return str(file.get("content_type", "")).strip().lower()


def is_media_or_pdf_content_type(content_type: str) -> bool:
    """True for PDFs and broad media families (video/audio/image)."""
    if not content_type:
        return False
    if content_type.startswith("application/pdf"):
        return True
    return content_type.startswith(("video/", "audio/", "image/"))


def is_substantive_file(file: Mapping[str, Any]) -> bool:
    """Non-correspondence attachment meeting size and type invariants."""
    kind = _attachment_kind(file)
    if kind in _DENIAL_KINDS or kind in _FEE_WAIVER_KINDS:
        return False
    size = file.get("size_bytes")
    if not isinstance(size, int) or size < MIN_SUBSTANTIVE_BYTES:
        return False
    return is_media_or_pdf_content_type(_content_type(file))


def attachment_needs_third_party_cctv_inspection(file: Mapping[str, Any]) -> bool:
    """Pre-tag Agent 3 quarantine when an attachment looks like video/CCTV."""
    if not is_substantive_file(file):
        return False
    content_type = _content_type(file)
    if content_type.startswith("video/"):
        return True
    name = str(file.get("filename", ""))
    if _CCTV_HINTS.search(name):
        return True
    return "cctv" in content_type


def _short_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _drop_is_eligible(drop: Mapping[str, Any]) -> bool:
    files = _coerce_files(drop)
    if not files:
        return False
    if drop.get("drop_kind") == "empty":
        return False
    return any(is_substantive_file(f) for f in files)


def _seed_from_drop(drop: Mapping[str, Any], *, cctv: bool) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "track": TRACK_B_FOIA_RADAR,
        "lead_classification": "LEAD_ONLY",
        "suspect_names": _short_text_list(drop.get("suspect_names")),
        "victim_names": _short_text_list(drop.get("victim_names")),
        "incident_date_or_year": str(drop.get("incident_date_or_year", "")).strip(),
        "county_state": str(drop.get("county_state", "")).strip(),
        "docket_ids": _short_text_list(drop.get("docket_ids")),
        "unanswered_comment_questions": _short_text_list(
            drop.get("unanswered_comment_questions")
        ),
        "needs_third_party_cctv_inspection": cctv,
    }
    return packet


def _iter_drops(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return
    for item in results:
        if isinstance(item, Mapping):
            yield item


class MuckRockCompletedDropRadar:
    """Poll completed MuckRock FOIA drops and emit Track B seed dicts."""

    def __init__(
        self,
        fetch_fn: FetchFn,
        saturation_fn: SaturationFn,
    ) -> None:
        self._fetch_fn = fetch_fn
        self._saturation_fn = saturation_fn

    def poll(self) -> list[dict[str, Any]]:
        """Fetch completed drops, filter, gate on saturation, return seed dicts."""
        payload = self._fetch_fn()
        seeds: list[dict[str, Any]] = []
        for drop in _iter_drops(payload):
            if not _drop_is_eligible(drop):
                continue
            files = _coerce_files(drop)
            cctv = any(attachment_needs_third_party_cctv_inspection(f) for f in files)
            candidate = _seed_from_drop(drop, cctv=cctv)
            if not (
                candidate["suspect_names"]
                or candidate["victim_names"]
                or candidate["docket_ids"]
            ):
                continue
            gate = self._saturation_fn(candidate)
            if not isinstance(gate, Mapping):
                continue
            if gate.get("rejected"):
                continue
            SeedPacket.model_validate(
                {k: v for k, v in candidate.items() if k != "needs_third_party_cctv_inspection"}
            )
            seeds.append(candidate)
        return seeds