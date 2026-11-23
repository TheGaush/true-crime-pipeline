/**
 * Visual-regression harness for deterministic 1920×1080 stills.
 *
 * SSIM at 0.995 absorbs font antialias noise. Exclusion borders still reject
 * high-contrast ink. Task 107 (`StickEmotions`) and Task 109 (`GradeContract`)
 * are imported when those files exist. They are not copied onto this branch.
 * Task 101's measured safe zone is used the same way when it is present.
 */

// This package shell has no @types/node dependency. Node 22 provides these at runtime.
// @ts-expect-error node:crypto is provided by the runtime.
import { createHash } from "node:crypto";
// @ts-expect-error node:fs is provided by the runtime.
import { existsSync } from "node:fs";
// @ts-expect-error node:path is provided by the runtime.
import { dirname, resolve } from "node:path";
// @ts-expect-error node:url is provided by the runtime.
import { fileURLToPath } from "node:url";

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const SSIM_MIN = 0.995;
export const SSIM_BLOCK = 8;
export const HIGH_CONTRAST_RATIO = 4.5;
export const END_SCREEN_FRAMES = 20 * FRAME_FPS;
export const PAPER_BG_HEX = "#E9E2D2";
export const INK_HEX = "#1B1B1D";
export const SLATE_HEX = "#3A4F66";
export const CRIMSON_HEX = "#C92A2A";
export const FOIA_PLATE_HEX = "#141618";
export const SAFE_ZONE_PADDING_TOP_PX = 108;
export const SAFE_ZONE_PADDING_BOTTOM_PX = 194;
export const SAFE_ZONE_EXCLUSION_WIDTH_RATIO = 0.22;
export const SAFE_ZONE_EXCLUSION_HEIGHT_RATIO = 0.14;
export const MIN_CONTENT_INK = 48;

export const SAMPLED_MOTIFS = [
  "StickmanStage",
  "AudioEvidenceCard",
  "RedactedDocReveal",
  "FoiaFootageFrame",
] as const;

export type SampledMotif = (typeof SAMPLED_MOTIFS)[number];

export type StillPlacement =
  | "contained"
  | "blank"
  | "top-border"
  | "bottom-border"
  | "bottom-right"
  | "foia-stamp"
  | "crimson-border";

export type BorderName = "top" | "bottom" | "bottom-right" | "left" | "right";

export const DEPENDENCY_SPECIFIERS = {
  emotions: "../rig/StickEmotions.js",
  grade: "../grade/GradeContract.js",
  safeZone: "../safe_zone.js",
} as const;

const SSIM_C1 = (0.01 * 255) ** 2;
const SSIM_C2 = (0.03 * 255) ** 2;
const SCENE_ID = /^[A-Za-z0-9_-]+$/;
const LINEAR = new Float64Array(256);

for (let channel = 0; channel < 256; channel += 1) {
  const unit = channel / 255;
  LINEAR[channel] = unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
}

export class FrameVerifierError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FrameVerifierError";
  }
}

export interface RgbaFrame {
  readonly width: number;
  readonly height: number;
  readonly data: Uint8Array;
}

export interface PixelRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface ExclusionBorder extends PixelRect {
  readonly name: BorderName;
}

export interface SafeZoneBorders {
  readonly width: number;
  readonly height: number;
  readonly content: PixelRect;
  readonly borders: readonly ExclusionBorder[];
}

export interface SafeZoneMeasurement {
  readonly content: PixelRect;
  readonly exclusion: PixelRect;
  readonly captionBar: PixelRect;
}

export interface BorderIntrusion {
  readonly border: BorderName;
  readonly x: number;
  readonly y: number;
  readonly hex: string;
  readonly contrast: number;
}

export interface BorderAudit {
  readonly clean: boolean;
  readonly intrusionCount: number;
  readonly intrusions: readonly BorderIntrusion[];
  readonly plateDelta: number;
}

export interface StillVerification {
  readonly ssim: number;
  readonly ssimPass: boolean;
  readonly hashMatches: boolean;
  readonly nonBlank: boolean;
  readonly borderClean: boolean;
  readonly pass: boolean;
}

export interface StickEmotionPath {
  readonly feature: string;
  readonly d: string;
}

export interface StickEmotionModule {
  readonly STICK_EMOTIONS: readonly string[];
  readonly resolveStickEmotion: (input: {
    readonly emotion: string;
    readonly frame: number;
    readonly scale?: number;
  }) => {
    readonly paths: readonly StickEmotionPath[];
  };
}

export interface UngradedPlate {
  readonly width: number;
  readonly height: number;
  readonly paperBgHex: string;
  readonly paperGrain: number;
  readonly vignette: number;
  readonly remotionGrainApplied: boolean;
  readonly remotionVignetteApplied: boolean;
}

export interface GradeModule {
  readonly REMOTION_PAPER_GRAIN: number;
  readonly REMOTION_VIGNETTE: number;
  readonly FRAME_WIDTH: number;
  readonly FRAME_HEIGHT: number;
  readonly sceneNeedsGrade: (scene: {
    readonly scene_id: string;
    readonly visual_engine: string;
    readonly motif_component?: string | null;
  }) => boolean;
  readonly renderUngradedFrame: (paperBgHex: string) => UngradedPlate;
  readonly rasterizeUngradedFrame: (frame: UngradedPlate) => Uint8Array;
}

export interface SafeZoneModule {
  readonly SAFE_ZONE_PADDING_TOP_PX: number | null;
  readonly SAFE_ZONE_PADDING_BOTTOM_PX: number | null;
  readonly SAFE_ZONE_EXCLUSION_WIDTH: string | null;
  readonly SAFE_ZONE_EXCLUSION_HEIGHT: string | null;
  readonly measureSafeZone: ((props: { readonly isEndScreen: boolean }) => SafeZoneMeasurement) | null;
}

export interface FrameVerifierDeps {
  readonly emotions: StickEmotionModule | null;
  readonly grade: GradeModule | null;
  readonly safeZone: SafeZoneModule | null;
}

export interface RenderStillRequest {
  readonly motif: SampledMotif;
  readonly frame: number;
  readonly durationInFrames: number;
  readonly paperBgHex?: string;
  readonly emotion?: string;
  readonly sceneId?: string;
  readonly placement?: StillPlacement;
}

