/** Zod .strict() mirrors of the v4 Pydantic contracts. */

import { z } from "zod";

export const CONTRACT_VERSION = "v4";
export const DEPRECATED_IDENTIFIERS = ["FRAMES_MOTION_ONLY", "VEO_3_1_LITE", "CrimeScenePanZoom"] as const;

export const MVP_MOTIFS = ["StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame"] as const;
export const CATALOG_MOTIFS = [
  ...MVP_MOTIFS,
  "TimelineScrubber",
  "AnimatedMapRoute",
  "CellTowerTriangulation",
  "SplitScreenComparison",
  "CaseBoardSpine",
  "QuotePullout",
  "EvidenceGridMatrix",
  "ChapterSlateTransition",
  "Illustrative2KPanZoom",
  "HeroVideoBridge",
] as const;

export const MOTIF_REGISTRY_V1 = MVP_MOTIFS.map((motif_component) => ({
  motif_component,
  owner_package: "render_catalog" as const,
  is_mvp_4: true,
}));

export const RELEASE_GATES = [
  "FACTUAL_ACCURACY",
  "PRIVACY_PII",
  "SOURCE_RIGHTS",
  "SYNTHETIC_DISCLOSURE",
  "ILLUSTRATIVE_LABELING",
] as const;

const entityId = z.string().regex(/^[A-Za-z0-9_-]+$/).min(1).max(128);
const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const hexColor = z.string().regex(/^#[0-9A-Fa-f]{6}$/);
const shortText = z.string().min(1).max(200);
const nullableSha = sha256.nullable().default(null);
const version = z.literal("v4").default("v4");
const ISO_DT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$/;

function deprecatedHit(value: unknown, where = "$"): string | null {
  if (typeof value === "string") {
    for (const token of DEPRECATED_IDENTIFIERS) {
      if (value.includes(token)) return `${token} at ${where}`;
    }
    return null;
  }
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      const found = deprecatedHit(value[index], `${where}[${index}]`);
      if (found) return found;
    }
    return null;
  }
  if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      for (const token of DEPRECATED_IDENTIFIERS) {
        if (key.includes(token)) return `${token} at ${where}.${key}`;
      }
      const found = deprecatedHit(item, `${where}.${key}`);
      if (found) return found;
    }
  }
  return null;
}

export function assertNoDeprecated(value: unknown): void {
  const found = deprecatedHit(value);
  if (found) throw new Error(`deprecated identifier rejected: ${found}`);
}

function unsafePath(value: string): boolean {
  const normalized = value.replace(/\\/g, "/");
  return normalized.startsWith("/") || normalized.includes("..");
}

function issue(ctx: z.RefinementCtx, message: string): void {
  ctx.addIssue({ code: z.ZodIssueCode.custom, message });
}

function enforceVideoPrompt(
  ctx: z.RefinementCtx,
  mode: string,
  durationMs: number,
  hasStart: boolean,
  hasEnd: boolean,
): void {
  if (mode === "TEXT_TO_VIDEO") {
    if (hasStart || hasEnd) issue(ctx, "TEXT_TO_VIDEO requires null frames");
    if (durationMs < 3000 || durationMs > 15000) issue(ctx, "TEXT_TO_VIDEO duration must be 3-15 seconds");
  } else if (mode === "FIRST_FRAME") {
    if (!hasStart || hasEnd) issue(ctx, "FIRST_FRAME requires a start frame and a null end frame");
    if (durationMs < 3000 || durationMs > 15000) issue(ctx, "FIRST_FRAME duration must be 3-15 seconds");
  } else if (mode === "FIRST_AND_LAST_FRAME") {
    if (!hasStart || !hasEnd) issue(ctx, "FIRST_AND_LAST_FRAME requires start and end frames");
    if (durationMs < 3000 || durationMs > 10000) issue(ctx, "FIRST_AND_LAST_FRAME duration must be 3-10 seconds");
  } else {
    issue(ctx, "prompt_mode is not a current video mode");
  }
}

