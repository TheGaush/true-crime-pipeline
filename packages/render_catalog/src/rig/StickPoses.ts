/**
 * Task 106 — StickFigure 14-pose choreography solver.
 *
 * Local joint angles are canonical right-facing degrees. `travel_axis`
 * `R_TO_L` mirrors with `facing = -1` and does not rewrite the angles.
 * `walk_loop` / `run_loop` stride velocity is signed by that axis
 * (`STATIC` holds phase and velocity at 0). Pose changes blend angles
 * and velocity with a 300ms cubic ease-in-out so the silhouette does not pop.
 */

export const STICK_POSES = [
  "idle",
  "walk_loop",
  "run_loop",
  "pointing",
  "seated",
  "evidence_hold",
  "doorway_entry",
  "listening",
  "writing",
  "phone_call",
  "arms_crossed",
  "handcuffed",
  "kneeling",
  "slumped",
] as const;

export type StickPoseId = (typeof STICK_POSES)[number];

export const STICK_POSE_COUNT = STICK_POSES.length;

export const TRAVEL_AXES = ["L_TO_R", "R_TO_L", "STATIC"] as const;

export type TravelAxis = (typeof TRAVEL_AXES)[number];

export const JOINT_IDS = [
  "torsoLean",
  "headTilt",
  "shoulderL",
  "shoulderR",
  "elbowL",
  "elbowR",
  "hipL",
  "hipR",
  "kneeL",
  "kneeR",
] as const;

export type JointId = (typeof JOINT_IDS)[number];

export type JointAngles = Record<JointId, number>;

/** Cubic pose blend. At 30 fps this is exactly 9 frames. */
export const POSE_TRANSITION_MS = 300;

export const FRAME_RATE_FPS = 30;

export const WALK_SPEED_PX_PER_SEC = 96;

export const RUN_SPEED_PX_PER_SEC = 240;

export const WALK_CYCLE_MS = 800;

export const RUN_CYCLE_MS = 450;

export const WALK_STRIDE_PX = (WALK_SPEED_PX_PER_SEC * WALK_CYCLE_MS) / 1000;

export const RUN_STRIDE_PX = (RUN_SPEED_PX_PER_SEC * RUN_CYCLE_MS) / 1000;

/** Minimum keyframe separation so two pose ids cannot collapse into one silhouette. */
export const MIN_POSE_SEPARATION_DEG = 8;

const POSE_SET: ReadonlySet<string> = new Set(STICK_POSES);
const AXIS_SET: ReadonlySet<string> = new Set(TRAVEL_AXES);

const WALK_AMP = { hip: 22, knee: 28, arm: 18, elbow: 10, torso: 2, head: 1 } as const;
const RUN_AMP = { hip: 36, knee: 48, arm: 32, elbow: 18, torso: 4, head: 2 } as const;

export type StickPoseErrorCode =
  | "UNKNOWN_POSE"
  | "UNKNOWN_TRAVEL_AXIS"
  | "NEGATIVE_TIME"
  | "POSE_COVERAGE";

export class StickPoseError extends Error {
  readonly code: StickPoseErrorCode;

  constructor(code: StickPoseErrorCode, message: string) {
    super(message);
    this.name = "StickPoseError";
    this.code = code;
  }
}

export type PoseSample = {
  pose: StickPoseId;
  travelAxis: TravelAxis;
  facing: 1 | -1;
  phase: number;
  cycleMs: number | null;
  velocityPxPerSec: number;
  angles: JointAngles;
  /** Cubic blend weight toward `pose`. 1 when the pose is settled. */
  transitionT: number;
  transitioning: boolean;
};

export type PoseSolveInput = {
  pose: StickPoseId;
  elapsedMs: number;
  travelAxis?: TravelAxis;
  fromPose?: StickPoseId;
  fromElapsedMs?: number;
};

export type ChoreographyState = {
  pose: StickPoseId;
  travelAxis: TravelAxis;
  elapsedMs: number;
  fromAngles: JointAngles | null;
  fromVelocityPxPerSec: number | null;
};

export function isStickPoseId(value: string): value is StickPoseId {
  return POSE_SET.has(value);
}

export function isTravelAxis(value: string): value is TravelAxis {
  return AXIS_SET.has(value);
}

export function zeroAngles(): JointAngles {
  return {
    torsoLean: 0,
    headTilt: 0,
    shoulderL: 0,
    shoulderR: 0,
    elbowL: 0,
    elbowR: 0,
    hipL: 0,
    hipR: 0,
    kneeL: 0,
    kneeR: 0,
  };
}

export function cloneAngles(angles: JointAngles): JointAngles {
  const copy = zeroAngles();
  for (const id of JOINT_IDS) copy[id] = angles[id];
  return copy;
}