export interface RenderedStill {
  readonly frame: RgbaFrame;
  readonly hash: string;
  readonly motif: SampledMotif;
  readonly frameIndex: number;
  readonly endScreen: boolean;
  readonly paperBgHex: string;
  readonly paperGrain: 0;
  readonly vignette: 0;
  readonly exemptSafeZoneFoia: boolean;
  readonly borders: SafeZoneBorders;
  readonly audit: BorderAudit;
  readonly blank: boolean;
}

export interface VerifyStillOptions {
  readonly minSsim?: number;
  readonly paperBgHex?: string;
  readonly exemptSafeZoneFoia?: boolean;
  readonly requireHashMatch?: boolean;
  readonly borders?: SafeZoneBorders;
}

type Rgb = readonly [number, number, number];

type Segment =
  | { readonly kind: "L"; readonly x0: number; readonly y0: number; readonly x1: number; readonly y1: number }
  | {
      readonly kind: "Q";
      readonly x0: number;
      readonly y0: number;
      readonly x1: number;
      readonly y1: number;
      readonly x2: number;
      readonly y2: number;
    }
  | {
      readonly kind: "C";
      readonly x0: number;
      readonly y0: number;
      readonly x1: number;
      readonly y1: number;
      readonly x2: number;
      readonly y2: number;
      readonly x3: number;
      readonly y3: number;
    };

export function isSampledMotif(value: string): value is SampledMotif {
  return (SAMPLED_MOTIFS as readonly string[]).includes(value);
}

export function hashFrame(frame: RgbaFrame): string {
  assertBuffer(frame);
  return createHash("sha256")
    .update(`${frame.width}x${frame.height}\n`)
    .update(frame.data)
    .digest("hex");
}

export function structuralSimilarity(left: RgbaFrame, right: RgbaFrame): number {
  assertBuffer(left);
  assertBuffer(right);
  if (left.width !== right.width || left.height !== right.height) {
    throw new FrameVerifierError("SSIM requires two frames of the same size");
  }
  if (bytesEqual(left.data, right.data)) return 1;

  const { width, height } = left;
  const lumaLeft = new Float64Array(width * height);
  const lumaRight = new Float64Array(width * height);
  for (let index = 0; index < lumaLeft.length; index += 1) {
    lumaLeft[index] = rec709(left.data, index);
    lumaRight[index] = rec709(right.data, index);
  }

  const blocksX = width / SSIM_BLOCK;
  const blocksY = height / SSIM_BLOCK;
  let total = 0;
  for (let by = 0; by < blocksY; by += 1) {
    for (let bx = 0; bx < blocksX; bx += 1) {
      total += blockSsim(lumaLeft, lumaRight, width, bx * SSIM_BLOCK, by * SSIM_BLOCK);
    }
  }
  return total / (blocksX * blocksY);
}

export function safeZoneBorders(deps: FrameVerifierDeps | null, endScreen: boolean): SafeZoneBorders {
  const measured = deps?.safeZone?.measureSafeZone?.({ isEndScreen: endScreen }) ?? null;
  if (measured) return bordersFromMeasurement(measured);
  return catalogBorders(deps?.safeZone ?? null);
}

export function foiaStampWindow(borders: SafeZoneBorders): PixelRect {
  const top = namedBorder(borders, "top");
  const height = Math.min(top.height, borders.height * 0.06);
  const x = borders.width * 0.7;
  return { x, y: top.y, width: borders.width - x, height };
}

export function auditExclusionBorders(
  frame: RgbaFrame,
  paperBgHex: string,
  options?: {
    readonly borders?: SafeZoneBorders;
    readonly exemptSafeZoneFoia?: boolean;
  },
): BorderAudit {
  assertBuffer(frame);
  const plate = parseHex(paperBgHex);
  const plateLuma = relativeLuminance(plate[0], plate[1], plate[2]);
  const borders = options?.borders ?? catalogBorders(null);
  if (borders.width !== frame.width || borders.height !== frame.height) {
    throw new FrameVerifierError("safe-zone borders do not match the frame size");
  }
  const exempt = options?.exemptSafeZoneFoia === true;
  const intrusions: BorderIntrusion[] = [];
  let intrusionCount = 0;
  let plateDelta = 0;

  for (const border of borders.borders) {
    const x0 = Math.ceil(border.x);
    const y0 = Math.ceil(border.y);
    const x1 = Math.floor(border.x + border.width);
    const y1 = Math.floor(border.y + border.height);
    for (let y = y0; y < y1; y += 1) {
      for (let x = x0; x < x1; x += 1) {
        if (owningBorder(borders, x, y) !== border.name) continue;
        const offset = (y * frame.width + x) * 4;
        const red = frame.data[offset] ?? 0;
        const green = frame.data[offset + 1] ?? 0;
        const blue = frame.data[offset + 2] ?? 0;
        plateDelta = Math.max(plateDelta, channelDelta(red, green, blue, plate));
        const contrast = contrastRatio(relativeLuminance(red, green, blue), plateLuma);
        const crimson = isCrimson(red, green, blue);
        if (contrast <= HIGH_CONTRAST_RATIO && !crimson) continue;
        if (exempt && !crimson && inRect(foiaStampWindow(borders), x, y)) continue;
        intrusionCount += 1;
        if (intrusions.length < 12) {
          intrusions.push({
            border: border.name,
            x,
            y,
            hex: toHex(red, green, blue),
            contrast,
          });
        }
      }
    }
  }

  return { clean: intrusionCount === 0, intrusionCount, intrusions, plateDelta };
}

export function isBlankFrame(frame: RgbaFrame, content: PixelRect, plateHex: string, hole?: PixelRect): boolean {
  assertBuffer(frame);
  if (isFlat(frame)) return true;
  const plate = parseHex(plateHex);
  let ink = 0;
  const y1 = Math.min(frame.height, Math.floor(content.y + content.height));
  const x1 = Math.min(frame.width, Math.floor(content.x + content.width));
  for (let y = Math.max(0, Math.ceil(content.y)); y < y1; y += 1) {
    for (let x = Math.max(0, Math.ceil(content.x)); x < x1; x += 1) {
      if (hole && inRect(hole, x, y)) continue;
      const offset = (y * frame.width + x) * 4;
      const delta = channelDelta(frame.data[offset] ?? 0, frame.data[offset + 1] ?? 0, frame.data[offset + 2] ?? 0, plate);
      if (delta > 24) {
        ink += 1;
        if (ink >= MIN_CONTENT_INK) return false;
      }
    }
  }
  return true;
}

