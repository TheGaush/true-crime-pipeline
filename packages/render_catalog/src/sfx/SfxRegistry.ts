/**
 * Built-in micro-SFX trigger dispatcher for Agent 6.
 *
 * Timestamps are sample-accurate at the 48 kHz mix rate. A Remotion frame on
 * the Task 101 clock (`1920x1080 @ 30 fps`) lands on an integer sample because
 * `48000 / fps` is an integer. Millisecond triggers from `WordTimestamp` values
 * do too: `48000 / 1000 = 48`.
 *
 * Task 101 owns `REMOTION_ROOT` in `../index.ts`. This module imports that
 * module and reads the export when it is present. It does not copy the parser
 * or the safe-zone frame. Pass `clock` explicitly on branches where Task 101
 * has not landed yet; a clock that disagrees with `REMOTION_ROOT` is rejected.
 *
 * Bursts stricter than 12 cues in any 1 second window keep a 60 ms cooldown
 * (2880 samples) and a gain taper. Overlapping envelopes are summed in integer
 * gain units and clamped so the bus stays at or below -1.0 dBTP.
 */

import * as task101Catalog from "../index.js";

export const MIX_SAMPLE_RATE_HZ = 48_000;
export const COOLDOWN_MS = 60;
export const COOLDOWN_SAMPLES = (COOLDOWN_MS * MIX_SAMPLE_RATE_HZ) / 1_000;
export const BURST_WINDOW_SAMPLES = MIX_SAMPLE_RATE_HZ;
export const BURST_CUE_LIMIT = 12;
export const TRUE_PEAK_CEILING_DBTP = -1;
export const GAIN_UNIT_SCALE = 1_000_000_000;

/**
 * Catalog lock shared with `code-animation-catalog.md` and Task 101
 * `REMOTION_ROOT`. Frame math uses the resolved clock's `fps`, not a second
 * hidden sample stride.
 */
const PUBLISHED_ROOT = { fps: 30, width: 1920, height: 1080 } as const;

const DEFINITION_TABLE = [
  { cue: "typing_tap", durationMs: 40, nominalDbtp: -12 },
  { cue: "highlighter_glide", durationMs: 280, nominalDbtp: -14 },
  { cue: "camera_shutter", durationMs: 90, nominalDbtp: -8 },
  { cue: "pin_thud", durationMs: 140, nominalDbtp: -8 },
  { cue: "conflict_stamp", durationMs: 400, nominalDbtp: -6 },
  { cue: "tick_sfx", durationMs: 30, nominalDbtp: -14 },
  { cue: "radio_squelch", durationMs: 200, nominalDbtp: -10 },
  { cue: "tape_click", durationMs: 55, nominalDbtp: -10 },
] as const;

export type MicroSfxName = (typeof DEFINITION_TABLE)[number]["cue"];

export const MICRO_SFX_ORDER: readonly MicroSfxName[] = DEFINITION_TABLE.map((item) => item.cue);

export type RemotionClock = {
  readonly fps: number;
  readonly width: number;
  readonly height: number;
};

export type MicroSfxDefinition = {
  readonly cue: MicroSfxName;
  readonly durationMs: number;
  readonly durationSamples: number;
  readonly nominalDbtp: number;
  readonly gainUnits: number;
};

export type MicroSfxTrigger = {
  readonly cue: MicroSfxName;
  readonly sceneId: string;
  readonly frame?: number;
  readonly offsetMs?: number;
  readonly sample?: number;
};

export type MicroSfxCue = {
  readonly cue_id: string;
  readonly cue: MicroSfxName;
  readonly scene_id: string;
  readonly start_sample: number;
  readonly sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  readonly start_frame: number;
  readonly offset_ms: number;
  readonly duration_samples: number;
  readonly cooldown_ms: typeof COOLDOWN_MS;
  readonly gain_units: number;
  readonly gain_unit_scale: typeof GAIN_UNIT_SCALE;
  readonly peak_dbtp: number | null;
  readonly burst: boolean;
  readonly tapered: boolean;
};

export type SuppressedMicroSfx = {
  readonly cue: MicroSfxName;
  readonly scene_id: string;
  readonly start_sample: number;
  readonly reason: "cooldown";
};

export type MicroSfxDispatch = {
  readonly cues: readonly MicroSfxCue[];
  readonly suppressed: readonly SuppressedMicroSfx[];
};