export function maxJointDelta(a: JointAngles, b: JointAngles): number {
  let max = 0;
  for (const id of JOINT_IDS) {
    const delta = Math.abs(a[id] - b[id]);
    if (delta > max) max = delta;
  }
  return max;
}

/** Cubic ease-in-out. End derivatives are 0, which removes the transition pop. */
export function cubicEaseInOut(t: number): number {
  const clamped = t < 0 ? 0 : t > 1 ? 1 : t;
  if (clamped < 0.5) return 4 * clamped * clamped * clamped;
  const tail = -2 * clamped + 2;
  return 1 - (tail * tail * tail) / 2;
}

export function shortestAngleDelta(from: number, to: number): number {
  const delta = to - from;
  if (delta > 180) return delta - 360;
  if (delta < -180) return delta + 360;
  return delta;
}

export function blendAngles(from: JointAngles, to: JointAngles, u: number): JointAngles {
  const out = zeroAngles();
  for (const id of JOINT_IDS) {
    out[id] = from[id] + shortestAngleDelta(from[id], to[id]) * u;
  }
  return out;
}

export function rootDeltaPx(velocityPxPerSec: number, deltaMs: number): number {
  if (!Number.isFinite(velocityPxPerSec) || !Number.isFinite(deltaMs)) {
    throw new StickPoseError("NEGATIVE_TIME", "root delta requires finite velocity and time");
  }
  if (deltaMs < 0) {
    throw new StickPoseError("NEGATIVE_TIME", "root delta time must be >= 0");
  }
  return (velocityPxPerSec * deltaMs) / 1000;
}

export function poseKeyframe(pose: StickPoseId): JointAngles {
  assertStickPoseId(pose);
  return cloneAngles(POSE_KEYFRAMES[pose]);
}

export function findPoseCoverageViolation(
  poses: readonly string[],
  keyframes: Readonly<Record<string, JointAngles>>,
): string | null {
  if (poses.length !== STICK_POSE_COUNT) {
    return `expected ${STICK_POSE_COUNT} poses, found ${poses.length}`;
  }
  if (poses[0] !== "idle" || poses[poses.length - 1] !== "slumped") {
    return "pose enum must run from idle through slumped";
  }
  if (!poses.includes("walk_loop") || !poses.includes("run_loop")) {
    return "pose enum must include walk_loop and run_loop";
  }
  if (new Set(poses).size !== poses.length) return "pose enum contains duplicates";
  for (const pose of poses) {
    const frame = keyframes[pose];
    if (!frame) return `missing keyframe for ${pose}`;
    for (const id of JOINT_IDS) {
      const value = frame[id];
      if (typeof value !== "number" || !Number.isFinite(value)) {
        return `non-finite ${id} on ${pose}`;
      }
    }
  }
  for (let i = 0; i < poses.length; i += 1) {
    const left = poses[i] ?? "";
    const leftFrame = keyframes[left];
    if (!leftFrame) return `missing keyframe for ${left}`;
    for (let j = i + 1; j < poses.length; j += 1) {
      const right = poses[j] ?? "";
      const rightFrame = keyframes[right];
      if (!rightFrame) return `missing keyframe for ${right}`;
      if (maxJointDelta(leftFrame, rightFrame) < MIN_POSE_SEPARATION_DEG) {
        return `${left} and ${right} are closer than ${MIN_POSE_SEPARATION_DEG} degrees`;
      }
    }
  }
  return null;
}

export function assertPoseCoverage(): void {
  const violation = findPoseCoverageViolation(STICK_POSES, POSE_KEYFRAMES);
  if (violation) throw new StickPoseError("POSE_COVERAGE", violation);
}

export function transitionPairs(): ReadonlyArray<readonly [StickPoseId, StickPoseId]> {
  const pairs: Array<readonly [StickPoseId, StickPoseId]> = [];
  for (const from of STICK_POSES) {
    for (const to of STICK_POSES) pairs.push([from, to]);
  }
  return pairs;
}

export function solvePose(input: PoseSolveInput): PoseSample {
  assertStickPoseId(input.pose);
  const travelAxis = input.travelAxis ?? "STATIC";
  assertTravelAxis(travelAxis);
  assertNonNegative(input.elapsedMs, "elapsedMs");
  const destination = evaluatePose(input.pose, travelAxis, input.elapsedMs);
  if (input.fromPose === undefined) return destination;
  assertStickPoseId(input.fromPose);
  const fromElapsedMs = input.fromElapsedMs ?? 0;
  assertNonNegative(fromElapsedMs, "fromElapsedMs");
  if (input.elapsedMs >= POSE_TRANSITION_MS) return destination;
  const source = evaluatePose(input.fromPose, travelAxis, fromElapsedMs);
  const transitionT = cubicEaseInOut(input.elapsedMs / POSE_TRANSITION_MS);
  return {
    ...destination,
    angles: blendAngles(source.angles, destination.angles, transitionT),
    velocityPxPerSec:
      source.velocityPxPerSec + (destination.velocityPxPerSec - source.velocityPxPerSec) * transitionT,
    transitionT,
    transitioning: true,
  };
}

