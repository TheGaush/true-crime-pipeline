/**
 * Motif bridge for an accepted Flow hero clip.
 *
 * Remotion does not grade this plate. Agent 6 reads `apply_grade: true` and
 * grades the stylized frame once. Task 109 owns that decision (`sceneNeedsGrade`).
 * Task 115 owns `StickmanStage`; a legal `CODE_STICKMAN` fallback delegates to it.
 * Neither file is copied onto this branch.
 *
 * A clip that is longer than the scene is trimmed to the scene in exact
 * milliseconds at 1.0x. Speed stays inside 0.85x–1.15x and is only used to
 * cover a shorter clip. `SWITCHED_TO_FALLBACK` drops the Flow file and mounts
 * `fallback_spec` when that engine is not the previous or next scene.
 */
// @ts-ignore Task 109 ships GradeContract.tsx on task/109-single-pass-grade-metadata.
import { sceneNeedsGrade as readSceneNeedsGrade } from "../grade/GradeContract.js";
// @ts-ignore Task 115 ships StickmanStage.tsx on task/115-motif-stickman-stage.
import { StickmanStage as renderStickmanStage } from "./StickmanStage.js";

export const HERO_MOTIF = "HeroVideoBridge";
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const HERO_SPEED_MIN = 0.85;
export const HERO_SPEED_MAX = 1.15;

const SPEED_MIN_HUNDREDTHS = 85;
const SPEED_MAX_HUNDREDTHS = 115;
const ENTITY_ID = /^[A-Za-z0-9_-]+$/;
const MAX_FALLBACK_JSON_CHARS = 8_000;

export const VISUAL_ENGINES = [
  "CODE_STICKMAN",
  "STILL_2K_PANZOOM",
  "AUDIO_EVIDENCE_CARD",
  "FOIA_REAL_FOOTAGE",
  "FLOW_HERO_VIDEO",
] as const;

export type VisualEngine = (typeof VISUAL_ENGINES)[number];