export function verifyStill(candidate: RgbaFrame, reference: RgbaFrame, options?: VerifyStillOptions): StillVerification {
  const minSsim = options?.minSsim ?? SSIM_MIN;
  const paper = options?.paperBgHex ?? PAPER_BG_HEX;
  const borders = options?.borders ?? catalogBorders(null);
  const ssim = structuralSimilarity(candidate, reference);
  const audit = auditExclusionBorders(candidate, paper, {
    borders,
    exemptSafeZoneFoia: options?.exemptSafeZoneFoia === true,
  });
  const hole = namedBorder(borders, "bottom-right");
  const blank = isBlankFrame(candidate, borders.content, paper, hole);
  const ssimPass = ssim >= minSsim;
  const hashMatches = hashFrame(candidate) === hashFrame(reference);
  const nonBlank = !blank;
  const borderClean = audit.clean;
  const hashOk = options?.requireHashMatch === true ? hashMatches : true;
  return {
    ssim,
    ssimPass,
    hashMatches,
    nonBlank,
    borderClean,
    pass: ssimPass && nonBlank && borderClean && hashOk,
  };
}

/** One-level halo on ink edges. Hashes move; SSIM stays at or above the threshold. */
export function applySubpixelAntialiasNoise(frame: RgbaFrame, plateHex: string): RgbaFrame {
  assertBuffer(frame);
  const plate = parseHex(plateHex);
  const source = frame.data;
  const data = new Uint8Array(source);
  const { width, height } = frame;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      if (channelDelta(source[index] ?? 0, source[index + 1] ?? 0, source[index + 2] ?? 0, plate) <= 24) continue;
      const nudge = (x + y) % 2 === 0 ? 1 : -1;
      data[index] = clamp8((source[index] ?? 0) + nudge);
      data[index + 1] = clamp8((source[index + 1] ?? 0) + nudge);
      data[index + 2] = clamp8((source[index + 2] ?? 0) + nudge);
      const neighbor = x + 1;
      if (neighbor >= width) continue;
      const next = (y * width + neighbor) * 4;
      if (channelDelta(source[next] ?? 0, source[next + 1] ?? 0, source[next + 2] ?? 0, plate) > 2) continue;
      data[next] = clamp8(plate[0] + Math.sign((source[index] ?? 0) - plate[0]));
      data[next + 1] = clamp8(plate[1] + Math.sign((source[index + 1] ?? 0) - plate[1]));
      data[next + 2] = clamp8(plate[2] + Math.sign((source[index + 2] ?? 0) - plate[2]));
    }
  }
  return { width, height, data };
}

export function renderStill(request: RenderStillRequest, deps?: FrameVerifierDeps | null): RenderedStill {
  assertRequest(request);
  const resolved = deps ?? { emotions: null, grade: null, safeZone: null };
  const paperBgHex = (request.paperBgHex ?? PAPER_BG_HEX).toUpperCase();
  parseHex(paperBgHex);
  const sceneId = request.sceneId ?? `still_${request.motif}`;
  if (!SCENE_ID.test(sceneId)) throw new FrameVerifierError("sceneId must match ^[A-Za-z0-9_-]+$");
  if (request.emotion !== undefined && request.motif !== "StickmanStage") {
    throw new FrameVerifierError("emotion stills are only sampled for StickmanStage");
  }

  const placement = request.placement ?? "contained";
  const endScreen = request.frame >= request.durationInFrames - END_SCREEN_FRAMES;
  const borders = safeZoneBorders(resolved, endScreen);
  const exemptSafeZoneFoia = resolveFoiaExemption(request.motif, sceneId, resolved.grade);
  const plate = paintPlate(paperBgHex, resolved.grade);
  const frame = rgbToRgba(plate.rgb, FRAME_WIDTH, FRAME_HEIGHT);
  if (placement !== "blank") {
    drawMotif(frame, request, borders, resolved.emotions, endScreen);
    drawPlacement(frame, borders, placement);
  }

  const audit = auditExclusionBorders(frame, plate.paperBgHex, { borders, exemptSafeZoneFoia });
  const blank = isBlankFrame(frame, borders.content, plate.paperBgHex, namedBorder(borders, "bottom-right"));
  return {
    frame,
    hash: hashFrame(frame),
    motif: request.motif,
    frameIndex: request.frame,
    endScreen,
    paperBgHex: plate.paperBgHex,
    paperGrain: 0,
    vignette: 0,
    exemptSafeZoneFoia,
    borders,
    audit,
    blank,
  };
}

export async function loadFrameVerifierDeps(
  load?: (specifier: string) => Promise<unknown>,
): Promise<FrameVerifierDeps> {
  const read = load ?? loadInstalled;
  const [emotions, grade, safeZone] = await Promise.all([
    readOptional(read, DEPENDENCY_SPECIFIERS.emotions),
    readOptional(read, DEPENDENCY_SPECIFIERS.grade),
    readOptional(read, DEPENDENCY_SPECIFIERS.safeZone),
  ]);
  return {
    emotions: asEmotions(emotions),
    grade: asGrade(grade),
    safeZone: asSafeZone(safeZone),
  };
}

function assertRequest(request: RenderStillRequest): void {
  if (!isSampledMotif(request.motif)) {
    throw new FrameVerifierError(`motif must be one of ${SAMPLED_MOTIFS.join(", ")}`);
  }
  if (!Number.isInteger(request.frame) || request.frame < 0) {
    throw new FrameVerifierError("frame must be a non-negative integer");
  }
  if (!Number.isInteger(request.durationInFrames) || request.durationInFrames < 1) {
    throw new FrameVerifierError("durationInFrames must be a positive integer");
  }
  if (request.frame >= request.durationInFrames) {
    throw new FrameVerifierError("frame must be inside the composition");
  }
}