const visualEngine = z.enum([
  "CODE_STICKMAN",
  "STILL_2K_PANZOOM",
  "AUDIO_EVIDENCE_CARD",
  "FOIA_REAL_FOOTAGE",
  "FLOW_HERO_VIDEO",
]);
const catalogMotif = z.enum(CATALOG_MOTIFS);
const mvpMotif = z.enum(MVP_MOTIFS);
const scenePrompt = z.enum(["NONE", "TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]);
const videoPrompt = z.enum(["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]);
const flowBackend = z.enum(["GEMINI_OMNI_INTERACTIONS", "VERTEX_VEO_ENTERPRISE", "HUMAN_BATCH_DESK"]);

export const SeedPacket = z
  .object({
    contract_version: version,
    track: z.enum(["TRACK_A_OUTLIER", "TRACK_B_FOIA_RADAR"]),
    lead_classification: z.literal("LEAD_ONLY").default("LEAD_ONLY"),
    suspect_names: z.array(shortText).max(8).default([]),
    victim_names: z.array(shortText).max(8).default([]),
    incident_date_or_year: shortText,
    county_state: shortText,
    docket_ids: z.array(entityId).max(8).default([]),
    unanswered_comment_questions: z.array(shortText).max(8).default([]),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.suspect_names.length + value.victim_names.length + value.docket_ids.length === 0) {
      issue(ctx, "SeedPacket requires a suspect, victim, or docket lookup key");
    }
    for (const question of value.unanswered_comment_questions) {
      const terminators = question.match(/[.!?]+/g) ?? [];
      if (terminators.length > 1) issue(ctx, "unanswered_comment_questions must be a single sentence");
    }
  });

export const TemporalFact = z
  .object({
    fact_id: entityId,
    case_id: entityId,
    datetime_iso: z.string(),
    event_summary: z.string().min(1).max(2000),
    physical_clues_json: z.array(shortText).max(32).default([]),
    location_text: z.string().min(1).max(300),
    source_type: z.enum(["court_ruling", "police_affidavit", "news_report"]),
    source_doc_id: entityId,
    citation_locator: z.string().min(1).max(300),
    hedging_required: z.boolean(),
    contradicts_json: z.array(entityId).default([]),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (!ISO_DT.test(value.datetime_iso) || Number.isNaN(Date.parse(value.datetime_iso))) {
      issue(ctx, "datetime_iso must be timezone-aware ISO-8601");
    }
    if (value.source_type === "news_report" && !value.hedging_required) {
      issue(ctx, "news_report facts require hedging_required");
    }
  });

export const TemporalFactLedger = z
  .object({
    contract_version: version,
    case_id: entityId,
    facts: z.array(TemporalFact).min(1),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.facts.some((fact) => fact.case_id !== value.case_id)) {
      issue(ctx, "fact case_id must match the ledger case_id");
    }
  });

export const ComplianceClearedCase = z
  .object({
    contract_version: version,
    case_id: entityId,
    defendant_name: shortText,
    incident_year: z.number().int().gte(1800).lte(2100),
    jurisdiction: z.string().min(1).max(200),
    verification_source: z.string().min(1).max(300),
    disposition_status: z.enum(["AFFIRMED", "STANDING_CONVICTION"]),
    conviction_confirmed: z.literal(true),
    primary_record_verified: z.literal(true),
    anonymization_status: z.literal("APPROVED"),
    anonymized_by: z.string().min(1).max(128),
    anonymized_at: z.number().int().gte(0),
    anonymization_artifact_sha256: sha256,
    audit_id: entityId,
    provenance_whitelist_ok: z.literal(true),
    that_vs_how_passed: z.literal(true),
    anti_legal_persona_passed: z.literal(true),
    first_30s_adsense_safe: z.literal(true),
    spoken_pii_audit_passed: z.literal(true),
    altered_content_disclosure: z.boolean(),
    audited_at: z.number().int().gte(0),
  })
  .strict();

const KeyframeRef = z
  .object({
    ref_id: entityId,
    role: z.enum(["START", "END"]),
    sha256,
  })
  .strict();

const TransitionSpec = z
  .object({
    transition_type: z.enum(["CUT", "DISSOLVE", "MATCH_CUT"]),
    duration_ms: z.number().int().gte(0).lte(1000),
  })
  .strict();

const SoundCue = z
  .object({
    cue_id: entityId,
    offset_ms: z.number().int().gte(0),
    role: z.enum(["BED", "HIT", "ROOM_TONE"]),
  })
  .strict();

const AcceptanceCriterion = z
  .object({
    criterion_id: entityId,
    kind: z.enum(["SEMANTIC", "TECHNICAL"]),
    text: z.string().min(1).max(500),
  })
  .strict();

export const ScenePlan = z
  .object({
    contract_version: version,
    scene_plan_id: entityId,
    episode_id: entityId,
    scene_id: entityId,
    plan_version: z.number().int().gte(1).default(1),
    seq_index: z.number().int().gte(1),
    story_purpose: z.string().min(1).max(500),
    intended_audience_effect: z.string().min(1).max(500),
    approved_narration_text: z.string().min(1).max(4000),
    narration_version_sha256: sha256,
    cited_fact_ids_json: z.array(entityId).min(1),
    visual_concept: z.string().min(1).max(500),
    visual_engine: visualEngine,
    motif_component: catalogMotif,
    prompt_mode: scenePrompt,
    visual_prompt: z.string().min(1).max(4000),
    keyframe_refs_json: z.array(KeyframeRef).default([]),
    expected_output_summary: z.string().min(1).max(500),
    timing_start_ms: z.number().int().gte(0),
    timing_end_ms: z.number().int(),
    transition_spec_json: TransitionSpec,
    sound_cues_json: z.array(SoundCue).default([]),
    edit_instructions: z.string().min(1).max(2000),
    acceptance_criteria_json: z.array(AcceptanceCriterion).min(1),
    asset_version_sha256: nullableSha,
    plan_status: z.enum(["DRAFT", "PLAN_APPROVED", "ASSETS_CREATED", "EDITED_APPROVED", "STALE_NEEDS_REAPPROVAL"]).default("DRAFT"),
    reviewed_by: z.string().min(1).nullable().default(null),
    reviewed_at: z.number().int().nullable().default(null),
    created_at: z.number().int().gte(0),
    updated_at: z.number().int().gte(0),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.timing_end_ms <= value.timing_start_ms) issue(ctx, "timing_end_ms must be greater than timing_start_ms");
    if (value.updated_at < value.created_at) issue(ctx, "updated_at must be >= created_at");
    if (!value.acceptance_criteria_json.some((item) => item.kind === "SEMANTIC")) {
      issue(ctx, "acceptance_criteria_json requires a SEMANTIC criterion");
    }
    if ((value.plan_status === "PLAN_APPROVED" || value.plan_status === "EDITED_APPROVED") && (!value.reviewed_by || value.reviewed_at === null)) {
      issue(ctx, "approved plans require reviewed_by and reviewed_at");
    }
    if (value.plan_status === "EDITED_APPROVED" && value.asset_version_sha256 === null) {
      issue(ctx, "EDITED_APPROVED requires asset_version_sha256");
    }
    const duration = value.timing_end_ms - value.timing_start_ms;
    const roles = value.keyframe_refs_json.map((item) => item.role).join(",");
    if (value.prompt_mode === "NONE") {
      if (roles) issue(ctx, "prompt_mode NONE does not take keyframes");
    } else if (value.prompt_mode === "TEXT_TO_VIDEO") {
      if (roles) issue(ctx, "TEXT_TO_VIDEO keyframe_refs_json must be empty");
      if (duration < 3000 || duration > 15000) issue(ctx, "TEXT_TO_VIDEO duration must be 3000-15000 ms");
    } else if (value.prompt_mode === "FIRST_FRAME") {
      if (roles !== "START") issue(ctx, "FIRST_FRAME requires exactly one START keyframe");
      if (duration < 3000 || duration > 15000) issue(ctx, "FIRST_FRAME duration must be 3000-15000 ms");
    } else if (roles !== "START,END") {
      issue(ctx, "FIRST_AND_LAST_FRAME requires START then END keyframes");
    } else if (duration < 3000 || duration > 10000) {
      issue(ctx, "FIRST_AND_LAST_FRAME duration must be 3000-10000 ms");
    }
  });

const WordTimestamp = z
  .object({
    segment_id: entityId,
    word: z.string().min(1).max(80),
    start_ms: z.number().int().gte(0),
    end_ms: z.number().int().gte(0),
  })
  .strict();

const CuePoint = z
  .object({
    cue_id: entityId,
    at_ms: z.number().int().gte(0),
    label: z.string().min(1).max(120),
  })
  .strict();

const VoiceSegment = z
  .object({
    segment_id: entityId,
    episode_id: entityId,
    seq_index: z.number().int().gte(1),
    segment_kind: z.enum(["NARRATION", "FOIA_AUDIO_SLOT", "TWIST_PAD"]),
    start_ms: z.number().int().gte(0),
    end_ms: z.number().int(),
    audio_path: z.string().nullable().default(null),
    foia_asset_id: entityId.nullable().default(null),
    narration_version_sha256: nullableSha,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.end_ms <= value.start_ms) issue(ctx, "segment end_ms must be greater than start_ms");
    if (value.audio_path && unsafePath(value.audio_path)) issue(ctx, "path must be a relative path without traversal");
    const duration = value.end_ms - value.start_ms;
    if (value.segment_kind === "NARRATION") {
      if (!value.audio_path || value.narration_version_sha256 === null) {
        issue(ctx, "NARRATION requires audio_path and narration_version_sha256");
      }
    } else if (value.segment_kind === "FOIA_AUDIO_SLOT") {
      if (value.foia_asset_id === null || value.audio_path !== null) {
        issue(ctx, "FOIA_AUDIO_SLOT requires foia_asset_id and a silent audio_path");
      }
    } else if (duration < 450 || duration > 750) {
      issue(ctx, "TWIST_PAD duration must be 450-750 ms");
    }
  });