export const HERO_FLOW_STATES = [
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

export type HeroFlowState = (typeof HERO_FLOW_STATES)[number];

export type HeroResolution = "720p" | "1080p";
export type ConformLabel = "720p->1080p" | "1080p";

const RESOLUTION_SIZE: Record<HeroResolution, { width: number; height: number }> = {
  "720p": { width: 1280, height: 720 },
  "1080p": { width: 1920, height: 1080 },
};

const MOTIF_ENGINE: Record<string, VisualEngine> = {
  StickmanStage: "CODE_STICKMAN",
  AudioEvidenceCard: "AUDIO_EVIDENCE_CARD",
  RedactedDocReveal: "CODE_STICKMAN",
  FoiaFootageFrame: "FOIA_REAL_FOOTAGE",
  TimelineScrubber: "CODE_STICKMAN",
  AnimatedMapRoute: "CODE_STICKMAN",
  CellTowerTriangulation: "CODE_STICKMAN",
  SplitScreenComparison: "CODE_STICKMAN",
  CaseBoardSpine: "CODE_STICKMAN",
  QuotePullout: "CODE_STICKMAN",
  EvidenceGridMatrix: "CODE_STICKMAN",
  ChapterSlateTransition: "CODE_STICKMAN",
  Illustrative2KPanZoom: "STILL_2K_PANZOOM",
  HeroVideoBridge: "FLOW_HERO_VIDEO",
};

export interface HeroClip {
  src: string;
  duration_ms: number;
  width: number;
  height: number;
}

export interface HeroVideoBridgeInput {
  scene_id: string;
  episode_id: string;
  start_ms: number;
  end_ms: number;
  flow_state: HeroFlowState;
  resolution: HeroResolution;
  clip: HeroClip | null;
  fallback_spec: unknown;
  prev_engine: string | null;
  next_engine: string | null;
}

export interface HeroPlaybackFit {
  playbackRate: number;
  rateNumerator: number;
  rateDenominator: number;
  trimStartMs: number;
  trimEndMs: number;
  timelineMs: number;
  discardedTailMs: number;
  speedAdjusted: boolean;
  speedDistorted: false;
  /** Set only when the trim lands on a 30 fps frame. Milliseconds stay exact either way. */
  trimEndFrame: number | null;
}

export interface FlowConform {
  sourceWidth: number;
  sourceHeight: number;
  width: typeof FRAME_WIDTH;
  height: typeof FRAME_HEIGHT;
  scaleX: number;
  scaleY: number;
  conform: ConformLabel;
  objectFit: "fill";
}

export interface NormalizedFallback {
  engine: VisualEngine;
  motif_component: string;
  reason: string | null;
  still_2k_id: string | null;
  anchor_id: string | null;
  rule: "RULE_04" | null;
}

export interface StickmanFallbackProps {
  scene_id: string;
  episode_id: string;
  duration_ms: number;
  from_fallback: true;
}

interface GradeProbe {
  scene_id: string;
  visual_engine: VisualEngine;
  motif_component: string;
}

interface CleanStyle {
  width: typeof FRAME_WIDTH;
  height: typeof FRAME_HEIGHT;
  filter: "none";
  backgroundImage: "none";
  opacity: 1;
}

interface VideoStyle extends CleanStyle {
  objectFit: "fill";
}

export interface HeroElement {
  type: "video" | "div";
  props: {
    "data-tc-role": "hero-video-bridge" | "hero-fallback" | "hero-video-withheld";
    "data-motif": typeof HERO_MOTIF;
    "data-apply-grade": "true" | "false" | "none";
    "data-paper-grain": "0";
    "data-vignette": "0";
    "data-flow-state": HeroFlowState;
    "data-gap-ms"?: "0";
    "data-conform"?: ConformLabel;
    "data-fallback-engine"?: VisualEngine;
    "data-fallback-motif"?: string;
    "data-still-2k-id"?: string;
    "data-anchor-id"?: string;
    src?: string;
    playbackRate?: number;
    trimStartMs?: number;
    trimEndMs?: number;
    style: CleanStyle | VideoStyle;
    children: null;
  };
}

export interface HeroBridgeResult {
  mode: "play" | "fallback" | "withheld";
  motif_component: typeof HERO_MOTIF;
  scene_id: string;
  episode_id: string;
  duration_ms: number;
  apply_grade: boolean | null;
  needs_grade: boolean | null;
  remotion_grain_applied: false;
  remotion_vignette_applied: false;
  paper_grain: 0;
  vignette: 0;
  grade_owner: "agent6_single_pass" | "none";
  flow_mounted: boolean;
  fallback_active: boolean;
  active_engine: VisualEngine;
  active_motif: string;
  playback: HeroPlaybackFit | null;
  conform: FlowConform | null;
  latent_fallback: NormalizedFallback | null;
  active_fallback: NormalizedFallback | null;
  delegate: unknown;
  element: HeroElement;
}

function fail(message: string): never {
  throw new Error(message);
}

function assertEntityId(value: string, label: string): void {
  if (typeof value !== "string" || !ENTITY_ID.test(value)) {
    fail(`${label} must match ^[A-Za-z0-9_-]+$`);
  }
}

function assertNonNegativeInt(value: number, label: string): void {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    fail(`${label} must be a non-negative integer`);
  }
}

function assertPositiveInt(value: number, label: string): void {
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    fail(`${label} must be a positive integer millisecond count`);
  }
}

function gcd(a: number, b: number): number {
  let x = Math.abs(a);
  let y = Math.abs(b);
  while (y !== 0) {
    const next = x % y;
    x = y;
    y = next;
  }
  return x;
}

function rateFractionAllowed(numerator: number, denominator: number): boolean {
  const scaled = numerator * 100;
  return scaled >= SPEED_MIN_HUNDREDTHS * denominator && scaled <= SPEED_MAX_HUNDREDTHS * denominator;
}

