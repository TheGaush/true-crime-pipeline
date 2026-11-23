/**
 * StickFigure face and posture rig.
 *
 * Ten enum-locked emotions run from `neutral` through `guilty`.
 * Blinks are a 4-frame closure every 105 frames (3.5s at 30 fps).
 * A scale magnitude below 0.45 drops brow strokes and the inner mouth.
 * Preview paths are plain stroked geometry. Task 104 owns locked bone lengths.
 */

export const STICK_EMOTIONS = [
  "neutral",
  "attentive",
  "skeptical",
  "concerned",
  "surprised",
  "fearful",
  "angry",
  "grieving",
  "ashamed",
  "guilty",
] as const;

export type StickEmotion = (typeof STICK_EMOTIONS)[number];
export type StickEmotionDetail = "full" | "simplified";

export const STICK_FPS = 30;
export const BLINK_PERIOD_SEC = 3.5;
export const BLINK_CYCLE_FRAMES = 105;
export const BLINK_DURATION_FRAMES = 4;
export const DETAIL_SCALE_MIN = 0.45;
export const DRAW_SCALE_MIN = 0.05;
export const STICK_EMOTION_INK = "#1B1B1D";

const PREVIEW_HEAD_RADIUS = 18;
const PREVIEW_TORSO_LEN = 64;
const PREVIEW_NECK_LEN = 8;
const EYE_LINE_OPEN = 0.12;
const MOUTH_INNER_OPEN = 0.12;
const CIRCLE_KAPPA = 0.5523;

export class StickEmotionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StickEmotionError";
  }
}

export interface EmotionFaceChannels {
  browInner: number;
  browOuter: number;
  browAsymmetry: number;
  eyeOpen: number;
  gazeX: number;
  gazeY: number;
  mouthCurve: number;
  mouthOpen: number;
  mouthTight: number;
}

export interface EmotionPostureChannels {
  headPitch: number;
  headYaw: number;
  headRoll: number;
  shoulderRaise: number;
  torsoLean: number;
  weightShift: number;
  spineCurl: number;
}

export interface StickEmotionChannels {
  emotion: StickEmotion;
  face: EmotionFaceChannels;
  posture: EmotionPostureChannels;
}

export type EmotionFeature =
  | "spine"
  | "shoulders"
  | "neck"
  | "head"
  | "brow-left"
  | "brow-right"
  | "eye-left"
  | "eye-right"
  | "mouth"
  | "mouth-inner";

export interface EmotionPath {
  feature: EmotionFeature;
  d: string;
}

export interface StickEmotionBlink {
  phase: number;
  closure: number;
  periodSec: number;
  periodFrames: number;
  durationFrames: number;
}

export interface StickEmotionRig {
  emotion: StickEmotion;
  frame: number;
  scale: number;
  drawScale: number;
  detail: StickEmotionDetail;
  blink: StickEmotionBlink;
  face: EmotionFaceChannels;
  posture: EmotionPostureChannels;
  paths: EmotionPath[];
  svg: string;
}

export interface StickEmotionProps {
  emotion: string;
  frame: number;
  scale?: number;
  blinkOffsetFrames?: number;
}

interface Layout {
  pelvisX: number;
  pelvisY: number;
  midX: number;
  midY: number;
  neckX: number;
  neckY: number;
  headX: number;
  headY: number;
  shoulderY: number;
  shoulderHalf: number;
  yawScale: number;
  pitch: number;
  s: number;
}

