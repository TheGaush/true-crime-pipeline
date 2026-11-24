"""Agent 4 director helpers."""

from agent4_director.case_bible import (
    EVIDENCE_CRIMSON_HEX,
    ColorChannel,
    ResolvedHex,
    build_style_dna,
    default_characters,
    lock_case_bible,
    overlay_callout_hex,
    resolve_character_color_for_flow,
    resolve_hex,
)
from shared_contracts.models import CaseBible

__all__ = [
    "EVIDENCE_CRIMSON_HEX",
    "CaseBible",
    "ColorChannel",
    "ResolvedHex",
    "build_style_dna",
    "default_characters",
    "lock_case_bible",
    "overlay_callout_hex",
    "resolve_character_color_for_flow",
    "resolve_hex",
]