/** Reject playback rates outside 0.85x–1.15x. Comparison is in hundredths. */
export function assertWithinSpeedBounds(rate: number): void {
  if (typeof rate !== "number" || !Number.isFinite(rate)) {
    fail("HERO_SPEED_BOUNDS: playback rate must be finite");
  }
  const scaled = rate * 100;
  if (scaled < SPEED_MIN_HUNDREDTHS - 1e-6 || scaled > SPEED_MAX_HUNDREDTHS + 1e-6) {
    fail(`HERO_SPEED_BOUNDS: playback rate ${rate} is outside ${HERO_SPEED_MIN}x–${HERO_SPEED_MAX}x`);
  }
}

function assertRateFraction(numerator: number, denominator: number): void {
  if (!rateFractionAllowed(numerator, denominator)) {
    fail(
      `HERO_SPEED_BOUNDS: playback rate ${numerator}/${denominator} is outside ${HERO_SPEED_MIN}x–${HERO_SPEED_MAX}x`,
    );
  }
}

/**
 * Fit a Flow clip to the scene.
 * Surplus media is cut at 1.0x (`7.6s` scene, `8.0s` clip → trim at 7600 ms).
 * A short clip may slow down, and only while the rate stays inside the bounds.
 */
export function fitHeroPlayback(sceneDurationMs: number, clipDurationMs: number): HeroPlaybackFit {
  assertPositiveInt(sceneDurationMs, "scene duration");
  assertPositiveInt(clipDurationMs, "clip duration");

  const surplus = clipDurationMs >= sceneDurationMs;
  const rateNumerator = surplus ? 1 : clipDurationMs;
  const rateDenominator = surplus ? 1 : sceneDurationMs;
  const divisor = surplus ? 1 : gcd(rateNumerator, rateDenominator);
  const numerator = rateNumerator / divisor;
  const denominator = rateDenominator / divisor;
  assertRateFraction(numerator, denominator);

  const trimEndMs = surplus ? sceneDurationMs : clipDurationMs;
  const playbackRate = numerator / denominator;
  assertWithinSpeedBounds(playbackRate);
  const timelineMs = (trimEndMs * denominator) / numerator;
  if (!Number.isInteger(timelineMs)) {
    fail("HERO_TRIM: timeline milliseconds must stay integral");
  }
  const trimEndFrame = (trimEndMs * FRAME_FPS) / 1000;

  return {
    playbackRate,
    rateNumerator: numerator,
    rateDenominator: denominator,
    trimStartMs: 0,
    trimEndMs,
    timelineMs,
    discardedTailMs: clipDurationMs - trimEndMs,
    speedAdjusted: !surplus,
    speedDistorted: false,
    trimEndFrame: Number.isInteger(trimEndFrame) ? trimEndFrame : null,
  };
}

export function conformFlowFrame(resolution: HeroResolution, width: number, height: number): FlowConform {
  const expected = RESOLUTION_SIZE[resolution];
  if (!expected) fail(`hero resolution must be 720p or 1080p`);
  if (width !== expected.width || height !== expected.height) {
    fail(`hero ${resolution} clip must be ${expected.width}x${expected.height}`);
  }
  const scaleX = FRAME_WIDTH / width;
  const scaleY = FRAME_HEIGHT / height;
  if (scaleX !== scaleY) fail("hero conform scale must stay uniform");
  return {
    sourceWidth: width,
    sourceHeight: height,
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT,
    scaleX,
    scaleY,
    conform: resolution === "720p" ? "720p->1080p" : "1080p",
    objectFit: "fill",
  };
}