const CHANNELS: Record<StickEmotion, { face: EmotionFaceChannels; posture: EmotionPostureChannels }> = {
  neutral: {
    face: { browInner: 0, browOuter: 0, browAsymmetry: 0, eyeOpen: 0.72, gazeX: 0, gazeY: 0, mouthCurve: 0, mouthOpen: 0, mouthTight: 0 },
    posture: { headPitch: 0, headYaw: 0, headRoll: 0, shoulderRaise: 0, torsoLean: 0, weightShift: 0, spineCurl: 0 },
  },
  attentive: {
    face: { browInner: 0.35, browOuter: 0.2, browAsymmetry: 0, eyeOpen: 0.9, gazeX: 0, gazeY: 0.2, mouthCurve: 0.08, mouthOpen: 0.02, mouthTight: 0 },
    posture: { headPitch: -0.12, headYaw: 0, headRoll: 0, shoulderRaise: 0.08, torsoLean: 0.16, weightShift: 0, spineCurl: 0 },
  },
  skeptical: {
    face: { browInner: 0.15, browOuter: -0.05, browAsymmetry: 0.7, eyeOpen: 0.6, gazeX: 0.25, gazeY: 0, mouthCurve: -0.18, mouthOpen: 0, mouthTight: 0.35 },
    posture: { headPitch: 0.06, headYaw: 0.18, headRoll: 0.12, shoulderRaise: 0.04, torsoLean: 0, weightShift: 0.14, spineCurl: 0.02 },
  },
  concerned: {
    face: { browInner: 0.62, browOuter: 0.28, browAsymmetry: 0, eyeOpen: 0.82, gazeX: 0, gazeY: -0.08, mouthCurve: -0.32, mouthOpen: 0.06, mouthTight: 0.1 },
    posture: { headPitch: 0.14, headYaw: 0, headRoll: 0, shoulderRaise: 0.36, torsoLean: 0.08, weightShift: 0, spineCurl: 0.1 },
  },
  surprised: {
    face: { browInner: 0.9, browOuter: 0.75, browAsymmetry: 0, eyeOpen: 1, gazeX: 0, gazeY: 0.12, mouthCurve: 0.05, mouthOpen: 0.82, mouthTight: 0 },
    posture: { headPitch: -0.16, headYaw: 0, headRoll: 0, shoulderRaise: 0.48, torsoLean: -0.26, weightShift: 0, spineCurl: 0 },
  },
  fearful: {
    face: { browInner: 0.74, browOuter: 0.4, browAsymmetry: 0.12, eyeOpen: 1, gazeX: -0.15, gazeY: 0.05, mouthCurve: -0.42, mouthOpen: 0.38, mouthTight: 0.15 },
    posture: { headPitch: 0.08, headYaw: -0.1, headRoll: -0.06, shoulderRaise: 0.78, torsoLean: -0.34, weightShift: -0.16, spineCurl: 0.24 },
  },
  angry: {
    face: { browInner: -0.85, browOuter: -0.4, browAsymmetry: 0.08, eyeOpen: 0.42, gazeX: 0, gazeY: 0.02, mouthCurve: -0.55, mouthOpen: 0.1, mouthTight: 0.72 },
    posture: { headPitch: -0.2, headYaw: 0, headRoll: 0, shoulderRaise: 0.22, torsoLean: 0.4, weightShift: 0, spineCurl: 0.04 },
  },
  grieving: {
    face: { browInner: 0.48, browOuter: 0.66, browAsymmetry: 0, eyeOpen: 0.5, gazeX: 0, gazeY: -0.55, mouthCurve: -0.72, mouthOpen: 0.08, mouthTight: 0.05 },
    posture: { headPitch: 0.36, headYaw: 0, headRoll: 0.04, shoulderRaise: 0.06, torsoLean: 0.06, weightShift: 0, spineCurl: 0.4 },
  },
  ashamed: {
    face: { browInner: 0.22, browOuter: 0.18, browAsymmetry: 0.16, eyeOpen: 0.34, gazeX: 0.4, gazeY: -0.78, mouthCurve: -0.22, mouthOpen: 0, mouthTight: 0.48 },
    posture: { headPitch: 0.52, headYaw: 0.28, headRoll: 0.16, shoulderRaise: 0.24, torsoLean: 0.1, weightShift: 0.26, spineCurl: 0.55 },
  },
  guilty: {
    face: { browInner: 0.3, browOuter: 0.08, browAsymmetry: -0.42, eyeOpen: 0.28, gazeX: -0.55, gazeY: -0.92, mouthCurve: -0.36, mouthOpen: 0.04, mouthTight: 0.64 },
    posture: { headPitch: 0.66, headYaw: -0.34, headRoll: -0.14, shoulderRaise: 0.42, torsoLean: 0.05, weightShift: -0.3, spineCurl: 0.72 },
  },
};

export function isStickEmotion(value: string): value is StickEmotion {
  return (STICK_EMOTIONS as readonly string[]).includes(value);
}

