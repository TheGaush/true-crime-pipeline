"""Shared types for manifest linting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LintScene:
    scene_id: str
    visual_engine: str
    start_ms: int
    end_ms: int
    foia_asset_id: str | None = None


@dataclass(frozen=True)
class LintVoiceSegment:
    segment_kind: str
    start_ms: int
    end_ms: int
    foia_asset_id: str | None = None


@dataclass(frozen=True)
class LintVoiceManifest:
    total_master_ms: int
    segments: tuple[LintVoiceSegment, ...] = ()


@dataclass(frozen=True)
class LintFinding:
    rule_id: str
    message: str
    severity: str = "error"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LintReport:
    passed: bool
    findings: tuple[LintFinding, ...]

    @property
    def errors(self) -> tuple[LintFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "error")