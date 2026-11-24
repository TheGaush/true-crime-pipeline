"""Altered-content disclosure and TRANSCRIPT DRAMATIZATION badge classifier.

Sets ``altered_content_disclosure`` for YouTube synthetic-content policy and
flags ``requires_dramatization_badge`` so Part 2 can render an unambiguous
``TRANSCRIPT DRAMATIZATION`` label on TTS-voiced verbatim quotes inside
``AUDIO_EVIDENCE_CARD`` or ``RedactedDocReveal`` beats (no live TTS, no network).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

TRANSCRIPT_DRAMATIZATION_BADGE = "TRANSCRIPT DRAMATIZATION"

QuoteKind = Literal["suspect", "witness", "911"]
AudioDelivery = Literal["TTS", "ARCHIVAL_WAV", "NARRATION", "FOIA_AUDIO_SLOT"]

_VISUAL_ENGINE_STICKMAN = "CODE_STICKMAN"
_MOTIF_STICKMAN_STAGE = "StickmanStage"
_VISUAL_ENGINE_AUDIO_CARD = "AUDIO_EVIDENCE_CARD"
_MOTIF_AUDIO_CARD = "AudioEvidenceCard"
_MOTIF_REDACTED_DOC = "RedactedDocReveal"

_VERBATIM_QUOTE_KINDS: frozenset[str] = frozenset({"suspect", "witness", "911"})

REALISTIC_RECONSTRUCTION_TAGS: frozenset[str] = frozenset(
    {
        "REALISTIC_RECONSTRUCTION",
        "PHOTOREALISTIC_RECONSTRUCTION",
        "REALISTIC_REENACTMENT",
        "REALISTIC_SCENE_RECONSTRUCTION",
    }
)

_REALISTIC_TAG_ALIASES: dict[str, str] = {
    "REALISTIC RECONSTRUCTION": "REALISTIC_RECONSTRUCTION",
    "PHOTOREALISTIC RECONSTRUCTION": "PHOTOREALISTIC_RECONSTRUCTION",
    "REALISTIC REENACTMENT": "REALISTIC_REENACTMENT",
    "REALISTIC SCENE RECONSTRUCTION": "REALISTIC_SCENE_RECONSTRUCTION",
}


@dataclass(frozen=True, slots=True)
class SceneDisclosureBeat:
    """One timed beat the gatekeeper classifies for disclosure policy."""

    visual_engine: str
    motif_component: str
    quote_kind: QuoteKind | None = None
    audio_delivery: AudioDelivery = "NARRATION"
    is_verbatim_quote: bool = False
    content_tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class SceneDisclosureResult:
    altered_content_disclosure: bool
    requires_dramatization_badge: bool
    dramatization_badge_label: str | None


@dataclass
class EpisodeDisclosureResult:
    altered_content_disclosure: bool
    scene_results: list[SceneDisclosureResult] = field(default_factory=list)

    def to_audit_fields(self) -> dict[str, Any]:
        return {
            "altered_content_disclosure": self.altered_content_disclosure,
            "scene_disclosure_json": [
                {
                    "altered_content_disclosure": r.altered_content_disclosure,
                    "requires_dramatization_badge": r.requires_dramatization_badge,
                    "dramatization_badge_label": r.dramatization_badge_label,
                }
                for r in self.scene_results
            ],
        }


def _normalize_tag(tag: str) -> str:
    collapsed = " ".join(tag.strip().split()).upper()
    if collapsed in _REALISTIC_TAG_ALIASES:
        return _REALISTIC_TAG_ALIASES[collapsed]
    return collapsed.replace(" ", "_")


def has_realistic_reconstruction_tag(tags: Iterable[str]) -> bool:
    """Return whether any tag marks photorealistic / realistic reconstruction."""
    for raw in tags:
        if _normalize_tag(raw) in REALISTIC_RECONSTRUCTION_TAGS:
            return True
    return False


def is_stylized_stick_figure(visual_engine: str, motif_component: str) -> bool:
    """Stylized 2D stick-figure staging does not by itself require altered disclosure."""
    return (
        visual_engine == _VISUAL_ENGINE_STICKMAN
        and motif_component == _MOTIF_STICKMAN_STAGE
    )


def _is_dramatization_surface(visual_engine: str, motif_component: str) -> bool:
    if visual_engine == _VISUAL_ENGINE_AUDIO_CARD:
        return True
    if motif_component in {_MOTIF_AUDIO_CARD, _MOTIF_REDACTED_DOC}:
        return True
    return False


def altered_content_disclosure_for_beat(beat: SceneDisclosureBeat) -> bool:
    """Classify whether this beat contributes to episode altered-content disclosure."""
    if has_realistic_reconstruction_tag(beat.content_tags):
        return True
    if is_stylized_stick_figure(beat.visual_engine, beat.motif_component):
        return False
    return False


def requires_dramatization_badge(beat: SceneDisclosureBeat) -> bool:
    """True when TTS voices a verbatim suspect/witness/911 quote on an evidence surface."""
    if not beat.is_verbatim_quote:
        return False
    if beat.quote_kind not in _VERBATIM_QUOTE_KINDS:
        return False
    if beat.audio_delivery != "TTS":
        return False
    return _is_dramatization_surface(beat.visual_engine, beat.motif_component)


def dramatization_badge_label(requires_badge: bool) -> str | None:
    return TRANSCRIPT_DRAMATIZATION_BADGE if requires_badge else None


def classify_scene_disclosure(beat: SceneDisclosureBeat) -> SceneDisclosureResult:
    badge = requires_dramatization_badge(beat)
    return SceneDisclosureResult(
        altered_content_disclosure=altered_content_disclosure_for_beat(beat),
        requires_dramatization_badge=badge,
        dramatization_badge_label=dramatization_badge_label(badge),
    )


def classify_episode_disclosure(
    beats: Sequence[SceneDisclosureBeat],
) -> EpisodeDisclosureResult:
    scene_results = [classify_scene_disclosure(b) for b in beats]
    return EpisodeDisclosureResult(
        altered_content_disclosure=any(r.altered_content_disclosure for r in scene_results),
        scene_results=scene_results,
    )


def beat_from_mapping(payload: Mapping[str, Any]) -> SceneDisclosureBeat:
    """Build a beat from a loose dict (scene plan fragments or test fixtures)."""
    tags_raw = payload.get("content_tags") or payload.get("realistic_reconstruction_tags") or ()
    if isinstance(tags_raw, str):
        tag_list = (tags_raw,)
    else:
        tag_list = tuple(tags_raw)
    return SceneDisclosureBeat(
        visual_engine=str(payload["visual_engine"]),
        motif_component=str(payload["motif_component"]),
        quote_kind=payload.get("quote_kind"),
        audio_delivery=payload.get("audio_delivery", "NARRATION"),
        is_verbatim_quote=bool(payload.get("is_verbatim_quote", False)),
        content_tags=frozenset(tag_list),
    )


class DisclosureClassifier:
    """Facade for batch scene and episode disclosure classification."""

    def classify_scene(self, beat: SceneDisclosureBeat) -> SceneDisclosureResult:
        return classify_scene_disclosure(beat)

    def classify_episode(
        self, beats: Sequence[SceneDisclosureBeat]
    ) -> EpisodeDisclosureResult:
        return classify_episode_disclosure(beats)