function assertRelativeMediaPath(src: string): void {
  if (typeof src !== "string" || src.length === 0 || src.length > 500) {
    fail("hero src must be a local relative path");
  }
  if (src.includes("://") || src.startsWith("//")) fail("hero src must be a local relative path");
  const normalized = src.replace(/\\/g, "/");
  if (normalized.startsWith("/") || normalized.split("/").includes("..")) {
    fail("hero src must be a relative path without traversal");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function optionalId(value: unknown, label: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || !ENTITY_ID.test(value)) fail(`${label} must match ^[A-Za-z0-9_-]+$`);
  return value;
}

function optionalReason(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || value.trim() === "" || value.length > 300) {
    fail("fallback reason must be 1–300 characters");
  }
  return value;
}

export function parseFallbackSpec(value: unknown): NormalizedFallback | null {
  if (value === undefined || value === null) return null;
  let record: unknown = value;
  if (typeof value === "string") {
    if (value.length > MAX_FALLBACK_JSON_CHARS) fail("fallback_spec json is too large");
    try {
      record = JSON.parse(value) as unknown;
    } catch {
      fail("fallback_spec json must be an object");
    }
  }
  if (!isRecord(record)) fail("fallback_spec must be an object");

  const allowed = new Set([
    "engine",
    "visual_engine",
    "motif_component",
    "reason",
    "still_2k_id",
    "anchor_id",
    "rule",
  ]);
  for (const key of Object.keys(record)) {
    if (!allowed.has(key)) fail(`fallback_spec has unknown field ${key}`);
  }

  const engineRaw = record.engine;
  const visualRaw = record.visual_engine;
  if (engineRaw !== undefined && visualRaw !== undefined && engineRaw !== visualRaw) {
    fail("fallback_spec engine and visual_engine disagree");
  }
  const engine = engineRaw ?? visualRaw;
  if (typeof engine !== "string" || !VISUAL_ENGINES.includes(engine as VisualEngine)) {
    fail("fallback_spec engine must be a visual engine");
  }
  const motif = record.motif_component;
  if (typeof motif !== "string" || !Object.prototype.hasOwnProperty.call(MOTIF_ENGINE, motif)) {
    fail("fallback_spec motif_component is not in MOTIF_REGISTRY_V1");
  }
  if (MOTIF_ENGINE[motif] !== engine) {
    fail(`fallback_spec motif ${motif} does not belong to ${engine}`);
  }
  const ruleRaw = record.rule;
  let rule: "RULE_04" | null = null;
  if (ruleRaw !== undefined && ruleRaw !== null) {
    if (ruleRaw !== "RULE_04") fail("fallback_spec rule must be RULE_04");
    rule = "RULE_04";
  }
  return {
    engine: engine as VisualEngine,
    motif_component: motif,
    reason: optionalReason(record.reason),
    still_2k_id: optionalId(record.still_2k_id, "still_2k_id"),
    anchor_id: optionalId(record.anchor_id, "anchor_id"),
    rule,
  };
}

export function assertNonNeighborFallback(
  fallbackEngine: VisualEngine,
  prevEngine: string | null,
  nextEngine: string | null,
): void {
  if (fallbackEngine === "FLOW_HERO_VIDEO") {
    fail("RULE_04: fallback engine cannot be FLOW_HERO_VIDEO");
  }
  if (prevEngine !== null && fallbackEngine === prevEngine) {
    fail("RULE_04: fallback engine matches the previous scene");
  }
  if (nextEngine !== null && fallbackEngine === nextEngine) {
    fail("RULE_04: fallback engine matches the next scene");
  }
}

function assertNeighbor(value: string | null, label: string): void {
  if (value === null) return;
  if (!VISUAL_ENGINES.includes(value as VisualEngine)) fail(`${label} must be a visual engine`);
}

function needsGrade(scene: GradeProbe): boolean {
  const result = (readSceneNeedsGrade as (input: GradeProbe) => boolean)(scene);
  if (typeof result !== "boolean") fail("sceneNeedsGrade must return a boolean");
  return result;
}

