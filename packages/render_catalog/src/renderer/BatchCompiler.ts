/**
 * Timeline batch compiler for `@tc/render_catalog`.
 *
 * Turns a 1920x1080 @ 30 fps `timeline_spec` (the golden-pack document, or the
 * same shape) into scene MP4 containers, `micro_sfx_cues.json`, and one
 * `scene_grade_manifest.json`. Remotion does not paint paper grain or vignette.
 * Agent 6 reads the manifest and grades non-FOIA scenes once.
 *
 * Tasks 109, 110, 112, and 115–127 own the grade module, the SFX dispatcher,
 * the worker pool, and the motif components. Those files are not on this
 * branch and are not copied here. Grade flags follow Task 109: `FOIA_REAL_FOOTAGE`
 * and `FoiaFootageFrame` stay raw (`apply_grade: false`); every other engine is
 * stylized (`apply_grade: true`). Cue names and sample math follow Task 110.
 *
 * `Illustrative2KPanZoom` stays with `crime_scene_2k`. `HeroVideoBridge` stays
 * with `flow_adapter` unless a job is `SWITCHED_TO_FALLBACK`, in which case the
 * scene swaps to `fallback_spec` with no timeline gap. `--mvp-4-motifs` compiles
 * only the four MVP motifs and still records every other scene in the manifest.
 */

declare const process: {
  getBuiltinModule(id: string): unknown;
};

type FsPromises = {
  mkdir(path: string, options: { recursive: boolean }): Promise<void>;
  writeFile(path: string, data: Uint8Array | string): Promise<void>;
};

type PathModule = {
  join(...parts: string[]): string;
  resolve(...parts: string[]): string;
};

export const SCENE_GRADE_MANIFEST_FILENAME = "scene_grade_manifest.json";
export const MICRO_SFX_CUES_FILENAME = "micro_sfx_cues.json";
export const GRADE_MANIFEST_SCHEMA = "scene_grade_manifest.v1";
export const MICRO_SFX_SCHEMA = "micro_sfx_cues.v1";
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const MIX_SAMPLE_RATE_HZ = 48_000;
export const COOLDOWN_MS = 60;
export const COOLDOWN_SAMPLES = (COOLDOWN_MS * MIX_SAMPLE_RATE_HZ) / 1_000;
export const GAIN_UNIT_SCALE = 1_000_000_000;

const SAMPLES_PER_MS = MIX_SAMPLE_RATE_HZ / 1_000;
const SAMPLES_PER_FRAME = MIX_SAMPLE_RATE_HZ / FRAME_FPS;
const ENTITY_ID = /^[A-Za-z0-9_-]+$/;
const BANNED_SVG = [/feTurbulence/i, /feDisplacementMap/i];

export const VISUAL_ENGINES = [
  "CODE_STICKMAN",
  "STILL_2K_PANZOOM",
  "AUDIO_EVIDENCE_CARD",
  "FOIA_REAL_FOOTAGE",
  "FLOW_HERO_VIDEO",
] as const;

export type VisualEngine = (typeof VISUAL_ENGINES)[number];

export const FLOW_STATES = [
  "PENDING",
  "SUBMITTING",
  "RUNNING",
  "UNKNOWN_RECONCILE",
  "PENDING_MANUAL_SPOT_CHECK",
  "STRIKE_1_RETRY_SAFE",
  "ACCEPTED",
  "FAILED_TERMINAL",
  "SWITCHED_TO_FALLBACK",
] as const;

export type FlowState = (typeof FLOW_STATES)[number];

const MICRO_SFX_TABLE = [
  { cue: "typing_tap", durationMs: 40, nominalDbtp: -12 },
  { cue: "highlighter_glide", durationMs: 280, nominalDbtp: -14 },
  { cue: "camera_shutter", durationMs: 90, nominalDbtp: -8 },
  { cue: "pin_thud", durationMs: 140, nominalDbtp: -8 },
  { cue: "conflict_stamp", durationMs: 400, nominalDbtp: -6 },
  { cue: "tick_sfx", durationMs: 30, nominalDbtp: -14 },
  { cue: "radio_squelch", durationMs: 200, nominalDbtp: -10 },
  { cue: "tape_click", durationMs: 55, nominalDbtp: -10 },
] as const;

export type MicroSfxName = (typeof MICRO_SFX_TABLE)[number]["cue"];

export const MVP_MOTIFS = ["StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame"] as const;

/** Twelve `@tc/render_catalog` motifs. 2K stills and the Flow bridge are not in this list. */
export const CATALOG_12 = [
  ...MVP_MOTIFS,
  "TimelineScrubber",
  "AnimatedMapRoute",
  "CellTowerTriangulation",
  "SplitScreenComparison",
  "CaseBoardSpine",
  "QuotePullout",
  "EvidenceGridMatrix",
  "ChapterSlateTransition",
] as const;

export type OwnerPackage = "render_catalog" | "crime_scene_2k" | "flow_adapter";
export type CompileStatus = "compiled" | "delegated" | "withheld" | "out_of_slice";

export type MotifRoute = {
  motif_component: string;
  visual_engine: VisualEngine;
  owner_package: OwnerPackage;
  is_mvp_4: boolean;
  catalog_12: boolean;
  /** Built-in cue emitted at the scene start when this package compiles the motif. */
  signature_cue: MicroSfxName | null;
};

