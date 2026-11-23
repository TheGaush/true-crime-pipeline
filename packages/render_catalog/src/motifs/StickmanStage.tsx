/**
 * MVP motif #1 — StickmanStage.
 *
 * Blocks 1–5 stick figures on one of six noir architectural presets, inside
 * Task 101's `<SafeZoneLayout>`, with a cubic camera pan locked to `travel_axis`.
 * Figures track the camera, so a 180px screen gap cannot collapse mid-shot and
 * neighboring heads cannot overlap. Task 104 draws each figure; this file does
 * not vendor that rig or the safe-zone frame.
 */

// @ts-expect-error TS2307 — Task 101's ../safe_zone.js lands in parallel and is not on this branch.
import { SafeZoneLayout } from "../safe_zone.js";
// @ts-expect-error TS2307 — Task 104's ../rig/StickFigureGeometry.js lands in parallel and is not on this branch.
import { StickFigureGeometry } from "../rig/StickFigureGeometry.js";

export const MOTIF_COMPONENT = "StickmanStage";

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const STAGE_FPS = 30;
export const END_SCREEN_SECONDS = 20;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;

/** Five-across crowding floor. Screen pelvis centers stay at least this far apart. */
export const MIN_FIGURE_SPACING_PX = 180;

export const MIN_FIGURES = 1;
export const MAX_FIGURES = 5;

/** Rest-pose lengths shared with the locked stick rig, so head circles match the drawn figure. */
export const HEAD_RADIUS_PX = 22;
export const TORSO_LEN_PX = 70;
export const THIGH_PX = 46;
export const SHIN_PX = 42;
export const HORIZONTAL_REACH_PX = 68;
export const STROKE_BLEED_PX = 5;
export const HEAD_CLEARANCE_PX = 1;

export const NOIR_ARCHITECTURAL_PRESETS = [
  "alley_night",
  "precinct_hallway",
  "interrogation_room",
  "courthouse_steps",
  "apartment_doorway",
  "evidence_desk",
] as const;

export type NoirPresetId = (typeof NOIR_ARCHITECTURAL_PRESETS)[number];

export const TRAVEL_AXES = ["L_TO_R", "R_TO_L", "STATIC"] as const;

export type TravelAxis = (typeof TRAVEL_AXES)[number];

export type StickmanStageErrorCode =
  | "COUNT"
  | "PRESET"
  | "TRAVEL_AXIS"
  | "CHARACTER"
  | "CROWDING"
  | "HEAD_COLLISION"
  | "AXIS_CONTINUITY"
  | "FRAME";

export class StickmanStageError extends Error {
  readonly code: StickmanStageErrorCode;

  constructor(code: StickmanStageErrorCode, message: string) {
    super(message);
    this.name = "StickmanStageError";
    this.code = code;
  }
}

export interface StageFigureInput {
  characterId: string;
  /** Requested screen-space pelvis x before the 180px spread. All figures must set it, or none. */
  x?: number;
}

export interface StickmanStageInput {
  preset: NoirPresetId;
  travelAxis: TravelAxis;
  figures: readonly StageFigureInput[];
  frame: number;
  durationFrames: number;
  scale?: number;
  isEndScreen?: boolean;
  label?: string;
  /** Camera world x at progress 0. Chain the previous shot's `exitWorldX` into this. */
  entryWorldX?: number;
  /** Previous shot's axis. Two directional axes may continue only when they match. */
  previousAxis?: TravelAxis;
}

export interface ArchitectureSegment {
  readonly name: string;
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
}

export interface HeadCircle {
  characterId: string;
  centerX: number;
  centerY: number;
  radius: number;
}

export interface SolvedFigure {
  characterId: string;
  pose: string;
  facing: "left" | "right";
  scale: number;
  screenX: number;
  screenY: number;
  worldX: number;
  seed: number;
  head: HeadCircle;
}

