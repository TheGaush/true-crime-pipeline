"""Byte-0 prompt-cached director client for cross-episode cache hits.

Tier ordering (required for DeepSeek prefix cache):
  1. Byte 0 — global static rules (JSON, ``sort_keys=True``)
  2. Tier 2 — episode ``CaseBible`` + ``spatial_anchors``
  3. Tier 3 — dynamic ``VoiceTrackManifest`` scene tail

Model ids and runtime caps are read from ``providers.yaml`` only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import yaml

TIER2_DELIMITER = "\n---TC-DIRECTOR-TIER2---\n"
TIER3_DELIMITER = "\n---TC-DIRECTOR-TIER3---\n"

_DIRECTOR_CONTRACT_ID = "director-manifest@4"
_MANIFESTS_ROLE = "manifests"

_ID_LINE = re.compile(r"^- id:\s*(\S+)\s*$")
_ROLES_LINE = re.compile(r"^roles:\s*\[([^\]]*)\]\s*$")

# Authoritative 12-motif render_catalog slice (matches shared_contracts.motifs MOTIF_CATALOG).
_MOTIF_CATALOG: tuple[dict[str, Any], ...] = (
    {"motif_component": "StickmanStage", "owner_package": "render_catalog", "is_mvp_4": True},
    {"motif_component": "AudioEvidenceCard", "owner_package": "render_catalog", "is_mvp_4": True},
    {"motif_component": "RedactedDocReveal", "owner_package": "render_catalog", "is_mvp_4": True},
    {"motif_component": "FoiaFootageFrame", "owner_package": "render_catalog", "is_mvp_4": True},
    {"motif_component": "TimelineScrubber", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "AnimatedMapRoute", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "CellTowerTriangulation", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "SplitScreenComparison", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "CaseBoardSpine", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "QuotePullout", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "EvidenceGridMatrix", "owner_package": "render_catalog", "is_mvp_4": False},
    {"motif_component": "ChapterSlateTransition", "owner_package": "render_catalog", "is_mvp_4": False},
)

_THIRTEEN_LAWS: tuple[dict[str, str], ...] = (
    {"id": "RULE_01", "summary": "voice_segments non-overlapping; sum matches total_master_ms +/- 250ms"},
    {"id": "RULE_02", "summary": "per-episode $10.40 cap and monthly $135 ALL_PROVIDERS headroom"},
    {"id": "RULE_03", "summary": "remainder beats >= 2.5s; FIRST_AND_LAST_FRAME <= 10s"},
    {"id": "RULE_04", "summary": "non-neighbor fallback_spec and engine streak <= 50s"},
    {"id": "RULE_05", "summary": "CaseBoardSpine in 210-270s flexible window; hero continuity exempt"},
    {"id": "RULE_06", "summary": "cold-open archetype entropy and AdSense-safe hook"},
    {"id": "RULE_07", "summary": "CSS safe-zones; callouts <= 12 words"},
    {"id": "RULE_08", "summary": "fact_ledger citations on verifiable claims"},
    {"id": "RULE_09", "summary": "news_report hedging_required and disclosure labels"},
    {"id": "RULE_10", "summary": "TRANSCRIPT DRAMATIZATION labels on dramatized audio"},
    {"id": "RULE_11", "summary": "ILLUSTRATIVE RECONSTRUCTION on 2K plates"},
    {"id": "RULE_12", "summary": "cinematography bigram whitelist for safety scans"},
    {"id": "RULE_13", "summary": "zero evidence crimson in Flow Start/End PNG keyframes"},
)

_CINEMATOGRAPHY_BIGRAM_WHITELIST: tuple[str, ...] = (
    "tracking shot",
    "static shot",
    "dolly shot",
    "wide shot",
    "medium shot",
    "panning shot",
    "establishing shot",
)

_METAPHOR_TABLES: dict[str, dict[str, Any]] = {
    "TEXT_TO_VIDEO": {
        "template": "atmospheric_stylized_silhouettes",
        "allow_appearance_descriptors": False,
        "duration_ms": {"min": 3000, "max": 15000},
    },
    "FIRST_FRAME": {
        "template": "motion_and_camera_verbs_only",
        "allow_appearance_descriptors": False,
        "cinematography_bigram_whitelist": list(_CINEMATOGRAPHY_BIGRAM_WHITELIST),
        "duration_ms": {"min": 3000, "max": 15000},
    },
    "FIRST_AND_LAST_FRAME": {
        "template": "motion_and_camera_verbs_only",
        "allow_appearance_descriptors": False,
        "cinematography_bigram_whitelist": list(_CINEMATOGRAPHY_BIGRAM_WHITELIST),
        "duration_ms": {"min": 3000, "max": 10000},
    },
}


def default_providers_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "providers.yaml"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("providers.yaml")


def load_model_id_for_role(path: str | Path, role: str = _MANIFESTS_ROLE) -> str:
    """Return the only model id in providers.yaml that lists role."""

    text = Path(path).read_text(encoding="utf-8")
    pending: str | None = None
    matches: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        id_match = _ID_LINE.match(line)
        if id_match:
            pending = id_match.group(1).strip("'\"")
            continue
        roles_match = _ROLES_LINE.match(line)
        if roles_match and pending is not None:
            roles = [
                part.strip().strip("'\"")
                for part in roles_match.group(1).split(",")
                if part.strip()
            ]
            if role in roles:
                matches.append(pending)
            pending = None
            continue
        pending = None
    unique = tuple(dict.fromkeys(matches))
    if len(unique) != 1:
        raise LookupError(f"expected exactly one model id for role {role}, found {unique}")
    return unique[0]


def _load_providers_mapping(path: str | Path) -> dict[str, Any]:
    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("providers.yaml must be a mapping")
    return loaded


def _video_model_config(registry: Mapping[str, Any]) -> dict[str, Any]:
    video = registry.get("video")
    if not isinstance(video, dict):
        raise ValueError("providers.yaml missing video section")
    primary = video.get("primary")
    if not isinstance(primary, dict):
        raise ValueError("providers.yaml missing video.primary")
    model_id = primary.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("video.primary.model_id missing")
    prompt_modes = primary.get("prompt_modes")
    if not isinstance(prompt_modes, dict):
        raise ValueError("video.primary.prompt_modes missing")
    return {
        "adapter": primary.get("adapter"),
        "model_id": model_id,
        "max_hero_clips": primary.get("max_hero_clips"),
        "max_hero_duration_sec": primary.get("max_hero_duration_sec"),
        "episode_cap_usd": primary.get("episode_cap_usd"),
        "prompt_modes": prompt_modes,
    }


def build_byte0_static_rules(providers_path: str | Path | None = None) -> str:
    """Serialize immutable global director rules as UTF-8 JSON at byte 0."""

    path = Path(providers_path) if providers_path is not None else default_providers_path()
    registry = _load_providers_mapping(path)
    runtime_split = registry.get("runtime_split")
    if not isinstance(runtime_split, dict):
        raise ValueError("providers.yaml missing runtime_split")
    manifests_model_id = load_model_id_for_role(path, _MANIFESTS_ROLE)
    payload = {
        "contract_id": _DIRECTOR_CONTRACT_ID,
        "manifests_model_id": manifests_model_id,
        "metaphor_tables": _METAPHOR_TABLES,
        "motif_catalog_v1": list(_MOTIF_CATALOG),
        "model_config": _video_model_config(registry),
        "runtime_split_sec": {
            "code_foia_sec": runtime_split.get("code_foia_sec"),
            "episode_target_sec": runtime_split.get("episode_target_sec"),
            "flow_hero_video_sec": runtime_split.get("flow_hero_video_sec"),
            "still_2k_panzoom_sec": runtime_split.get("still_2k_panzoom_sec"),
        },
        "thirteen_laws": list(_THIRTEEN_LAWS),
        "tier": "byte0_global_static",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"


def byte0_prefix_sha256(prompt: str, *, byte0_text: str | None = None) -> str:
    """SHA-256 over the byte-0 static rules prefix bytes."""

    if byte0_text is None:
        delimiter_at = prompt.find(TIER2_DELIMITER)
        if delimiter_at < 0:
            raise ValueError("prompt is missing tier-2 delimiter")
        byte0_text = prompt[:delimiter_at]
    raw = byte0_text.encode("utf-8")
    if not prompt.encode("utf-8").startswith(raw):
        raise ValueError("static rules are not at byte 0")
    return hashlib.sha256(raw).hexdigest()


def leading_prefix_sha256(prompt: str, *, byte_count: int) -> str:
    """SHA-256 over the first ``byte_count`` UTF-8 bytes (v1-order regression probe)."""

    if byte_count < 0:
        raise ValueError("byte_count must be non-negative")
    return hashlib.sha256(prompt.encode("utf-8")[:byte_count]).hexdigest()


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"unsupported payload type: {type(value)!r}")


def _tier2_payload(
    case_bible: Any,
    spatial_anchors: Sequence[Any],
) -> dict[str, Any]:
    return {
        "case_bible": _to_jsonable(case_bible),
        "spatial_anchors": [_to_jsonable(anchor) for anchor in spatial_anchors],
        "tier": "episode_case_context",
    }


def _tier3_payload(voice_track_manifest: Any, *, scene_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "tier": "dynamic_voice_scene",
        "voice_track_manifest": _to_jsonable(voice_track_manifest),
    }
    if scene_id is not None:
        payload["scene_id"] = scene_id
    return payload


@dataclass(frozen=True)
class DirectorPrompt:
    text: str
    byte0_sha256: str
    manifests_model_id: str


class CachedDirectorClient:
    """Builds cache-friendly director prompts with a shared byte-0 prefix."""

    def __init__(self, providers_path: str | Path | None = None) -> None:
        self.providers_path = (
            Path(providers_path) if providers_path is not None else default_providers_path()
        )
        self._byte0 = build_byte0_static_rules(self.providers_path)
        self.manifests_model_id = load_model_id_for_role(self.providers_path, _MANIFESTS_ROLE)

    @property
    def byte0_static_rules(self) -> str:
        return self._byte0

    def build_prompt(
        self,
        *,
        case_bible: Any,
        spatial_anchors: Sequence[Any],
        voice_track_manifest: Any,
        scene_id: str | None = None,
    ) -> DirectorPrompt:
        tier2 = json.dumps(_tier2_payload(case_bible, spatial_anchors), sort_keys=True, separators=(",", ":"))
        tier3 = json.dumps(
            _tier3_payload(voice_track_manifest, scene_id=scene_id),
            sort_keys=True,
            separators=(",", ":"),
        )
        text = f"{self._byte0}{TIER2_DELIMITER}{tier2}\n{TIER3_DELIMITER}{tier3}\n"
        return DirectorPrompt(
            text=text,
            byte0_sha256=byte0_prefix_sha256(text, byte0_text=self._byte0),
            manifests_model_id=self.manifests_model_id,
        )

    def build_prompt_v1_bug(
        self,
        *,
        case_bible: Any,
        spatial_anchors: Sequence[Any],
        voice_track_manifest: Any,
        scene_id: str | None = None,
    ) -> DirectorPrompt:
        """Regression helper: CaseBible before static rules (breaks cross-episode cache)."""

        tier2 = json.dumps(_tier2_payload(case_bible, spatial_anchors), sort_keys=True, separators=(",", ":"))
        tier3 = json.dumps(
            _tier3_payload(voice_track_manifest, scene_id=scene_id),
            sort_keys=True,
            separators=(",", ":"),
        )
        text = f"{tier2}\n{TIER2_DELIMITER}{self._byte0}{TIER3_DELIMITER}{tier3}\n"
        byte_count = len(self._byte0.encode("utf-8"))
        return DirectorPrompt(
            text=text,
            byte0_sha256=leading_prefix_sha256(text, byte_count=byte_count),
            manifests_model_id=self.manifests_model_id,
        )