export const MOTIF_ROUTES: readonly MotifRoute[] = [
  { motif_component: "StickmanStage", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: true, catalog_12: true, signature_cue: null },
  { motif_component: "AudioEvidenceCard", visual_engine: "AUDIO_EVIDENCE_CARD", owner_package: "render_catalog", is_mvp_4: true, catalog_12: true, signature_cue: "tape_click" },
  { motif_component: "RedactedDocReveal", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: true, catalog_12: true, signature_cue: "highlighter_glide" },
  { motif_component: "FoiaFootageFrame", visual_engine: "FOIA_REAL_FOOTAGE", owner_package: "render_catalog", is_mvp_4: true, catalog_12: true, signature_cue: "radio_squelch" },
  { motif_component: "TimelineScrubber", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: "tick_sfx" },
  { motif_component: "AnimatedMapRoute", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: null },
  { motif_component: "CellTowerTriangulation", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: "radio_squelch" },
  { motif_component: "SplitScreenComparison", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: "conflict_stamp" },
  { motif_component: "CaseBoardSpine", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: "pin_thud" },
  { motif_component: "QuotePullout", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: null },
  { motif_component: "EvidenceGridMatrix", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: "camera_shutter" },
  { motif_component: "ChapterSlateTransition", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: true, signature_cue: null },
  { motif_component: "Illustrative2KPanZoom", visual_engine: "STILL_2K_PANZOOM", owner_package: "crime_scene_2k", is_mvp_4: false, catalog_12: false, signature_cue: null },
  { motif_component: "HeroVideoBridge", visual_engine: "FLOW_HERO_VIDEO", owner_package: "flow_adapter", is_mvp_4: false, catalog_12: false, signature_cue: null },
  { motif_component: "CustomDiagramScene", visual_engine: "CODE_STICKMAN", owner_package: "render_catalog", is_mvp_4: false, catalog_12: false, signature_cue: null },
];

const ROUTE_BY_MOTIF = new Map<string, MotifRoute>(MOTIF_ROUTES.map((route) => [route.motif_component, route]));

type MicroSfxDefinition = {
  cue: MicroSfxName;
  durationMs: number;
  durationSamples: number;
  nominalDbtp: number;
  gainUnits: number;
  registryIndex: number;
};

const SFX_BY_CUE = new Map<MicroSfxName, MicroSfxDefinition>(
  MICRO_SFX_TABLE.map((item, registryIndex) => {
    const definition: MicroSfxDefinition = {
      cue: item.cue,
      durationMs: item.durationMs,
      durationSamples: item.durationMs * SAMPLES_PER_MS,
      nominalDbtp: item.nominalDbtp,
      gainUnits: linearGainUnits(item.nominalDbtp),
      registryIndex,
    };
    return [item.cue, definition];
  }),
);

export class BatchCompilerError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "BatchCompilerError";
    this.code = code;
  }
}

export type BatchCompileOptions = {
  outDir: string;
  /** `--mvp-4-motifs`. Extended catalog motifs stay in the manifest and are not encoded. */
  mvp4Motifs?: boolean;
};

export type SceneGradeRecord = {
  timeline_index: number;
  seq_index: number;
  scene_id: string;
  visual_engine: VisualEngine;
  motif_component: string;
  requested_visual_engine: VisualEngine;
  requested_motif_component: string;
  apply_grade: boolean;
  needs_grade: boolean;
  is_foia: boolean;
  exempt_from_grain: boolean;
  remotion_grain_applied: false;
  remotion_vignette_applied: false;
  paper_grain: 0;
  vignette: 0;
  grain_phase: null;
  grade_owner: "agent6_single_pass" | "none";
  ungraded_masks: [];
  stylized_overlays: [];
  owner_package: OwnerPackage;
  compile_status: CompileStatus;
  fallback_applied: boolean;
  gap_ms: 0;
  routed: true;
  flow_state: FlowState | null;
  mp4_relpath: string | null;
  start_frame: number;
  duration_frames: number;
};

export type SceneGradeManifest = {
  filename: typeof SCENE_GRADE_MANIFEST_FILENAME;
  schema: typeof GRADE_MANIFEST_SCHEMA;
  contract_version: "v4";
  fps: typeof FRAME_FPS;
  width_px: typeof FRAME_WIDTH;
  height_px: typeof FRAME_HEIGHT;
  remotion_grain_applied: false;
  remotion_vignette_applied: false;
  paper_grain: 0;
  vignette: 0;
  grain_phase: null;
  grade_owner: "agent6_single_pass";
  single_grade_pass: true;
  mode: "full" | "mvp-4-motifs";
  episode_id: string;
  scenes: SceneGradeRecord[];
};

export type MicroSfxCue = {
  cue_id: string;
  cue: MicroSfxName;
  scene_id: string;
  start_sample: number;
  sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  start_frame: number;
  offset_ms: number;
  duration_samples: number;
  cooldown_ms: typeof COOLDOWN_MS;
  gain_units: number;
  gain_unit_scale: typeof GAIN_UNIT_SCALE;
  peak_dbtp: number;
  burst: false;
  tapered: false;
};

export type SuppressedMicroSfx = {
  cue: MicroSfxName;
  scene_id: string;
  start_sample: number;
  reason: "cooldown";
};

