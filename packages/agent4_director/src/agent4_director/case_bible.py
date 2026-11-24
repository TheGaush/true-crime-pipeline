"""Lock ``CaseBible`` style DNA and keep crimson out of Flow keyframe PNGs."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import TypeAdapter
from shared_contracts.models import CaseBible, CharacterSpec, StyleDna

EVIDENCE_CRIMSON_HEX = "#C92A2A"
PAPER_BG_HEX = "#E9E2D2"
INK_HEX = "#1B1B1D"
MUTED_SLATE_HEX = "#3A4F66"
WARM_AMBER_HEX = "#C4A574"

DEFAULT_FLOW_KEYFRAME_SAFE_PALETTE: tuple[str, ...] = (
    INK_HEX,
    PAPER_BG_HEX,
    MUTED_SLATE_HEX,
    WARM_AMBER_HEX,
)

_DEFAULT_CHARACTERS: tuple[CharacterSpec, ...] = (
    CharacterSpec(character_id="detective_01", prop="notepad", color_hex=MUTED_SLATE_HEX),
    CharacterSpec(character_id="suspect_01", prop="coat", color_hex=WARM_AMBER_HEX),
)


class ColorChannel(Enum):
    """Where a resolved hex may legally appear."""

    FLOW_KEYFRAME = "flow_keyframe"
    REMOTION_OVERLAY = "remotion_overlay"
    STILL_2K_CALLOUT = "still_2k_callout"


SubstituteReason = Literal[
    "unchanged",
    "crimson_banned_in_flow_keyframe",
    "crimson_substituted_for_character_accent",
]


@dataclass(frozen=True, slots=True)
class ResolvedHex:
    """Result of palette routing for a requested accent color."""

    requested_hex: str
    resolved_hex: str
    channel: ColorChannel
    substituted: bool
    reason: SubstituteReason
    character_id: str | None = None


def _hex_key(value: str) -> str:
    return value.upper()


def _is_banned_crimson(style: StyleDna, color_hex: str) -> bool:
    banned = {_hex_key(style.evidence_crimson_hex), _hex_key(EVIDENCE_CRIMSON_HEX)}
    return _hex_key(color_hex) in banned


def build_style_dna(
    *,
    evidence_crimson_hex: str = EVIDENCE_CRIMSON_HEX,
    flow_keyframe_safe_palette: list[str] | None = None,
) -> StyleDna:
    palette = list(flow_keyframe_safe_palette or DEFAULT_FLOW_KEYFRAME_SAFE_PALETTE)
    return StyleDna(
        evidence_crimson_hex=evidence_crimson_hex,
        paper_bg_hex=PAPER_BG_HEX,
        ink_hex=INK_HEX,
        slate_hex=MUTED_SLATE_HEX,
        flow_keyframe_safe_palette=palette,
    )


def default_characters() -> list[CharacterSpec]:
    return list(_DEFAULT_CHARACTERS)


def lock_case_bible(
    episode_id: str,
    *,
    characters: list[CharacterSpec] | None = None,
    style_dna: StyleDna | None = None,
    locked_at: int | None = None,
) -> CaseBible:
    """Materialize and validate a locked ``CaseBible`` for an episode."""
    style = style_dna or build_style_dna()
    specs = characters if characters is not None else default_characters()
    stamp = int(time.time()) if locked_at is None else locked_at
    return CaseBible(
        episode_id=episode_id,
        style_dna_json=style,
        characters_json=specs,
        locked_at=stamp,
    )


def overlay_callout_hex(style: StyleDna) -> str:
    """Crimson reserved for Remotion overlays and 2K still callouts."""
    return style.evidence_crimson_hex


def _flow_substitute_hex(
    style: StyleDna,
    *,
    character_id: str | None = None,
) -> str:
    if character_id == "suspect_01":
        return WARM_AMBER_HEX
    if _hex_key(style.slate_hex) in {_hex_key(c) for c in style.flow_keyframe_safe_palette}:
        return style.slate_hex
    return MUTED_SLATE_HEX


def resolve_hex(
    style: StyleDna,
    requested_hex: str,
    *,
    channel: ColorChannel,
    character_id: str | None = None,
) -> ResolvedHex:
    """Route a requested hex to Flow-safe or overlay-allowed colors."""
    if channel in (ColorChannel.REMOTION_OVERLAY, ColorChannel.STILL_2K_CALLOUT):
        resolved = (
            style.evidence_crimson_hex
            if _is_banned_crimson(style, requested_hex)
            else requested_hex
        )
        return ResolvedHex(
            requested_hex=requested_hex,
            resolved_hex=resolved,
            channel=channel,
            substituted=False,
            reason="unchanged",
            character_id=character_id,
        )

    if not _is_banned_crimson(style, requested_hex):
        if _hex_key(requested_hex) not in {_hex_key(c) for c in style.flow_keyframe_safe_palette}:
            # Non-palette accents still allowed when they are not crimson.
            return ResolvedHex(
                requested_hex=requested_hex,
                resolved_hex=requested_hex,
                channel=channel,
                substituted=False,
                reason="unchanged",
                character_id=character_id,
            )
        return ResolvedHex(
            requested_hex=requested_hex,
            resolved_hex=requested_hex,
            channel=channel,
            substituted=False,
            reason="unchanged",
            character_id=character_id,
        )

    substitute = _flow_substitute_hex(style, character_id=character_id)
    reason: SubstituteReason = (
        "crimson_substituted_for_character_accent"
        if character_id
        else "crimson_banned_in_flow_keyframe"
    )
    return ResolvedHex(
        requested_hex=requested_hex,
        resolved_hex=substitute,
        channel=ColorChannel.FLOW_KEYFRAME,
        substituted=True,
        reason=reason,
        character_id=character_id,
    )


def resolve_character_color_for_flow(bible: CaseBible, character_id: str) -> ResolvedHex:
    """Map a character accent to a Flow Start/End PNG safe color."""
    spec = next(c for c in bible.characters_json if c.character_id == character_id)
    return resolve_hex(
        bible.style_dna_json,
        spec.color_hex,
        channel=ColorChannel.FLOW_KEYFRAME,
        character_id=character_id,
    )


def flow_palette_excludes_crimson(style: StyleDna) -> bool:
    return not any(_is_banned_crimson(style, color) for color in style.flow_keyframe_safe_palette)


_CASE_BIBLE_ADAPTER: TypeAdapter[CaseBible] = TypeAdapter(CaseBible)
_CHAR_ADAPTER: TypeAdapter[list[CharacterSpec]] = TypeAdapter(list[CharacterSpec])
_STYLE_ADAPTER: TypeAdapter[StyleDna] = TypeAdapter(StyleDna)


def ensure_case_bibles_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS case_bibles (
          episode_id        TEXT PRIMARY KEY,
          style_dna_json    TEXT NOT NULL,
          characters_json   TEXT NOT NULL,
          locked_at         INTEGER NOT NULL
        ) STRICT, WITHOUT ROWID
        """
    )