export interface SolvedStickmanStage {
  preset: NoirPresetId;
  travelAxis: TravelAxis;
  pose: string;
  frame: number;
  durationFrames: number;
  progress: number;
  appliedScale: number;
  isEndScreen: boolean;
  entryWorldX: number;
  exitWorldX: number;
  signedTravelPx: number;
  cameraOffsetPx: number;
  cameraWorldX: number;
  figures: SolvedFigure[];
  segments: readonly ArchitectureSegment[];
}

export interface StageNode {
  type: string;
  dataset: Readonly<Record<string, string>>;
  props: {
    style?: Readonly<Record<string, string | number>>;
    transform?: string;
    d?: string;
    fill?: string;
    stroke?: string;
    strokeWidth?: number;
    children?: StageNode | readonly StageNode[];
  };
}

interface PresetSpec {
  readonly groundY: number;
  readonly travelPx: number;
  readonly pose: string;
  readonly segments: readonly ArchitectureSegment[];
}

interface ContentInterval {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const CHARACTER_ID = /^[a-z][a-z0-9_]*$/;
const PRESET_SET: ReadonlySet<string> = new Set(NOIR_ARCHITECTURAL_PRESETS);
const AXIS_SET: ReadonlySet<string> = new Set(TRAVEL_AXES);
const AXIS_CYCLE: readonly TravelAxis[] = ["L_TO_R", "R_TO_L", "STATIC"];
const WORLD_LEFT = -640;
const WORLD_RIGHT = 2560;

export function isNoirPreset(value: string): value is NoirPresetId {
  return PRESET_SET.has(value);
}

export function isTravelAxis(value: string): value is TravelAxis {
  return AXIS_SET.has(value);
}

/** Cubic ease-in-out. End slopes are 0, so a following STATIC hold does not pop. */
export function cubicEaseInOut(t: number): number {
  const clamped = t < 0 ? 0 : t > 1 ? 1 : t;
  if (clamped < 0.5) return 4 * clamped * clamped * clamped;
  const tail = -2 * clamped + 2;
  return 1 - (tail * tail * tail) / 2;
}

export function stageProgress(frame: number, durationFrames: number): number {
  if (!Number.isFinite(frame) || !Number.isFinite(durationFrames) || durationFrames < 1) {
    throw new StickmanStageError("FRAME", "frame and durationFrames must be finite and durationFrames must be >= 1");
  }
  if (frame < 0 || frame > durationFrames - 1) {
    throw new StickmanStageError("FRAME", "frame is outside this StickmanStage shot");
  }
  if (durationFrames === 1) return 0;
  return frame / (durationFrames - 1);
}

export function signedTravelFor(axis: TravelAxis, magnitudePx: number): number {
  if (axis === "STATIC") return 0;
  if (axis === "L_TO_R") return magnitudePx;
  return -magnitudePx;
}

export function cameraOffsetPx(progress: number, signedTravelPx: number): number {
  const offset = signedTravelPx * cubicEaseInOut(progress);
  return Object.is(offset, -0) ? 0 : offset;
}

export function contentInterval(scale: number): ContentInterval {
  const inset = STROKE_BLEED_PX + HORIZONTAL_REACH_PX * scale;
  return {
    left: inset,
    right: FRAME_WIDTH - inset,
    top: SAFE_PADDING_TOP,
    bottom: FRAME_HEIGHT - SAFE_PADDING_BOTTOM,
  };
}

export function horizontalSpacing(figures: readonly { screenX: number }[]): number[] {
  const xs = figures.map((figure) => figure.screenX).sort((a, b) => a - b);
  const gaps: number[] = [];
  for (let i = 1; i < xs.length; i += 1) {
    const previous = xs[i - 1];
    const current = xs[i];
    if (previous === undefined || current === undefined) continue;
    gaps.push(current - previous);
  }
  return gaps;
}

export function assertNoHeadCollision(heads: readonly HeadCircle[]): void {
  for (let i = 0; i < heads.length; i += 1) {
    const left = heads[i];
    if (!left) continue;
    for (let j = i + 1; j < heads.length; j += 1) {
      const right = heads[j];
      if (!right) continue;
      const dx = left.centerX - right.centerX;
      const dy = left.centerY - right.centerY;
      const limit = left.radius + right.radius;
      if (dx * dx + dy * dy < limit * limit) {
        throw new StickmanStageError(
          "HEAD_COLLISION",
          `${left.characterId} head overlaps ${right.characterId}`,
        );
      }
    }
  }
}

export interface AxisBeat {
  travelAxis: TravelAxis;
  signedTravelPx: number;
}

/** Directional shots may follow each other only along the same axis. STATIC is a hold. */
export function axisContinuityViolations(beats: readonly AxisBeat[]): string[] {
  const violations: string[] = [];
  for (let i = 1; i < beats.length; i += 1) {
    const previous = beats[i - 1];
    const next = beats[i];
    if (!previous || !next) continue;
    if (
      previous.travelAxis !== "STATIC" &&
      next.travelAxis !== "STATIC" &&
      previous.travelAxis !== next.travelAxis
    ) {
      violations.push(
        `beat ${i - 1} ${previous.travelAxis} reverses into beat ${i} ${next.travelAxis}`,
      );
    }
  }
  return violations;
}

/** Entry world x for each beat. The cursor never teleports between beats. */
export function chainCameraEntries(beats: readonly AxisBeat[], initialEntry = 0): number[] {
  const entries: number[] = [];
  let cursor = initialEntry;
  for (const beat of beats) {
    entries.push(cursor);
    cursor += beat.signedTravelPx;
  }
  return entries;
}

/**
 * Isolated StickmanStage scenes each start a run. Consecutive sequence indexes
 * stay on the run's axis so a cut inside the motif cannot reverse direction.
 */
export function travelAxesForSceneRuns(seqIndexes: readonly number[]): TravelAxis[] {
  const axes: TravelAxis[] = [];
  let run = -1;
  for (let i = 0; i < seqIndexes.length; i += 1) {
    const seq = seqIndexes[i];
    if (seq === undefined || !Number.isInteger(seq)) {
      throw new StickmanStageError("FRAME", "scene seq_index must be an integer");
    }
    const previous = i === 0 ? undefined : seqIndexes[i - 1];
    const consecutive = previous !== undefined && seq === previous + 1;
    if (!consecutive) run += 1;
    const axis = AXIS_CYCLE[run % AXIS_CYCLE.length];
    if (!axis) throw new StickmanStageError("TRAVEL_AXIS", "travel axis cycle missed a value");
    axes.push(axis);
  }
  return axes;
}

export function presetForSceneIndex(index: number): NoirPresetId {
  if (!Number.isInteger(index) || index < 0) {
    throw new StickmanStageError("PRESET", "preset index must be an integer >= 0");
  }
  const preset = NOIR_ARCHITECTURAL_PRESETS[index % NOIR_ARCHITECTURAL_PRESETS.length];
  if (!preset) throw new StickmanStageError("PRESET", "noir preset registry is empty");
  return preset;
}

/** Absolute frame sits in the final 20 seconds of a 30 fps timeline. */
export function frameIsEndScreen(absoluteFrame: number, totalFrames: number): boolean {
  if (!Number.isFinite(absoluteFrame) || !Number.isFinite(totalFrames) || totalFrames < 1) {
    throw new StickmanStageError("FRAME", "end-screen check needs a finite timeline");
  }
  const start = totalFrames - END_SCREEN_SECONDS * STAGE_FPS;
  return absoluteFrame >= start;
}

export function characterSeed(characterId: string): number {
  let hash = 2166136261;
  for (let i = 0; i < characterId.length; i += 1) {
    hash = Math.imul(hash ^ characterId.charCodeAt(i), 16777619);
  }
  return hash >>> 0;
}

function hline(name: string, y: number, x1 = WORLD_LEFT, x2 = WORLD_RIGHT): ArchitectureSegment {
  return { name, x1, y1: y, x2, y2: y };
}

function vline(name: string, x: number, y1: number, y2: number): ArchitectureSegment {
  return { name, x1: x, y1, x2: x, y2 };
}

function seg(name: string, x1: number, y1: number, x2: number, y2: number): ArchitectureSegment {
  return { name, x1, y1, x2, y2 };
}

function alleySegments(): ArchitectureSegment[] {
  const lines = [hline("alley-curb", 820), hline("alley-skyline", 280)];
  for (let x = WORLD_LEFT; x <= WORLD_RIGHT; x += 360) {
    lines.push(seg("alley-wall", x, 820, x + 120, 280));
    lines.push(vline("alley-fire-escape", x + 180, 340, 800));
  }
  return lines;
}

function precinctSegments(): ArchitectureSegment[] {
  const lines = [hline("hall-floor", 800), hline("hall-ceiling", 200)];
  for (let x = WORLD_LEFT; x <= WORLD_RIGHT; x += 300) {
    lines.push(vline("hall-door", x, 280, 800));
    lines.push(hline("hall-lintel", 280, x, x + 120));
  }
  return lines;
}

function interrogationSegments(): ArchitectureSegment[] {
  return [
    hline("room-floor", 790),
    hline("room-ceiling", 220),
    seg("table-top", 420, 690, 1500, 690),
    vline("mirror-left", 180, 260, 620),
    vline("mirror-right", 1740, 260, 620),
    hline("mirror-top", 260, 180, 1740),
  ];
}

function courthouseSegments(): ArchitectureSegment[] {
  const lines = [vline("column-left", 280, 180, 860), vline("column-right", 1640, 180, 860)];
  for (let step = 0; step < 6; step += 1) {
    lines.push(hline("step-tread", 860 - step * 36));
  }
  return lines;
}

function doorwaySegments(): ArchitectureSegment[] {
  return [
    hline("threshold", 840),
    vline("jamb-left", 760, 220, 840),
    vline("jamb-right", 1160, 220, 840),
    hline("lintel", 220, 760, 1160),
    seg("door-slab", 780, 240, 780, 830),
    hline("porch", 860),
  ];
}

function deskSegments(): ArchitectureSegment[] {
  return [
    hline("desk-top", 740, 360, 1680),
    vline("desk-leg-left", 400, 740, 880),
    vline("desk-leg-right", 1640, 740, 880),
    vline("lamp-stand", 1180, 480, 740),
    seg("lamp-arm", 1180, 480, 1420, 480),
    hline("baseboard", 880),
  ];
}

const PRESETS: Record<NoirPresetId, PresetSpec> = {
  alley_night: { groundY: 760, travelPx: 420, pose: "walk_loop", segments: alleySegments() },
  precinct_hallway: { groundY: 740, travelPx: 360, pose: "walk_loop", segments: precinctSegments() },
  interrogation_room: { groundY: 700, travelPx: 80, pose: "seated", segments: interrogationSegments() },
  courthouse_steps: { groundY: 680, travelPx: 300, pose: "walk_loop", segments: courthouseSegments() },
  apartment_doorway: { groundY: 750, travelPx: 160, pose: "doorway_entry", segments: doorwaySegments() },
  evidence_desk: { groundY: 720, travelPx: 120, pose: "evidence_hold", segments: deskSegments() },
};

export function noirPreset(id: NoirPresetId): PresetSpec {
  return PRESETS[id];
}

function poseFor(presetPose: string, axis: TravelAxis): string {
  if (axis === "STATIC" && (presetPose === "walk_loop" || presetPose === "run_loop")) return "idle";
  return presetPose;
}

function facingFor(axis: TravelAxis): "left" | "right" {
  return axis === "R_TO_L" ? "left" : "right";
}

function requiredGap(scale: number): number {
  return Math.max(MIN_FIGURE_SPACING_PX, 2 * HEAD_RADIUS_PX * scale + HEAD_CLEARANCE_PX);
}

function scaleFits(scale: number, count: number): boolean {
  if (!(scale > 0) || !Number.isFinite(scale)) return false;
  const band = contentInterval(scale);
  if (band.left >= band.right) return false;
  const headAbove = (TORSO_LEN_PX + 2 * HEAD_RADIUS_PX) * scale + STROKE_BLEED_PX;
  const feetBelow = (THIGH_PX + SHIN_PX) * scale + STROKE_BLEED_PX;
  if (band.top + headAbove > band.bottom - feetBelow) return false;
  if (count > 1 && band.right - band.left < requiredGap(scale) * (count - 1)) return false;
  return true;
}

function fitScale(requested: number, count: number): number {
  if (scaleFits(requested, count)) return requested;
  let lo = 0;
  let hi = requested;
  let best = 0;
  for (let pass = 0; pass < 28; pass += 1) {
    const mid = (lo + hi) / 2;
    if (scaleFits(mid, count)) {
      best = mid;
      lo = mid;
    } else {
      hi = mid;
    }
  }
  if (!(best > 0)) {
    throw new StickmanStageError("CROWDING", "stick figures do not fit inside the safe zone");
  }
  return best;
}

function clamp(value: number, lo: number, hi: number): number {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return value;
}

function evenCenters(count: number, left: number, right: number): number[] {
  if (count === 1) return [(left + right) / 2];
  const gap = (right - left) / (count - 1);
  const centers: number[] = [];
  for (let i = 0; i < count; i += 1) centers.push(left + gap * i);
  return centers;
}

function spreadCenters(requested: readonly number[], minGap: number, left: number, right: number): number[] {
  if ((requested.length - 1) * minGap > right - left + 1e-6) {
    throw new StickmanStageError("CROWDING", "180px spacing does not fit inside the safe zone");
  }
  const order = requested.map((x, index) => ({ x, index })).sort((a, b) => a.x - b.x || a.index - b.index);
  const placed: number[] = [];
  for (const item of order) placed.push(clamp(item.x, left, right));
  for (let i = 1; i < placed.length; i += 1) {
    const previous = placed[i - 1];
    const current = placed[i];
    if (previous === undefined || current === undefined) continue;
    placed[i] = Math.max(current, previous + minGap);
  }
  const last = placed[placed.length - 1];
  if (last !== undefined && last > right) {
    const shift = last - right;
    for (let i = 0; i < placed.length; i += 1) {
      const value = placed[i];
      if (value !== undefined) placed[i] = value - shift;
    }
  }
  const first = placed[0];
  if (first !== undefined && first < left) {
    const shift = left - first;
    for (let i = 0; i < placed.length; i += 1) {
      const value = placed[i];
      if (value !== undefined) placed[i] = value + shift;
    }
  }
  const fitted = placed[0];
  const fittedLast = placed[placed.length - 1];
  if (fitted === undefined || fittedLast === undefined || fitted < left - 1e-6 || fittedLast > right + 1e-6) {
    throw new StickmanStageError("CROWDING", "spread figures left the safe zone");
  }
  const restored = new Array<number>(requested.length);
  order.forEach((item, index) => {
    const value = placed[index];
    if (value === undefined) throw new StickmanStageError("CROWDING", "missing spread center");
    restored[item.index] = value;
  });
  return restored;
}

function pelvisY(preferred: number, scale: number): number {
  const band = contentInterval(scale);
  const minY = band.top + STROKE_BLEED_PX + (TORSO_LEN_PX + 2 * HEAD_RADIUS_PX) * scale;
  const maxY = band.bottom - STROKE_BLEED_PX - (THIGH_PX + SHIN_PX) * scale;
  if (minY > maxY) throw new StickmanStageError("CROWDING", "figure height exceeds the safe zone");
  return clamp(preferred, minY, maxY);
}

function readFigures(figures: readonly StageFigureInput[]): StageFigureInput[] {
  if (!Array.isArray(figures) || figures.length < MIN_FIGURES || figures.length > MAX_FIGURES) {
    throw new StickmanStageError(
      "COUNT",
      `StickmanStage renders ${MIN_FIGURES}–${MAX_FIGURES} figures, received ${Array.isArray(figures) ? figures.length : "none"}`,
    );
  }
  const seen = new Set<string>();
  let withX = 0;
  for (const figure of figures) {
    if (!figure || typeof figure.characterId !== "string" || !CHARACTER_ID.test(figure.characterId)) {
      throw new StickmanStageError("CHARACTER", "characterId must match ^[a-z][a-z0-9_]*$");
    }
    if (seen.has(figure.characterId)) {
      throw new StickmanStageError("CHARACTER", `duplicate characterId ${figure.characterId}`);
    }
    seen.add(figure.characterId);
    if (figure.x !== undefined) {
      if (!Number.isFinite(figure.x)) throw new StickmanStageError("CROWDING", "figure x must be finite");
      withX += 1;
    }
  }
  if (withX !== 0 && withX !== figures.length) {
    throw new StickmanStageError("CROWDING", "set screen x on every figure, or on none");
  }
  return [...figures];
}

export function solveStickmanStage(input: StickmanStageInput): SolvedStickmanStage {
  if (!isNoirPreset(input.preset)) {
    throw new StickmanStageError("PRESET", `unknown noir architectural preset ${String(input.preset)}`);
  }
  if (!isTravelAxis(input.travelAxis)) {
    throw new StickmanStageError("TRAVEL_AXIS", `unknown travel_axis ${String(input.travelAxis)}`);
  }
  if (input.previousAxis !== undefined && !isTravelAxis(input.previousAxis)) {
    throw new StickmanStageError("TRAVEL_AXIS", `unknown previous travel_axis ${String(input.previousAxis)}`);
  }
  if (
    input.previousAxis !== undefined &&
    input.previousAxis !== "STATIC" &&
    input.travelAxis !== "STATIC" &&
    input.previousAxis !== input.travelAxis
  ) {
    throw new StickmanStageError(
      "AXIS_CONTINUITY",
      `travel_axis ${input.previousAxis} cannot reverse into ${input.travelAxis}`,
    );
  }

  const figures = readFigures(input.figures);
  const requestedScale = input.scale ?? 1;
  if (!Number.isFinite(requestedScale) || requestedScale <= 0) {
    throw new StickmanStageError("CROWDING", "scale must be a finite number > 0");
  }
  const entryWorldX = input.entryWorldX ?? 0;
  if (!Number.isFinite(entryWorldX)) {
    throw new StickmanStageError("AXIS_CONTINUITY", "entryWorldX must be finite");
  }

  const preset = PRESETS[input.preset];
  const progress = stageProgress(input.frame, input.durationFrames);
  const appliedScale = fitScale(requestedScale, figures.length);
  const band = contentInterval(appliedScale);
  const gap = requiredGap(appliedScale);
  const requestedX = figures.map((figure) => figure.x);
  const centers =
    requestedX.every((x) => x !== undefined)
      ? spreadCenters(requestedX as number[], gap, band.left, band.right)
      : evenCenters(figures.length, band.left, band.right);
  const screenY = pelvisY(preset.groundY, appliedScale);
  const signedTravelPx = signedTravelFor(input.travelAxis, preset.travelPx);
  const offset = cameraOffsetPx(progress, signedTravelPx);
  const cameraWorldX = entryWorldX + offset;
  const facing = facingFor(input.travelAxis);
  const pose = poseFor(preset.pose, input.travelAxis);
  const radius = HEAD_RADIUS_PX * appliedScale;
  const headCenterY = screenY - (TORSO_LEN_PX + HEAD_RADIUS_PX) * appliedScale;

  const solvedFigures: SolvedFigure[] = figures.map((figure, index) => {
    const screenX = centers[index];
    if (screenX === undefined) throw new StickmanStageError("CROWDING", "missing figure center");
    return {
      characterId: figure.characterId,
      pose,
      facing,
      scale: appliedScale,
      screenX,
      screenY,
      worldX: screenX + cameraWorldX,
      seed: characterSeed(figure.characterId),
      head: {
        characterId: figure.characterId,
        centerX: screenX,
        centerY: headCenterY,
        radius,
      },
    };
  });

  for (const gapPx of horizontalSpacing(solvedFigures)) {
    if (gapPx < MIN_FIGURE_SPACING_PX - 1e-6) {
      throw new StickmanStageError("CROWDING", `figure spacing ${gapPx}px is under ${MIN_FIGURE_SPACING_PX}px`);
    }
  }
  assertNoHeadCollision(solvedFigures.map((figure) => figure.head));
  const exclusion = {
    left: FRAME_WIDTH * 0.78,
    top: FRAME_HEIGHT * 0.86,
    right: FRAME_WIDTH,
    bottom: FRAME_HEIGHT,
  };
  for (const figure of solvedFigures) {
    const top = figure.head.centerY - figure.head.radius;
    const bottom = figure.screenY + (THIGH_PX + SHIN_PX) * appliedScale;
    if (top < band.top - 1e-6 || bottom > band.bottom + 1e-6) {
      throw new StickmanStageError("CROWDING", `${figure.characterId} leaves the safe zone`);
    }
    if (figure.head.centerX - figure.head.radius < -1e-6 || figure.head.centerX + figure.head.radius > FRAME_WIDTH + 1e-6) {
      throw new StickmanStageError("CROWDING", `${figure.characterId} head leaves the frame`);
    }
    if (input.isEndScreen === true) {
      const headLeft = figure.head.centerX - figure.head.radius;
      const headRight = figure.head.centerX + figure.head.radius;
      const headBottom = figure.head.centerY + figure.head.radius;
      const hitsExclusion =
        headRight > exclusion.left &&
        headLeft < exclusion.right &&
        headBottom > exclusion.top &&
        top < exclusion.bottom;
      if (hitsExclusion) {
        throw new StickmanStageError("CROWDING", `${figure.characterId} head enters the end-screen exclusion`);
      }
    }
  }

  return {
    preset: input.preset,
    travelAxis: input.travelAxis,
    pose,
    frame: input.frame,
    durationFrames: input.durationFrames,
    progress,
    appliedScale,
    isEndScreen: input.isEndScreen === true,
    entryWorldX,
    exitWorldX: entryWorldX + signedTravelPx,
    signedTravelPx,
    cameraOffsetPx: offset,
    cameraWorldX,
    figures: solvedFigures,
    segments: preset.segments,
  };
}

function pathNode(segment: ArchitectureSegment): StageNode {
  return {
    type: "path",
    dataset: { line: segment.name },
    props: {
      d: `M ${segment.x1} ${segment.y1} L ${segment.x2} ${segment.y2}`,
      fill: "none",
      stroke: "currentColor",
      strokeWidth: 4,
    },
  };
}

function formatTranslate(offsetPx: number): string {
  const x = Object.is(offsetPx, -0) ? 0 : offsetPx;
  return `translate(${x} 0)`;
}

function renderStageContent(solved: SolvedStickmanStage): StageNode {
  const figures = solved.figures.map((figure) => {
    const drawn = StickFigureGeometry({
      x: figure.screenX,
      y: figure.screenY,
      scale: figure.scale,
      facing: figure.facing,
      seed: figure.seed,
      frame: solved.frame,
      isEndScreen: solved.isEndScreen,
    }) as StageNode;
    return {
      type: "g",
      dataset: {
        character: figure.characterId,
        pose: figure.pose,
        facing: figure.facing,
        "screen-x": String(figure.screenX),
        "world-x": String(figure.worldX),
      },
      props: { children: drawn },
    };
  });
  return {
    type: "g",
    dataset: {
      motif: MOTIF_COMPONENT,
      preset: solved.preset,
      "travel-axis": solved.travelAxis,
      pose: solved.pose,
      "apply-grade": "true",
      "needs-grade": "true",
      "camera-offset": String(solved.cameraOffsetPx),
      "figure-count": String(solved.figures.length),
    },
    props: {
      children: [
        {
          type: "g",
          dataset: { layer: "architecture" },
          props: {
            transform: formatTranslate(-solved.cameraOffsetPx),
            children: solved.segments.map(pathNode),
          },
        },
        {
          type: "g",
          dataset: { layer: "figures" },
          props: { children: figures },
        },
      ],
    },
  };
}

export function StickmanStage(input: StickmanStageInput): StageNode {
  const solved = solveStickmanStage(input);
  const content = renderStageContent(solved);
  const zone: {
    isEndScreen: boolean;
    label?: string;
    children: StageNode;
  } = {
    isEndScreen: solved.isEndScreen,
    children: content,
  };
  if (input.label !== undefined) zone.label = input.label;
  return SafeZoneLayout(zone) as StageNode;
}