export type MicroSfxDocument = {
  filename: typeof MICRO_SFX_CUES_FILENAME;
  schema: typeof MICRO_SFX_SCHEMA;
  contract_version: "v4";
  sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  fps: typeof FRAME_FPS;
  cooldown_ms: typeof COOLDOWN_MS;
  episode_id: string;
  cues: MicroSfxCue[];
  suppressed: SuppressedMicroSfx[];
};

export type SceneMp4Receipt = {
  scene_id: string;
  relpath: string;
  path: string;
  width_px: typeof FRAME_WIDTH;
  height_px: typeof FRAME_HEIGHT;
  fps: typeof FRAME_FPS;
  duration_frames: number;
  paper_grain: 0;
  vignette: 0;
  remotion_grain_applied: false;
  svg_turbulence: false;
};

export type BatchCompileResult = {
  episode_id: string;
  mode: "full" | "mvp-4-motifs";
  fps: typeof FRAME_FPS;
  width_px: typeof FRAME_WIDTH;
  height_px: typeof FRAME_HEIGHT;
  out_dir: string;
  grade_manifest_path: string;
  micro_sfx_path: string;
  grade_manifest: SceneGradeManifest;
  micro_sfx: MicroSfxDocument;
  mp4s: SceneMp4Receipt[];
};

type NormalizedFallback = {
  visual_engine: VisualEngine;
  motif_component: string;
};

type PlanCue = {
  label: string;
  offset_ms: number;
};

type ExplicitCue = {
  scene_id: string;
  cue: MicroSfxName;
  offset_ms: number;
};

type PlannedScene = {
  scene_id: string;
  seq_index: number;
  start_frame: number;
  duration_frames: number;
  start_ms: number;
  duration_ms: number;
  requested_motif: string;
  requested_engine: VisualEngine;
  flow_state: FlowState | null;
  fallback: NormalizedFallback | null;
  swap: boolean;
  withheld: boolean;
  plan_cues: PlanCue[];
};

type ResolvedScene = PlannedScene & {
  timeline_index: number;
  route: MotifRoute;
  active_motif: string;
  active_engine: VisualEngine;
  compile_status: CompileStatus;
};

type PlannedCue = {
  cue: MicroSfxName;
  scene_id: string;
  sample: number;
  registryIndex: number;
  inputIndex: number;
};

function fail(code: string, message: string): never {
  throw new BatchCompilerError(code, message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function nodeBuiltin<T>(id: string): T {
  const loaded = process.getBuiltinModule(id);
  if (!loaded || typeof loaded !== "object") fail("RUNTIME", `node builtin ${id} is unavailable`);
  return loaded as T;
}

function linearGainUnits(dbtp: number): number {
  return Math.floor(10 ** (dbtp / 20) * GAIN_UNIT_SCALE + 1e-6);
}

function assertEntityId(value: string, label: string): void {
  if (!ENTITY_ID.test(value)) fail("BAD_TIMELINE", `${label} must match ^[A-Za-z0-9_-]+$`);
}

function isVisualEngine(value: string): value is VisualEngine {
  return (VISUAL_ENGINES as readonly string[]).includes(value);
}

function isFlowState(value: string): value is FlowState {
  return (FLOW_STATES as readonly string[]).includes(value);
}

function isMicroSfxName(value: string): value is MicroSfxName {
  return SFX_BY_CUE.has(value as MicroSfxName);
}

export function motifRoute(motif: string): MotifRoute {
  const route = ROUTE_BY_MOTIF.get(motif);
  if (!route) fail("UNKNOWN_MOTIF", `UNKNOWN_MOTIF: ${motif} is not in the catalog route table`);
  return route;
}

/** FOIA footage stays raw. Code, audio cards, 2K, Flow, and other stylized engines need one Agent 6 pass. */
export function sceneApplyGrade(visualEngine: VisualEngine, motifComponent: string): boolean {
  return visualEngine !== "FOIA_REAL_FOOTAGE" && motifComponent !== "FoiaFootageFrame";
}

function readEngine(value: unknown, label: string): VisualEngine {
  if (typeof value !== "string" || !isVisualEngine(value)) {
    fail("BAD_TIMELINE", `${label} must be a visual engine`);
  }
  return value;
}

function readMotif(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) fail("BAD_TIMELINE", `${label} motif_component is required`);
  return value;
}

function readInt(value: unknown, label: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum) {
    fail("FRAME_CLOCK", `${label} must be an integer >= ${minimum}`);
  }
  return value;
}

function assertNoSvg(source: unknown): void {
  const text = JSON.stringify(source);
  for (const pattern of BANNED_SVG) {
    if (pattern.test(text)) {
      fail("SVG_FILTER", `SVG_FILTER: ${pattern.source} is banned in render_catalog`);
    }
  }
}

