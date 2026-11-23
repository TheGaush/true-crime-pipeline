/**
 * Parametric stick-figure skeleton for `@tc/render_catalog`.
 *
 * Bone lengths are `LOCKED_BONE_RATIOS * scale` and do not change with joint
 * angles or facing. Task 103 owns the stroke boil: this module imports
 * `BoilPath` and does not copy that implementation.
 *
 * Angles are degrees. 0 keeps a bone in its parent rest direction
 * (torso and head point up; arms and legs hang with the torso). Positive
 * degrees rotate toward screen-left in y-down frame space. `facing: "left"`
 * mirrors local x about the pelvis.
 *
 * Safe zone matches the CSS frame: 1920×1080, top 108px, bottom 194px, and
 * the bottom-right 22%×14% end-screen box.
 */

// @ts-expect-error TS2307 — Task 103's ./LineBoilPath.js lands in parallel and is not on this branch.
import { BoilPath } from "./LineBoilPath.js";

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const END_SCREEN_WIDTH_RATIO = 0.22;
export const END_SCREEN_HEIGHT_RATIO = 0.14;

/** 1080p charcoal stroke. Theme color stays `currentColor` (no hex palette). */
export const STICK_STROKE_PX = 9;

/** Circle samples passed to BoilPath. The last point repeats the first. */
export const HEAD_SEGMENTS = 16;

/**
 * Locked lengths at scale 1, in frame pixels.
 * Head diameter is `2 * headRadius`.
 */
export const LOCKED_BONE_RATIOS = Object.freeze({
  headRadius: 22,
  torsoLen: 70,
  upperArm: 36,
  forearm: 32,
  thigh: 46,
  shin: 42,
});

export type BoneRatio = keyof typeof LOCKED_BONE_RATIOS;

export interface BoilPoint {
  x: number;
  y: number;
}

export interface StickJoints {
  torsoDeg: number;
  headDeg: number;
  upperArmLeftDeg: number;
  forearmLeftDeg: number;
  upperArmRightDeg: number;
  forearmRightDeg: number;
  thighLeftDeg: number;
  shinLeftDeg: number;
  thighRightDeg: number;
  shinRightDeg: number;
}

export const DEFAULT_JOINTS: StickJoints = Object.freeze({
  torsoDeg: 0,
  headDeg: 0,
  upperArmLeftDeg: 16,
  forearmLeftDeg: 12,
  upperArmRightDeg: -16,
  forearmRightDeg: -12,
  thighLeftDeg: 8,
  shinLeftDeg: 4,
  thighRightDeg: -8,
  shinRightDeg: -4,
});

export const SOCKET_IDS = [
  "crown",
  "brow",
  "neck",
  "chest",
  "hip",
  "handLeft",
  "handRight",
  "elbowLeft",
  "elbowRight",
  "kneeLeft",
  "kneeRight",
  "ankleLeft",
  "ankleRight",
] as const;

export type SocketId = (typeof SOCKET_IDS)[number];

export const BONE_IDS = [
  "torso",
  "neck",
  "head",
  "upperArmLeft",
  "forearmLeft",
  "upperArmRight",
  "forearmRight",
  "thighLeft",
  "shinLeft",
  "thighRight",
  "shinRight",
] as const;

export type BoneId = (typeof BONE_IDS)[number];

export type Facing = "left" | "right";

export interface StickFigureProps {
  x: number;
  y: number;
  scale?: number;
  facing?: Facing;
  joints?: Partial<StickJoints>;
  seed?: number;
  frame?: number;
  isEndScreen?: boolean;
}

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

export interface StickBone {
  id: BoneId;
  ratio: BoneRatio;
  points: BoilPoint[];
  closed: boolean;
}

export interface SolvedStickFigure {
  requestedScale: number;
  appliedScale: number;
  anchor: BoilPoint;
  facing: Facing;
  joints: StickJoints;
  head: { center: BoilPoint; radius: number };
  bones: StickBone[];
  sockets: Record<SocketId, BoilPoint>;
  safeRect: Rect;
  isEndScreen: boolean;
}

export interface StickElement {
  $$typeof: symbol;
  type: unknown;
  key: string | null;
  ref: null;
  props: Record<string, unknown>;
}

export interface StickFigureNode extends StickElement {
  type: "g";
  solved: SolvedStickFigure;
}

const REACT_ELEMENT = Symbol.for("react.element");
const UP: BoilPoint = { x: 0, y: -1 };
const JOINT_KEYS = Object.keys(DEFAULT_JOINTS) as (keyof StickJoints)[];

export function safeContentRect(
  frameWidth = FRAME_WIDTH,
  frameHeight = FRAME_HEIGHT,
): Rect {
  return {
    left: 0,
    top: SAFE_PADDING_TOP,
    right: frameWidth,
    bottom: frameHeight - SAFE_PADDING_BOTTOM,
  };
}

