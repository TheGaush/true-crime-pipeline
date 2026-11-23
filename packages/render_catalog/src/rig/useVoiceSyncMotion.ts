/**
 * TTS RMS head-nod and gesture bounce for the stick-figure rig.
 *
 * Samples `VoiceTrackManifest.amplitude_envelope[]` at 30 fps. Nod pitch and
 * gesture bounce scale with that sample during `NARRATION` only. `TWIST_PAD`
 * and `FOIA_AUDIO_SLOT` stay flat at 0, including when a bad envelope still
 * carries energy there. A frame index outside the envelope is also 0.
 *
 * Tasks 106 and 107 own the pose solver and emotion rig. This module imports
 * those files at runtime and does not vendor them:
 *   - `STICK_POSES` from `./StickPoses.ts` (`task/106-stick-figure-14-poses`)
 *   - `./StickEmotions.tsx` (`task/107-stick-figure-10-emotions`)
 *
 * Nod pitch is added to `headTilt` (Task 106: positive tilts forward; slumped
 * is +38, listening is -14). Gesture bounce is added to the shoulder that is
 * already more extended, with `shoulderR` winning a tie so an idle figure
 * pulses the canonical right-facing gesture arm.
 */

export const VOICE_SYNC_FPS = 30;

/** Forward head nod at amplitude 1. A few degrees, not a bow. */
export const MAX_NOD_PITCH_DEG = 4.5;

/** Gesture-joint bounce at amplitude 1. A few degrees, not a new pose. */
export const MAX_GESTURE_BOUNCE_DEG = 6;

export const TASK_106_POSE_MODULE = "StickPoses.ts";
export const TASK_107_EMOTION_MODULE = "StickEmotions.tsx";

export const SILENCE_SEGMENT_KINDS = ["TWIST_PAD", "FOIA_AUDIO_SLOT"] as const;

export type VoiceSyncSegmentKind = "NARRATION" | (typeof SILENCE_SEGMENT_KINDS)[number];

export interface VoiceSyncSegment {
  segment_kind: VoiceSyncSegmentKind | string;
  start_ms: number;
  end_ms: number;
}

/** Structural subset of the segmented `VoiceTrackManifest` contract. */
export interface VoiceSyncManifest {
  total_master_ms?: number;
  segments: readonly VoiceSyncSegment[];
  amplitude_envelope?: readonly number[] | null;
}

/** Pose channels this offset is added to. Task 106 owns the base joint degrees. */
export interface StickRigChannels {
  headTilt: number;
  shoulderL: number;
  shoulderR: number;
}

export type GestureJoint = "shoulderL" | "shoulderR";

export interface VoiceSyncMotion {
  frameIndex: number | null;
  timeMs: number | null;
  segmentKind: VoiceSyncSegmentKind | "NONE";
  /** Envelope sample after the silence lock and the out-of-bounds clamp. */
  amplitude: number;
  nodPitchDeg: number;
  gestureBounceDeg: number;
  /** Shoulder that receives `gestureBounceDeg`. */
  gestureJoint: GestureJoint;
  /** Base `headTilt` plus `nodPitchDeg`. */
  headTilt: number;
  shoulderL: number;
  shoulderR: number;
}

export interface UseVoiceSyncMotionInput {
  manifest: VoiceSyncManifest;
  frame: number;
  rig?: StickRigChannels;
}

/** Rounded envelope index. Non-finite frames do not sample. */
export function voiceSyncFrameIndex(frame: number): number | null {
  if (typeof frame !== "number" || !Number.isFinite(frame)) return null;
  return Math.round(frame);
}

/** Inclusive start of a 30 fps frame, in integer milliseconds. */
export function voiceSyncFrameStartMs(frameIndex: number): number {
  return Math.floor((frameIndex * 1000) / VOICE_SYNC_FPS);
}

function segmentAt(segments: readonly VoiceSyncSegment[], timeMs: number): VoiceSyncSegment | null {
  let found: VoiceSyncSegment | null = null;
  for (const segment of segments) {
    if (segment.start_ms <= timeMs && timeMs < segment.end_ms) found = segment;
  }
  return found;
}

function amplitudeAt(envelope: readonly number[] | null | undefined, index: number): number {
  if (!envelope || index < 0 || index >= envelope.length) return 0;
  const sample = envelope[index];
  if (typeof sample !== "number" || !Number.isFinite(sample) || sample <= 0) return 0;
  if (sample >= 1) return 1;
  return sample;
}

function segmentKindOf(segment: VoiceSyncSegment | null): VoiceSyncSegmentKind | "NONE" {
  if (!segment) return "NONE";
  const kind = segment.segment_kind;
  if (kind === "NARRATION" || kind === "TWIST_PAD" || kind === "FOIA_AUDIO_SLOT") return kind;
  return "NONE";
}