function cleanStyle(): CleanStyle {
  return {
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT,
    filter: "none",
    backgroundImage: "none",
    opacity: 1,
  };
}

function gradeFlags(applyGrade: boolean): {
  apply_grade: boolean;
  needs_grade: boolean;
  grade_owner: "agent6_single_pass";
  "data-apply-grade": "true" | "false";
} {
  return {
    apply_grade: applyGrade,
    needs_grade: applyGrade,
    grade_owner: "agent6_single_pass",
    "data-apply-grade": applyGrade ? "true" : "false",
  };
}

function delegateStickman(props: StickmanFallbackProps): unknown {
  if (typeof renderStickmanStage !== "function") {
    fail("StickmanStage must be a named function export");
  }
  const rendered = (renderStickmanStage as (input: StickmanFallbackProps) => unknown)(props);
  if (rendered === null || rendered === undefined) fail("StickmanStage returned an empty fallback frame");
  return rendered;
}

function sceneDuration(input: HeroVideoBridgeInput): number {
  assertEntityId(input.scene_id, "scene_id");
  assertEntityId(input.episode_id, "episode_id");
  assertNonNegativeInt(input.start_ms, "start_ms");
  assertNonNegativeInt(input.end_ms, "end_ms");
  if (input.end_ms <= input.start_ms) fail("scene end_ms must be after start_ms");
  if (!HERO_FLOW_STATES.includes(input.flow_state)) fail("flow_state is not a flow job state");
  if (input.resolution !== "720p" && input.resolution !== "1080p") {
    fail("hero resolution must be 720p or 1080p");
  }
  assertNeighbor(input.prev_engine, "prev_engine");
  assertNeighbor(input.next_engine, "next_engine");
  return input.end_ms - input.start_ms;
}

function baseResult(
  input: HeroVideoBridgeInput,
  durationMs: number,
  mode: HeroBridgeResult["mode"],
): Pick<
  HeroBridgeResult,
  | "motif_component"
  | "scene_id"
  | "episode_id"
  | "duration_ms"
  | "remotion_grain_applied"
  | "remotion_vignette_applied"
  | "paper_grain"
  | "vignette"
  | "mode"
> {
  return {
    mode,
    motif_component: HERO_MOTIF,
    scene_id: input.scene_id,
    episode_id: input.episode_id,
    duration_ms: durationMs,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
  };
}

function withheld(input: HeroVideoBridgeInput, durationMs: number, latent: NormalizedFallback | null): HeroBridgeResult {
  return {
    ...baseResult(input, durationMs, "withheld"),
    apply_grade: null,
    needs_grade: null,
    grade_owner: "none",
    flow_mounted: false,
    fallback_active: false,
    active_engine: "FLOW_HERO_VIDEO",
    active_motif: HERO_MOTIF,
    playback: null,
    conform: null,
    latent_fallback: latent,
    active_fallback: null,
    delegate: null,
    element: {
      type: "div",
      props: {
        "data-tc-role": "hero-video-withheld",
        "data-motif": HERO_MOTIF,
        "data-apply-grade": "none",
        "data-paper-grain": "0",
        "data-vignette": "0",
        "data-flow-state": input.flow_state,
        style: cleanStyle(),
        children: null,
      },
    },
  };
}