export type DispatchOptions = {
  readonly clock?: RemotionClock;
};

export class SfxDispatchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SfxDispatchError";
  }
}

type Task101Module = {
  readonly REMOTION_ROOT?: RemotionClock;
};

type Planned = {
  readonly cue: MicroSfxName;
  readonly sceneId: string;
  readonly sample: number;
  readonly registryIndex: number;
  readonly inputIndex: number;
  burst: boolean;
  burstIndex: number;
  gainUnits: number;
};

const SAMPLES_PER_MS = MIX_SAMPLE_RATE_HZ / 1_000;

const DEFINITIONS: readonly MicroSfxDefinition[] = DEFINITION_TABLE.map((item) => ({
  cue: item.cue,
  durationMs: item.durationMs,
  durationSamples: item.durationMs * SAMPLES_PER_MS,
  nominalDbtp: item.nominalDbtp,
  gainUnits: linearGainUnits(item.nominalDbtp),
}));

const BY_CUE = new Map<MicroSfxName, MicroSfxDefinition>(DEFINITIONS.map((item) => [item.cue, item]));

export const TRUE_PEAK_CEILING_UNITS = linearGainUnits(TRUE_PEAK_CEILING_DBTP);

/** `REMOTION_ROOT` from Task 101 when that branch's export is on the module. */
export function importedRemotionRoot(): RemotionClock | undefined {
  return (task101Catalog as Task101Module).REMOTION_ROOT;
}

export function linearGainUnits(dbtp: number): number {
  if (!Number.isFinite(dbtp) || dbtp > TRUE_PEAK_CEILING_DBTP) {
    throw new SfxDispatchError(`nominal peak ${dbtp} dBTP exceeds ${TRUE_PEAK_CEILING_DBTP} dBTP`);
  }
  return Math.floor(10 ** (dbtp / 20) * GAIN_UNIT_SCALE + 1e-6);
}

export function isMicroSfxName(value: string): value is MicroSfxName {
  return BY_CUE.has(value as MicroSfxName);
}

export function listMicroSfx(): readonly MicroSfxDefinition[] {
  return DEFINITIONS;
}

export function microSfxDefinition(cue: MicroSfxName): MicroSfxDefinition {
  const definition = BY_CUE.get(cue);
  if (!definition) throw new SfxDispatchError(`unknown micro-SFX cue ${cue}`);
  return definition;
}

export function frameToMixSample(frame: number, fps: number): number {
  if (!Number.isInteger(frame) || frame < 0) {
    throw new SfxDispatchError("frame must be a non-negative integer");
  }
  if (!Number.isInteger(fps) || fps <= 0 || MIX_SAMPLE_RATE_HZ % fps !== 0) {
    throw new SfxDispatchError(`mix rate ${MIX_SAMPLE_RATE_HZ} is not an integer number of samples per ${fps} fps frame`);
  }
  return frame * (MIX_SAMPLE_RATE_HZ / fps);
}

export function msToMixSample(offsetMs: number): number {
  if (!Number.isInteger(offsetMs) || offsetMs < 0) {
    throw new SfxDispatchError("offsetMs must be a non-negative integer");
  }
  return offsetMs * SAMPLES_PER_MS;
}

export function resolveRemotionClock(override?: RemotionClock): RemotionClock {
  const imported = importedRemotionRoot();
  if (imported) assertClock(imported, "Task 101 REMOTION_ROOT");
  if (override && imported && !sameClock(override, imported)) {
    throw new SfxDispatchError(
      `clock ${override.width}x${override.height} @ ${override.fps} fps does not match Task 101 REMOTION_ROOT ${imported.width}x${imported.height} @ ${imported.fps} fps`,
    );
  }
  const clock = override ?? imported;
  if (!clock) {
    throw new SfxDispatchError(
      "Task 101 REMOTION_ROOT is not exported from packages/render_catalog/src/index.ts. Pass a 1920x1080 @ 30 fps clock, or merge task/101-remotion-30fps-css-safezone.",
    );
  }
  assertClock(clock, override ? "Remotion clock" : "Task 101 REMOTION_ROOT");
  return { fps: clock.fps, width: clock.width, height: clock.height };
}