export function initialChoreography(
  pose: StickPoseId = "idle",
  travelAxis: TravelAxis = "STATIC",
): ChoreographyState {
  assertStickPoseId(pose);
  assertTravelAxis(travelAxis);
  return {
    pose,
    travelAxis,
    elapsedMs: 0,
    fromAngles: null,
    fromVelocityPxPerSec: null,
  };
}

export function requestPose(state: ChoreographyState, next: StickPoseId): ChoreographyState {
  assertStickPoseId(next);
  if (next === state.pose) return state;
  const current = sampleChoreography(state);
  return {
    pose: next,
    travelAxis: state.travelAxis,
    elapsedMs: 0,
    fromAngles: cloneAngles(current.angles),
    fromVelocityPxPerSec: current.velocityPxPerSec,
  };
}

export function setTravelAxis(state: ChoreographyState, travelAxis: TravelAxis): ChoreographyState {
  assertTravelAxis(travelAxis);
  if (travelAxis === state.travelAxis) return state;
  return { ...state, travelAxis };
}

export function advanceChoreography(state: ChoreographyState, deltaMs: number): ChoreographyState {
  assertNonNegative(deltaMs, "deltaMs");
  if (deltaMs === 0) return state;
  return { ...state, elapsedMs: state.elapsedMs + deltaMs };
}

export function sampleChoreography(state: ChoreographyState): PoseSample {
  assertStickPoseId(state.pose);
  assertTravelAxis(state.travelAxis);
  assertNonNegative(state.elapsedMs, "elapsedMs");
  const destination = evaluatePose(state.pose, state.travelAxis, state.elapsedMs);
  const fromAngles = state.fromAngles;
  const fromVelocity = state.fromVelocityPxPerSec;
  if (fromAngles === null || fromVelocity === null || state.elapsedMs >= POSE_TRANSITION_MS) {
    return destination;
  }
  const transitionT = cubicEaseInOut(state.elapsedMs / POSE_TRANSITION_MS);
  return {
    ...destination,
    angles: blendAngles(fromAngles, destination.angles, transitionT),
    velocityPxPerSec: fromVelocity + (destination.velocityPxPerSec - fromVelocity) * transitionT,
    transitionT,
    transitioning: true,
  };
}

function assertStickPoseId(value: string): asserts value is StickPoseId {
  if (!isStickPoseId(value)) {
    throw new StickPoseError("UNKNOWN_POSE", `unknown stick pose: ${value}`);
  }
}

function assertTravelAxis(value: string): asserts value is TravelAxis {
  if (!isTravelAxis(value)) {
    throw new StickPoseError("UNKNOWN_TRAVEL_AXIS", `unknown travel axis: ${value}`);
  }
}

function assertNonNegative(value: number, label: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new StickPoseError("NEGATIVE_TIME", `${label} must be a finite time >= 0`);
  }
}

function evaluatePose(pose: StickPoseId, travelAxis: TravelAxis, elapsedMs: number): PoseSample {
  const locomotion = locomotionSpec(pose);
  const sign = travelAxis === "L_TO_R" ? 1 : travelAxis === "R_TO_L" ? -1 : 0;
  const moving = locomotion !== null && sign !== 0;
  const phase = moving ? positiveMod(elapsedMs, locomotion.cycleMs) / locomotion.cycleMs : 0;
  const velocityPxPerSec = moving ? locomotion.speed * sign : 0;
  const angles = moving
    ? addAngles(POSE_KEYFRAMES[pose], loopOffset(pose, phase))
    : cloneAngles(POSE_KEYFRAMES[pose]);
  return {
    pose,
    travelAxis,
    facing: travelAxis === "R_TO_L" ? -1 : 1,
    phase,
    cycleMs: locomotion?.cycleMs ?? null,
    velocityPxPerSec,
    angles,
    transitionT: 1,
    transitioning: false,
  };
}

function locomotionSpec(pose: StickPoseId): { speed: number; cycleMs: number } | null {
  if (pose === "walk_loop") return { speed: WALK_SPEED_PX_PER_SEC, cycleMs: WALK_CYCLE_MS };
  if (pose === "run_loop") return { speed: RUN_SPEED_PX_PER_SEC, cycleMs: RUN_CYCLE_MS };
  return null;
}