function resolveFoiaExemption(motif: SampledMotif, sceneId: string, grade: GradeModule | null): boolean {
  if (motif !== "FoiaFootageFrame") {
    if (grade) grade.sceneNeedsGrade({ scene_id: sceneId, visual_engine: visualEngine(motif), motif_component: motif });
    return false;
  }
  if (!grade) return true;
  return grade.sceneNeedsGrade({
    scene_id: sceneId,
    visual_engine: "FOIA_REAL_FOOTAGE",
    motif_component: motif,
  }) === false;
}

function visualEngine(motif: SampledMotif): "CODE_STICKMAN" | "AUDIO_EVIDENCE_CARD" | "FOIA_REAL_FOOTAGE" {
  if (motif === "FoiaFootageFrame") return "FOIA_REAL_FOOTAGE";
  if (motif === "AudioEvidenceCard") return "AUDIO_EVIDENCE_CARD";
  return "CODE_STICKMAN";
}

function paintPlate(paperBgHex: string, grade: GradeModule | null): { rgb: Uint8Array; paperBgHex: string } {
  if (!grade) {
    return { rgb: fillRgb(parseHex(paperBgHex)), paperBgHex };
  }
  if (grade.REMOTION_PAPER_GRAIN !== 0 || grade.REMOTION_VIGNETTE !== 0) {
    throw new FrameVerifierError("Remotion stills cannot carry paper grain or vignette");
  }
  const plate = grade.renderUngradedFrame(paperBgHex);
  if (plate.paperGrain !== 0 || plate.vignette !== 0 || plate.remotionGrainApplied || plate.remotionVignetteApplied) {
    throw new FrameVerifierError("Remotion stills cannot carry paper grain or vignette");
  }
  if (plate.width !== FRAME_WIDTH || plate.height !== FRAME_HEIGHT) {
    throw new FrameVerifierError("ungraded plate must be 1920x1080");
  }
  const rgb = grade.rasterizeUngradedFrame(plate);
  if (rgb.length !== FRAME_WIDTH * FRAME_HEIGHT * 3) {
    throw new FrameVerifierError("ungraded plate raster has the wrong length");
  }
  return { rgb, paperBgHex: plate.paperBgHex.toUpperCase() };
}

function fillRgb(color: Rgb): Uint8Array {
  const rgb = new Uint8Array(FRAME_WIDTH * FRAME_HEIGHT * 3);
  for (let index = 0; index < rgb.length; index += 3) {
    rgb[index] = color[0];
    rgb[index + 1] = color[1];
    rgb[index + 2] = color[2];
  }
  return rgb;
}

function rgbToRgba(rgb: Uint8Array, width: number, height: number): RgbaFrame {
  const data = new Uint8Array(width * height * 4);
  for (let pixel = 0; pixel < width * height; pixel += 1) {
    const source = pixel * 3;
    const target = pixel * 4;
    data[target] = rgb[source] ?? 0;
    data[target + 1] = rgb[source + 1] ?? 0;
    data[target + 2] = rgb[source + 2] ?? 0;
    data[target + 3] = 255;
  }
  return { width, height, data };
}

function drawMotif(
  frame: RgbaFrame,
  request: RenderStillRequest,
  borders: SafeZoneBorders,
  emotions: StickEmotionModule | null,
  endScreen: boolean,
): void {
  const clip = contentClip(borders);
  const ink = parseHex(INK_HEX);
  if (request.motif === "StickmanStage") drawStickman(frame, borders, request, emotions, clip, ink);
  else if (request.motif === "AudioEvidenceCard") drawAudioCard(frame, borders, request.frame, clip);
  else if (request.motif === "RedactedDocReveal") drawRedactedDoc(frame, borders, request.frame, clip, ink);
  else drawFoia(frame, borders, clip, ink);
  if (endScreen) drawEndScreenCard(frame, borders, clip);
}

function drawStickman(
  frame: RgbaFrame,
  borders: SafeZoneBorders,
  request: RenderStillRequest,
  emotions: StickEmotionModule | null,
  clip: (x: number, y: number) => boolean,
  ink: Rgb,
): void {
  if (emotions) {
    const rig = emotions.resolveStickEmotion({
      emotion: request.emotion ?? "neutral",
      frame: request.frame,
      scale: 1,
    });
    strokePaths(frame, rig.paths, borders.content, ink, clip);
    return;
  }
  const content = borders.content;
  const cx = content.x + content.width / 2;
  const crown = content.y + 80;
  const head = crown + 36;
  stampDisc(frame, cx, head, 36, ink, clip);
  strokeSegment(frame, cx, crown + 72, cx, crown + 250, ink, clip);
  strokeSegment(frame, cx, crown + 110, cx - 90, crown + 200, ink, clip);
  strokeSegment(frame, cx, crown + 110, cx + 90, crown + 200, ink, clip);
  strokeSegment(frame, cx, crown + 250, cx - 70, crown + 400, ink, clip);
  strokeSegment(frame, cx, crown + 250, cx + 70, crown + 400, ink, clip);
}

function drawAudioCard(frame: RgbaFrame, borders: SafeZoneBorders, frameIndex: number, clip: (x: number, y: number) => boolean): void {
  const content = borders.content;
  const left = content.x + 180;
  const top = content.y + 90;
  const width = Math.min(1200, content.width - 360);
  const height = Math.min(460, content.height - 180);
  fillRect(frame, left, top, width, height, parseHex(SLATE_HEX), clip);
  const random = mulberry32(hashSeed(`audio:${frameIndex}`));
  const bars = 24;
  const gap = width / bars;
  for (let bar = 0; bar < bars; bar += 1) {
    const barHeight = 36 + Math.floor(random() * (height - 80));
    fillRect(frame, left + bar * gap + 8, top + height - 24 - barHeight, Math.max(4, gap - 16), barHeight, parseHex(INK_HEX), clip);
  }
}

function drawRedactedDoc(
  frame: RgbaFrame,
  borders: SafeZoneBorders,
  frameIndex: number,
  clip: (x: number, y: number) => boolean,
  ink: Rgb,
): void {
  const content = borders.content;
  const left = content.x + 240;
  const top = content.y + 70;
  const width = Math.min(980, content.width - 480);
  const height = Math.min(520, content.height - 150);
  fillRect(frame, left, top, width, height, parseHex("#F7F1E4"), clip);
  for (let line = 0; line < 8; line += 1) {
    fillRect(frame, left + 48, top + 48 + line * 56, width - 96, 8, ink, clip);
  }
  fillRect(frame, left + 48, top + 160, width * 0.55, 36, ink, clip);
  const sweep = left + 48 + (frameIndex % 90) * 4;
  fillRect(frame, Math.min(sweep, left + width - 80), top + 300, 64, 28, parseHex(SLATE_HEX), clip);
}