export function assertStickEmotionCoverage(emotions: readonly string[] = STICK_EMOTIONS): void {
  if (emotions.length !== STICK_EMOTIONS.length || emotions.some((name, index) => name !== STICK_EMOTIONS[index])) {
    throw new StickEmotionError(`stick emotions must be exactly ${STICK_EMOTIONS.join(", ")}`);
  }
}

export function blinkPhase(frame: number, blinkOffsetFrames = 0): number {
  if (!Number.isFinite(frame) || !Number.isFinite(blinkOffsetFrames)) {
    throw new StickEmotionError("blink frame and offset must be finite numbers");
  }
  const shifted = Math.floor(frame) - Math.floor(blinkOffsetFrames);
  return ((shifted % BLINK_CYCLE_FRAMES) + BLINK_CYCLE_FRAMES) % BLINK_CYCLE_FRAMES;
}

export function blinkClosure(frame: number, blinkOffsetFrames = 0): number {
  const phase = blinkPhase(frame, blinkOffsetFrames);
  if (phase === 0 || phase === 3) return 0.5;
  if (phase === 1 || phase === 2) return 1;
  return 0;
}

export function stickEmotionChannels(emotion: string): StickEmotionChannels {
  const name = parseEmotion(emotion);
  const row = CHANNELS[name];
  return { emotion: name, face: copyFace(row.face), posture: copyPosture(row.posture) };
}

export function resolveStickEmotion(input: StickEmotionProps): StickEmotionRig {
  const emotion = parseEmotion(input.emotion);
  if (typeof input.frame !== "number" || !Number.isFinite(input.frame)) {
    throw new StickEmotionError("frame must be a finite number");
  }
  const sized = readScale(input.scale);
  if (input.blinkOffsetFrames !== undefined && !Number.isFinite(input.blinkOffsetFrames)) {
    throw new StickEmotionError("blinkOffsetFrames must be a finite number");
  }
  const blinkOffsetFrames = input.blinkOffsetFrames ?? 0;
  const phase = blinkPhase(input.frame, blinkOffsetFrames);
  const closure = blinkClosure(input.frame, blinkOffsetFrames);
  const base = CHANNELS[emotion];
  const face = resolveFace(base.face, closure, sized.detail);
  const posture = copyPosture(base.posture);
  const drawn = drawEmotion(emotion, face, posture, sized, closure);
  return {
    emotion,
    frame: input.frame,
    scale: sized.scale,
    drawScale: sized.drawScale,
    detail: sized.detail,
    blink: {
      phase,
      closure,
      periodSec: BLINK_PERIOD_SEC,
      periodFrames: BLINK_CYCLE_FRAMES,
      durationFrames: BLINK_DURATION_FRAMES,
    },
    face,
    posture,
    paths: drawn.paths,
    svg: drawn.svg,
  };
}

export function StickEmotions(props: StickEmotionProps): StickEmotionRig {
  return resolveStickEmotion(props);
}

export function serializeStickEmotion(rig: StickEmotionRig): string {
  return JSON.stringify({
    emotion: rig.emotion,
    frame: rig.frame,
    scale: rig.scale,
    drawScale: rig.drawScale,
    detail: rig.detail,
    blink: rig.blink,
    face: rig.face,
    posture: rig.posture,
    paths: rig.paths,
  });
}

function parseEmotion(emotion: string): StickEmotion {
  if (typeof emotion !== "string" || !isStickEmotion(emotion)) {
    throw new StickEmotionError(`unknown stick emotion ${JSON.stringify(emotion)}`);
  }
  return emotion;
}

function readScale(scale: number | undefined): { scale: number; drawScale: number; detail: StickEmotionDetail } {
  const requested = scale ?? 1;
  if (typeof requested !== "number" || !Number.isFinite(requested)) {
    throw new StickEmotionError("scale must be a finite number");
  }
  const magnitude = Math.abs(requested);
  return {
    scale: requested,
    drawScale: Math.max(magnitude, DRAW_SCALE_MIN),
    detail: magnitude >= DETAIL_SCALE_MIN ? "full" : "simplified",
  };
}