function parseFallback(value: unknown): NormalizedFallback | null {
  if (value === undefined || value === null) return null;
  let record: unknown = value;
  if (typeof value === "string") {
    try {
      record = JSON.parse(value) as unknown;
    } catch {
      fail("BAD_TIMELINE", "fallback_spec json must be an object");
    }
  }
  if (!isRecord(record)) fail("BAD_TIMELINE", "fallback_spec must be an object");
  const engineRaw = record.engine ?? record.visual_engine;
  if (record.engine !== undefined && record.visual_engine !== undefined && record.engine !== record.visual_engine) {
    fail("ENGINE_MISMATCH", "ENGINE_MISMATCH: fallback engine and visual_engine disagree");
  }
  const visualEngine = readEngine(engineRaw, "fallback_spec engine");
  const motif = readMotif(record.motif_component, "fallback_spec");
  const route = motifRoute(motif);
  if (route.visual_engine !== visualEngine) {
    fail(
      "ENGINE_MISMATCH",
      `ENGINE_MISMATCH: motif ${motif} belongs to ${route.visual_engine}, not ${visualEngine}`,
    );
  }
  return { visual_engine: visualEngine, motif_component: motif };
}

function readPlanCues(value: unknown): PlanCue[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) fail("BAD_TIMELINE", "sound_cues_json must be an array");
  return value.map((item, index) => {
    if (!isRecord(item)) fail("BAD_TIMELINE", `sound cue ${index} must be an object`);
    const label = item.label ?? item.cue ?? item.role;
    if (typeof label !== "string" || label.length === 0) fail("BAD_TIMELINE", `sound cue ${index} needs a label`);
    return { label, offset_ms: readInt(item.offset_ms ?? 0, `sound cue ${index} offset_ms`, 0) };
  });
}

function readExplicitCues(source: Record<string, unknown>): ExplicitCue[] {
  const raw = source.micro_sfx ?? source.micro_sfx_triggers;
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) fail("BAD_TIMELINE", "micro_sfx must be an array");
  return raw.map((item, index) => {
    if (!isRecord(item)) fail("BAD_TIMELINE", `micro_sfx ${index} must be an object`);
    const sceneId = item.scene_id;
    if (typeof sceneId !== "string") fail("BAD_TIMELINE", `micro_sfx ${index} scene_id is required`);
    assertEntityId(sceneId, `micro_sfx ${index} scene_id`);
    const cue = item.cue;
    if (typeof cue !== "string" || !isMicroSfxName(cue)) {
      fail("UNKNOWN_CUE", `UNKNOWN_CUE: ${String(cue)} is not a micro-SFX cue`);
    }
    return { scene_id: sceneId, cue, offset_ms: readInt(item.offset_ms ?? 0, `micro_sfx ${index} offset_ms`, 0) };
  });
}

function episodeIdOf(source: Record<string, unknown>, sceneIds: readonly string[]): string {
  const found = new Set<string>();
  const episode = source.episode;
  if (isRecord(episode) && typeof episode.episode_id === "string") found.add(episode.episode_id);
  if (typeof source.episode_id === "string") found.add(source.episode_id);
  if (typeof source.pack_id === "string") found.add(source.pack_id);
  const rows = Array.isArray(source.scenes) ? source.scenes : [];
  for (const row of rows) {
    if (isRecord(row) && typeof row.episode_id === "string") found.add(row.episode_id);
  }
  if (found.size > 1) fail("BAD_TIMELINE", "episode_id values disagree");
  const chosen = [...found][0];
  if (!chosen) fail("BAD_TIMELINE", "episode_id is required");
  assertEntityId(chosen, "episode_id");
  if (sceneIds.length === 0) fail("BAD_TIMELINE", "timeline_spec has no scenes");
  return chosen;
}

function timelineRows(source: Record<string, unknown>): Record<string, unknown>[] {
  const timeline = source.timeline_spec;
  if (isRecord(timeline) && Array.isArray(timeline.scenes)) {
    const fps = timeline.fps;
    const width = timeline.width;
    const height = timeline.height;
    if (fps !== undefined && fps !== FRAME_FPS) fail("FRAME_CLOCK", "FRAME_CLOCK: timeline fps must be 30");
    if (width !== undefined && width !== FRAME_WIDTH) fail("FRAME_CLOCK", "FRAME_CLOCK: timeline width must be 1920");
    if (height !== undefined && height !== FRAME_HEIGHT) fail("FRAME_CLOCK", "FRAME_CLOCK: timeline height must be 1080");
    return timeline.scenes.filter((row): row is Record<string, unknown> => {
      if (!isRecord(row)) fail("BAD_TIMELINE", "timeline scene must be an object");
      return true;
    });
  }
  if (Array.isArray(source.scenes)) {
    return source.scenes.filter((row): row is Record<string, unknown> => {
      if (!isRecord(row)) fail("BAD_TIMELINE", "scene must be an object");
      return true;
    });
  }
  fail("BAD_TIMELINE", "timeline_spec.scenes is required");
}

function indexByScene(rows: unknown, label: string): Map<string, Record<string, unknown>> {
  const map = new Map<string, Record<string, unknown>>();
  if (rows === undefined || rows === null) return map;
  if (!Array.isArray(rows)) fail("BAD_TIMELINE", `${label} must be an array`);
  for (const row of rows) {
    if (!isRecord(row) || typeof row.scene_id !== "string") fail("BAD_TIMELINE", `${label} entry needs scene_id`);
    if (map.has(row.scene_id)) fail("BAD_TIMELINE", `BAD_TIMELINE: duplicate ${label} scene_id ${row.scene_id}`);
    map.set(row.scene_id, row);
  }
  return map;
}

