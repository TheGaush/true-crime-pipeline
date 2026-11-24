"""Layer-2 manifest linter core (RULE_01–RULE_13 entrypoint)."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from agent4_director.linter_types import (
    LintFinding,
    LintReport,
    LintScene,
    LintVoiceManifest,
    LintVoiceSegment,
)
from agent4_director.rules.rule_01_03_timing import check_rule_01, check_rule_03

RuleCheck = Callable[[Sequence[LintScene], LintVoiceManifest], list[LintFinding]]
SceneRuleCheck = Callable[[Sequence[LintScene]], list[LintFinding]]


def adapt_voice_manifest(manifest: Any) -> LintVoiceManifest:
    """Coerce a VoiceTrackManifest (or dict-like payload) into lint inputs."""
    if isinstance(manifest, LintVoiceManifest):
        return manifest

    total_master_ms = manifest.total_master_ms
    segments: list[LintVoiceSegment] = []
    for segment in manifest.segments:
        segments.append(
            LintVoiceSegment(
                segment_kind=segment.segment_kind,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                foia_asset_id=getattr(segment, "foia_asset_id", None),
            )
        )
    return LintVoiceManifest(total_master_ms=total_master_ms, segments=tuple(segments))


def adapt_scenes(scenes: Sequence[Any]) -> tuple[LintScene, ...]:
    """Coerce ScenePlan rows or lint scenes into LintScene."""
    adapted: list[LintScene] = []
    for scene in scenes:
        if isinstance(scene, LintScene):
            adapted.append(scene)
            continue
        if hasattr(scene, "timing_start_ms"):
            adapted.append(
                LintScene(
                    scene_id=scene.scene_id,
                    visual_engine=scene.visual_engine,
                    start_ms=scene.timing_start_ms,
                    end_ms=scene.timing_end_ms,
                    foia_asset_id=getattr(scene, "foia_asset_id", None),
                )
            )
            continue
        adapted.append(
            LintScene(
                scene_id=scene["scene_id"],
                visual_engine=scene["visual_engine"],
                start_ms=scene["start_ms"],
                end_ms=scene["end_ms"],
                foia_asset_id=scene.get("foia_asset_id"),
            )
        )
    return tuple(adapted)


class ManifestLinter:
    """Runs deterministic manifest rules with zero LLM calls."""

    def __init__(self) -> None:
        self._paired_rules: tuple[RuleCheck, ...] = (check_rule_01,)
        self._scene_rules: tuple[SceneRuleCheck, ...] = (check_rule_03,)

    def lint(
        self,
        scenes: Sequence[Any],
        voice: Any,
    ) -> LintReport:
        lint_scenes = adapt_scenes(scenes)
        voice_manifest = adapt_voice_manifest(voice)

        findings: list[LintFinding] = []
        for rule in self._paired_rules:
            findings.extend(rule(lint_scenes, voice_manifest))
        for rule in self._scene_rules:
            findings.extend(rule(lint_scenes))

        return LintReport(passed=not any(f.severity == "error" for f in findings), findings=tuple(findings))


_default_linter = ManifestLinter()


def lint_manifest(scenes: Sequence[Any], voice: Any) -> LintReport:
    """Lint scenes against the segmented voice manifest."""
    return _default_linter.lint(scenes, voice)