export function dispatchMicroSfx(
  triggers: readonly MicroSfxTrigger[],
  options?: DispatchOptions,
): MicroSfxDispatch {
  if (!Array.isArray(triggers)) throw new SfxDispatchError("triggers must be an array");
  const clock = resolveRemotionClock(options?.clock);
  const planned = triggers.map((trigger, inputIndex) => planTrigger(trigger, inputIndex, clock.fps));
  planned.sort(comparePlanned);
  const burst = markBursts(planned);
  for (let index = 0; index < planned.length; index += 1) {
    const item = planned[index];
    if (item) item.burst = burst[index] === true;
  }

  const emitted: Planned[] = [];
  const suppressed: SuppressedMicroSfx[] = [];
  let lastSample: number | null = null;
  for (const item of planned) {
    if (lastSample !== null && item.sample - lastSample < COOLDOWN_SAMPLES) {
      suppressed.push({
        cue: item.cue,
        scene_id: item.sceneId,
        start_sample: item.sample,
        reason: "cooldown",
      });
      continue;
    }
    emitted.push(item);
    lastSample = item.sample;
  }

  let burstIndex = 0;
  for (const item of emitted) {
    if (item.burst) {
      item.burstIndex = burstIndex;
      burstIndex += 1;
    } else {
      item.burstIndex = 0;
      burstIndex = 0;
    }
  }
  assignGains(emitted);

  return {
    cues: emitted.map((item) => toCue(item, clock.fps)),
    suppressed,
  };
}

/** Agent 6 mix list. Suppressed cooldown hits are omitted. Key order is fixed. */
export function exportMicroSfxCues(cues: readonly MicroSfxCue[]): string {
  const rows = cues.map((cue) => ({
    cue_id: cue.cue_id,
    cue: cue.cue,
    scene_id: cue.scene_id,
    start_sample: cue.start_sample,
    sample_rate_hz: cue.sample_rate_hz,
    start_frame: cue.start_frame,
    offset_ms: cue.offset_ms,
    duration_samples: cue.duration_samples,
    cooldown_ms: cue.cooldown_ms,
    gain_units: cue.gain_units,
    gain_unit_scale: cue.gain_unit_scale,
    peak_dbtp: cue.peak_dbtp,
    burst: cue.burst,
    tapered: cue.tapered,
  }));
  return `${JSON.stringify(rows, null, 2)}\n`;
}

function planTrigger(trigger: MicroSfxTrigger, inputIndex: number, fps: number): Planned {
  if (trigger === null || typeof trigger !== "object") {
    throw new SfxDispatchError("trigger must be an object");
  }
  if (typeof trigger.cue !== "string" || !isMicroSfxName(trigger.cue)) {
    throw new SfxDispatchError(`unknown micro-SFX cue ${String(trigger.cue)}`);
  }
  if (typeof trigger.sceneId !== "string" || trigger.sceneId.length === 0 || trigger.sceneId.length > 200) {
    throw new SfxDispatchError("sceneId must be a non-empty string of at most 200 characters");
  }
  const definition = microSfxDefinition(trigger.cue);
  const sample = resolveSample(trigger, fps);
  return {
    cue: trigger.cue,
    sceneId: trigger.sceneId,
    sample,
    registryIndex: MICRO_SFX_ORDER.indexOf(trigger.cue),
    inputIndex,
    burst: false,
    burstIndex: 0,
    gainUnits: definition.gainUnits,
  };
}

function resolveSample(trigger: MicroSfxTrigger, fps: number): number {
  const parts: number[] = [];
  if (trigger.frame !== undefined) parts.push(frameToMixSample(trigger.frame, fps));
  if (trigger.offsetMs !== undefined) parts.push(msToMixSample(trigger.offsetMs));
  if (trigger.sample !== undefined) {
    if (!Number.isInteger(trigger.sample) || trigger.sample < 0) {
      throw new SfxDispatchError("sample must be a non-negative integer");
    }
    parts.push(trigger.sample);
  }
  if (parts.length === 0) throw new SfxDispatchError("trigger needs a frame, offsetMs, or sample");
  const sample = parts[0];
  if (sample === undefined || parts.some((part) => part !== sample)) {
    throw new SfxDispatchError("frame, offsetMs, and sample do not name the same mix sample");
  }
  return sample;
}