export const VoiceTrackManifest = z
  .object({
    contract_version: version,
    episode_id: entityId,
    total_master_ms: z.number().int().gte(0),
    segments: z.array(VoiceSegment).min(1),
    word_timestamps: z.array(WordTimestamp).default([]),
    cue_points: z.array(CuePoint).default([]),
    amplitude_envelope: z.array(z.number()).default([]),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.amplitude_envelope.some((sample) => sample < 0 || sample > 1)) {
      issue(ctx, "amplitude_envelope samples must be within 0..1");
    }
    const ordered = [...value.segments].sort((left, right) => left.start_ms - right.start_ms);
    const expected = ordered.map((_, index) => index + 1);
    if (ordered.some((segment, index) => segment.seq_index !== expected[index])) {
      issue(ctx, "seq_index must follow start time and begin at 1");
    }
    if (ordered[0].start_ms !== 0) issue(ctx, "voice timeline must start at 0 ms");
    for (let index = 1; index < ordered.length; index += 1) {
      if (ordered[index].start_ms < ordered[index - 1].end_ms) issue(ctx, "voice segments must not overlap");
    }
    if (ordered[ordered.length - 1].end_ms > value.total_master_ms) {
      issue(ctx, "segments must end at or before total_master_ms");
    }
    const ids = new Set(value.segments.map((segment) => segment.segment_id));
    if (ids.size !== value.segments.length) issue(ctx, "segment_id values must be unique");
    if (value.segments.some((segment) => segment.episode_id !== value.episode_id)) {
      issue(ctx, "segment episode_id must match the manifest");
    }
    const byId = new Map(value.segments.map((segment) => [segment.segment_id, segment]));
    const spans = new Map<string, Array<[number, number]>>();
    for (const stamp of value.word_timestamps) {
      const host = byId.get(stamp.segment_id);
      if (!host || host.segment_kind !== "NARRATION") issue(ctx, "word timestamp must cite a NARRATION segment");
      else if (stamp.end_ms <= stamp.start_ms || stamp.start_ms < host.start_ms || stamp.end_ms > host.end_ms) {
        issue(ctx, "word timestamp must sit inside its narration segment");
      }
      const bucket = spans.get(stamp.segment_id) ?? [];
      bucket.push([stamp.start_ms, stamp.end_ms]);
      spans.set(stamp.segment_id, bucket);
    }
    for (const bucket of spans.values()) {
      bucket.sort((left, right) => left[0] - right[0]);
      for (let index = 1; index < bucket.length; index += 1) {
        if (bucket[index][0] < bucket[index - 1][1]) issue(ctx, "word timestamps must not overlap");
      }
    }
    if (value.cue_points.some((cue) => cue.at_ms > value.total_master_ms)) {
      issue(ctx, "cue_point lies outside the manifest");
    }
  });

