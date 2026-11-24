"""v4 contract models. Field names follow schema/pipeline.sql column names.

JSON object keys that end in `_json` carry the parsed JSON value (array or
object), not a second-encoded string. Boolean flags are JSON booleans.
`estimated_micro_usd` has no library default: the SQL column default is a
price and is intentionally not copied into this package.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from shared_contracts.base import ContractModel
from shared_contracts.motifs import CatalogMotif, MotifRegistryEntry, MvpMotif
from shared_contracts.version import CONTRACT_VERSION

EntityId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
ShortText = Annotated[str, Field(min_length=1, max_length=200)]
_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
_UNSAFE_PATH = re.compile(r"(^[/\\])|(\.\.)")

ContractVersion = Literal["v4"]
Track = Literal["TRACK_A_OUTLIER", "TRACK_B_FOIA_RADAR"]
SourceType = Literal["court_ruling", "police_affidavit", "news_report"]
DispositionCleared = Literal["AFFIRMED", "STANDING_CONVICTION"]
VisualEngine = Literal[
    "CODE_STICKMAN",
    "STILL_2K_PANZOOM",
    "AUDIO_EVIDENCE_CARD",
    "FOIA_REAL_FOOTAGE",
    "FLOW_HERO_VIDEO",
]
ScenePromptMode = Literal["NONE", "TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]
VideoPromptMode = Literal["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]
PlanStatus = Literal[
    "DRAFT",
    "PLAN_APPROVED",
    "ASSETS_CREATED",
    "EDITED_APPROVED",
    "STALE_NEEDS_REAPPROVAL",
]
SegmentKind = Literal["NARRATION", "FOIA_AUDIO_SLOT", "TWIST_PAD"]
LockStatus = Literal["DRAFT", "IN_REVIEW", "LOCKED"]
TravelAxis = Literal["L_TO_R", "R_TO_L", "STATIC"]
ColdOpenArchetype = Literal[
    "911_CALL_IN_MEDIA_RES",
    "SINGLE_FORENSIC_ANOMALY",
    "ALIBI_THAT_CRACKED",
    "CHRONOLOGICAL_COUNTDOWN",
]
FlowBackendMode = Literal[
    "GEMINI_OMNI_INTERACTIONS",
    "VERTEX_VEO_ENTERPRISE",
    "HUMAN_BATCH_DESK",
]
EngineModel = Literal[
    "gemini-omni-1.2-flash",
    "vertex-veo-enterprise",
    "manual-desk-video",
]
Resolution = Literal["360p", "720p", "1080p", "4k"]
FlowJobState = Literal[
    "PENDING",
    "SUBMITTING",
    "RUNNING",
    "UNKNOWN_RECONCILE",
    "PENDING_MANUAL_SPOT_CHECK",
    "STRIKE_1_RETRY_SAFE",
    "ACCEPTED",
    "FAILED_TERMINAL",
    "SWITCHED_TO_FALLBACK",
]
AdsenseStatus = Literal[
    "UNKNOWN",
    "PENDING",
    "NOT_LINKED",
    "GREEN_FULL_ADS",
    "YELLOW_LIMITED",
    "NONE",
]
AdsenseSource = Literal["STUDIO_CSV_EXPORT", "MANUAL_CREATOR_ENTRY", "UNAVAILABLE"]
MetricsSource = Literal["YT_ANALYTICS_API", "STUDIO_CSV_EXPORT", "COMBINED"]
ReleaseGate = Literal[
    "FACTUAL_ACCURACY",
    "PRIVACY_PII",
    "SOURCE_RIGHTS",
    "SYNTHETIC_DISCLOSURE",
    "ILLUSTRATIVE_LABELING",
]
VisionQaStatus = Literal["PASSED", "PENDING_MANUAL_SPOT_CHECK"]
RELEASE_GATES: tuple[str, ...] = (
    "FACTUAL_ACCURACY",
    "PRIVACY_PII",
    "SOURCE_RIGHTS",
    "SYNTHETIC_DISCLOSURE",
    "ILLUSTRATIVE_LABELING",
)


def _iso_datetime(value: str) -> str:
    if _ISO_DT.fullmatch(value) is None:
        raise ValueError("datetime_iso must be timezone-aware ISO-8601")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _safe_relpath(value: str) -> str:
    if _UNSAFE_PATH.search(value.replace("\\", "/")):
        raise ValueError("path must be a relative path without traversal")
    return value


def _hex_key(value: str) -> str:
    return value.upper()


class SeedPacket(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    track: Track
    lead_classification: Literal["LEAD_ONLY"] = "LEAD_ONLY"
    suspect_names: list[ShortText] = Field(default_factory=list, max_length=8)
    victim_names: list[ShortText] = Field(default_factory=list, max_length=8)
    incident_date_or_year: ShortText
    county_state: ShortText
    docket_ids: list[EntityId] = Field(default_factory=list, max_length=8)
    unanswered_comment_questions: list[ShortText] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def closed_lookup_keys(self) -> SeedPacket:
        if not (self.suspect_names or self.victim_names or self.docket_ids):
            raise ValueError("SeedPacket requires a suspect, victim, or docket lookup key")
        for question in self.unanswered_comment_questions:
            terminators = re.findall(r"[.!?]+", question)
            if len(terminators) > 1:
                raise ValueError("unanswered_comment_questions must be a single sentence")
        return self


class TemporalFact(ContractModel):
    fact_id: EntityId
    case_id: EntityId
    datetime_iso: str
    event_summary: str = Field(min_length=1, max_length=2000)
    physical_clues_json: list[ShortText] = Field(default_factory=list, max_length=32)
    location_text: str = Field(min_length=1, max_length=300)
    source_type: SourceType
    source_doc_id: EntityId
    citation_locator: str = Field(min_length=1, max_length=300)
    hedging_required: bool
    contradicts_json: list[EntityId] = Field(default_factory=list)

    @model_validator(mode="after")
    def news_requires_hedging(self) -> TemporalFact:
        _iso_datetime(self.datetime_iso)
        if self.source_type == "news_report" and not self.hedging_required:
            raise ValueError("news_report facts require hedging_required")
        return self


class TemporalFactLedger(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    case_id: EntityId
    facts: list[TemporalFact] = Field(min_length=1)

    @model_validator(mode="after")
    def facts_match_case(self) -> TemporalFactLedger:
        for fact in self.facts:
            if fact.case_id != self.case_id:
                raise ValueError("fact case_id must match the ledger case_id")
        return self


class ComplianceClearedCase(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    case_id: EntityId
    defendant_name: ShortText
    incident_year: int = Field(ge=1800, le=2100)
    jurisdiction: str = Field(min_length=1, max_length=200)
    verification_source: str = Field(min_length=1, max_length=300)
    disposition_status: DispositionCleared
    conviction_confirmed: Literal[True]
    primary_record_verified: Literal[True]
    anonymization_status: Literal["APPROVED"]
    anonymized_by: str = Field(min_length=1, max_length=128)
    anonymized_at: int = Field(ge=0)
    anonymization_artifact_sha256: Sha256
    audit_id: EntityId
    provenance_whitelist_ok: Literal[True]
    that_vs_how_passed: Literal[True]
    anti_legal_persona_passed: Literal[True]
    first_30s_adsense_safe: Literal[True]
    spoken_pii_audit_passed: Literal[True]
    altered_content_disclosure: bool
    audited_at: int = Field(ge=0)


class KeyframeRef(ContractModel):
    ref_id: EntityId
    role: Literal["START", "END"]
    sha256: Sha256


class TransitionSpec(ContractModel):
    transition_type: Literal["CUT", "DISSOLVE", "MATCH_CUT"]
    duration_ms: int = Field(ge=0, le=1000)


class SoundCue(ContractModel):
    cue_id: EntityId
    offset_ms: int = Field(ge=0)
    role: Literal["BED", "HIT", "ROOM_TONE"]


class AcceptanceCriterion(ContractModel):
    criterion_id: EntityId
    kind: Literal["SEMANTIC", "TECHNICAL"]
    text: str = Field(min_length=1, max_length=500)


class ScenePlan(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    scene_plan_id: EntityId
    episode_id: EntityId
    scene_id: EntityId
    plan_version: int = Field(default=1, ge=1)
    seq_index: int = Field(ge=1)
    story_purpose: str = Field(min_length=1, max_length=500)
    intended_audience_effect: str = Field(min_length=1, max_length=500)
    approved_narration_text: str = Field(min_length=1, max_length=4000)
    narration_version_sha256: Sha256
    cited_fact_ids_json: list[EntityId] = Field(min_length=1)
    visual_concept: str = Field(min_length=1, max_length=500)
    visual_engine: VisualEngine
    motif_component: CatalogMotif
    prompt_mode: ScenePromptMode
    visual_prompt: str = Field(min_length=1, max_length=4000)
    keyframe_refs_json: list[KeyframeRef] = Field(default_factory=list)
    expected_output_summary: str = Field(min_length=1, max_length=500)
    timing_start_ms: int = Field(ge=0)
    timing_end_ms: int
    transition_spec_json: TransitionSpec
    sound_cues_json: list[SoundCue] = Field(default_factory=list)
    edit_instructions: str = Field(min_length=1, max_length=2000)
    acceptance_criteria_json: list[AcceptanceCriterion] = Field(min_length=1)
    asset_version_sha256: Sha256 | None = None
    plan_status: PlanStatus = "DRAFT"
    reviewed_by: str | None = None
    reviewed_at: int | None = None
    created_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)

    @model_validator(mode="after")
    def plan_rules(self) -> ScenePlan:
        if self.timing_end_ms <= self.timing_start_ms:
            raise ValueError("timing_end_ms must be greater than timing_start_ms")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must be >= created_at")
        if not any(item.kind == "SEMANTIC" for item in self.acceptance_criteria_json):
            raise ValueError("acceptance_criteria_json requires a SEMANTIC criterion")
        if self.plan_status in {"PLAN_APPROVED", "EDITED_APPROVED"} and (
            not self.reviewed_by or self.reviewed_at is None
        ):
            raise ValueError("approved plans require reviewed_by and reviewed_at")
        if self.plan_status == "EDITED_APPROVED" and self.asset_version_sha256 is None:
            raise ValueError("EDITED_APPROVED requires asset_version_sha256")
        duration = self.timing_end_ms - self.timing_start_ms
        roles = [item.role for item in self.keyframe_refs_json]
        if self.prompt_mode == "NONE":
            if roles:
                raise ValueError("prompt_mode NONE does not take keyframes")
        elif self.prompt_mode == "TEXT_TO_VIDEO":
            if roles:
                raise ValueError("TEXT_TO_VIDEO keyframe_refs_json must be empty")
            if not 3000 <= duration <= 15000:
                raise ValueError("TEXT_TO_VIDEO duration must be 3000-15000 ms")
        elif self.prompt_mode == "FIRST_FRAME":
            if roles != ["START"]:
                raise ValueError("FIRST_FRAME requires exactly one START keyframe")
            if not 3000 <= duration <= 15000:
                raise ValueError("FIRST_FRAME duration must be 3000-15000 ms")
        elif self.prompt_mode == "FIRST_AND_LAST_FRAME":
            if roles != ["START", "END"]:
                raise ValueError("FIRST_AND_LAST_FRAME requires START then END keyframes")
            if not 3000 <= duration <= 10000:
                raise ValueError("FIRST_AND_LAST_FRAME duration must be 3000-10000 ms")
        return self


class WordTimestamp(ContractModel):
    segment_id: EntityId
    word: str = Field(min_length=1, max_length=80)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class CuePoint(ContractModel):
    cue_id: EntityId
    at_ms: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=120)


class VoiceSegment(ContractModel):
    segment_id: EntityId
    episode_id: EntityId
    seq_index: int = Field(ge=1)
    segment_kind: SegmentKind
    start_ms: int = Field(ge=0)
    end_ms: int
    audio_path: str | None = None
    foia_asset_id: EntityId | None = None
    narration_version_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def kind_media(self) -> VoiceSegment:
        if self.end_ms <= self.start_ms:
            raise ValueError("segment end_ms must be greater than start_ms")
        duration = self.end_ms - self.start_ms
        if self.audio_path is not None:
            _safe_relpath(self.audio_path)
        if self.segment_kind == "NARRATION":
            if not self.audio_path or self.narration_version_sha256 is None:
                raise ValueError("NARRATION requires audio_path and narration_version_sha256")
        elif self.segment_kind == "FOIA_AUDIO_SLOT":
            if self.foia_asset_id is None or self.audio_path is not None:
                raise ValueError("FOIA_AUDIO_SLOT requires foia_asset_id and a silent audio_path")
        elif self.segment_kind == "TWIST_PAD" and not 450 <= duration <= 750:
            raise ValueError("TWIST_PAD duration must be 450-750 ms")
        return self


class VoiceTrackManifest(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    episode_id: EntityId
    total_master_ms: int = Field(ge=0)
    segments: list[VoiceSegment] = Field(min_length=1)
    word_timestamps: list[WordTimestamp] = Field(default_factory=list)
    cue_points: list[CuePoint] = Field(default_factory=list)
    amplitude_envelope: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def non_overlapping(self) -> VoiceTrackManifest:
        for sample in self.amplitude_envelope:
            if not 0.0 <= sample <= 1.0:
                raise ValueError("amplitude_envelope samples must be within 0..1")
        ordered = sorted(self.segments, key=lambda segment: segment.start_ms)
        if [segment.seq_index for segment in ordered] != list(range(1, len(ordered) + 1)):
            raise ValueError("seq_index must follow start time and begin at 1")
        if ordered[0].start_ms != 0:
            raise ValueError("voice timeline must start at 0 ms")
        for previous, nxt in zip(ordered, ordered[1:]):
            if nxt.start_ms < previous.end_ms:
                raise ValueError("voice segments must not overlap")
        if ordered[-1].end_ms > self.total_master_ms:
            raise ValueError("segments must end at or before total_master_ms")
        by_id = {segment.segment_id: segment for segment in self.segments}
        if len(by_id) != len(self.segments):
            raise ValueError("segment_id values must be unique")
        for segment in self.segments:
            if segment.episode_id != self.episode_id:
                raise ValueError("segment episode_id must match the manifest")
        seen: dict[str, list[tuple[int, int]]] = {}
        for stamp in self.word_timestamps:
            host = by_id.get(stamp.segment_id)
            if host is None or host.segment_kind != "NARRATION":
                raise ValueError("word timestamp must cite a NARRATION segment")
            if stamp.end_ms <= stamp.start_ms or stamp.start_ms < host.start_ms or stamp.end_ms > host.end_ms:
                raise ValueError("word timestamp must sit inside its narration segment")
            seen.setdefault(stamp.segment_id, []).append((stamp.start_ms, stamp.end_ms))
        for spans in seen.values():
            spans.sort()
            for previous, nxt in zip(spans, spans[1:]):
                if nxt[0] < previous[1]:
                    raise ValueError("word timestamps must not overlap")
        for cue in self.cue_points:
            if cue.at_ms > self.total_master_ms:
                raise ValueError("cue_point lies outside the manifest")
        return self


class SpatialAnchor(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    anchor_id: EntityId
    episode_id: EntityId
    still_2k_id: EntityId
    clue_name: str = Field(min_length=1, max_length=200)
    cited_fact_id: EntityId | None = None
    grid_cell: str = Field(pattern=r"^[A-J]([1-9]|10)$")
    span_cols: float = Field(default=1.0, gt=0, le=10)
    span_rows: float = Field(default=1.0, gt=0, le=10)
    x_px: int = Field(ge=0)
    y_px: int = Field(ge=0)
    target_zoom: float = Field(default=2.5, ge=1.0, le=3.8)
    travel_axis: TravelAxis | None = None
    lock_status: LockStatus = "DRAFT"
    locked_by: str | None = None
    locked_at: int | None = None
    still_asset_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def locked_requires_proof(self) -> SpatialAnchor:
        if self.lock_status == "LOCKED" and (
            not self.locked_by or self.locked_at is None or self.still_asset_sha256 is None
        ):
            raise ValueError("LOCKED anchors require locked_by, locked_at, and still_asset_sha256")
        return self


class StyleDna(ContractModel):
    evidence_crimson_hex: HexColor = "#C92A2A"
    paper_bg_hex: HexColor = "#E9E2D2"
    ink_hex: HexColor = "#1B1B1D"
    slate_hex: HexColor = "#3A4F66"
    flow_keyframe_safe_palette: list[HexColor] = Field(
        default_factory=lambda: ["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"],
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def palette_excludes_crimson(self) -> StyleDna:
        banned = {_hex_key(self.evidence_crimson_hex), "#C92A2A"}
        if any(_hex_key(color) in banned for color in self.flow_keyframe_safe_palette):
            raise ValueError("flow_keyframe_safe_palette must exclude evidence crimson")
        return self


class CharacterSpec(ContractModel):
    character_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)
    prop: str = Field(min_length=1, max_length=80)
    color_hex: HexColor


class CaseBible(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    episode_id: EntityId
    style_dna_json: StyleDna
    characters_json: list[CharacterSpec] = Field(min_length=1)
    locked_at: int = Field(ge=0)


class ProductionManifest(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    manifest_id: EntityId
    episode_id: EntityId
    case_id: EntityId
    fps: Literal[30] = 30
    cold_open_archetype: ColdOpenArchetype
    flow_backend_mode: FlowBackendMode
    target_duration_ms: int = Field(gt=0)
    code_foia_ms: int = Field(ge=0)
    still_2k_ms: int = Field(ge=0)
    hero_ms: int = Field(ge=0)
    max_hero_clips: int = Field(default=10, ge=0, le=10)
    max_hero_duration_sec: int = Field(default=80, ge=0, le=80)
    hero_clip_count: int = Field(ge=0, le=10)
    hero_duration_sec: int = Field(ge=0, le=80)
    scene_plan_ids: list[EntityId] = Field(min_length=1)
    voice_total_master_ms: int = Field(ge=0)
    timeline_validated_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def runtime_caps(self) -> ProductionManifest:
        if self.code_foia_ms + self.still_2k_ms + self.hero_ms != self.target_duration_ms:
            raise ValueError("code_foia_ms + still_2k_ms + hero_ms must equal target_duration_ms")
        if self.hero_ms != self.hero_duration_sec * 1000:
            raise ValueError("hero_ms must equal hero_duration_sec * 1000")
        if self.hero_clip_count > self.max_hero_clips:
            raise ValueError("hero_clip_count exceeds max_hero_clips")
        if self.hero_duration_sec > self.max_hero_duration_sec:
            raise ValueError("hero_duration_sec exceeds max_hero_duration_sec")
        if abs(self.voice_total_master_ms - self.target_duration_ms) > 250:
            raise ValueError("voice_total_master_ms must be within 250 ms of target_duration_ms")
        return self


class TimelineSpec(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    episode_id: EntityId
    scene_id: EntityId
    scene_plan_id: EntityId
    fps: Literal[30] = 30
    width_px: Literal[1920] = 1920
    height_px: Literal[1080] = 1080
    motif_registry: Literal["MOTIF_REGISTRY_V1"] = "MOTIF_REGISTRY_V1"
    motif_component: MvpMotif
    prompt_mode: VideoPromptMode
    duration_ms: int
    start_frame_sha256: Sha256 | None = None
    end_frame_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def prompt_frames(self) -> TimelineSpec:
        _enforce_video_prompt(
            self.prompt_mode,
            self.duration_ms,
            self.start_frame_sha256 is not None,
            self.end_frame_sha256 is not None,
        )
        return self


class FallbackSpec(ContractModel):
    visual_engine: VisualEngine
    motif_component: CatalogMotif
    reason: str = Field(min_length=1, max_length=300)


class FlowJobCard(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    flow_job_id: EntityId
    episode_id: EntityId
    scene_id: EntityId
    idempotency_key: str = Field(min_length=8, max_length=200)
    assigned_account_id: EntityId | None = None
    provider_route: FlowBackendMode = "GEMINI_OMNI_INTERACTIONS"
    engine_model: EngineModel = "gemini-omni-1.2-flash"
    prompt_mode: VideoPromptMode
    resolution: Resolution = "720p"
    duration_bucket_sec: int = Field(ge=3, le=15)
    variations: Literal[1] = 1
    estimated_micro_usd: int = Field(ge=0)
    estimated_credits: int = Field(default=0, ge=0)
    start_frame_png: str | None = None
    end_frame_png: str | None = None
    prompt_v1: str = Field(min_length=1, max_length=4000)
    prompt_v2_safe: str = Field(min_length=1, max_length=4000)
    fallback_spec_json: FallbackSpec
    provider_operation_id: str | None = None
    attempts_used: int = Field(default=0, ge=0, le=2)
    state: FlowJobState = "PENDING"
    output_asset_path: str | None = None
    updated_at: int = Field(ge=0)

    @model_validator(mode="after")
    def prompt_frames(self) -> FlowJobCard:
        for path in (self.start_frame_png, self.end_frame_png, self.output_asset_path):
            if path is not None:
                _safe_relpath(path)
        _enforce_video_prompt(
            self.prompt_mode,
            self.duration_bucket_sec * 1000,
            self.start_frame_png is not None,
            self.end_frame_png is not None,
        )
        return self


class EpisodeAnalyticsSnapshot(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    snapshot_id: EntityId
    episode_id: EntityId
    days_since_publish: int = Field(ge=1)
    ctr_pct: float | None = None
    retention_30s_pct: float | None = None
    retention_min6_14_pct: float | None = None
    avd_pct: float | None = None
    watch_hours_total: float = Field(default=0.0, ge=0)
    rpm_micro_usd: int | None = None
    adsense_status: AdsenseStatus = "UNKNOWN"
    adsense_source: AdsenseSource = "UNAVAILABLE"
    adsense_checked_at: int | None = None
    metrics_source: MetricsSource = "YT_ANALYTICS_API"
    captured_at: int = Field(ge=0)

    @model_validator(mode="after")
    def honest_adsense(self) -> EpisodeAnalyticsSnapshot:
        for name in ("ctr_pct", "retention_30s_pct", "retention_min6_14_pct", "avd_pct"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 100:
                raise ValueError(f"{name} must be within 0..100")
        if self.rpm_micro_usd is not None and self.rpm_micro_usd < 0:
            raise ValueError("rpm_micro_usd must be >= 0")
        monetized = self.adsense_status not in {"UNKNOWN", "NOT_LINKED"}
        if monetized and self.adsense_source == "UNAVAILABLE":
            raise ValueError("a known adsense_status requires a Studio or manual source")
        if self.adsense_source != "UNAVAILABLE" and self.adsense_checked_at is None:
            raise ValueError("adsense_checked_at is required when a source is recorded")
        return self


class ReadyToUploadPack(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    episode_id: EntityId
    episode_slug: EntityId
    ready_pack_dir: str = Field(min_length=1, max_length=240)
    ready_bundle_sha256: Sha256
    final_mp4_relpath: Literal["final_1080p30.mp4"]
    final_mp4_sha256: Sha256
    integrated_lufs: float
    true_peak_dbtp: float
    lufs_passed: Literal[True]
    safe_zone_passed: Literal[True]
    vision_frame_qa_status: Literal["PASSED"]
    thumbnail_brand_passed: Literal[True]
    thumbnail_relpaths: list[str] = Field(min_length=1, max_length=3)
    chapters_relpath: Literal["chapters.txt"]
    youtube_synthetic_disclosure_required: bool
    provenance_bundle_relpath: Literal["provenance_bundle.json"]
    qa_certificate_relpath: Literal["qa_certificate.json"]
    human_review_flags: list[str] = Field(default_factory=list, max_length=0)
    approved_release_gates: list[ReleaseGate] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def ready_rules(self) -> ReadyToUploadPack:
        _safe_relpath(self.ready_pack_dir)
        for rel in self.thumbnail_relpaths:
            _safe_relpath(rel)
            if not rel.endswith(".png"):
                raise ValueError("thumbnail_relpaths must be png files")
        if self.true_peak_dbtp > -1.0:
            raise ValueError("true_peak_dbtp must be <= -1.0")
        if not -14.5 <= self.integrated_lufs <= -13.5:
            raise ValueError("integrated_lufs must stay within 0.5 of -14.0")
        if self.vision_frame_qa_status != "PASSED":
            raise ValueError("vision_frame_qa_status must be PASSED before upload")
        if self.human_review_flags:
            raise ValueError("human_review_flags must be empty before upload")
        if list(self.approved_release_gates) != list(RELEASE_GATES):
            raise ValueError("approved_release_gates must be the five release gates in order")
        for flag in self.human_review_flags:
            if not flag or len(flag) > 200:
                raise ValueError("human_review_flags entries must be 1-200 characters")
        return self


class ProviderEntry(ContractModel):
    model_id: str = Field(min_length=1, max_length=128)
    api: str = Field(min_length=1, max_length=128)
    pricing: dict[str, float] = Field(default_factory=dict)
    limits: dict[str, int] = Field(default_factory=dict)


class ProviderRegistry(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    providers: dict[str, ProviderEntry] = Field(min_length=1)


class CraftPrinciple(ContractModel):
    principle_id: EntityId
    summary: str = Field(min_length=1, max_length=240)


class CraftRubric(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    rubric_id: Literal["craft_rubric_v4"]
    principles: list[CraftPrinciple] = Field(min_length=1, max_length=40)


class RenderReceipt(ContractModel):
    contract_version: ContractVersion = CONTRACT_VERSION
    backend_name: str = Field(min_length=1, max_length=80)
    output_relpath: str = Field(min_length=1, max_length=240)
    fps: Literal[30] = 30
    sha256: Sha256


def _enforce_video_prompt(mode: str, duration_ms: int, has_start: bool, has_end: bool) -> None:
    if mode == "TEXT_TO_VIDEO":
        if has_start or has_end:
            raise ValueError("TEXT_TO_VIDEO requires null frames")
        if not 3000 <= duration_ms <= 15000:
            raise ValueError("TEXT_TO_VIDEO duration must be 3-15 seconds")
    elif mode == "FIRST_FRAME":
        if not has_start or has_end:
            raise ValueError("FIRST_FRAME requires a start frame and a null end frame")
        if not 3000 <= duration_ms <= 15000:
            raise ValueError("FIRST_FRAME duration must be 3-15 seconds")
    elif mode == "FIRST_AND_LAST_FRAME":
        if not has_start or not has_end:
            raise ValueError("FIRST_AND_LAST_FRAME requires start and end frames")
        if not 3000 <= duration_ms <= 10000:
            raise ValueError("FIRST_AND_LAST_FRAME duration must be 3-10 seconds")
    else:
        raise ValueError("prompt_mode is not a current video mode")


TOP_LEVEL_MODELS: dict[str, type[ContractModel]] = {
    "SeedPacket": SeedPacket,
    "TemporalFactLedger": TemporalFactLedger,
    "ComplianceClearedCase": ComplianceClearedCase,
    "ScenePlan": ScenePlan,
    "VoiceTrackManifest": VoiceTrackManifest,
    "SpatialAnchor": SpatialAnchor,
    "CaseBible": CaseBible,
    "ProductionManifest": ProductionManifest,
    "TimelineSpec": TimelineSpec,
    "FlowJobCard": FlowJobCard,
    "EpisodeAnalyticsSnapshot": EpisodeAnalyticsSnapshot,
    "ReadyToUploadPack": ReadyToUploadPack,
    "ProviderRegistry": ProviderRegistry,
    "CraftRubric": CraftRubric,
    "RenderReceipt": RenderReceipt,
    "MotifRegistryEntry": MotifRegistryEntry,
}


def parse_contract(model_name: str, payload: Any) -> ContractModel:
    try:
        model = TOP_LEVEL_MODELS[model_name]
    except KeyError as exc:
        raise KeyError(f"unknown contract model {model_name}") from exc
    return model.model_validate(payload)