function comparePlanned(left: Planned, right: Planned): number {
  if (left.sample !== right.sample) return left.sample - right.sample;
  if (left.registryIndex !== right.registryIndex) return left.registryIndex - right.registryIndex;
  if (left.sceneId !== right.sceneId) return left.sceneId < right.sceneId ? -1 : 1;
  return left.inputIndex - right.inputIndex;
}

function markBursts(items: readonly Planned[]): boolean[] {
  const burst = items.map(() => false);
  let right = 0;
  for (let left = 0; left < items.length; left += 1) {
    if (right < left) right = left;
    const origin = items[left];
    if (!origin) continue;
    while (right + 1 < items.length) {
      const next = items[right + 1];
      if (!next || next.sample - origin.sample >= BURST_WINDOW_SAMPLES) break;
      right += 1;
    }
    if (right - left + 1 > BURST_CUE_LIMIT) {
      for (let index = left; index <= right; index += 1) burst[index] = true;
    }
  }
  return burst;
}

function assignGains(emitted: readonly Planned[]): void {
  const active: { start: number; end: number; units: number }[] = [];
  for (const item of emitted) {
    const definition = microSfxDefinition(item.cue);
    let sum = 0;
    for (const prev of active) {
      if (prev.start <= item.sample && item.sample < prev.end) sum += prev.units;
    }
    const headroom = Math.max(0, TRUE_PEAK_CEILING_UNITS - sum);
    const tapered = item.burst ? shiftGainUnits(definition.gainUnits, item.burstIndex) : definition.gainUnits;
    const units = Math.min(tapered, headroom);
    item.gainUnits = units;
    active.push({ start: item.sample, end: item.sample + definition.durationSamples, units });
  }
}

function shiftGainUnits(units: number, index: number): number {
  if (index <= 0) return units;
  if (index >= 53) return 0;
  return Number(BigInt(units) >> BigInt(index));
}

function toCue(item: Planned, fps: number): MicroSfxCue {
  const definition = microSfxDefinition(item.cue);
  const samplesPerFrame = MIX_SAMPLE_RATE_HZ / fps;
  return {
    cue_id: `${item.sceneId}:${item.cue}:${item.sample}`,
    cue: item.cue,
    scene_id: item.sceneId,
    start_sample: item.sample,
    sample_rate_hz: MIX_SAMPLE_RATE_HZ,
    start_frame: Math.floor(item.sample / samplesPerFrame),
    offset_ms: offsetMsFromSample(item.sample),
    duration_samples: definition.durationSamples,
    cooldown_ms: COOLDOWN_MS,
    gain_units: item.gainUnits,
    gain_unit_scale: GAIN_UNIT_SCALE,
    peak_dbtp: peakDbtp(item.gainUnits, definition),
    burst: item.burst,
    tapered: item.gainUnits !== definition.gainUnits,
  };
}

function offsetMsFromSample(sample: number): number {
  const rate = BigInt(MIX_SAMPLE_RATE_HZ);
  const scaled = BigInt(sample) * 1_000_000_000n;
  const rounded = (scaled + rate / 2n) / rate;
  return Number(rounded) / 1_000_000;
}

function peakDbtp(units: number, definition: MicroSfxDefinition): number | null {
  if (units <= 0) return null;
  if (units === definition.gainUnits) return definition.nominalDbtp;
  return Math.round(20 * Math.log10(units / GAIN_UNIT_SCALE) * 1000) / 1000;
}

function sameClock(left: RemotionClock, right: RemotionClock): boolean {
  return left.fps === right.fps && left.width === right.width && left.height === right.height;
}

function assertClock(clock: RemotionClock, source: string): void {
  if (
    !Number.isInteger(clock.fps) ||
    !Number.isInteger(clock.width) ||
    !Number.isInteger(clock.height) ||
    clock.fps !== PUBLISHED_ROOT.fps ||
    clock.width !== PUBLISHED_ROOT.width ||
    clock.height !== PUBLISHED_ROOT.height
  ) {
    throw new SfxDispatchError(
      `${source} is locked to ${PUBLISHED_ROOT.width}x${PUBLISHED_ROOT.height} @ ${PUBLISHED_ROOT.fps} fps, received ${clock.width}x${clock.height} @ ${clock.fps} fps`,
    );
  }
  if (MIX_SAMPLE_RATE_HZ % clock.fps !== 0) {
    throw new SfxDispatchError(`mix rate ${MIX_SAMPLE_RATE_HZ} is not an integer number of samples per frame`);
  }
}
