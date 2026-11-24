"""RULE_08: cold-open rotation, turning-point floor, brand-coherent thumbnail novelty."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RULE_ID = "RULE_08"

MIN_TURNING_POINTS = 3
RECENT_ARCHETYPE_WINDOW = 5
RECENT_THUMBNAIL_WINDOW = 3

CHANNEL_TYPOGRAPHY = "documentary_serif_sans_lockup"
CHANNEL_FRAMING = "charcoal_parchment_high_contrast"

COMPOSITION_ARCHETYPES = frozenset(
    {
        "doorway_silhouette",
        "desk_evidence_closeup",
        "map_trajectory_split",
        "redacted_dossier_reveal",
    }
)
ACCENT_MOODS = frozenset(
    {
        "muted_amber",
        "slate_blue",
        "deep_crimson_stamp",
    }
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_QUERIES_PATH = _REPO_ROOT / "schema" / "queries.sql"


@dataclass(frozen=True, slots=True)
class ThumbnailBrandSpec:
    typography: str
    framing: str
    focal_subject: str
    composition: str
    accent_mood: str

    def novelty_axes(self) -> tuple[str, str, str]:
        return (self.focal_subject, self.composition, self.accent_mood)

    def to_mood_vec_json(self) -> str:
        return json.dumps(
            {
                "typography": self.typography,
                "framing": self.framing,
                "focal_subject": self.focal_subject,
                "composition": self.composition,
                "accent_mood": self.accent_mood,
            },
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class Rule08Proposal:
    episode_id: str
    cold_open_archetype: str
    turning_point_count: int
    thumbnail: ThumbnailBrandSpec


@dataclass(frozen=True, slots=True)
class Rule08EntropyContext:
    """Recent publish fingerprints; CTR weights are advisory only (never bypass rotation)."""

    recent_cold_open_archetypes: tuple[str, ...] = ()
    recent_thumbnail_specs: tuple[ThumbnailBrandSpec, ...] = ()
    archetype_ctr_pct: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Rule08Violation:
    code: str
    message: str
    rule_id: str = RULE_ID


@dataclass(slots=True)
class Rule08Result:
    violations: list[Rule08Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def parse_thumbnail_mood_vec(raw: str | None) -> ThumbnailBrandSpec | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    required = (
        "typography",
        "framing",
        "focal_subject",
        "composition",
        "accent_mood",
    )
    if any(key not in payload for key in required):
        return None
    return ThumbnailBrandSpec(
        typography=str(payload["typography"]),
        framing=str(payload["framing"]),
        focal_subject=str(payload["focal_subject"]),
        composition=str(payload["composition"]),
        accent_mood=str(payload["accent_mood"]),
    )


def _check_turning_points(proposal: Rule08Proposal) -> list[Rule08Violation]:
    if proposal.turning_point_count >= MIN_TURNING_POINTS:
        return []
    return [
        Rule08Violation(
            code="TURNING_POINT_MIN",
            message=(
                f"turning_point_count {proposal.turning_point_count} "
                f"< {MIN_TURNING_POINTS} evidence-backed insights required"
            ),
        )
    ]


def _check_cold_open_rotation(
    proposal: Rule08Proposal,
    context: Rule08EntropyContext,
) -> list[Rule08Violation]:
    if not context.recent_cold_open_archetypes:
        return []
    previous = context.recent_cold_open_archetypes[0]
    if proposal.cold_open_archetype != previous:
        return []
    ctr = context.archetype_ctr_pct.get(proposal.cold_open_archetype)
    ctr_note = (
        f" (ctr_pct={ctr:.1f} ignored)" if ctr is not None else ""
    )
    return [
        Rule08Violation(
            code="COLD_OPEN_REPEAT",
            message=(
                f"cold_open_archetype {proposal.cold_open_archetype!r} repeats "
                f"previous episode{ctr_note}; RULE_08 forbids back-to-back archetypes"
            ),
        )
    ]


def _check_brand_locks(thumbnail: ThumbnailBrandSpec) -> list[Rule08Violation]:
    violations: list[Rule08Violation] = []
    if thumbnail.typography != CHANNEL_TYPOGRAPHY:
        violations.append(
            Rule08Violation(
                code="BRAND_TYPOGRAPHY",
                message=(
                    f"thumbnail typography must stay {CHANNEL_TYPOGRAPHY!r}, "
                    f"got {thumbnail.typography!r}"
                ),
            )
        )
    if thumbnail.framing != CHANNEL_FRAMING:
        violations.append(
            Rule08Violation(
                code="BRAND_FRAMING",
                message=(
                    f"thumbnail framing must stay {CHANNEL_FRAMING!r}, "
                    f"got {thumbnail.framing!r}"
                ),
            )
        )
    if thumbnail.composition not in COMPOSITION_ARCHETYPES:
        violations.append(
            Rule08Violation(
                code="THUMBNAIL_COMPOSITION",
                message=f"unknown composition archetype {thumbnail.composition!r}",
            )
        )
    if thumbnail.accent_mood not in ACCENT_MOODS:
        violations.append(
            Rule08Violation(
                code="THUMBNAIL_ACCENT",
                message=f"unknown accent mood {thumbnail.accent_mood!r}",
            )
        )
    return violations


def _check_thumbnail_novelty(
    thumbnail: ThumbnailBrandSpec,
    context: Rule08EntropyContext,
) -> list[Rule08Violation]:
    if not context.recent_thumbnail_specs:
        return []
    prior = context.recent_thumbnail_specs[0]
    if thumbnail.novelty_axes() == prior.novelty_axes():
        return [
            Rule08Violation(
                code="THUMBNAIL_NO_NOVELTY",
                message=(
                    "thumbnail must rotate focal_subject, composition, or "
                    "accent_mood while preserving channel typography and framing"
                ),
            )
        ]
    return []


def validate_rule_08(
    proposal: Rule08Proposal,
    context: Rule08EntropyContext | None = None,
) -> Rule08Result:
    """Validate cold-open entropy, insight floor, and brand-coherent thumbnail novelty."""
    ctx = context or Rule08EntropyContext()
    violations: list[Rule08Violation] = []
    violations.extend(_check_turning_points(proposal))
    violations.extend(_check_cold_open_rotation(proposal, ctx))
    violations.extend(_check_brand_locks(proposal.thumbnail))
    violations.extend(_check_thumbnail_novelty(proposal.thumbnail, ctx))
    return Rule08Result(violations=violations)


def _extract_named_query(queries_sql: str, name: str) -> str:
    import re

    pattern = rf"-- name: {re.escape(name)}\r?\n([\s\S]*?)(?=\r?\n-- name:|$)"
    match = re.search(pattern, queries_sql)
    if not match:
        raise KeyError(f"Query '{name}' not found in queries.sql")
    return match.group(1).strip()


def load_entropy_context_from_db(
    conn: sqlite3.Connection,
    *,
    queries_path: Path | None = None,
) -> Rule08EntropyContext:
    """Build RULE_08 context from ``published_entropy_history`` (Task 013 schema)."""
    path = queries_path or _DEFAULT_QUERIES_PATH
    recent_sql = _extract_named_query(path.read_text(encoding="utf-8"), "recent_entropy_window")
    rows = conn.execute(recent_sql).fetchall()

    archetypes: list[str] = []
    thumbs: list[ThumbnailBrandSpec] = []
    for row in rows:
        archetypes.append(str(row["cold_open_archetype"] if isinstance(row, sqlite3.Row) else row[1]))
        raw_vec = row["thumbnail_mood_vec"] if isinstance(row, sqlite3.Row) else row[2]
        spec = parse_thumbnail_mood_vec(str(raw_vec))
        if spec is not None and len(thumbs) < RECENT_THUMBNAIL_WINDOW:
            thumbs.append(spec)

    return Rule08EntropyContext(
        recent_cold_open_archetypes=tuple(archetypes[:RECENT_ARCHETYPE_WINDOW]),
        recent_thumbnail_specs=tuple(thumbs[:RECENT_THUMBNAIL_WINDOW]),
    )