export const SpatialAnchor = z
  .object({
    contract_version: version,
    anchor_id: entityId,
    episode_id: entityId,
    still_2k_id: entityId,
    clue_name: z.string().min(1).max(200),
    cited_fact_id: entityId.nullable().default(null),
    grid_cell: z.string().regex(/^[A-J]([1-9]|10)$/),
    span_cols: z.number().gt(0).lte(10).default(1),
    span_rows: z.number().gt(0).lte(10).default(1),
    x_px: z.number().int().gte(0),
    y_px: z.number().int().gte(0),
    target_zoom: z.number().gte(1).lte(3.8).default(2.5),
    travel_axis: z.enum(["L_TO_R", "R_TO_L", "STATIC"]).nullable().default(null),
    lock_status: z.enum(["DRAFT", "IN_REVIEW", "LOCKED"]).default("DRAFT"),
    locked_by: z.string().min(1).nullable().default(null),
    locked_at: z.number().int().nullable().default(null),
    still_asset_sha256: nullableSha,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.lock_status === "LOCKED" && (!value.locked_by || value.locked_at === null || value.still_asset_sha256 === null)) {
      issue(ctx, "LOCKED anchors require locked_by, locked_at, and still_asset_sha256");
    }
  });

const StyleDna = z
  .object({
    evidence_crimson_hex: hexColor.default("#C92A2A"),
    paper_bg_hex: hexColor.default("#E9E2D2"),
    ink_hex: hexColor.default("#1B1B1D"),
    slate_hex: hexColor.default("#3A4F66"),
    flow_keyframe_safe_palette: z.array(hexColor).min(1).max(8).default(["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"]),
  })
  .strict()
  .superRefine((value, ctx) => {
    const banned = new Set([value.evidence_crimson_hex.toUpperCase(), "#C92A2A"]);
    if (value.flow_keyframe_safe_palette.some((color) => banned.has(color.toUpperCase()))) {
      issue(ctx, "flow_keyframe_safe_palette must exclude evidence crimson");
    }
  });