function resolveFace(base: EmotionFaceChannels, closure: number, detail: StickEmotionDetail): EmotionFaceChannels {
  const eyeOpen = clamp(base.eyeOpen * (1 - closure), 0, 1);
  if (detail === "simplified") {
    return {
      browInner: 0,
      browOuter: 0,
      browAsymmetry: 0,
      eyeOpen,
      gazeX: base.gazeX,
      gazeY: base.gazeY,
      mouthCurve: base.mouthCurve * 0.5,
      mouthOpen: 0,
      mouthTight: 0,
    };
  }
  return { ...copyFace(base), eyeOpen };
}

function drawEmotion(
  emotion: StickEmotion,
  face: EmotionFaceChannels,
  posture: EmotionPostureChannels,
  sized: { scale: number; drawScale: number; detail: StickEmotionDetail },
  closure: number,
): { paths: EmotionPath[]; svg: string } {
  const layout = buildLayout(posture, sized.drawScale);
  const paths: EmotionPath[] = [
    { feature: "spine", d: spinePath(layout) },
    { feature: "shoulders", d: shoulderPath(layout) },
    { feature: "neck", d: neckPath(layout) },
    { feature: "head", d: headPath(layout) },
  ];
  if (sized.detail === "full") {
    paths.push({ feature: "brow-left", d: browPath(-1, face, layout) });
    paths.push({ feature: "brow-right", d: browPath(1, face, layout) });
  }
  paths.push({ feature: "eye-left", d: eyePath(-1, face, layout) });
  paths.push({ feature: "eye-right", d: eyePath(1, face, layout) });
  paths.push({ feature: "mouth", d: mouthPath(face, layout) });
  if (sized.detail === "full" && face.mouthOpen > MOUTH_INNER_OPEN) {
    paths.push({ feature: "mouth-inner", d: mouthInnerPath(face, layout) });
  }
  return { paths, svg: svgDocument(emotion, sized, closure, paths) };
}

function buildLayout(posture: EmotionPostureChannels, s: number): Layout {
  const pelvisX = posture.weightShift * 10 * s;
  const midX = (posture.weightShift * 4 + posture.torsoLean * 16) * s;
  const midY = (-PREVIEW_TORSO_LEN * 0.5 + posture.spineCurl * 8) * s;
  const neckX = (posture.torsoLean * 22 + posture.weightShift * 2) * s;
  const neckY = (-PREVIEW_TORSO_LEN + posture.spineCurl * 16) * s;
  // Pitch ducks the skull along the neck without pulling it through the spine.
  const pitchDrop = clamp(posture.headPitch * PREVIEW_NECK_LEN, -PREVIEW_NECK_LEN * 0.45, PREVIEW_NECK_LEN * 0.85);
  return {
    pelvisX,
    pelvisY: 0,
    midX,
    midY,
    neckX,
    neckY,
    headX: neckX + (posture.headRoll * 6 + posture.headYaw * 2) * s,
    headY: neckY - (PREVIEW_NECK_LEN + PREVIEW_HEAD_RADIUS - pitchDrop) * s,
    shoulderY: neckY + (14 - posture.shoulderRaise * 12) * s,
    shoulderHalf: 18 * s,
    yawScale: 1 - Math.min(0.4, Math.abs(posture.headYaw) * 0.45),
    pitch: posture.headPitch * 0.45,
    s,
  };
}

function spinePath(layout: Layout): string {
  return cmd(["M", layout.pelvisX, layout.pelvisY, "Q", layout.midX, layout.midY, layout.neckX, layout.neckY]);
}

function shoulderPath(layout: Layout): string {
  return cmd(["M", layout.neckX - layout.shoulderHalf, layout.shoulderY, "L", layout.neckX + layout.shoulderHalf, layout.shoulderY]);
}

function neckPath(layout: Layout): string {
  return cmd(["M", layout.neckX, layout.neckY, "L", layout.headX, layout.headY + PREVIEW_HEAD_RADIUS * layout.s]);
}

function headPath(layout: Layout): string {
  return circlePath(layout.headX, layout.headY, PREVIEW_HEAD_RADIUS * layout.yawScale * layout.s, PREVIEW_HEAD_RADIUS * layout.s);
}

