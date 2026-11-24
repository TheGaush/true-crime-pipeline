"""Clean-room seed firewall for Agent 1.

Offline only: no sockets, no HTTP clients, no subprocess network tools.

After authorized metadata (and optional owner-permitted transcript) extraction,
``CleanRoomFirewall`` emits a strictly factual ``SeedPacket`` and wipes any
fallback transcript buffer so creator script bytes do not survive Agent 1.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from shared_contracts.deprecated import DeprecatedIdentifierError
from shared_contracts.models import SeedPacket

MAX_FIELD_CHARS = 200
MAX_COMMENT_QUESTION_CHARS = 120

SEED_PACKET_FIELDS = frozenset(
    {
        "contract_version",
        "track",
        "lead_classification",
        "suspect_names",
        "victim_names",
        "incident_date_or_year",
        "county_state",
        "docket_ids",
        "unanswered_comment_questions",
    }
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "beat_order",
        "beat_outline",
        "creator_commentary",
        "creator_script",
        "narrative_outline",
        "story_outline",
        "transcript",
        "transcript_text",
        "video_script",
    }
)

_STRING_LIST_FIELDS = frozenset(
    {
        "suspect_names",
        "victim_names",
        "docket_ids",
        "unanswered_comment_questions",
    }
)

_NARRATIVE_VALUE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bnarrative\s+outline\b",
        r"\bbeat\s+order\b",
        r"\bcreator\s+commentary\b",
        r"\b(?:act|beat)\s+(?:i{1,3}|iv|one|two|three|four|\d+)\b",
        r"\bthree[\s-]act\b",
        r"\bcold\s+open\b",
        r"\bstory\s+arc\b",
    )
)

_TERMINATOR_RE = re.compile(r"[.!?]+")
_MULTI_CLAUSE_RE = re.compile(r"[.!]\s+\S")

_TRANSCRIPT_MIN_FINGERPRINT = 8


class CleanRoomFirewallError(ValueError):
    """Raised when a candidate seed fails clean-room policy."""


class CleanRoomFirewall:
    """Validate extraction output and purge fallback transcript buffers."""

    def emit_seed(
        self,
        candidate: Mapping[str, Any],
        *,
        transcript_buffer: str | Path | None = None,
    ) -> SeedPacket:
        """Return a factual ``SeedPacket`` and wipe ``transcript_buffer`` when provided."""
        buffer_path = Path(transcript_buffer) if transcript_buffer is not None else None
        transcript_text: str | None = None
        if buffer_path is not None and buffer_path.is_file():
            transcript_text = buffer_path.read_text(encoding="utf-8")

        packet = self._validate_candidate(candidate)
        if transcript_text:
            self._reject_transcript_residue(packet, transcript_text)
        if buffer_path is not None:
            self.wipe_transcript(buffer_path)
        return packet

    def wipe_transcript(self, buffer_path: str | Path) -> None:
        """Delete the fallback transcript file if it exists."""
        path = Path(buffer_path)
        if path.is_file():
            path.unlink()

    def _validate_candidate(self, candidate: Mapping[str, Any]) -> SeedPacket:
        if not isinstance(candidate, Mapping):
            raise CleanRoomFirewallError("seed candidate must be a mapping")

        forbidden = FORBIDDEN_PAYLOAD_KEYS.intersection(candidate.keys())
        if forbidden:
            raise CleanRoomFirewallError(
                f"forbidden narrative or commentary fields: {sorted(forbidden)}"
            )

        unknown = set(candidate.keys()) - SEED_PACKET_FIELDS
        if unknown:
            raise CleanRoomFirewallError(f"closed SeedPacket schema rejects extra fields: {sorted(unknown)}")

        normalized = dict(candidate)
        for field in _STRING_LIST_FIELDS:
            if field not in normalized:
                continue
            value = normalized[field]
            if value is None:
                normalized[field] = []
                continue
            if not isinstance(value, list):
                raise CleanRoomFirewallError(f"{field} must be a list of strings")
            cleaned: list[str] = []
            for index, item in enumerate(value):
                if not isinstance(item, str):
                    raise CleanRoomFirewallError(f"{field}[{index}] must be a string")
                self._enforce_max_length(item, where=f"{field}[{index}]")
                self._reject_narrative_markers(item, where=f"{field}[{index}]")
                if field == "unanswered_comment_questions":
                    self._validate_comment_question(item)
                cleaned.append(item)
            normalized[field] = cleaned

        for field in ("incident_date_or_year", "county_state"):
            if field in normalized:
                value = normalized[field]
                if not isinstance(value, str):
                    raise CleanRoomFirewallError(f"{field} must be a string")
                self._enforce_max_length(value, where=field)
                self._reject_narrative_markers(value, where=field)

        try:
            return SeedPacket.model_validate(normalized)
        except DeprecatedIdentifierError as exc:
            raise CleanRoomFirewallError(str(exc)) from exc
        except ValidationError as exc:
            raise CleanRoomFirewallError(str(exc)) from exc

    def _enforce_max_length(self, text: str, *, where: str) -> None:
        if not text:
            raise CleanRoomFirewallError(f"{where} must be a non-empty string")
        if len(text) > MAX_FIELD_CHARS:
            raise CleanRoomFirewallError(f"{where} exceeds {MAX_FIELD_CHARS} characters")

    def _reject_narrative_markers(self, text: str, *, where: str) -> None:
        for pattern in _NARRATIVE_VALUE_PATTERNS:
            if pattern.search(text):
                raise CleanRoomFirewallError(f"{where} contains narrative outline or beat-order markers")

    def _validate_comment_question(self, text: str) -> None:
        stripped = text.strip()
        if not stripped.endswith("?"):
            raise CleanRoomFirewallError("unanswered_comment_questions must be short questions ending with ?")
        body = stripped[:-1].strip()
        if not body:
            raise CleanRoomFirewallError("unanswered_comment_questions must be a non-empty question")
        if _MULTI_CLAUSE_RE.search(stripped):
            raise CleanRoomFirewallError(
                "unanswered_comment_questions must not smuggle multi-sentence narrative prose"
            )
        terminators = _TERMINATOR_RE.findall(stripped)
        if len(terminators) > 1:
            raise CleanRoomFirewallError("unanswered_comment_questions must be a single sentence")
        if len(stripped) > MAX_COMMENT_QUESTION_CHARS:
            raise CleanRoomFirewallError(
                f"unanswered_comment_questions must stay short (max {MAX_COMMENT_QUESTION_CHARS} characters)"
            )
        if len(body.split()) > 24:
            raise CleanRoomFirewallError("unanswered_comment_questions must stay short")

    def _reject_transcript_residue(self, packet: SeedPacket, transcript: str) -> None:
        fingerprint = transcript.strip()
        if len(fingerprint) < _TRANSCRIPT_MIN_FINGERPRINT:
            return
        for value in _iter_packet_strings(packet):
            if fingerprint in value:
                raise CleanRoomFirewallError("transcript buffer text appears in the emitted seed")


def _iter_packet_strings(packet: SeedPacket) -> Iterator[str]:
    yield packet.incident_date_or_year
    yield packet.county_state
    for collection in (
        packet.suspect_names,
        packet.victim_names,
        packet.docket_ids,
        packet.unanswered_comment_questions,
    ):
        yield from collection