/**
 * Nod and gesture offsets for one frame.
 * Silence pads and out-of-range frames return exact 0, not a clamped neighbor sample.
 */
export function sampleVoiceSyncMotion(
  manifest: VoiceSyncManifest,
  frame: number,
): Omit<VoiceSyncMotion, "gestureJoint" | "headTilt" | "shoulderL" | "shoulderR"> {
  const frameIndex = voiceSyncFrameIndex(frame);
  if (frameIndex === null) {
    return {
      frameIndex: null,
      timeMs: null,
      segmentKind: "NONE",
      amplitude: 0,
      nodPitchDeg: 0,
      gestureBounceDeg: 0,
    };
  }
  const timeMs = voiceSyncFrameStartMs(frameIndex);
  const segment = segmentAt(manifest.segments, timeMs);
  const kind = segmentKindOf(segment);
  const amplitude = kind === "NARRATION" ? amplitudeAt(manifest.amplitude_envelope, frameIndex) : 0;
  return {
    frameIndex,
    timeMs,
    segmentKind: kind,
    amplitude,
    nodPitchDeg: amplitude === 0 ? 0 : amplitude * MAX_NOD_PITCH_DEG,
    gestureBounceDeg: amplitude === 0 ? 0 : amplitude * MAX_GESTURE_BOUNCE_DEG,
  };
}

/** Right arm wins a tie. That is the canonical gesture side in Task 106. */
export function activeGestureJoint(angles: Pick<StickRigChannels, "shoulderL" | "shoulderR">): GestureJoint {
  return Math.abs(angles.shoulderR) >= Math.abs(angles.shoulderL) ? "shoulderR" : "shoulderL";
}

/** Per-frame sampler. Pass `rig` to add the offsets onto Task 106 joint degrees. */
export function useVoiceSyncMotion(input: UseVoiceSyncMotionInput): VoiceSyncMotion {
  const sample = sampleVoiceSyncMotion(input.manifest, input.frame);
  const base: StickRigChannels = input.rig ?? { headTilt: 0, shoulderL: 0, shoulderR: 0 };
  const applied = applyVoiceSyncToRig(base, sample);
  return {
    ...sample,
    gestureJoint: activeGestureJoint(base),
    headTilt: applied.headTilt,
    shoulderL: applied.shoulderL,
    shoulderR: applied.shoulderR,
  };
}

export function applyVoiceSyncToRig<T extends StickRigChannels>(
  rig: T,
  motion: Pick<VoiceSyncMotion, "nodPitchDeg" | "gestureBounceDeg">,
): T {
  const gestureJoint = activeGestureJoint(rig);
  return {
    ...rig,
    headTilt: rig.headTilt + motion.nodPitchDeg,
    shoulderL: rig.shoulderL + (gestureJoint === "shoulderL" ? motion.gestureBounceDeg : 0),
    shoulderR: rig.shoulderR + (gestureJoint === "shoulderR" ? motion.gestureBounceDeg : 0),
  };
}

function rigModuleHref(fileName: string): string {
  return new URL(fileName, import.meta.url).href;
}

async function importRigModule(fileName: string, taskLabel: string): Promise<Record<string, unknown>> {
  const href = rigModuleHref(fileName);
  let loaded: unknown;
  try {
    loaded = await import(href);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${taskLabel} module ${fileName} is not on this branch (${href}): ${message}`);
  }
  if (loaded === null || typeof loaded !== "object") {
    throw new Error(`${taskLabel} module ${fileName} did not export a module namespace`);
  }
  return loaded as Record<string, unknown>;
}

/** Import Task 106 `STICK_POSES`. Does not copy `StickPoses.ts` onto this branch. */
export async function importStickPoses(): Promise<Record<string, unknown>> {
  const loaded = await importRigModule(TASK_106_POSE_MODULE, "Task 106");
  if (!Array.isArray(loaded.STICK_POSES)) {
    throw new Error("Task 106 module StickPoses.ts does not export STICK_POSES");
  }
  return loaded;
}

/** Import Task 107. Does not copy `StickEmotions.tsx` onto this branch. */
export function importStickEmotions(): Promise<Record<string, unknown>> {
  return importRigModule(TASK_107_EMOTION_MODULE, "Task 107");
}

/** Load the pose solver and the emotion rig. Both are parallel dependencies. */
export async function loadStickRigModules(): Promise<{
  poses: Record<string, unknown>;
  emotions: Record<string, unknown>;
}> {
  const [poses, emotions] = await Promise.all([importStickPoses(), importStickEmotions()]);
  return { poses, emotions };
}