function clockMs(frames: number): number {
  if (frames % 3 !== 0) {
    fail("FRAME_CLOCK", `FRAME_CLOCK: ${frames} frames is not an integer number of milliseconds at 30 fps`);
  }
  return (frames * 1000) / FRAME_FPS;
}

function planScenes(source: Record<string, unknown>): PlannedScene[] {
  const rows = timelineRows(source);
  const sceneRows = indexByScene(source.scenes, "scenes");
  const plans = indexByScene(source.scene_plans, "scene_plans");
  const jobs = indexByScene(source.flow_job_cards ?? source.flow_jobs, "flow_job_cards");
  const ordered = [...rows].sort((left, right) => readInt(left.seq_index, "seq_index", 1) - readInt(right.seq_index, "seq_index", 1));
  const seen = new Set<string>();
  let cursor = 0;
  const planned: PlannedScene[] = [];

  for (let index = 0; index < ordered.length; index += 1) {
    const row = ordered[index];
    if (!row) fail("BAD_TIMELINE", "timeline scene is missing");
    const sceneId = row.scene_id;
    if (typeof sceneId !== "string") fail("BAD_TIMELINE", "scene_id is required");
    assertEntityId(sceneId, "scene_id");
    if (seen.has(sceneId)) fail("BAD_TIMELINE", `BAD_TIMELINE: duplicate scene_id ${sceneId}`);
    seen.add(sceneId);
    const seq = readInt(row.seq_index, `${sceneId} seq_index`, 1);
    if (seq !== index + 1) fail("FRAME_CLOCK", `FRAME_CLOCK: seq_index ${seq} is not ${index + 1}`);

    const scene = sceneRows.get(sceneId);
    const spec = scene && isRecord(scene.timeline_spec_json) ? scene.timeline_spec_json : null;
    const durationFrames = readInt(
      row.duration_frames ?? spec?.duration_frames ?? scene?.duration_frames,
      `${sceneId} duration_frames`,
      1,
    );
    const startFrame = readInt(row.start_frame ?? spec?.start_frame ?? scene?.start_frame ?? cursor, `${sceneId} start_frame`, 0);
    if (startFrame !== cursor) {
      fail("FRAME_CLOCK", `FRAME_CLOCK: scene ${sceneId} start_frame ${startFrame} does not follow ${cursor}`);
    }
    const durationMs = clockMs(durationFrames);
    const startMs = clockMs(startFrame);
    if (scene) {
      if (scene.start_ms !== undefined && scene.end_ms !== undefined) {
        const start = readInt(scene.start_ms, `${sceneId} start_ms`, 0);
        const end = readInt(scene.end_ms, `${sceneId} end_ms`, 1);
        if (start !== startMs || end - start !== durationMs) {
          fail("FRAME_CLOCK", `FRAME_CLOCK: scene ${sceneId} milliseconds do not match 30 fps frames`);
        }
      }
      if (typeof scene.motif_component === "string" && scene.motif_component !== (row.motif_component ?? spec?.motif_component)) {
        fail("ENGINE_MISMATCH", `ENGINE_MISMATCH: scene ${sceneId} motif disagrees with timeline_spec`);
      }
      if (typeof scene.visual_engine === "string" && scene.visual_engine !== (row.visual_engine ?? spec?.visual_engine)) {
        fail("ENGINE_MISMATCH", `ENGINE_MISMATCH: scene ${sceneId} engine disagrees with timeline_spec`);
      }
    }

    const requestedMotif = readMotif(row.motif_component ?? spec?.motif_component ?? scene?.motif_component, sceneId);
    const requestedEngine = readEngine(row.visual_engine ?? spec?.visual_engine ?? scene?.visual_engine, `${sceneId} visual_engine`);
    const requestedRoute = motifRoute(requestedMotif);
    if (requestedRoute.visual_engine !== requestedEngine) {
      fail(
        "ENGINE_MISMATCH",
        `ENGINE_MISMATCH: motif ${requestedMotif} belongs to ${requestedRoute.visual_engine}, not ${requestedEngine}`,
      );
    }

    const job = jobs.get(sceneId);
    let flowState: FlowState | null = null;
    let jobFallback: unknown = null;
    if (job) {
      if (typeof job.state !== "string" || !isFlowState(job.state)) {
        fail("BAD_TIMELINE", `flow state for ${sceneId} is not a flow job state`);
      }
      flowState = job.state;
      jobFallback = job.fallback_spec_json ?? job.fallback_spec;
    }
    const sceneFallback = scene ? scene.fallback_spec_json ?? scene.fallback_spec : null;
    const fallback = parseFallback(jobFallback ?? sceneFallback);
    // An ACCEPTED job keeps a latent fallback and does not swap. Only SWITCHED_TO_FALLBACK,
    // or a hero scene row that already carries a fallback and has no job yet, swaps.
    const swap = flowState === "SWITCHED_TO_FALLBACK" || (flowState === null && requestedMotif === "HeroVideoBridge" && fallback !== null);
    const withheld = flowState !== null && flowState !== "ACCEPTED" && flowState !== "SWITCHED_TO_FALLBACK";
    if (swap && !fallback) fail("BAD_TIMELINE", `SWITCHED_TO_FALLBACK requires fallback_spec on ${sceneId}`);

    const plan = plans.get(sceneId);
    planned.push({
      scene_id: sceneId,
      seq_index: seq,
      start_frame: startFrame,
      duration_frames: durationFrames,
      start_ms: startMs,
      duration_ms: durationMs,
      requested_motif: requestedMotif,
      requested_engine: requestedEngine,
      flow_state: flowState,
      fallback: swap ? fallback : null,
      swap,
      withheld,
      plan_cues: readPlanCues(plan?.sound_cues_json),
    });
    cursor += durationFrames;
  }

  for (const sceneId of sceneRows.keys()) {
    if (!seen.has(sceneId)) fail("BAD_TIMELINE", `BAD_TIMELINE: scene ${sceneId} is missing from timeline_spec`);
  }
  for (const sceneId of jobs.keys()) {
    if (!seen.has(sceneId)) fail("BAD_TIMELINE", `BAD_TIMELINE: flow job ${sceneId} is missing from timeline_spec`);
  }
  const timeline = source.timeline_spec;
  if (isRecord(timeline) && timeline.frame_count !== undefined) {
    const frameCount = readInt(timeline.frame_count, "frame_count", 0);
    if (frameCount !== cursor) fail("FRAME_CLOCK", `FRAME_CLOCK: frame_count ${frameCount} does not equal ${cursor}`);
  }
  return planned;
}