function drawFoia(frame: RgbaFrame, borders: SafeZoneBorders, clip: (x: number, y: number) => boolean, ink: Rgb): void {
  const content = borders.content;
  const left = content.x + 160;
  const top = content.y + 60;
  const width = Math.min(1440, content.width - 320);
  const height = Math.min(560, content.height - 140);
  fillRect(frame, left, top, width, height, parseHex(FOIA_PLATE_HEX), clip);
  fillRect(frame, left + 24, top + 24, 180, 16, ink, clip);
  fillRect(frame, left + 24, top + 48, 120, 8, parseHex("#D9D3C5"), clip);
}

function drawEndScreenCard(frame: RgbaFrame, borders: SafeZoneBorders, clip: (x: number, y: number) => boolean): void {
  const content = borders.content;
  const exclusion = namedBorder(borders, "bottom-right");
  const left = Math.floor(content.x) + 48;
  const right = Math.floor(exclusion.x) - 16;
  const bottom = Math.floor(content.y + content.height);
  const top = bottom - 64;
  if (right - left < 32 || top < content.y) return;
  fillRect(frame, left, top, right - left, bottom - top, parseHex(SLATE_HEX), clip);
  fillRect(frame, left + 24, top + 20, 220, 10, parseHex(INK_HEX), clip);
}

function drawPlacement(frame: RgbaFrame, borders: SafeZoneBorders, placement: StillPlacement): void {
  if (placement === "contained" || placement === "blank") return;
  const ink = parseHex(INK_HEX);
  if (placement === "top-border") {
    stampInside(frame, namedBorder(borders, "top"), 160, ink);
    return;
  }
  if (placement === "bottom-border") {
    stampInside(frame, namedBorder(borders, "bottom"), 160, ink);
    return;
  }
  if (placement === "bottom-right") {
    stampInside(frame, namedBorder(borders, "bottom-right"), 8, ink);
    return;
  }
  const stamp = foiaStampWindow(borders);
  const color = placement === "crimson-border" ? parseHex(CRIMSON_HEX) : ink;
  stampInside(frame, stamp, 8, color);
}

function stampInside(frame: RgbaFrame, rect: PixelRect, xOffset: number, color: Rgb): void {
  const x = Math.ceil(rect.x) + xOffset;
  const y = Math.ceil(rect.y) + 8;
  const width = Math.floor(rect.x + rect.width) - x - 4;
  const height = Math.floor(rect.y + rect.height) - y - 4;
  if (width < 4 || height < 4) {
    throw new FrameVerifierError("placement mark does not fit in the exclusion border");
  }
  fillRect(frame, x, y, Math.min(36, width), Math.min(16, height), color, () => true);
}

function strokePaths(
  frame: RgbaFrame,
  paths: readonly StickEmotionPath[],
  content: PixelRect,
  color: Rgb,
  clip: (x: number, y: number) => boolean,
): void {
  const segments = paths.flatMap((path) => parseSegments(path.d));
  if (segments.length === 0) throw new FrameVerifierError("StickEmotions returned no drawable paths");
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const segment of segments) {
    for (const point of segmentPoints(segment)) {
      minX = Math.min(minX, point[0]);
      minY = Math.min(minY, point[1]);
      maxX = Math.max(maxX, point[0]);
      maxY = Math.max(maxY, point[1]);
    }
  }
  const margin = 36;
  const availW = content.width - margin * 2;
  const availH = content.height - margin * 2;
  if (availW < 8 || availH < 8) throw new FrameVerifierError("safe-zone content is too small to draw");
  const boundsW = Math.max(maxX - minX, 1);
  const boundsH = Math.max(maxY - minY, 1);
  const scale = Math.min(availW / boundsW, availH / boundsH);
  const originX = content.x + margin + (availW - boundsW * scale) / 2 - minX * scale;
  const originY = content.y + margin + (availH - boundsH * scale) / 2 - minY * scale;
  const mapX = (value: number) => originX + value * scale;
  const mapY = (value: number) => originY + value * scale;
  for (const segment of segments) {
    const samples = mappedSamples(segment, mapX, mapY);
    for (const sample of samples) stampDisc(frame, sample[0], sample[1], 1.6, color, clip);
  }
}

