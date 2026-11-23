import { readFileSync } from "node:fs";

import { expect, test, vi } from "vitest";

import {
  BURST_CUE_LIMIT,
  COOLDOWN_MS,
  COOLDOWN_SAMPLES,
  GAIN_UNIT_SCALE,
  MIX_SAMPLE_RATE_HZ,
  MICRO_SFX_ORDER,
  SfxDispatchError,
  TRUE_PEAK_CEILING_DBTP,
  TRUE_PEAK_CEILING_UNITS,
  dispatchMicroSfx,
  exportMicroSfxCues,
  frameToMixSample,
  importedRemotionRoot,
  linearGainUnits,
  listMicroSfx,
  microSfxDefinition,
  msToMixSample,
  resolveRemotionClock,
  type MicroSfxCue,
  type MicroSfxName,
  type MicroSfxTrigger,
} from "../src/sfx/SfxRegistry.ts";

const CLOCK = { fps: 30, width: 1920, height: 1080 } as const;

const MOTIF_CUE = {
  StickmanStage: "typing_tap",
  AudioEvidenceCard: "tape_click",
  RedactedDocReveal: "highlighter_glide",
  FoiaFootageFrame: "radio_squelch",
  Illustrative2KPanZoom: "camera_shutter",
  HeroVideoBridge: "pin_thud",
} as const;

function trigger(cue: MicroSfxName, at: Partial<MicroSfxTrigger> & { sceneId?: string }): MicroSfxTrigger {
  return { cue, sceneId: at.sceneId ?? "scene", ...at };
}

function activeSum(cues: readonly MicroSfxCue[], sample: number): number {
  let sum = 0;
  for (const cue of cues) {
    if (cue.start_sample <= sample && sample < cue.start_sample + cue.duration_samples) {
      sum += cue.gain_units;
    }
  }
  return sum;
}

function assertUnderCeiling(cues: readonly MicroSfxCue[]): void {
  for (const cue of cues) {
    expect(activeSum(cues, cue.start_sample)).toBeLessThanOrEqual(TRUE_PEAK_CEILING_UNITS);
    if (cue.peak_dbtp !== null) expect(cue.peak_dbtp).toBeLessThanOrEqual(TRUE_PEAK_CEILING_DBTP);
  }
}

test("registry lists the eight built-in cues in catalog order", () => {
  expect(MICRO_SFX_ORDER).toEqual([
    "typing_tap",
    "highlighter_glide",
    "camera_shutter",
    "pin_thud",
    "conflict_stamp",
    "tick_sfx",
    "radio_squelch",
    "tape_click",
  ]);
  expect(listMicroSfx().map((item) => item.cue)).toEqual(MICRO_SFX_ORDER);
  for (const cue of MICRO_SFX_ORDER) {
    const definition = microSfxDefinition(cue);
    expect(definition.gainUnits).toBe(linearGainUnits(definition.nominalDbtp));
    expect(definition.gainUnits).toBeLessThan(TRUE_PEAK_CEILING_UNITS);
    expect(definition.durationSamples).toBe(definition.durationMs * (MIX_SAMPLE_RATE_HZ / 1000));
  }
  expect(linearGainUnits(-1)).toBe(891_250_938);
  expect(linearGainUnits(-12)).toBe(251_188_643);
  expect(COOLDOWN_MS).toBe(60);
  expect(COOLDOWN_SAMPLES).toBe(2_880);
  expect(TRUE_PEAK_CEILING_DBTP).toBe(-1);
});