function resolveScenes(planned: readonly PlannedScene[], mvp4Motifs: boolean): ResolvedScene[] {
  const resolved: ResolvedScene[] = planned.map((scene, timelineIndex) => {
    const activeMotif = scene.swap && scene.fallback ? scene.fallback.motif_component : scene.requested_motif;
    const activeEngine = scene.swap && scene.fallback ? scene.fallback.visual_engine : scene.requested_engine;
    const route = motifRoute(activeMotif);
    if (route.visual_engine !== activeEngine) {
      fail("ENGINE_MISMATCH", `ENGINE_MISMATCH: motif ${activeMotif} belongs to ${route.visual_engine}, not ${activeEngine}`);
    }
    let compileStatus: CompileStatus;
    if (scene.withheld) compileStatus = "withheld";
    else if (route.owner_package !== "render_catalog") compileStatus = "delegated";
    else if (mvp4Motifs && !route.is_mvp_4) compileStatus = "out_of_slice";
    else compileStatus = "compiled";
    return {
      ...scene,
      timeline_index: timelineIndex,
      route,
      active_motif: activeMotif,
      active_engine: activeEngine,
      compile_status: compileStatus,
    };
  });

  for (const scene of resolved) {
    if (!scene.swap) continue;
    if (scene.active_engine === "FLOW_HERO_VIDEO") {
      fail("RULE_04", "RULE_04: fallback engine cannot be FLOW_HERO_VIDEO");
    }
    const previous = resolved[scene.timeline_index - 1];
    const next = resolved[scene.timeline_index + 1];
    if (previous && previous.active_engine === scene.active_engine) {
      fail("RULE_04", `RULE_04: fallback engine matches the previous scene (${scene.scene_id})`);
    }
    if (next && next.active_engine === scene.active_engine) {
      fail("RULE_04", `RULE_04: fallback engine matches the next scene (${scene.scene_id})`);
    }
  }
  return resolved;
}

function pushCue(target: PlannedCue[], scene: ResolvedScene, cue: MicroSfxName, offsetMs: number, inputIndex: number): void {
  if (offsetMs < 0 || offsetMs >= scene.duration_ms) {
    fail("BAD_TIMELINE", `micro-SFX ${cue} on ${scene.scene_id} falls outside the scene`);
  }
  const definition = SFX_BY_CUE.get(cue);
  if (!definition) fail("UNKNOWN_CUE", `UNKNOWN_CUE: ${cue} is not a micro-SFX cue`);
  target.push({
    cue,
    scene_id: scene.scene_id,
    sample: (scene.start_ms + offsetMs) * SAMPLES_PER_MS,
    registryIndex: definition.registryIndex,
    inputIndex,
  });
}

type CueDispatch = {
  cues: MicroSfxCue[];
  suppressed: SuppressedMicroSfx[];
};