function parseSegments(d: string): Segment[] {
  const tokens = d.match(/[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?/g);
  if (!tokens || tokens.length === 0) throw new FrameVerifierError("emotion path is empty");
  const segments: Segment[] = [];
  let index = 0;
  let cx = 0;
  let cy = 0;
  let sx = 0;
  let sy = 0;
  let command = "";
  const read = (): number => {
    const token = tokens[index];
    index += 1;
    if (token === undefined || /[A-Za-z]/.test(token)) throw new FrameVerifierError("emotion path is missing a coordinate");
    return Number(token);
  };
  while (index < tokens.length) {
    const peeked = tokens[index] ?? "";
    if (/[A-Za-z]/.test(peeked)) {
      command = peeked;
      index += 1;
    }
    if (!/^[MLHVQCZ]$/.test(command)) throw new FrameVerifierError(`unsupported emotion path command ${command}`);
    if (command === "M" || command === "L") {
      const x = read();
      const y = read();
      if (command === "M") {
        cx = x;
        cy = y;
        sx = x;
        sy = y;
        command = "L";
        continue;
      }
      segments.push({ kind: "L", x0: cx, y0: cy, x1: x, y1: y });
      cx = x;
      cy = y;
    } else if (command === "H") {
      const x = read();
      segments.push({ kind: "L", x0: cx, y0: cy, x1: x, y1: cy });
      cx = x;
    } else if (command === "V") {
      const y = read();
      segments.push({ kind: "L", x0: cx, y0: cy, x1: cx, y1: y });
      cy = y;
    } else if (command === "Q") {
      const x1 = read();
      const y1 = read();
      const x2 = read();
      const y2 = read();
      segments.push({ kind: "Q", x0: cx, y0: cy, x1, y1, x2, y2 });
      cx = x2;
      cy = y2;
    } else if (command === "C") {
      const x1 = read();
      const y1 = read();
      const x2 = read();
      const y2 = read();
      const x3 = read();
      const y3 = read();
      segments.push({ kind: "C", x0: cx, y0: cy, x1, y1, x2, y2, x3, y3 });
      cx = x3;
      cy = y3;
    } else {
      segments.push({ kind: "L", x0: cx, y0: cy, x1: sx, y1: sy });
      cx = sx;
      cy = sy;
    }
  }
  return segments;
}

function segmentPoints(segment: Segment): readonly (readonly [number, number])[] {
  if (segment.kind === "L") return [[segment.x0, segment.y0], [segment.x1, segment.y1]];
  if (segment.kind === "Q") return [[segment.x0, segment.y0], [segment.x1, segment.y1], [segment.x2, segment.y2]];
  return [[segment.x0, segment.y0], [segment.x1, segment.y1], [segment.x2, segment.y2], [segment.x3, segment.y3]];
}

function mappedSamples(
  segment: Segment,
  mapX: (value: number) => number,
  mapY: (value: number) => number,
): readonly (readonly [number, number])[] {
  const span = segmentPoints(segment).reduce((total, point, index, points) => {
    const previous = points[index - 1];
    if (!previous) return total;
    return total + Math.hypot(mapX(point[0]) - mapX(previous[0]), mapY(point[1]) - mapY(previous[1]));
  }, 0);
  const steps = Math.max(1, Math.ceil(span / 1.25));
  const samples: (readonly [number, number])[] = [];
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    if (segment.kind === "L") {
      samples.push([
        mapX(segment.x0 + (segment.x1 - segment.x0) * t),
        mapY(segment.y0 + (segment.y1 - segment.y0) * t),
      ]);
    } else if (segment.kind === "Q") {
      const u = 1 - t;
      samples.push([
        mapX(u * u * segment.x0 + 2 * u * t * segment.x1 + t * t * segment.x2),
        mapY(u * u * segment.y0 + 2 * u * t * segment.y1 + t * t * segment.y2),
      ]);
    } else {
      const u = 1 - t;
      samples.push([
        mapX(u ** 3 * segment.x0 + 3 * u ** 2 * t * segment.x1 + 3 * u * t ** 2 * segment.x2 + t ** 3 * segment.x3),
        mapY(u ** 3 * segment.y0 + 3 * u ** 2 * t * segment.y1 + 3 * u * t ** 2 * segment.y2 + t ** 3 * segment.y3),
      ]);
    }
  }
  return samples;
}

function strokeSegment(
  frame: RgbaFrame,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  color: Rgb,
  clip: (x: number, y: number) => boolean,
): void {
  const steps = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0)));
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    stampDisc(frame, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 2.2, color, clip);
  }
}

function stampDisc(
  frame: RgbaFrame,
  cx: number,
  cy: number,
  radius: number,
  color: Rgb,
  clip: (x: number, y: number) => boolean,
): void {
  const reach = Math.ceil(radius);
  const limit = radius * radius;
  const x0 = Math.round(cx);
  const y0 = Math.round(cy);
  for (let dy = -reach; dy <= reach; dy += 1) {
    for (let dx = -reach; dx <= reach; dx += 1) {
      if (dx * dx + dy * dy > limit) continue;
      const x = x0 + dx;
      const y = y0 + dy;
      if (!clip(x, y)) continue;
      setPixel(frame, x, y, color);
    }
  }
}

function fillRect(
  frame: RgbaFrame,
  x: number,
  y: number,
  width: number,
  height: number,
  color: Rgb,
  clip: (x: number, y: number) => boolean,
): void {
  const x0 = Math.ceil(x);
  const y0 = Math.ceil(y);
  const x1 = Math.floor(x + width);
  const y1 = Math.floor(y + height);
  for (let py = y0; py < y1; py += 1) {
    for (let px = x0; px < x1; px += 1) {
      if (!clip(px, py)) continue;
      setPixel(frame, px, py, color);
    }
  }
}

function setPixel(frame: RgbaFrame, x: number, y: number, color: Rgb): void {
  if (x < 0 || y < 0 || x >= frame.width || y >= frame.height) return;
  const offset = (y * frame.width + x) * 4;
  frame.data[offset] = color[0];
  frame.data[offset + 1] = color[1];
  frame.data[offset + 2] = color[2];
  frame.data[offset + 3] = 255;
}

function contentClip(borders: SafeZoneBorders): (x: number, y: number) => boolean {
  const content = borders.content;
  const hole = namedBorder(borders, "bottom-right");
  return (x, y) => inRect(content, x, y) && !inRect(hole, x, y);
}

function catalogBorders(safeZone: SafeZoneModule | null): SafeZoneBorders {
  const padTop = safeZone?.SAFE_ZONE_PADDING_TOP_PX ?? SAFE_ZONE_PADDING_TOP_PX;
  const padBottom = safeZone?.SAFE_ZONE_PADDING_BOTTOM_PX ?? SAFE_ZONE_PADDING_BOTTOM_PX;
  const widthRatio = ratioOf(safeZone?.SAFE_ZONE_EXCLUSION_WIDTH, SAFE_ZONE_EXCLUSION_WIDTH_RATIO);
  const heightRatio = ratioOf(safeZone?.SAFE_ZONE_EXCLUSION_HEIGHT, SAFE_ZONE_EXCLUSION_HEIGHT_RATIO);
  const exclusionWidth = FRAME_WIDTH * widthRatio;
  const exclusionHeight = FRAME_HEIGHT * heightRatio;
  return bordersFromMeasurement({
    content: {
      x: 0,
      y: padTop,
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT - padTop - padBottom,
    },
    exclusion: {
      x: FRAME_WIDTH - exclusionWidth,
      y: FRAME_HEIGHT - exclusionHeight,
      width: exclusionWidth,
      height: exclusionHeight,
    },
    captionBar: {
      x: 0,
      y: FRAME_HEIGHT - padBottom,
      width: FRAME_WIDTH,
      height: padBottom,
    },
  });
}