export function endScreenExclusionRect(
  frameWidth = FRAME_WIDTH,
  frameHeight = FRAME_HEIGHT,
): Rect {
  const width = frameWidth * END_SCREEN_WIDTH_RATIO;
  const height = frameHeight * END_SCREEN_HEIGHT_RATIO;
  return {
    left: frameWidth - width,
    top: frameHeight - height,
    right: frameWidth,
    bottom: frameHeight,
  };
}

/** Minimum translation that moves `bounds` out of `obstacle`. `{0,0}` when they miss. */
export function separateFromRect(bounds: Bounds, obstacle: Rect): BoilPoint {
  const overlapsX = bounds.maxX > obstacle.left && bounds.minX < obstacle.right;
  const overlapsY = bounds.maxY > obstacle.top && bounds.minY < obstacle.bottom;
  if (!overlapsX || !overlapsY) return { x: 0, y: 0 };
  const options = [
    { x: obstacle.left - bounds.maxX, y: 0 },
    { x: obstacle.right - bounds.minX, y: 0 },
    { x: 0, y: obstacle.top - bounds.maxY },
    { x: 0, y: obstacle.bottom - bounds.minY },
  ];
  options.sort((a, b) => Math.hypot(a.x, a.y) - Math.hypot(b.x, b.y));
  return options[0] ?? { x: 0, y: 0 };
}

/** Stable per-bone seed forwarded to BoilPath. Not vertex jitter. */
export function boneSeed(seed: number, boneId: string): number {
  let hash = seed >>> 0;
  for (let i = 0; i < boneId.length; i += 1) {
    hash = Math.imul(hash ^ boneId.charCodeAt(i), 16777619) >>> 0;
  }
  return hash;
}

export function solveStickFigure(props: StickFigureProps): SolvedStickFigure {
  const requested = readRequest(props);
  const safeRect = safeContentRect();
  const appliedScale = fitScale(requested, safeRect);
  const local = layout(appliedScale, requested.joints, requested.facing);
  const localBounds = boundsOf(local);
  let dx = 0;
  let dy = 0;
  if (requested.y + localBounds.minY < safeRect.top) {
    dy = safeRect.top - (requested.y + localBounds.minY);
  }
  if (requested.y + localBounds.maxY + dy > safeRect.bottom) {
    dy = safeRect.bottom - (requested.y + localBounds.maxY);
  }
  if (requested.x + localBounds.minX < safeRect.left) {
    dx = safeRect.left - (requested.x + localBounds.minX);
  }
  if (requested.x + localBounds.maxX + dx > safeRect.right) {
    dx = safeRect.right - (requested.x + localBounds.maxX);
  }
  if (requested.isEndScreen) {
    const placed: Bounds = {
      minX: requested.x + localBounds.minX + dx,
      maxX: requested.x + localBounds.maxX + dx,
      minY: requested.y + localBounds.minY + dy,
      maxY: requested.y + localBounds.maxY + dy,
    };
    const push = separateFromRect(placed, endScreenExclusionRect());
    dx += push.x;
    dy += push.y;
  }
  const anchor = { x: requested.x + dx, y: requested.y + dy };
  const placed = translatePose(local, anchor);
  return {
    requestedScale: requested.scale,
    appliedScale,
    anchor,
    facing: requested.facing,
    joints: requested.joints,
    head: placed.head,
    bones: placed.bones,
    sockets: placed.sockets,
    safeRect,
    isEndScreen: requested.isEndScreen,
  };
}

export function StickFigureGeometry(props: StickFigureProps): StickFigureNode {
  if (typeof BoilPath !== "function") {
    throw new Error("StickFigureGeometry: Task 103 BoilPath export must be a function");
  }
  const solved = solveStickFigure(props);
  const seed = props.seed ?? 1;
  const frame = props.frame ?? 0;
  const children = solved.bones.map((bone) =>
    element(
      BoilPath,
      {
        points: bone.points,
        seed: boneSeed(seed, bone.id),
        closed: bone.closed,
        frame,
        strokeWidth: STICK_STROKE_PX,
        stroke: "currentColor",
        fill: "none",
        boneId: bone.id,
      },
      bone.id,
    ),
  );
  const node = element(
    "g",
    {
      "data-stick-figure": "true",
      "data-applied-scale": String(solved.appliedScale),
      children,
    },
    "stick-figure",
  );
  return { ...node, type: "g", solved };
}

interface Request {
  x: number;
  y: number;
  scale: number;
  facing: Facing;
  joints: StickJoints;
  isEndScreen: boolean;
}

interface LocalPose {
  head: { center: BoilPoint; radius: number };
  bones: StickBone[];
  sockets: Record<SocketId, BoilPoint>;
}