function collectCues(scenes: readonly ResolvedScene[], explicit: readonly ExplicitCue[]): CueDispatch {
  const known = new Set(scenes.map((scene) => scene.scene_id));
  const planned: PlannedCue[] = [];
  let inputIndex = 0;
  for (const scene of scenes) {
    if (scene.compile_status !== "compiled") continue;
    if (scene.route.signature_cue) {
      pushCue(planned, scene, scene.route.signature_cue, 0, inputIndex);
      inputIndex += 1;
    }
    for (const cue of scene.plan_cues) {
      if (!isMicroSfxName(cue.label)) continue;
      pushCue(planned, scene, cue.label, cue.offset_ms, inputIndex);
      inputIndex += 1;
    }
  }
  for (const cue of explicit) {
    if (!known.has(cue.scene_id)) fail("BAD_TIMELINE", `micro_sfx scene_id ${cue.scene_id} is not in the timeline`);
    const scene = scenes.find((item) => item.scene_id === cue.scene_id);
    if (!scene || scene.compile_status !== "compiled") continue;
    pushCue(planned, scene, cue.cue, cue.offset_ms, inputIndex);
    inputIndex += 1;
  }
  planned.sort((left, right) => {
    if (left.sample !== right.sample) return left.sample - right.sample;
    if (left.registryIndex !== right.registryIndex) return left.registryIndex - right.registryIndex;
    if (left.scene_id !== right.scene_id) return left.scene_id < right.scene_id ? -1 : 1;
    return left.inputIndex - right.inputIndex;
  });

  const cues: MicroSfxCue[] = [];
  const suppressed: SuppressedMicroSfx[] = [];
  let lastSample: number | null = null;
  for (const item of planned) {
    if (lastSample !== null && item.sample - lastSample < COOLDOWN_SAMPLES) {
      suppressed.push({ cue: item.cue, scene_id: item.scene_id, start_sample: item.sample, reason: "cooldown" });
      continue;
    }
    const definition = SFX_BY_CUE.get(item.cue);
    if (!definition) fail("UNKNOWN_CUE", `UNKNOWN_CUE: ${item.cue} is not a micro-SFX cue`);
    cues.push({
      cue_id: `${item.scene_id}:${item.cue}:${item.sample}`,
      cue: item.cue,
      scene_id: item.scene_id,
      start_sample: item.sample,
      sample_rate_hz: MIX_SAMPLE_RATE_HZ,
      start_frame: Math.floor(item.sample / SAMPLES_PER_FRAME),
      offset_ms: item.sample / SAMPLES_PER_MS,
      duration_samples: definition.durationSamples,
      cooldown_ms: COOLDOWN_MS,
      gain_units: definition.gainUnits,
      gain_unit_scale: GAIN_UNIT_SCALE,
      peak_dbtp: definition.nominalDbtp,
      burst: false,
      tapered: false,
    });
    lastSample = item.sample;
  }
  return { cues, suppressed };
}

function gradeRecord(scene: ResolvedScene): SceneGradeRecord {
  const applyGrade = sceneApplyGrade(scene.active_engine, scene.active_motif);
  const foia = !applyGrade;
  return {
    timeline_index: scene.timeline_index,
    seq_index: scene.seq_index,
    scene_id: scene.scene_id,
    visual_engine: scene.active_engine,
    motif_component: scene.active_motif,
    requested_visual_engine: scene.requested_engine,
    requested_motif_component: scene.requested_motif,
    apply_grade: applyGrade,
    needs_grade: applyGrade,
    is_foia: foia,
    exempt_from_grain: foia,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
    grain_phase: null,
    grade_owner: applyGrade ? "agent6_single_pass" : "none",
    ungraded_masks: [],
    stylized_overlays: [],
    owner_package: scene.route.owner_package,
    compile_status: scene.compile_status,
    fallback_applied: scene.swap,
    gap_ms: 0,
    routed: true,
    flow_state: scene.flow_state,
    mp4_relpath: scene.compile_status === "compiled" ? `${scene.scene_id}.mp4` : null,
    start_frame: scene.start_frame,
    duration_frames: scene.duration_frames,
  };
}

function buildManifest(episodeId: string, mode: SceneGradeManifest["mode"], scenes: readonly ResolvedScene[]): SceneGradeManifest {
  return {
    filename: SCENE_GRADE_MANIFEST_FILENAME,
    schema: GRADE_MANIFEST_SCHEMA,
    contract_version: "v4",
    fps: FRAME_FPS,
    width_px: FRAME_WIDTH,
    height_px: FRAME_HEIGHT,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
    grain_phase: null,
    grade_owner: "agent6_single_pass",
    single_grade_pass: true,
    mode,
    episode_id: episodeId,
    scenes: scenes.map((scene) => gradeRecord(scene)),
  };
}

function buildSfx(episodeId: string, cues: MicroSfxCue[], suppressed: SuppressedMicroSfx[]): MicroSfxDocument {
  return {
    filename: MICRO_SFX_CUES_FILENAME,
    schema: MICRO_SFX_SCHEMA,
    contract_version: "v4",
    sample_rate_hz: MIX_SAMPLE_RATE_HZ,
    fps: FRAME_FPS,
    cooldown_ms: COOLDOWN_MS,
    episode_id: episodeId,
    cues,
    suppressed,
  };
}

function u32(value: number): Uint8Array {
  return Uint8Array.of((value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff);
}

function u16(value: number): Uint8Array {
  return Uint8Array.of((value >> 8) & 0xff, value & 0xff);
}

function ascii(value: string): Uint8Array {
  const out = new Uint8Array(value.length);
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code > 127) fail("RUNTIME", "MP4 box text must be ASCII");
    out[index] = code;
  }
  return out;
}