function bordersFromMeasurement(measured: SafeZoneMeasurement): SafeZoneBorders {
  const content = measured.content;
  const borders: ExclusionBorder[] = [];
  if (content.y > 0) borders.push({ name: "top", x: 0, y: 0, width: FRAME_WIDTH, height: content.y });
  const bottom = FRAME_HEIGHT - (content.y + content.height);
  if (bottom > 0) {
    borders.push({
      name: "bottom",
      x: 0,
      y: content.y + content.height,
      width: FRAME_WIDTH,
      height: bottom,
    });
  }
  if (content.x > 0) borders.push({ name: "left", x: 0, y: content.y, width: content.x, height: content.height });
  const rightGap = FRAME_WIDTH - (content.x + content.width);
  if (rightGap > 0) {
    borders.push({
      name: "right",
      x: content.x + content.width,
      y: content.y,
      width: rightGap,
      height: content.height,
    });
  }
  borders.push({ name: "bottom-right", ...measured.exclusion });
  return { width: FRAME_WIDTH, height: FRAME_HEIGHT, content, borders };
}

function ratioOf(token: string | null | undefined, fallback: number): number {
  if (token == null) return fallback;
  const match = /^([-\d.]+)%$/.exec(token);
  if (!match?.[1]) throw new FrameVerifierError(`exclusion size must be a percent, got ${token}`);
  return Number(match[1]) / 100;
}

function namedBorder(borders: SafeZoneBorders, name: BorderName): ExclusionBorder {
  const found = borders.borders.find((border) => border.name === name);
  if (!found) throw new FrameVerifierError(`safe zone is missing the ${name} border`);
  return found;
}

function owningBorder(borders: SafeZoneBorders, x: number, y: number): BorderName | null {
  const bottomRight = borders.borders.find((border) => border.name === "bottom-right");
  if (bottomRight && inRect(bottomRight, x, y)) return "bottom-right";
  for (const border of borders.borders) {
    if (border.name === "bottom-right") continue;
    if (inRect(border, x, y)) return border.name;
  }
  return null;
}

function inRect(rect: PixelRect, x: number, y: number): boolean {
  return x >= rect.x && y >= rect.y && x < rect.x + rect.width && y < rect.y + rect.height;
}

function blockSsim(left: Float64Array, right: Float64Array, width: number, originX: number, originY: number): number {
  let meanLeft = 0;
  let meanRight = 0;
  for (let y = 0; y < SSIM_BLOCK; y += 1) {
    for (let x = 0; x < SSIM_BLOCK; x += 1) {
      const index = (originY + y) * width + originX + x;
      meanLeft += left[index] ?? 0;
      meanRight += right[index] ?? 0;
    }
  }
  const count = SSIM_BLOCK * SSIM_BLOCK;
  meanLeft /= count;
  meanRight /= count;
  let varianceLeft = 0;
  let varianceRight = 0;
  let covariance = 0;
  for (let y = 0; y < SSIM_BLOCK; y += 1) {
    for (let x = 0; x < SSIM_BLOCK; x += 1) {
      const index = (originY + y) * width + originX + x;
      const deltaLeft = (left[index] ?? 0) - meanLeft;
      const deltaRight = (right[index] ?? 0) - meanRight;
      varianceLeft += deltaLeft * deltaLeft;
      varianceRight += deltaRight * deltaRight;
      covariance += deltaLeft * deltaRight;
    }
  }
  varianceLeft /= count;
  varianceRight /= count;
  covariance /= count;
  const numerator = (2 * meanLeft * meanRight + SSIM_C1) * (2 * covariance + SSIM_C2);
  const denominator = (meanLeft * meanLeft + meanRight * meanRight + SSIM_C1) * (varianceLeft + varianceRight + SSIM_C2);
  return numerator / denominator;
}

function rec709(data: Uint8Array, pixel: number): number {
  const offset = pixel * 4;
  return 0.299 * (data[offset] ?? 0) + 0.587 * (data[offset + 1] ?? 0) + 0.114 * (data[offset + 2] ?? 0);
}

function relativeLuminance(red: number, green: number, blue: number): number {
  return 0.2126 * (LINEAR[red] ?? 0) + 0.7152 * (LINEAR[green] ?? 0) + 0.0722 * (LINEAR[blue] ?? 0);
}

function contrastRatio(left: number, right: number): number {
  const lighter = Math.max(left, right);
  const darker = Math.min(left, right);
  return (lighter + 0.05) / (darker + 0.05);
}

function isCrimson(red: number, green: number, blue: number): boolean {
  return red >= 180 && red <= 220 && green >= 20 && green <= 70 && blue >= 20 && blue <= 70 && red - green >= 120 && red - blue >= 120;
}

function channelDelta(red: number, green: number, blue: number, plate: Rgb): number {
  return Math.max(Math.abs(red - plate[0]), Math.abs(green - plate[1]), Math.abs(blue - plate[2]));
}

function isFlat(frame: RgbaFrame): boolean {
  const red = frame.data[0] ?? 0;
  const green = frame.data[1] ?? 0;
  const blue = frame.data[2] ?? 0;
  for (let index = 4; index < frame.data.length; index += 4) {
    if (
      Math.abs((frame.data[index] ?? 0) - red) > 2
      || Math.abs((frame.data[index + 1] ?? 0) - green) > 2
      || Math.abs((frame.data[index + 2] ?? 0) - blue) > 2
    ) {
      return false;
    }
  }
  return true;
}

function assertBuffer(frame: RgbaFrame): void {
  if (!Number.isInteger(frame.width) || !Number.isInteger(frame.height) || frame.width < SSIM_BLOCK || frame.height < SSIM_BLOCK) {
    throw new FrameVerifierError("frame width and height must be integers of at least one SSIM block");
  }
  if (frame.width % SSIM_BLOCK !== 0 || frame.height % SSIM_BLOCK !== 0) {
    throw new FrameVerifierError("frame width and height must be divisible by the SSIM block");
  }
  if (frame.data.length !== frame.width * frame.height * 4) {
    throw new FrameVerifierError("RGBA buffer length does not match the frame size");
  }
}

function bytesEqual(left: Uint8Array, right: Uint8Array): boolean {
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return false;
  }
  return true;
}

function parseHex(hex: string): Rgb {
  if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) throw new FrameVerifierError(`color must be #RRGGBB, got ${hex}`);
  return [
    Number.parseInt(hex.slice(1, 3), 16),
    Number.parseInt(hex.slice(3, 5), 16),
    Number.parseInt(hex.slice(5, 7), 16),
  ];
}