function loopOffset(pose: StickPoseId, phase: number): JointAngles {
  const amp = pose === "run_loop" ? RUN_AMP : WALK_AMP;
  const theta = phase * Math.PI * 2;
  const swing = Math.sin(theta);
  const liftL = Math.max(0, swing);
  const liftR = Math.max(0, Math.sin(theta + Math.PI));
  return {
    torsoLean: amp.torso * Math.abs(swing),
    headTilt: amp.head * swing,
    shoulderL: -amp.arm * swing,
    shoulderR: amp.arm * swing,
    elbowL: amp.elbow * liftL,
    elbowR: amp.elbow * liftR,
    hipL: amp.hip * swing,
    hipR: -amp.hip * swing,
    kneeL: amp.knee * liftL,
    kneeR: amp.knee * liftR,
  };
}

function addAngles(base: JointAngles, offset: JointAngles): JointAngles {
  const out = zeroAngles();
  for (const id of JOINT_IDS) out[id] = base[id] + offset[id];
  return out;
}

function positiveMod(value: number, period: number): number {
  const remainder = value % period;
  return remainder < 0 ? remainder + period : remainder;
}

function angles(partial: Partial<JointAngles>): JointAngles {
  const full = zeroAngles();
  for (const id of JOINT_IDS) {
    const value = partial[id];
    if (value !== undefined) full[id] = value;
  }
  return Object.freeze(full);
}

const POSE_KEYFRAMES: { readonly [P in StickPoseId]: JointAngles } = {
  idle: angles({ headTilt: 4, elbowL: 6, elbowR: 6 }),
  walk_loop: angles({
    torsoLean: 8,
    headTilt: 2,
    shoulderL: -8,
    shoulderR: 10,
    elbowL: 18,
    elbowR: 16,
    hipL: 18,
    hipR: -12,
    kneeL: 12,
    kneeR: 22,
  }),
  run_loop: angles({
    torsoLean: 22,
    headTilt: 8,
    shoulderL: -16,
    shoulderR: 18,
    elbowL: 48,
    elbowR: 42,
    hipL: 32,
    hipR: -18,
    kneeL: 28,
    kneeR: 46,
  }),
  pointing: angles({
    torsoLean: 4,
    headTilt: -6,
    shoulderL: 8,
    shoulderR: 118,
    elbowL: 10,
    elbowR: 6,
  }),
  seated: angles({
    torsoLean: 6,
    headTilt: 8,
    shoulderL: 12,
    shoulderR: 12,
    elbowL: 20,
    elbowR: 20,
    hipL: 88,
    hipR: 88,
    kneeL: 92,
    kneeR: 92,
  }),
  evidence_hold: angles({
    torsoLean: 10,
    headTilt: 18,
    shoulderL: 78,
    shoulderR: 82,
    elbowL: 46,
    elbowR: 40,
  }),
  doorway_entry: angles({
    torsoLean: 14,
    shoulderL: 28,
    shoulderR: -18,
    elbowL: 12,
    elbowR: 8,
    hipL: 36,
    hipR: -6,
    kneeL: 48,
    kneeR: 8,
  }),
  listening: angles({
    torsoLean: -6,
    headTilt: -14,
    shoulderL: 42,
    shoulderR: 6,
    elbowL: 96,
    elbowR: 8,
  }),
  writing: angles({
    torsoLean: 20,
    headTilt: 26,
    shoulderL: 36,
    shoulderR: 64,
    elbowL: 54,
    elbowR: 88,
    hipL: 4,
    hipR: 4,
  }),
  phone_call: angles({
    torsoLean: 2,
    headTilt: 10,
    shoulderL: 108,
    shoulderR: 4,
    elbowL: 118,
    elbowR: 8,
  }),
  arms_crossed: angles({
    torsoLean: 3,
    headTilt: 6,
    shoulderL: 62,
    shoulderR: 66,
    elbowL: 108,
    elbowR: 112,
  }),
  handcuffed: angles({
    torsoLean: 4,
    headTilt: 12,
    shoulderL: -28,
    shoulderR: -28,
    elbowL: 72,
    elbowR: 72,
    hipL: 2,
    hipR: 2,
  }),
  kneeling: angles({
    torsoLean: 10,
    headTilt: 8,
    shoulderL: 8,
    shoulderR: 8,
    elbowL: 12,
    elbowR: 12,
    hipL: 96,
    kneeL: 150,
    hipR: 18,
    kneeR: 96,
  }),
  slumped: angles({
    torsoLean: 42,
    headTilt: 38,
    shoulderL: 18,
    shoulderR: 16,
    elbowL: 24,
    elbowR: 22,
    hipL: 16,
    hipR: 14,
    kneeL: 22,
    kneeR: 18,
  }),
};

assertPoseCoverage();