function concat(parts: readonly Uint8Array[]): Uint8Array {
  const size = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function box(type: string, payload: Uint8Array): Uint8Array {
  return concat([u32(8 + payload.length), ascii(type), payload]);
}

const IDENTITY_MATRIX = concat([
  u32(0x00010000), u32(0), u32(0),
  u32(0), u32(0x00010000), u32(0),
  u32(0), u32(0), u32(0x40000000),
]);

/** ISO-BMFF container. Timescale is 30 and duration is the frame count. No encoded pictures and no grade filters. */
export function encodeSceneMp4(durationFrames: number): Uint8Array {
  if (!Number.isInteger(durationFrames) || durationFrames < 1) {
    fail("FRAME_CLOCK", "MP4 duration_frames must be a positive integer");
  }
  const ftyp = box("ftyp", concat([ascii("isom"), u32(0x200), ascii("isom"), ascii("mp42"), ascii("iso2")]));
  const mvhd = box(
    "mvhd",
    concat([
      u32(0),
      u32(0),
      u32(0),
      u32(FRAME_FPS),
      u32(durationFrames),
      u32(0x00010000),
      u16(0x0100),
      u16(0),
      u32(0),
      u32(0),
      IDENTITY_MATRIX,
      new Uint8Array(24),
      u32(2),
    ]),
  );
  const tkhd = box(
    "tkhd",
    concat([
      u32(0x00000003),
      u32(0),
      u32(0),
      u32(1),
      u32(0),
      u32(durationFrames),
      u32(0),
      u32(0),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      IDENTITY_MATRIX,
      u32(FRAME_WIDTH << 16),
      u32(FRAME_HEIGHT << 16),
    ]),
  );
  const mdhd = box("mdhd", concat([u32(0), u32(0), u32(0), u32(FRAME_FPS), u32(durationFrames), u16(0x55c4), u16(0)]));
  const hdlr = box("hdlr", concat([u32(0), u32(0), ascii("vide"), new Uint8Array(12), ascii("VideoHandler"), Uint8Array.of(0)]));
  const minf = box("minf", concat([box("vmhd", concat([u32(1), u16(0), u16(0), u16(0), u16(0)])), box("dinf", box("dref", concat([u32(0), u32(1), box("url ", u32(1))])))]));
  const moov = box("moov", concat([mvhd, box("trak", concat([tkhd, box("mdia", concat([mdhd, hdlr, minf]))]))]));
  const mdat = box("mdat", new Uint8Array(0));
  return concat([ftyp, moov, mdat]);
}

function jsonText(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

export class BatchCompiler {
  private readonly mvp4Motifs: boolean;

  private readonly outDir: string;

  constructor(options: BatchCompileOptions) {
    if (!options || typeof options.outDir !== "string" || options.outDir.length === 0 || options.outDir.includes("\0")) {
      fail("BAD_TIMELINE", "outDir must be a non-empty path");
    }
    this.outDir = options.outDir;
    this.mvp4Motifs = options.mvp4Motifs === true;
  }

  async compile(source: unknown): Promise<BatchCompileResult> {
    if (!isRecord(source)) fail("BAD_TIMELINE", "timeline batch must be an object");
    assertNoSvg(source);
    const explicit = readExplicitCues(source);
    const planned = planScenes(source);
    const scenes = resolveScenes(planned, this.mvp4Motifs);
    const episodeId = episodeIdOf(source, scenes.map((scene) => scene.scene_id));
    const mode = this.mvp4Motifs ? "mvp-4-motifs" : "full";
    const manifest = buildManifest(episodeId, mode, scenes);
    const dispatched = collectCues(scenes, explicit);
    const sfx = buildSfx(episodeId, dispatched.cues, dispatched.suppressed);
    if (manifest.scenes.length !== scenes.length || !manifest.scenes.every((scene) => scene.routed)) {
      fail("ROUTE", "ROUTE: a timeline scene was dropped");
    }
    if (new Set(manifest.scenes.map((scene) => scene.motif_component)).size === 0) {
      fail("ROUTE", "ROUTE: no motif was routed");
    }

    const path = nodeBuiltin<PathModule>("node:path");
    const fs = nodeBuiltin<FsPromises>("node:fs/promises");
    const outDir = path.resolve(this.outDir);
    await fs.mkdir(outDir, { recursive: true });
    const mp4s: SceneMp4Receipt[] = [];
    for (const scene of manifest.scenes) {
      if (scene.compile_status !== "compiled" || scene.mp4_relpath === null) continue;
      const relpath = scene.mp4_relpath;
      const filePath = path.join(outDir, relpath);
      await fs.writeFile(filePath, encodeSceneMp4(scene.duration_frames));
      mp4s.push({
        scene_id: scene.scene_id,
        relpath,
        path: filePath,
        width_px: FRAME_WIDTH,
        height_px: FRAME_HEIGHT,
        fps: FRAME_FPS,
        duration_frames: scene.duration_frames,
        paper_grain: 0,
        vignette: 0,
        remotion_grain_applied: false,
        svg_turbulence: false,
      });
    }
    const gradePath = path.join(outDir, SCENE_GRADE_MANIFEST_FILENAME);
    const sfxPath = path.join(outDir, MICRO_SFX_CUES_FILENAME);
    await fs.writeFile(gradePath, jsonText(manifest));
    await fs.writeFile(sfxPath, jsonText(sfx));
    return {
      episode_id: episodeId,
      mode,
      fps: FRAME_FPS,
      width_px: FRAME_WIDTH,
      height_px: FRAME_HEIGHT,
      out_dir: outDir,
      grade_manifest_path: gradePath,
      micro_sfx_path: sfxPath,
      grade_manifest: manifest,
      micro_sfx: sfx,
      mp4s,
    };
  }
}

export async function compileTimelineBatch(source: unknown, options: BatchCompileOptions): Promise<BatchCompileResult> {
  return new BatchCompiler(options).compile(source);
}