def persist_case_bible(connection: sqlite3.Connection, bible: CaseBible) -> None:
    ensure_case_bibles_table(connection)
    style_payload = _STYLE_ADAPTER.dump_python(
        bible.style_dna_json, mode="json", by_alias=False
    )
    characters_payload = _CHAR_ADAPTER.dump_python(
        bible.characters_json, mode="json", by_alias=False
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO case_bibles (episode_id, style_dna_json, characters_json, locked_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            bible.episode_id,
            json.dumps(style_payload, sort_keys=True, separators=(",", ":")),
            json.dumps(characters_payload, sort_keys=True, separators=(",", ":")),
            bible.locked_at,
        ),
    )
    connection.commit()


def load_case_bible(connection: sqlite3.Connection, episode_id: str) -> CaseBible | None:
    ensure_case_bibles_table(connection)
    row = connection.execute(
        "SELECT episode_id, style_dna_json, characters_json, locked_at FROM case_bibles WHERE episode_id = ?",
        (episode_id,),
    ).fetchone()
    if row is None:
        return None
    payload: dict[str, Any] = {
        "episode_id": row[0],
        "style_dna_json": json.loads(row[1]),
        "characters_json": json.loads(row[2]),
        "locked_at": row[3],
    }
    return _CASE_BIBLE_ADAPTER.validate_python(payload)