test("places a frame on an integer 48 kHz sample using the 30 fps clock", () => {
  expect(importedRemotionRoot()).toBeUndefined();
  expect(() => resolveRemotionClock()).toThrow(/Task 101 REMOTION_ROOT/);
  expect(resolveRemotionClock(CLOCK)).toEqual(CLOCK);
  expect(() => resolveRemotionClock({ fps: 60, width: 1920, height: 1080 })).toThrow(/30 fps/);

  const dispatched = dispatchMicroSfx(
    MICRO_SFX_ORDER.map((cue, index) => trigger(cue, { sceneId: `s${index}`, frame: (index + 1) * 30 })),
    { clock: CLOCK },
  );
  expect(dispatched.suppressed).toEqual([]);
  expect(dispatched.cues).toHaveLength(8);
  for (const [index, cue] of dispatched.cues.entries()) {
    const frame = (index + 1) * 30;
    expect(cue.cue).toBe(MICRO_SFX_ORDER[index]);
    expect(cue.cue_id).toBe(`s${index}:${cue.cue}:${frame * 1_600}`);
    expect(cue.start_sample).toBe(frame * 1_600);
    expect(cue.start_sample).toBe(frameToMixSample(frame, CLOCK.fps));
    expect(cue.start_frame).toBe(frame);
    expect(cue.sample_rate_hz).toBe(48_000);
    expect(cue.cooldown_ms).toBe(60);
    expect(cue.gain_unit_scale).toBe(GAIN_UNIT_SCALE);
    expect(cue.burst).toBe(false);
    expect(cue.tapered).toBe(false);
    expect(cue.peak_dbtp).toBe(microSfxDefinition(cue.cue).nominalDbtp);
    expect(cue.gain_units).toBe(microSfxDefinition(cue.cue).gainUnits);
  }
  const oneFrame = dispatchMicroSfx([trigger("typing_tap", { frame: 1 })], { clock: CLOCK }).cues[0];
  expect(oneFrame?.start_sample).toBe(1_600);
  expect(oneFrame?.offset_ms).toBeCloseTo(33.333333, 6);
  expect(exportMicroSfxCues(dispatched.cues)).toContain('"start_sample": 48000');
});

test("keeps a 60 ms cue on its sample instead of rounding it to a frame", () => {
  const dispatched = dispatchMicroSfx([trigger("tick_sfx", { offsetMs: 60 })], { clock: CLOCK });
  const cue = dispatched.cues[0];
  expect(cue?.start_sample).toBe(msToMixSample(60));
  expect(cue?.start_sample).toBe(2_880);
  expect(cue?.offset_ms).toBe(60);
  expect(cue?.start_frame).toBe(1);
  expect(frameToMixSample(2, CLOCK.fps)).toBe(3_200);

  expect(() =>
    dispatchMicroSfx([trigger("tick_sfx", { frame: 30, offsetMs: 1001 })], { clock: CLOCK }),
  ).toThrow(/same mix sample/);
  expect(
    dispatchMicroSfx([trigger("tape_click", { frame: 30, offsetMs: 1000, sample: 48_000 })], { clock: CLOCK })
      .cues[0]?.start_sample,
  ).toBe(48_000);
});

test("drops triggers inside the 60 ms cooldown and keeps the boundary", () => {
  const dispatched = dispatchMicroSfx(
    [
      trigger("pin_thud", { sample: 0, sceneId: "board" }),
      trigger("pin_thud", { sample: COOLDOWN_SAMPLES - 1, sceneId: "board" }),
      trigger("pin_thud", { sample: COOLDOWN_SAMPLES, sceneId: "board" }),
    ],
    { clock: CLOCK },
  );
  expect(dispatched.cues.map((cue) => cue.start_sample)).toEqual([0, COOLDOWN_SAMPLES]);
  expect(dispatched.suppressed).toEqual([
    { cue: "pin_thud", scene_id: "board", start_sample: COOLDOWN_SAMPLES - 1, reason: "cooldown" },
  ]);
  const exported = exportMicroSfxCues(dispatched.cues);
  expect(exported).not.toContain('"reason"');
  expect(exported).not.toContain(String(COOLDOWN_SAMPLES - 1));
  expect(exportMicroSfxCues([])).toBe("[]\n");
});

test("same-sample ties follow registry order, then scene id, then input order", () => {
  const dispatched = dispatchMicroSfx(
    [
      trigger("camera_shutter", { frame: 4, sceneId: "b" }),
      trigger("typing_tap", { frame: 4, sceneId: "b" }),
      trigger("typing_tap", { frame: 4, sceneId: "a" }),
      trigger("typing_tap", { frame: 4, sceneId: "a" }),
    ],
    { clock: CLOCK },
  );
  expect(dispatched.cues).toHaveLength(1);
  expect(dispatched.cues[0]).toMatchObject({ cue: "typing_tap", scene_id: "a", start_frame: 4 });
  expect(dispatched.suppressed).toHaveLength(3);
});