function readRequest(props: StickFigureProps): Request {
  assertFinite("x", props.x);
  assertFinite("y", props.y);
  const scale = props.scale ?? 1;
  assertFinite("scale", scale);
  if (scale <= 0) throw new Error("StickFigureGeometry: scale must be > 0");
  const facing = props.facing ?? "right";
  if (facing !== "left" && facing !== "right") {
    throw new Error('StickFigureGeometry: facing must be "left" or "right"');
  }
  const frame = props.frame ?? 0;
  const seed = props.seed ?? 1;
  assertFinite("frame", frame);
  assertFinite("seed", seed);
  const joints = resolveJoints(props.joints);
  return {
    x: props.x,
    y: props.y,
    scale,
    facing,
    joints,
    isEndScreen: props.isEndScreen === true,
  };
}

function resolveJoints(partial: Partial<StickJoints> | undefined): StickJoints {
  const joints = { ...DEFAULT_JOINTS };
  if (!partial) return joints;
  for (const key of JOINT_KEYS) {
    const value = partial[key];
    if (value === undefined) continue;
    assertFinite(key, value);
    joints[key] = value;
  }
  return joints;
}

function assertFinite(name: string, value: number): void {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`StickFigureGeometry: ${name} must be a finite number`);
  }
}

function fitScale(requested: Request, safeRect: Rect): number {
  const safeW = safeRect.right - safeRect.left;
  const safeH = safeRect.bottom - safeRect.top;
  const slack = 1e-4;
  let applied = requested.scale;
  for (let pass = 0; pass < 4; pass += 1) {
    const bounds = boundsOf(layout(applied, requested.joints, requested.facing));
    const spanX = bounds.maxX - bounds.minX;
    const spanY = bounds.maxY - bounds.minY;
    const fitX = spanX > 0 ? (safeW - slack) / spanX : 1;
    const fitY = spanY > 0 ? (safeH - slack) / spanY : 1;
    const fit = Math.min(1, fitX, fitY);
    if (fit > 1 - 1e-9) break;
    applied *= fit;
  }
  return applied;
}

function layout(scale: number, joints: StickJoints, facing: Facing): LocalPose {
  const radius = LOCKED_BONE_RATIOS.headRadius * scale;
  const torsoLen = LOCKED_BONE_RATIOS.torsoLen * scale;
  const upperArm = LOCKED_BONE_RATIOS.upperArm * scale;
  const forearm = LOCKED_BONE_RATIOS.forearm * scale;
  const thigh = LOCKED_BONE_RATIOS.thigh * scale;
  const shin = LOCKED_BONE_RATIOS.shin * scale;

  const pelvis = { x: 0, y: 0 };
  const torsoDir = rotate(UP, joints.torsoDeg);
  const neck = add(pelvis, mul(torsoDir, torsoLen));
  const headDir = rotate(torsoDir, joints.headDeg);
  const headCenter = add(neck, mul(headDir, radius));
  const downTorso = mul(torsoDir, -1);

  const leftArm = chain(neck, downTorso, joints.upperArmLeftDeg, upperArm, joints.forearmLeftDeg, forearm);
  const rightArm = chain(neck, downTorso, joints.upperArmRightDeg, upperArm, joints.forearmRightDeg, forearm);
  const leftLeg = chain(pelvis, downTorso, joints.thighLeftDeg, thigh, joints.shinLeftDeg, shin);
  const rightLeg = chain(pelvis, downTorso, joints.thighRightDeg, thigh, joints.shinRightDeg, shin);

  const crown = add(headCenter, mul(headDir, radius));
  const chest = midpoint(pelvis, neck);
  const mirror = facing === "left";

  const bones: StickBone[] = [
    bone("torso", "torsoLen", [pelvis, neck], false, mirror),
    bone("neck", "headRadius", [neck, headCenter], false, mirror),
    bone("head", "headRadius", headLoop(headCenter, radius), true, mirror),
    bone("upperArmLeft", "upperArm", leftArm.upper, false, mirror),
    bone("forearmLeft", "forearm", leftArm.lower, false, mirror),
    bone("upperArmRight", "upperArm", rightArm.upper, false, mirror),
    bone("forearmRight", "forearm", rightArm.lower, false, mirror),
    bone("thighLeft", "thigh", leftLeg.upper, false, mirror),
    bone("shinLeft", "shin", leftLeg.lower, false, mirror),
    bone("thighRight", "thigh", rightLeg.upper, false, mirror),
    bone("shinRight", "shin", rightLeg.lower, false, mirror),
  ];

  const sockets: Record<SocketId, BoilPoint> = {
    crown: maybeMirror(crown, mirror),
    brow: maybeMirror(headCenter, mirror),
    neck: maybeMirror(neck, mirror),
    chest: maybeMirror(chest, mirror),
    hip: maybeMirror(pelvis, mirror),
    handLeft: maybeMirror(leftArm.hand, mirror),
    handRight: maybeMirror(rightArm.hand, mirror),
    elbowLeft: maybeMirror(leftArm.elbow, mirror),
    elbowRight: maybeMirror(rightArm.elbow, mirror),
    kneeLeft: maybeMirror(leftLeg.elbow, mirror),
    kneeRight: maybeMirror(rightLeg.elbow, mirror),
    ankleLeft: maybeMirror(leftLeg.hand, mirror),
    ankleRight: maybeMirror(rightLeg.hand, mirror),
  };

  return {
    head: { center: maybeMirror(headCenter, mirror), radius },
    bones,
    sockets,
  };
}