const CharacterSpec = z
  .object({
    character_id: z.string().regex(/^[a-z][a-z0-9_]*$/).max(64),
    prop: z.string().min(1).max(80),
    color_hex: hexColor,
  })
  .strict();

export const CaseBible = z
  .object({
    contract_version: version,
    episode_id: entityId,
    style_dna_json: StyleDna,
    characters_json: z.array(CharacterSpec).min(1),
    locked_at: z.number().int().gte(0),
  })
  .strict();

export const ProductionManifest = z
  .object({
    contract_version: version,
    manifest_id: entityId,
    episode_id: entityId,
    case_id: entityId,
    fps: z.literal(30).default(30),
    cold_open_archetype: z.enum([
      "911_CALL_IN_MEDIA_RES",
      "SINGLE_FORENSIC_ANOMALY",
      "ALIBI_THAT_CRACKED",
      "CHRONOLOGICAL_COUNTDOWN",
    ]),
    flow_backend_mode: flowBackend,
    target_duration_ms: z.number().int().gt(0),
    code_foia_ms: z.number().int().gte(0),
    still_2k_ms: z.number().int().gte(0),
    hero_ms: z.number().int().gte(0),
    max_hero_clips: z.number().int().gte(0).lte(10).default(10),
    max_hero_duration_sec: z.number().int().gte(0).lte(80).default(80),
    hero_clip_count: z.number().int().gte(0).lte(10),
    hero_duration_sec: z.number().int().gte(0).lte(80),
    scene_plan_ids: z.array(entityId).min(1),
    voice_total_master_ms: z.number().int().gte(0),
    timeline_validated_sha256: nullableSha,
  })
  .strict()
  .superRefine((value, ctx) => {
    if (value.code_foia_ms + value.still_2k_ms + value.hero_ms !== value.target_duration_ms) {
      issue(ctx, "code_foia_ms + still_2k_ms + hero_ms must equal target_duration_ms");
    }
    if (value.hero_ms !== value.hero_duration_sec * 1000) issue(ctx, "hero_ms must equal hero_duration_sec * 1000");
    if (value.hero_clip_count > value.max_hero_clips) issue(ctx, "hero_clip_count exceeds max_hero_clips");
    if (value.hero_duration_sec > value.max_hero_duration_sec) issue(ctx, "hero_duration_sec exceeds max_hero_duration_sec");
    if (Math.abs(value.voice_total_master_ms - value.target_duration_ms) > 250) {
      issue(ctx, "voice_total_master_ms must be within 250 ms of target_duration_ms");
    }
  });