function browPath(side: -1 | 1, face: EmotionFaceChannels, layout: Layout): string {
  const asym = face.browAsymmetry * side;
  const innerY = -8.2 - face.browInner * 3.6 - asym * 2.8;
  const outerY = -7.4 - face.browOuter * 3.2 - asym * 1.6;
  const controlY = -9.4 - Math.max(face.browInner, face.browOuter) * 2.4 - Math.abs(asym);
  const start = facePoint(side * 2.4, innerY, layout);
  const control = facePoint(side * 5.4, controlY, layout);
  const end = facePoint(side * 8.8, outerY, layout);
  return cmd(["M", start[0], start[1], "Q", control[0], control[1], end[0], end[1]]);
}

function eyePath(side: -1 | 1, face: EmotionFaceChannels, layout: Layout): string {
  const localX = side * 6.4 + face.gazeX * 1.4;
  const localY = 1.2 - face.gazeY * 1.3;
  const center = facePoint(localX, localY, layout);
  if (face.eyeOpen < EYE_LINE_OPEN) {
    const left = facePoint(localX - 3.1, localY, layout);
    const right = facePoint(localX + 3.1, localY, layout);
    return cmd(["M", left[0], left[1], "H", right[0]]);
  }
  const rx = 3.1 * layout.yawScale * layout.s;
  const ry = (0.4 + face.eyeOpen * 2.5) * layout.s;
  return cmd([
    "M", center[0] - rx, center[1],
    "Q", center[0], center[1] - ry, center[0] + rx, center[1],
    "Q", center[0], center[1] + ry, center[0] - rx, center[1],
  ]);
}

function mouthPath(face: EmotionFaceChannels, layout: Layout): string {
  const half = 6.4 - face.mouthTight * 2.4;
  const cornerY = 7.6 - face.mouthCurve * 3.8;
  const midY = 7.6 + face.mouthCurve * 1.2 + face.mouthOpen * 0.4;
  const left = facePoint(-half, cornerY, layout);
  const mid = facePoint(0, midY, layout);
  const right = facePoint(half, cornerY, layout);
  return cmd(["M", left[0], left[1], "Q", mid[0], mid[1], right[0], right[1]]);
}

function mouthInnerPath(face: EmotionFaceChannels, layout: Layout): string {
  const half = (6.4 - face.mouthTight * 2.4) * 0.72;
  const cornerY = 8.2 - face.mouthCurve * 3.8;
  const midY = 7.6 + face.mouthCurve * 1.2 + face.mouthOpen * 5.2;
  const left = facePoint(-half, cornerY, layout);
  const mid = facePoint(0, midY, layout);
  const right = facePoint(half, cornerY, layout);
  return cmd(["M", left[0], left[1], "Q", mid[0], mid[1], right[0], right[1]]);
}

function facePoint(x: number, y: number, layout: Layout): [number, number] {
  const xr = x - y * layout.pitch;
  const yr = y + x * layout.pitch;
  return [layout.headX + xr * layout.yawScale * layout.s, layout.headY + yr * layout.s];
}

function circlePath(cx: number, cy: number, rx: number, ry: number): string {
  const kx = rx * CIRCLE_KAPPA;
  const ky = ry * CIRCLE_KAPPA;
  return cmd([
    "M", cx - rx, cy,
    "C", cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry,
    "C", cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy,
    "C", cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry,
    "C", cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy,
  ]);
}

function svgDocument(
  emotion: StickEmotion,
  sized: { scale: number; drawScale: number; detail: StickEmotionDetail },
  closure: number,
  paths: EmotionPath[],
): string {
  const s = sized.drawScale;
  const body = paths.map((path) => `<path data-feature="${path.feature}" d="${path.d}"/>`).join("");
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${fmt1(-90 * s)} ${fmt1(-160 * s)} ${fmt1(180 * s)} ${fmt1(190 * s)}" ` +
    `fill="none" stroke="${STICK_EMOTION_INK}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" ` +
    `data-rig="stick-emotion" data-emotion="${emotion}" data-detail="${sized.detail}" data-scale="${fmt4(sized.scale)}" ` +
    `data-draw-scale="${fmt4(sized.drawScale)}" data-blink-closure="${fmt1(closure)}">` +
    body +
    `</svg>`
  );
}

function cmd(parts: Array<string | number>): string {
  return parts.map((part) => (typeof part === "number" ? fmt1(part) : part)).join(" ");
}