test("twelve cues in one second stay at nominal gain", () => {
  const triggers = Array.from({ length: BURST_CUE_LIMIT }, (_, index) =>
    trigger("typing_tap", { offsetMs: index * COOLDOWN_MS, sceneId: "sms" }),
  );
  const dispatched = dispatchMicroSfx(triggers, { clock: CLOCK });
  expect(dispatched.cues).toHaveLength(BURST_CUE_LIMIT);
  expect(dispatched.suppressed).toEqual([]);
  for (const cue of dispatched.cues) {
    expect(cue.burst).toBe(false);
    expect(cue.tapered).toBe(false);
    expect(cue.gain_units).toBe(microSfxDefinition("typing_tap").gainUnits);
  }
  assertUnderCeiling(dispatched.cues);
});

test("a burst above 12 cues/sec tapers gain after the 60 ms cooldown", () => {
  const triggers = Array.from({ length: 13 }, (_, index) =>
    trigger("typing_tap", { offsetMs: index * 50, sceneId: "sms" }),
  );
  const dispatched = dispatchMicroSfx(triggers, { clock: CLOCK });
  const nominal = microSfxDefinition("typing_tap").gainUnits;
  expect(dispatched.cues.map((cue) => cue.start_sample)).toEqual([0, 4_800, 9_600, 14_400, 19_200, 24_000, 28_800]);
  expect(dispatched.suppressed).toHaveLength(6);
  expect(dispatched.cues.map((cue) => cue.burst)).toEqual([true, true, true, true, true, true, true]);
  expect(dispatched.cues.map((cue) => cue.gain_units)).toEqual([
    nominal,
    Number(BigInt(nominal) >> 1n),
    Number(BigInt(nominal) >> 2n),
    Number(BigInt(nominal) >> 3n),
    Number(BigInt(nominal) >> 4n),
    Number(BigInt(nominal) >> 5n),
    Number(BigInt(nominal) >> 6n),
  ]);
  expect(dispatched.cues[0]?.tapered).toBe(false);
  expect(dispatched.cues[1]?.tapered).toBe(true);
  expect(dispatched.cues[1]?.peak_dbtp).toBeLessThan(-12);
  assertUnderCeiling(dispatched.cues);

  const forward = exportMicroSfxCues(dispatched.cues);
  const reversed = exportMicroSfxCues(dispatchMicroSfx([...triggers].reverse(), { clock: CLOCK }).cues);
  expect(reversed).toBe(forward);
});

test("overlapping conflict stamps taper and stay at or below -1.0 dBTP", () => {
  const triggers = Array.from({ length: 17 }, (_, index) =>
    trigger("conflict_stamp", { offsetMs: index * COOLDOWN_MS, sceneId: "split" }),
  );
  const dispatched = dispatchMicroSfx(triggers, { clock: CLOCK });
  const nominal = microSfxDefinition("conflict_stamp").gainUnits;
  expect(dispatched.suppressed).toEqual([]);
  expect(dispatched.cues).toHaveLength(17);
  expect(dispatched.cues.map((cue) => cue.gain_units).slice(0, 5)).toEqual([
    nominal,
    Number(BigInt(nominal) >> 1n),
    Number(BigInt(nominal) >> 2n),
    14_173_281,
    0,
  ]);
  expect(dispatched.cues[3]?.tapered).toBe(true);
  expect(dispatched.cues[3]?.peak_dbtp).toBeLessThanOrEqual(TRUE_PEAK_CEILING_DBTP);
  expect(dispatched.cues[4]?.peak_dbtp).toBeNull();
  assertUnderCeiling(dispatched.cues);
  for (let index = 1; index < dispatched.cues.length; index += 1) {
    const previous = dispatched.cues[index - 1];
    const current = dispatched.cues[index];
    expect(current && previous && current.start_sample - previous.start_sample).toBe(COOLDOWN_SAMPLES);
  }
});

test("five hundred cooldown-spaced cues stay deterministic and under the ceiling", () => {
  const triggers = Array.from({ length: 500 }, (_, index) =>
    trigger(index % 2 === 0 ? "radio_squelch" : "tape_click", {
      sample: index * COOLDOWN_SAMPLES,
      sceneId: "bus",
    }),
  );
  const first = dispatchMicroSfx(triggers, { clock: CLOCK });
  const second = dispatchMicroSfx(triggers, { clock: CLOCK });
  expect(first.cues).toHaveLength(500);
  expect(exportMicroSfxCues(first.cues)).toBe(exportMicroSfxCues(second.cues));
  assertUnderCeiling(first.cues);
  expect(first.cues.every((cue, index) => cue.start_sample === index * COOLDOWN_SAMPLES)).toBe(true);
});