export const TimelineSpec = z
  .object({
    contract_version: version,
    episode_id: entityId,
    scene_id: entityId,
    scene_plan_id: entityId,
    fps: z.literal(30).default(30),
    width_px: z.literal(1920).default(1920),
    height_px: z.literal(1080).default(1080),
    motif_registry: z.literal("MOTIF_REGISTRY_V1").default("MOTIF_REGISTRY_V1"),
    motif_component: mvpMotif,
    prompt_mode: videoPrompt,
    duration_ms: z.number().int(),
    start_frame_sha256: nullableSha,
    end_frame_sha256: nullableSha,
  })
  .strict()
  .superRefine((value, ctx) => {
    enforceVideoPrompt(ctx, value.prompt_mode, value.duration_ms, value.start_frame_sha256 !== null, value.end_frame_sha256 !== null);
  });

const FallbackSpec = z
  .object({
    visual_engine: visualEngine,
    motif_component: catalogMotif,
    reason: z.string().min(1).max(300),
  })
  .strict();

export const FlowJobCard = z
  .object({
    contract_version: version,
    flow_job_id: entityId,
    episode_id: entityId,
    scene_id: entityId,
    idempotency_key: z.string().min(8).max(200),
    assigned_account_id: entityId.nullable().default(null),
    provider_route: flowBackend.default("GEMINI_OMNI_INTERACTIONS"),
    engine_model: z.enum(["gemini-omni-1.2-flash", "vertex-veo-enterprise", "manual-desk-video"]).default("gemini-omni-1.2-flash"),
    prompt_mode: videoPrompt,
    resolution: z.enum(["360p", "720p", "1080p", "4k"]).default("720p"),
    duration_bucket_sec: z.number().int().gte(3).lte(15),
    variations: z.literal(1).default(1),
    estimated_micro_usd: z.number().int().gte(0),
    estimated_credits: z.number().int().gte(0).default(0),
    start_frame_png: z.string().nullable().default(null),
    end_frame_png: z.string().nullable().default(null),
    prompt_v1: z.string().min(1).max(4000),
    prompt_v2_safe: z.string().min(1).max(4000),
    fallback_spec_json: FallbackSpec,
    provider_operation_id: z.string().nullable().default(null),
    attempts_used: z.number().int().gte(0).lte(2).default(0),
    state: z
      .enum([
        "PENDING",
        "SUBMITTING",
        "RUNNING",
        "UNKNOWN_RECONCILE",
        "PENDING_MANUAL_SPOT_CHECK",
        "STRIKE_1_RETRY_SAFE",
        "ACCEPTED",
        "FAILED_TERMINAL",
        "SWITCHED_TO_FALLBACK",
      ])
      .default("PENDING"),
    output_asset_path: z.string().nullable().default(null),
    updated_at: z.number().int().gte(0),
  })
  .strict()
  .superRefine((value, ctx) => {
    for (const path of [value.start_frame_png, value.end_frame_png, value.output_asset_path]) {
      if (path && unsafePath(path)) issue(ctx, "path must be a relative path without traversal");
    }
    enforceVideoPrompt(
      ctx,
      value.prompt_mode,
      value.duration_bucket_sec * 1000,
      value.start_frame_png !== null,
      value.end_frame_png !== null,
    );
  });