function toHex(red: number, green: number, blue: number): string {
  return `#${red.toString(16).padStart(2, "0")}${green.toString(16).padStart(2, "0")}${blue.toString(16).padStart(2, "0")}`.toUpperCase();
}

function clamp8(value: number): number {
  return Math.max(0, Math.min(255, value));
}

function hashSeed(text: string): number {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash = Math.imul(hash ^ text.charCodeAt(index), 16777619);
  }
  return hash >>> 0;
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) | 0;
    let next = Math.imul(state ^ (state >>> 15), 1 | state);
    next = (next + Math.imul(next ^ (next >>> 7), 61 | next)) ^ next;
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296;
  };
}

const MODULE_DIR = dirname(fileURLToPath(import.meta.url));

function modulePresent(specifier: string): boolean {
  const javascript = resolve(MODULE_DIR, specifier);
  return [javascript, javascript.replace(/\.js$/, ".ts"), javascript.replace(/\.js$/, ".tsx")].some((file) => existsSync(file));
}

async function loadInstalled(specifier: string): Promise<unknown | null> {
  if (!modulePresent(specifier)) return null;
  try {
    return await import(/* @vite-ignore */ specifier);
  } catch (error) {
    if (isMissingModule(error)) return null;
    throw error;
  }
}

async function readOptional(load: (specifier: string) => Promise<unknown>, specifier: string): Promise<unknown | null> {
  try {
    return await load(specifier);
  } catch (error) {
    if (isMissingModule(error)) return null;
    throw error;
  }
}

function isMissingModule(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const code = "code" in error ? String(error.code) : "";
  const message = error instanceof Error ? error.message : "";
  return code === "ERR_MODULE_NOT_FOUND" || message.includes("Cannot find module") || message.includes("Failed to load");
}

function asEmotions(value: unknown): StickEmotionModule | null {
  if (value == null) return null;
  if (typeof value !== "object") throw new FrameVerifierError("StickEmotions module is not an object");
  const record = value as Record<string, unknown>;
  if (!Array.isArray(record.STICK_EMOTIONS) || typeof record.resolveStickEmotion !== "function") {
    throw new FrameVerifierError("StickEmotions module is missing STICK_EMOTIONS or resolveStickEmotion");
  }
  const names = record.STICK_EMOTIONS.map((entry) => String(entry));
  if (names.length !== 10 || names[0] !== "neutral" || names[9] !== "guilty") {
    throw new FrameVerifierError("StickEmotions must run from neutral through guilty");
  }
  return {
    STICK_EMOTIONS: names,
    resolveStickEmotion: record.resolveStickEmotion as StickEmotionModule["resolveStickEmotion"],
  };
}

function asGrade(value: unknown): GradeModule | null {
  if (value == null) return null;
  if (typeof value !== "object") throw new FrameVerifierError("GradeContract module is not an object");
  const record = value as Record<string, unknown>;
  for (const key of ["sceneNeedsGrade", "renderUngradedFrame", "rasterizeUngradedFrame"] as const) {
    if (typeof record[key] !== "function") throw new FrameVerifierError(`GradeContract is missing ${key}`);
  }
  if (record.REMOTION_PAPER_GRAIN !== 0 || record.REMOTION_VIGNETTE !== 0) {
    throw new FrameVerifierError("Remotion stills cannot carry paper grain or vignette");
  }
  if (record.FRAME_WIDTH !== FRAME_WIDTH || record.FRAME_HEIGHT !== FRAME_HEIGHT) {
    throw new FrameVerifierError("GradeContract frame size must be 1920x1080");
  }
  return record as unknown as GradeModule;
}

function asSafeZone(value: unknown): SafeZoneModule | null {
  if (value == null) return null;
  if (typeof value !== "object") throw new FrameVerifierError("SafeZone module is not an object");
  const record = value as Record<string, unknown>;
  if ("SAFE_ZONE_PADDING_TOP_PX" in record && record.SAFE_ZONE_PADDING_TOP_PX !== SAFE_ZONE_PADDING_TOP_PX) {
    throw new FrameVerifierError("SafeZoneLayout paddingTop drifted from 108");
  }
  if ("SAFE_ZONE_PADDING_BOTTOM_PX" in record && record.SAFE_ZONE_PADDING_BOTTOM_PX !== SAFE_ZONE_PADDING_BOTTOM_PX) {
    throw new FrameVerifierError("SafeZoneLayout paddingBottom drifted from 194");
  }
  if ("SAFE_ZONE_EXCLUSION_WIDTH" in record && record.SAFE_ZONE_EXCLUSION_WIDTH !== "22%") {
    throw new FrameVerifierError("SafeZoneLayout exclusion width drifted from 22%");
  }
  if ("SAFE_ZONE_EXCLUSION_HEIGHT" in record && record.SAFE_ZONE_EXCLUSION_HEIGHT !== "14%") {
    throw new FrameVerifierError("SafeZoneLayout exclusion height drifted from 14%");
  }
  const measureSafeZone = typeof record.measureSafeZone === "function"
    ? record.measureSafeZone as SafeZoneModule["measureSafeZone"]
    : null;
  if (!measureSafeZone && !("SAFE_ZONE_PADDING_TOP_PX" in record)) {
    throw new FrameVerifierError("SafeZone module has no padding and no measureSafeZone");
  }
  return {
    SAFE_ZONE_PADDING_TOP_PX: typeof record.SAFE_ZONE_PADDING_TOP_PX === "number" ? record.SAFE_ZONE_PADDING_TOP_PX : null,
    SAFE_ZONE_PADDING_BOTTOM_PX: typeof record.SAFE_ZONE_PADDING_BOTTOM_PX === "number" ? record.SAFE_ZONE_PADDING_BOTTOM_PX : null,
    SAFE_ZONE_EXCLUSION_WIDTH: typeof record.SAFE_ZONE_EXCLUSION_WIDTH === "string" ? record.SAFE_ZONE_EXCLUSION_WIDTH : null,
    SAFE_ZONE_EXCLUSION_HEIGHT: typeof record.SAFE_ZONE_EXCLUSION_HEIGHT === "string" ? record.SAFE_ZONE_EXCLUSION_HEIGHT : null,
    measureSafeZone,
  };
}