test("golden episode frames become sample offsets at 30 fps", () => {
  const pack = JSON.parse(
    readFileSync(new URL("../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url), "utf8"),
  ) as {
    timeline_spec: {
      fps: number;
      width: number;
      height: number;
      scenes: { scene_id: string; motif_component: keyof typeof MOTIF_CUE; start_frame: number }[];
    };
  };
  expect(pack.timeline_spec.fps).toBe(CLOCK.fps);
  const triggers = pack.timeline_spec.scenes.map((scene) =>
    trigger(MOTIF_CUE[scene.motif_component], { sceneId: scene.scene_id, frame: scene.start_frame }),
  );
  const dispatched = dispatchMicroSfx(triggers, { clock: CLOCK });
  expect(dispatched.suppressed).toEqual([]);
  expect(dispatched.cues.map((cue) => cue.scene_id)).toEqual(pack.timeline_spec.scenes.map((scene) => scene.scene_id));
  for (const [index, cue] of dispatched.cues.entries()) {
    const scene = pack.timeline_spec.scenes[index];
    expect(scene).toBeDefined();
    if (!scene) continue;
    expect(cue.start_sample).toBe(frameToMixSample(scene.start_frame, pack.timeline_spec.fps));
    expect(cue.start_frame).toBe(scene.start_frame);
    expect(cue.cue).toBe(MOTIF_CUE[scene.motif_component]);
    expect(cue.tapered).toBe(false);
  }
});

test("rejects unknown cues, empty scenes, and non-integer times", () => {
  expect(() => dispatchMicroSfx([trigger("whoosh" as MicroSfxName, { frame: 0 })], { clock: CLOCK })).toThrow(
    SfxDispatchError,
  );
  expect(() => dispatchMicroSfx([trigger("tick_sfx", { frame: 0, sceneId: "" })], { clock: CLOCK })).toThrow(
    /sceneId/,
  );
  expect(() => dispatchMicroSfx([trigger("tick_sfx", { frame: 1.5 })], { clock: CLOCK })).toThrow(/frame/);
  expect(() => dispatchMicroSfx([trigger("tick_sfx", { offsetMs: -60 })], { clock: CLOCK })).toThrow(/offsetMs/);
  expect(() => dispatchMicroSfx([trigger("tick_sfx", {})], { clock: CLOCK })).toThrow(/frame, offsetMs, or sample/);
  expect(() => dispatchMicroSfx({} as unknown as MicroSfxTrigger[], { clock: CLOCK })).toThrow(/array/);
});

test("reads Task 101 REMOTION_ROOT when the export is present", async () => {
  vi.resetModules();
  vi.doMock("../src/index.ts", () => ({
    REMOTION_ROOT: { fps: 30, width: 1920, height: 1080 },
  }));
  try {
    const loaded = await import("../src/sfx/SfxRegistry.ts");
    expect(loaded.importedRemotionRoot()).toEqual({ fps: 30, width: 1920, height: 1080 });
    const dispatched = loaded.dispatchMicroSfx([
      { cue: "camera_shutter", sceneId: "exhibit", frame: 2 },
    ]);
    expect(dispatched.cues[0]?.start_sample).toBe(3_200);
    expect(() =>
      loaded.dispatchMicroSfx([{ cue: "camera_shutter", sceneId: "exhibit", frame: 2 }], {
        clock: { fps: 60, width: 1920, height: 1080 },
      }),
    ).toThrow(/30 fps/);
  } finally {
    vi.doUnmock("../src/index.ts");
    vi.resetModules();
  }
});

test("rejects a 60 fps REMOTION_ROOT from the Task 101 module", async () => {
  vi.resetModules();
  vi.doMock("../src/index.ts", () => ({
    REMOTION_ROOT: { fps: 60, width: 1920, height: 1080 },
  }));
  try {
    const loaded = await import("../src/sfx/SfxRegistry.ts");
    expect(() => loaded.dispatchMicroSfx([{ cue: "tape_click", sceneId: "foia", frame: 0 }])).toThrow(
      loaded.SfxDispatchError,
    );
    expect(() => loaded.dispatchMicroSfx([{ cue: "tape_click", sceneId: "foia", frame: 0 }])).toThrow(/60 fps/);
  } finally {
    vi.doUnmock("../src/index.ts");
    vi.resetModules();
  }
});