export const EpisodeAnalyticsSnapshot = z
  .object({
    contract_version: version,
    snapshot_id: entityId,
    episode_id: entityId,
    days_since_publish: z.number().int().gte(1),
    ctr_pct: z.number().nullable().default(null),
    retention_30s_pct: z.number().nullable().default(null),
    retention_min6_14_pct: z.number().nullable().default(null),
    avd_pct: z.number().nullable().default(null),
    watch_hours_total: z.number().gte(0).default(0),
    rpm_micro_usd: z.number().int().nullable().default(null),
    adsense_status: z.enum(["UNKNOWN", "PENDING", "NOT_LINKED", "GREEN_FULL_ADS", "YELLOW_LIMITED", "NONE"]).default("UNKNOWN"),
    adsense_source: z.enum(["STUDIO_CSV_EXPORT", "MANUAL_CREATOR_ENTRY", "UNAVAILABLE"]).default("UNAVAILABLE"),
    adsense_checked_at: z.number().int().nullable().default(null),
    metrics_source: z.enum(["YT_ANALYTICS_API", "STUDIO_CSV_EXPORT", "COMBINED"]).default("YT_ANALYTICS_API"),
    captured_at: z.number().int().gte(0),
  })
  .strict()
  .superRefine((value, ctx) => {
    for (const name of ["ctr_pct", "retention_30s_pct", "retention_min6_14_pct", "avd_pct"] as const) {
      const sample = value[name];
      if (sample !== null && (sample < 0 || sample > 100)) issue(ctx, `${name} must be within 0..100`);
    }
    if (value.rpm_micro_usd !== null && value.rpm_micro_usd < 0) issue(ctx, "rpm_micro_usd must be >= 0");
    const monetized = value.adsense_status !== "UNKNOWN" && value.adsense_status !== "NOT_LINKED";
    if (monetized && value.adsense_source === "UNAVAILABLE") {
      issue(ctx, "a known adsense_status requires a Studio or manual source");
    }
    if (value.adsense_source !== "UNAVAILABLE" && value.adsense_checked_at === null) {
      issue(ctx, "adsense_checked_at is required when a source is recorded");
    }
  });