function fmt1(value: number): string {
  if (!Number.isFinite(value)) throw new StickEmotionError("non-finite path coordinate");
  const rounded = Math.round(value * 10) / 10;
  return (rounded === 0 ? 0 : rounded).toFixed(1);
}

function fmt4(value: number): string {
  if (!Number.isFinite(value)) throw new StickEmotionError("non-finite scale");
  const rounded = Math.round(value * 10000) / 10000;
  return (rounded === 0 ? 0 : rounded).toFixed(4);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function copyFace(face: EmotionFaceChannels): EmotionFaceChannels {
  return {
    browInner: face.browInner,
    browOuter: face.browOuter,
    browAsymmetry: face.browAsymmetry,
    eyeOpen: face.eyeOpen,
    gazeX: face.gazeX,
    gazeY: face.gazeY,
    mouthCurve: face.mouthCurve,
    mouthOpen: face.mouthOpen,
    mouthTight: face.mouthTight,
  };
}

function copyPosture(posture: EmotionPostureChannels): EmotionPostureChannels {
  return {
    headPitch: posture.headPitch,
    headYaw: posture.headYaw,
    headRoll: posture.headRoll,
    shoulderRaise: posture.shoulderRaise,
    torsoLean: posture.torsoLean,
    weightShift: posture.weightShift,
    spineCurl: posture.spineCurl,
  };
}

function validateRig(): void {
  const names: readonly string[] = STICK_EMOTIONS;
  if (names.length !== 10 || names[0] !== "neutral" || names[9] !== "guilty" || new Set(names).size !== names.length) {
    throw new StickEmotionError("stick emotion enum must run from neutral through guilty");
  }
  const keys = Object.keys(CHANNELS);
  if (keys.length !== names.length || keys.some((key, index) => key !== names[index])) {
    throw new StickEmotionError("emotion channel table must follow the enum");
  }
  if (BLINK_CYCLE_FRAMES !== BLINK_PERIOD_SEC * STICK_FPS) {
    throw new StickEmotionError("blink cycle must be 3.5s at 30 fps");
  }
  let closed = 0;
  for (let phase = 0; phase < BLINK_CYCLE_FRAMES; phase += 1) {
    if (blinkClosure(phase) > 0) closed += 1;
  }
  if (closed !== BLINK_DURATION_FRAMES) {
    throw new StickEmotionError("blink duration must be 4 frames");
  }
  const seen = new Set<string>();
  const seenFar = new Set<string>();
  for (const emotion of STICK_EMOTIONS) {
    const row = CHANNELS[emotion];
    assertChannelRange(emotion, row.face, row.posture);
    const near = resolveStickEmotion({ emotion, frame: 30, scale: 1 }).svg;
    const far = resolveStickEmotion({ emotion, frame: 30, scale: 0.4 }).svg;
    if (seen.has(near) || seenFar.has(far)) throw new StickEmotionError(`duplicate rig for ${emotion}`);
    if (near.toLowerCase().includes("filter") || far.toLowerCase().includes("filter")) {
      throw new StickEmotionError(`emotion rig emitted a filtered svg for ${emotion}`);
    }
    seen.add(near);
    seenFar.add(far);
  }
}

function assertChannelRange(emotion: StickEmotion, face: EmotionFaceChannels, posture: EmotionPostureChannels): void {
  const numbers = [
    face.browInner, face.browOuter, face.browAsymmetry, face.eyeOpen, face.gazeX, face.gazeY,
    face.mouthCurve, face.mouthOpen, face.mouthTight, posture.headPitch, posture.headYaw, posture.headRoll,
    posture.shoulderRaise, posture.torsoLean, posture.weightShift, posture.spineCurl,
  ];
  for (const value of numbers) {
    if (!Number.isFinite(value) || value < -1 || value > 1) {
      throw new StickEmotionError(`${emotion} channel out of range`);
    }
  }
  if (face.eyeOpen < 0 || face.mouthOpen < 0 || face.mouthTight < 0 || posture.shoulderRaise < 0 || posture.spineCurl < 0) {
    throw new StickEmotionError(`${emotion} unipolar channel is negative`);
  }
}

validateRig();