function playAccepted(input: HeroVideoBridgeInput, durationMs: number, latent: NormalizedFallback | null): HeroBridgeResult {
  if (!input.clip) fail("ACCEPTED hero clip is missing");
  assertRelativeMediaPath(input.clip.src);
  assertPositiveInt(input.clip.duration_ms, "clip duration");
  const playback = fitHeroPlayback(durationMs, input.clip.duration_ms);
  const conform = conformFlowFrame(input.resolution, input.clip.width, input.clip.height);
  const graded = needsGrade({
    scene_id: input.scene_id,
    visual_engine: "FLOW_HERO_VIDEO",
    motif_component: HERO_MOTIF,
  });
  if (!graded) fail("SINGLE_GRADE: HeroVideoBridge must be tagged apply_grade true");
  const grade = gradeFlags(true);
  return {
    ...baseResult(input, durationMs, "play"),
    apply_grade: grade.apply_grade,
    needs_grade: grade.needs_grade,
    grade_owner: grade.grade_owner,
    flow_mounted: true,
    fallback_active: false,
    active_engine: "FLOW_HERO_VIDEO",
    active_motif: HERO_MOTIF,
    playback,
    conform,
    latent_fallback: latent,
    active_fallback: null,
    delegate: null,
    element: {
      type: "video",
      props: {
        "data-tc-role": "hero-video-bridge",
        "data-motif": HERO_MOTIF,
        "data-apply-grade": grade["data-apply-grade"],
        "data-paper-grain": "0",
        "data-vignette": "0",
        "data-flow-state": input.flow_state,
        "data-conform": conform.conform,
        src: input.clip.src,
        playbackRate: playback.playbackRate,
        trimStartMs: playback.trimStartMs,
        trimEndMs: playback.trimEndMs,
        style: { ...cleanStyle(), objectFit: "fill" },
        children: null,
      },
    },
  };
}

function switchFallback(
  input: HeroVideoBridgeInput,
  durationMs: number,
  fallback: NormalizedFallback,
): HeroBridgeResult {
  assertNonNeighborFallback(fallback.engine, input.prev_engine, input.next_engine);
  const graded = needsGrade({
    scene_id: input.scene_id,
    visual_engine: fallback.engine,
    motif_component: fallback.motif_component,
  });
  if (!graded) fail("SINGLE_GRADE: fallback must stay stylized so Agent 6 grades the scene once");
  const delegate =
    fallback.engine === "CODE_STICKMAN" && fallback.motif_component === "StickmanStage"
      ? delegateStickman({
          scene_id: input.scene_id,
          episode_id: input.episode_id,
          duration_ms: durationMs,
          from_fallback: true,
        })
      : null;
  const grade = gradeFlags(true);
  return {
    ...baseResult(input, durationMs, "fallback"),
    apply_grade: grade.apply_grade,
    needs_grade: grade.needs_grade,
    grade_owner: grade.grade_owner,
    flow_mounted: false,
    fallback_active: true,
    active_engine: fallback.engine,
    active_motif: fallback.motif_component,
    playback: null,
    conform: null,
    latent_fallback: null,
    active_fallback: fallback,
    delegate,
    element: {
      type: "div",
      props: {
        "data-tc-role": "hero-fallback",
        "data-motif": HERO_MOTIF,
        "data-apply-grade": grade["data-apply-grade"],
        "data-paper-grain": "0",
        "data-vignette": "0",
        "data-flow-state": input.flow_state,
        "data-gap-ms": "0",
        "data-fallback-engine": fallback.engine,
        "data-fallback-motif": fallback.motif_component,
        ...(fallback.still_2k_id ? { "data-still-2k-id": fallback.still_2k_id } : {}),
        ...(fallback.anchor_id ? { "data-anchor-id": fallback.anchor_id } : {}),
        style: cleanStyle(),
        children: null,
      },
    },
  };
}

/** Resolve one hero scene: play the accepted clip, switch fallback, or withhold. */
export function HeroVideoBridge(input: HeroVideoBridgeInput): HeroBridgeResult {
  if (!input || typeof input !== "object") fail("hero bridge input must be an object");
  const durationMs = sceneDuration(input);
  const latent = parseFallbackSpec(input.fallback_spec);
  if (input.flow_state === "ACCEPTED") return playAccepted(input, durationMs, latent);
  if (input.flow_state === "SWITCHED_TO_FALLBACK") {
    if (!latent) fail("SWITCHED_TO_FALLBACK requires fallback_spec");
    return switchFallback(input, durationMs, latent);
  }
  return withheld(input, durationMs, latent);
}