function chain(
  origin: BoilPoint,
  parentDown: BoilPoint,
  upperDeg: number,
  upperLen: number,
  lowerDeg: number,
  lowerLen: number,
): { upper: BoilPoint[]; lower: BoilPoint[]; elbow: BoilPoint; hand: BoilPoint } {
  const upperDir = rotate(parentDown, upperDeg);
  const elbow = add(origin, mul(upperDir, upperLen));
  const lowerDir = rotate(upperDir, lowerDeg);
  const hand = add(elbow, mul(lowerDir, lowerLen));
  return {
    upper: [origin, elbow],
    lower: [elbow, hand],
    elbow,
    hand,
  };
}

function bone(
  id: BoneId,
  ratio: BoneRatio,
  points: BoilPoint[],
  closed: boolean,
  mirror: boolean,
): StickBone {
  const placed = points.map((point) => maybeMirror(point, mirror));
  if (closed && placed.length > 1) {
    const first = placed[0];
    const last = placed[placed.length - 1];
    if (first && last) {
      last.x = first.x;
      last.y = first.y;
    }
  }
  return { id, ratio, points: placed, closed };
}

function headLoop(center: BoilPoint, radius: number): BoilPoint[] {
  const points: BoilPoint[] = [];
  for (let i = 0; i < HEAD_SEGMENTS; i += 1) {
    const angle = (i / HEAD_SEGMENTS) * Math.PI * 2;
    points.push({
      x: center.x + Math.cos(angle) * radius,
      y: center.y + Math.sin(angle) * radius,
    });
  }
  const first = points[0];
  if (!first) return points;
  points.push({ x: first.x, y: first.y });
  return points;
}

function boundsOf(pose: LocalPose): Bounds {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  const push = (point: BoilPoint) => {
    if (point.x < minX) minX = point.x;
    if (point.x > maxX) maxX = point.x;
    if (point.y < minY) minY = point.y;
    if (point.y > maxY) maxY = point.y;
  };
  for (const stickBone of pose.bones) {
    for (const point of stickBone.points) push(point);
  }
  for (const id of SOCKET_IDS) push(pose.sockets[id]);
  const { center, radius } = pose.head;
  push({ x: center.x - radius, y: center.y });
  push({ x: center.x + radius, y: center.y });
  push({ x: center.x, y: center.y - radius });
  push({ x: center.x, y: center.y + radius });
  return { minX, maxX, minY, maxY };
}

function translatePose(pose: LocalPose, anchor: BoilPoint): LocalPose {
  const move = (point: BoilPoint) => add(point, anchor);
  const sockets = {} as Record<SocketId, BoilPoint>;
  for (const id of SOCKET_IDS) sockets[id] = move(pose.sockets[id]);
  return {
    head: { center: move(pose.head.center), radius: pose.head.radius },
    bones: pose.bones.map((stickBone) => ({
      ...stickBone,
      points: stickBone.points.map(move),
    })),
    sockets,
  };
}

function element(type: unknown, props: Record<string, unknown>, key: string): StickElement {
  return {
    $$typeof: REACT_ELEMENT,
    type,
    key,
    ref: null,
    props,
  };
}

function rotate(vector: BoilPoint, deg: number): BoilPoint {
  const rad = (deg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  return {
    x: cos * vector.x - sin * vector.y,
    y: sin * vector.x + cos * vector.y,
  };
}

function add(a: BoilPoint, b: BoilPoint): BoilPoint {
  return { x: a.x + b.x, y: a.y + b.y };
}

function mul(vector: BoilPoint, scalar: number): BoilPoint {
  return { x: vector.x * scalar, y: vector.y * scalar };
}

function midpoint(a: BoilPoint, b: BoilPoint): BoilPoint {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function maybeMirror(point: BoilPoint, mirror: boolean): BoilPoint {
  return mirror ? { x: -point.x, y: point.y } : { x: point.x, y: point.y };
}