export const ReadyToUploadPack = z
  .object({
    contract_version: version,
    episode_id: entityId,
    episode_slug: entityId,
    ready_pack_dir: z.string().min(1).max(240),
    ready_bundle_sha256: sha256,
    final_mp4_relpath: z.literal("final_1080p30.mp4"),
    final_mp4_sha256: sha256,
    integrated_lufs: z.number(),
    true_peak_dbtp: z.number(),
    lufs_passed: z.literal(true),
    safe_zone_passed: z.literal(true),
    vision_frame_qa_status: z.literal("PASSED"),
    thumbnail_brand_passed: z.literal(true),
    thumbnail_relpaths: z.array(z.string()).min(1).max(3),
    chapters_relpath: z.literal("chapters.txt"),
    youtube_synthetic_disclosure_required: z.boolean(),
    provenance_bundle_relpath: z.literal("provenance_bundle.json"),
    qa_certificate_relpath: z.literal("qa_certificate.json"),
    human_review_flags: z.array(z.string()).max(0).default([]),
    approved_release_gates: z.array(z.enum(RELEASE_GATES)).length(5),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (unsafePath(value.ready_pack_dir)) issue(ctx, "path must be a relative path without traversal");
    for (const rel of value.thumbnail_relpaths) {
      if (unsafePath(rel) || !rel.endsWith(".png")) issue(ctx, "thumbnail_relpaths must be safe png files");
    }
    if (value.true_peak_dbtp > -1) issue(ctx, "true_peak_dbtp must be <= -1.0");
    if (value.integrated_lufs < -14.5 || value.integrated_lufs > -13.5) {
      issue(ctx, "integrated_lufs must stay within 0.5 of -14.0");
    }
    if (value.human_review_flags.length > 0) issue(ctx, "human_review_flags must be empty before upload");
    if (value.approved_release_gates.join("|") !== RELEASE_GATES.join("|")) {
      issue(ctx, "approved_release_gates must be the five release gates in order");
    }
    if (value.human_review_flags.some((flag) => flag.length < 1 || flag.length > 200)) {
      issue(ctx, "human_review_flags entries must be 1-200 characters");
    }
  });

export const ProviderEntry = z
  .object({
    model_id: z.string().min(1).max(128),
    api: z.string().min(1).max(128),
    pricing: z.record(z.string(), z.number()).default({}),
    limits: z.record(z.string(), z.number().int()).default({}),
  })
  .strict();

export const ProviderRegistry = z
  .object({
    contract_version: version,
    providers: z.record(z.string(), ProviderEntry).refine((value) => Object.keys(value).length > 0),
  })
  .strict();

export const CraftPrinciple = z
  .object({
    principle_id: entityId,
    summary: z.string().min(1).max(240),
  })
  .strict();

export const CraftRubric = z
  .object({
    contract_version: version,
    rubric_id: z.literal("craft_rubric_v4"),
    principles: z.array(CraftPrinciple).min(1).max(40),
  })
  .strict();

export const RenderReceipt = z
  .object({
    contract_version: version,
    backend_name: z.string().min(1).max(80),
    output_relpath: z.string().min(1).max(240),
    fps: z.literal(30).default(30),
    sha256,
  })
  .strict();

export const SCHEMAS = {
  SeedPacket,
  TemporalFactLedger,
  ComplianceClearedCase,
  ScenePlan,
  VoiceTrackManifest,
  SpatialAnchor,
  CaseBible,
  ProductionManifest,
  TimelineSpec,
  FlowJobCard,
  EpisodeAnalyticsSnapshot,
  ReadyToUploadPack,
  ProviderRegistry,
  CraftRubric,
  RenderReceipt,
} as const;

export type ContractName = keyof typeof SCHEMAS;

export function parseContract(modelName: string, payload: unknown): unknown {
  assertNoDeprecated(payload);
  const schema = SCHEMAS[modelName as ContractName];
  if (!schema) throw new Error(`unknown contract model ${modelName}`);
  return schema.parse(payload);
}
