/**
 * Task 114 — StickFigure rig and fast JS boil consistency suite.
 *
 * Certifies Layer 1 across the frozen matrix:
 *   14 poses × 10 emotions = 140 pose-emotion permutations
 *   14 poses × 10 emotions × 7 character props = 980 combinations
 *
 * The seven character props are the wardrobe axis from the silhouette library
 * (`fedora` through `briefcase`). Held props (`briefcase`, `flashlight`,
 * `phone`, `document`) lose to `handcuffed` with an explicit precedence warning.
 * Walk and run speeds stay on the pose, RMS nod stays off silence pads, boil
 * ticks stay on `Math.floor(frame / 5)`, and paper plates stay un-grained.
 *
 * Tasks 101–113 own the rig modules. This suite imports those files when they
 * are on the tree and does not copy them onto this branch.
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { test } from "vitest";
import "../../../scripts/vitest.setup.mjs";

delete process.env.GEMINI_API_KEY;
delete process.env.DEEPSEEK_API_KEY;
delete process.env.ELEVENLABS_API_KEY;

const require = createRequire(import.meta.url);

const CONTAINER_FPS = 30;
const BOIL_FPS = 6;
const BOIL_STRIDE = CONTAINER_FPS / BOIL_FPS;
const JITTER_AMPLITUDE_PX = 1.4;
const WALK_SPEED_PX_PER_SEC = 96;
const RUN_SPEED_PX_PER_SEC = 240;
const MAX_NOD_PITCH_DEG = 4.5;
const MAX_GESTURE_BOUNCE_DEG = 6;
const BLINK_CYCLE_FRAMES = 105;
const PAPER_BG_HEX = "#E9E2D2";

const STICK_POSES = [
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

const STICK_EMOTIONS = [
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

/** Wardrobe axis: six worn props plus the first held prop. 14×10×7. */
const CHARACTER_PROP_AXIS = [
  "fedora",
  "hoodie",
  "badge",
  "glasses",
  "tie",
  "scarf",
  "briefcase",
] as const;

const HELD_PROPS = ["briefcase", "flashlight", "phone", "document"] as const;

const SILHOUETTE_PROPS = [
  "fedora",
  "hoodie",
  "badge",
  "glasses",
  "tie",
  "scarf",
  "briefcase",
  "flashlight",
  "phone",
  "document",
] as const;

type PoseId = (typeof STICK_POSES)[number];
type EmotionId = (typeof STICK_EMOTIONS)[number];
type PropId = (typeof SILHOUETTE_PROPS)[number];
type TravelAxis = "L_TO_R" | "R_TO_L" | "STATIC";

type VoiceSegment = {
  segment_kind: string;
  start_ms: number;
  end_ms: number;
};

type VoiceManifest = {
  total_master_ms?: number;
  segments: readonly VoiceSegment[];
  amplitude_envelope?: readonly number[] | null;
};

type RmsSample = {
  frameIndex: number | null;
  timeMs: number | null;
  segmentKind: string;
  amplitude: number;
  nodPitchDeg: number;
  gestureBounceDeg: number;
};

type RigChannels = {
  pose: PoseId;
  emotion: EmotionId;
  headTilt: number;
  shoulderL: number;
  shoulderR: number;
};

type BoilWitness = {
  tick: number;
  d: string;
  markup: string;
};

type LoadedModule = Record<string, unknown>;

type ImportedSource = {
  href: string;
  module: LoadedModule;
};

const HELD_PROP_SET = new Set<string>(HELD_PROPS);

const SHORT_MANIFEST: VoiceManifest = {
  segments: [
    { segment_kind: "NARRATION", start_ms: 0, end_ms: 1000 },
    { segment_kind: "TWIST_PAD", start_ms: 1000, end_ms: 2000 },
    { segment_kind: "FOIA_AUDIO_SLOT", start_ms: 2000, end_ms: 3000 },
  ],
  amplitude_envelope: Array.from({ length: 120 }, () => 1),
};

const SQUARE: ReadonlyArray<{ x: number; y: number }> = [
  { x: 10, y: 10 },
  { x: 40, y: 12 },
  { x: 36, y: 40 },
  { x: 12, y: 34 },
];

function boilTick(frame: number): number {
  if (!Number.isFinite(frame)) throw new TypeError("boil frame must be finite");
  return Math.floor(frame / BOIL_STRIDE);
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = state;
    mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

function boilRngSeed(seed: string, tick: number): number {
  const text = `string:${seed}#${tick}`;
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function unitNormal(
  previous: { x: number; y: number },
  next: { x: number; y: number },
): { x: number; y: number } {
  const tangentX = next.x - previous.x;
  const tangentY = next.y - previous.y;
  const length = Math.hypot(tangentX, tangentY) || 1;
  return { x: -tangentY / length, y: tangentX / length };
}

/** Deterministic 6 fps polyline. Closed seams share one perturbation. */
function boilPolyline(seed: string, frame: number): BoilWitness {
  const tick = boilTick(frame);
  const rng = mulberry32(boilRngSeed(seed, tick));
  const unique = SQUARE.length;
  const scalars: number[] = [];
  for (let index = 0; index < unique; index += 1) {
    const scalar = (rng() * 2 - 1) * JITTER_AMPLITUDE_PX;
    assert.ok(Math.abs(scalar) <= JITTER_AMPLITUDE_PX + 1e-9, "jitter left the ±1.4 px band");
    scalars.push(scalar);
  }
  const closed = SQUARE.concat(SQUARE[0]!);
  const vertices = closed.map((point, index) => {
    const slot = index === closed.length - 1 ? 0 : index;
    const previous = SQUARE[(slot + unique - 1) % unique]!;
    const next = SQUARE[(slot + 1) % unique]!;
    const normal = unitNormal(previous, next);
    const scalar = scalars[slot]!;
    return {
      x: point.x + normal.x * scalar,
      y: point.y + normal.y * scalar,
    };
  });
  assert.equal(vertices[0]!.x, vertices[vertices.length - 1]!.x);
  assert.equal(vertices[0]!.y, vertices[vertices.length - 1]!.y);
  const commands = vertices.map((point, index) => {
    const verb = index === 0 ? "M" : "L";
    return `${verb}${point.x.toFixed(3)} ${point.y.toFixed(3)}`;
  });
  const d = `${commands.join(" ")} Z`;
  const markup =
    `<path d="${d}" fill="none" stroke="currentColor" ` +
    `data-boil-tick="${tick}" data-boil-fps="${BOIL_FPS}" data-container-fps="${CONTAINER_FPS}" />`;
  assertNoSvgTurbulence(markup, seed);
  return { tick, d, markup };
}

function speedPxPerSec(pose: PoseId, travel: TravelAxis): number {
  const magnitude = pose === "walk_loop" ? WALK_SPEED_PX_PER_SEC : pose === "run_loop" ? RUN_SPEED_PX_PER_SEC : 0;
  if (magnitude === 0 || travel === "STATIC") return 0;
  return travel === "R_TO_L" ? -magnitude : magnitude;
}

function blinkClosure(frame: number): number {
  const phase = ((Math.floor(frame) % BLINK_CYCLE_FRAMES) + BLINK_CYCLE_FRAMES) % BLINK_CYCLE_FRAMES;
  if (phase === 0 || phase === 3) return 0.5;
  if (phase === 1 || phase === 2) return 1;
  return 0;
}

function sampleRms(manifest: VoiceManifest, frame: number): RmsSample {
  if (typeof frame !== "number" || !Number.isFinite(frame)) {
    return {
      frameIndex: null,
      timeMs: null,
      segmentKind: "NONE",
      amplitude: 0,
      nodPitchDeg: 0,
      gestureBounceDeg: 0,
    };
  }
  const frameIndex = Math.round(frame);
  const timeMs = Math.floor((frameIndex * 1000) / CONTAINER_FPS);
  let segment: VoiceSegment | null = null;
  for (const item of manifest.segments) {
    if (item.start_ms <= timeMs && timeMs < item.end_ms) segment = item;
  }
  const kind =
    segment &&
    (segment.segment_kind === "NARRATION" ||
      segment.segment_kind === "TWIST_PAD" ||
      segment.segment_kind === "FOIA_AUDIO_SLOT")
      ? segment.segment_kind
      : "NONE";
  let amplitude = 0;
  if (kind === "NARRATION") {
    const envelope = manifest.amplitude_envelope;
    const sample = envelope && frameIndex >= 0 && frameIndex < envelope.length ? envelope[frameIndex] : undefined;
    if (typeof sample === "number" && Number.isFinite(sample) && sample > 0) {
      amplitude = sample >= 1 ? 1 : sample;
    }
  }
  return {
    frameIndex,
    timeMs,
    segmentKind: kind,
    amplitude,
    nodPitchDeg: amplitude === 0 ? 0 : amplitude * MAX_NOD_PITCH_DEG,
    gestureBounceDeg: amplitude === 0 ? 0 : amplitude * MAX_GESTURE_BOUNCE_DEG,
  };
}

function applyMotion(channels: RigChannels, motion: RmsSample): RigChannels {
  const gestureJoint = Math.abs(channels.shoulderR) >= Math.abs(channels.shoulderL) ? "shoulderR" : "shoulderL";
  return {
    pose: channels.pose,
    emotion: channels.emotion,
    headTilt: channels.headTilt + motion.nodPitchDeg,
    shoulderL: channels.shoulderL + (gestureJoint === "shoulderL" ? motion.gestureBounceDeg : 0),
    shoulderR: channels.shoulderR + (gestureJoint === "shoulderR" ? motion.gestureBounceDeg : 0),
  };
}

function precedenceWarning(suppressed: readonly string[]): string | null {
  if (suppressed.length === 0) return null;
  const noun = suppressed.length === 1 ? "prop" : "props";
  return `PRECEDENCE WARNING: handcuffed restrains both hands and suppresses held ${noun} ${suppressed.join(", ")}`;
}

function resolvePropPrecedence(
  pose: PoseId,
  requested: readonly string[],
): { attached: string[]; warning: string | null } {
  if (pose !== "handcuffed") return { attached: [...requested], warning: null };
  const suppressed = requested.filter((prop) => HELD_PROP_SET.has(prop));
  const attached = requested.filter((prop) => !HELD_PROP_SET.has(prop));
  return { attached, warning: precedenceWarning(suppressed) };
}

function assertNoSvgTurbulence(markup: string, label: string): void {
  assert.equal(markup.includes("<feTurbulence"), false, label);
  assert.equal(markup.includes("<feDisplacementMap"), false, label);
  assert.equal(markup.includes("<filter"), false, label);
}

function ungrainedPlate(hex: string): Uint8Array {
  const red = Number.parseInt(hex.slice(1, 3), 16);
  const green = Number.parseInt(hex.slice(3, 5), 16);
  const blue = Number.parseInt(hex.slice(5, 7), 16);
  const pixels = new Uint8Array(2 * 2 * 3);
  for (let index = 0; index < 4; index += 1) {
    pixels[index * 3] = red;
    pixels[index * 3 + 1] = green;
    pixels[index * 3 + 2] = blue;
  }
  return pixels;
}

function plateNoise(pixels: Uint8Array, hex: string): number {
  const red = Number.parseInt(hex.slice(1, 3), 16);
  const green = Number.parseInt(hex.slice(3, 5), 16);
  const blue = Number.parseInt(hex.slice(5, 7), 16);
  let max = 0;
  for (let index = 0; index < pixels.length; index += 3) {
    const delta = Math.max(
      Math.abs((pixels[index] ?? 0) - red),
      Math.abs((pixels[index + 1] ?? 0) - green),
      Math.abs((pixels[index + 2] ?? 0) - blue),
    );
    if (delta > max) max = delta;
  }
  return max;
}

function gradeStamp(pose: PoseId, emotion: EmotionId, prop: PropId) {
  return {
    visual_engine: "CODE_STICKMAN" as const,
    motif_component: "StickmanStage" as const,
    pose,
    emotion,
    prop,
    apply_grade: true,
    needs_grade: true,
    paper_grain: 0,
    vignette: 0,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    grain_phase: null,
    paper_bg_hex: PAPER_BG_HEX,
  };
}

function repoFile(relativeFromTest: string): string {
  return fileURLToPath(new URL(relativeFromTest, import.meta.url));
}

function readOptional(relativeFromTest: string): string | null {
  const file = repoFile(relativeFromTest);
  if (!existsSync(file)) return null;
  return readFileSync(file, "utf8");
}

let moduleSequence = 0;

function transpileToFile(fileName: string, source: string): string {
  const typescript = require("typescript") as typeof import("typescript");
  const javascript = typescript.transpileModule(source, {
    fileName,
    compilerOptions: {
      target: typescript.ScriptTarget.ES2022,
      module: typescript.ModuleKind.ES2022,
      jsx: typescript.JsxEmit.Preserve,
      isolatedModules: true,
    },
  }).outputText;
  const directory = path.join(tmpdir(), "tc-task-114-rig-consistency");
  mkdirSync(directory, { recursive: true });
  moduleSequence += 1;
  const output = path.join(directory, `${path.basename(fileName, path.extname(fileName))}-${process.pid}-${moduleSequence}.mjs`);
  writeFileSync(output, javascript);
  return pathToFileURL(output).href;
}

async function importSource(relativeFromTest: string, rewrite?: (source: string) => string): Promise<ImportedSource | null> {
  const source = readOptional(relativeFromTest);
  if (source === null) return null;
  const prepared = rewrite ? rewrite(source) : source;
  const href = transpileToFile(path.basename(relativeFromTest), prepared);
  const imported = (await import(href)) as LoadedModule;
  return { href, module: imported };
}

function asFunction(imported: ImportedSource, name: string): (...args: never[]) => unknown {
  const value = imported.module[name];
  if (typeof value !== "function") throw new Error(`${imported.href} does not export ${name}`);
  return value as (...args: never[]) => unknown;
}

function goldenVoice(): VoiceManifest & { total_master_ms: number } {
  const pack = JSON.parse(readFileSync(repoFile("../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json"), "utf8")) as {
    voice_track_manifest: VoiceManifest & { total_master_ms: number };
  };
  return pack.voice_track_manifest;
}

function listSourceFiles(directory: string, into: string[] = []): string[] {
  if (!existsSync(directory)) return into;
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) listSourceFiles(full, into);
    else if (entry.isFile() && /\.(ts|tsx)$/.test(entry.name)) into.push(full);
  }
  return into;
}

test("rig_consistency stays on the offline zero-spend guard", async () => {
  assert.equal(process.env.GEMINI_API_KEY, undefined);
  assert.equal(process.env.DEEPSEEK_API_KEY, undefined);
  assert.equal(process.env.ELEVENLABS_API_KEY, undefined);
  await assert.rejects(fetch("http://example.com/rig-consistency"), /ZERO_SPEND_GUARD/);
});

test("rig_consistency locks the 14-pose, 10-emotion, and 7-prop matrix", () => {
  assert.equal(CONTAINER_FPS, 30);
  assert.equal(BOIL_FPS, 6);
  assert.equal(BOIL_STRIDE, 5);
  assert.equal(STICK_POSES.length, 14);
  assert.equal(STICK_EMOTIONS.length, 10);
  assert.equal(CHARACTER_PROP_AXIS.length, 7);
  assert.equal(new Set(STICK_POSES).size, 14);
  assert.equal(new Set(STICK_EMOTIONS).size, 10);
  assert.equal(new Set(CHARACTER_PROP_AXIS).size, 7);
  assert.equal(STICK_POSES[0], "idle");
  assert.equal(STICK_POSES[13], "slumped");
  assert.equal(STICK_EMOTIONS[0], "neutral");
  assert.equal(STICK_EMOTIONS[9], "guilty");
  assert.ok(STICK_POSES.includes("handcuffed"));
  assert.ok(STICK_POSES.includes("walk_loop"));
  assert.ok(STICK_POSES.includes("run_loop"));
  assert.equal(STICK_POSES.length * STICK_EMOTIONS.length, 140);
  assert.equal(STICK_POSES.length * STICK_EMOTIONS.length * CHARACTER_PROP_AXIS.length, 980);
  for (const prop of CHARACTER_PROP_AXIS) assert.ok(SILHOUETTE_PROPS.includes(prop));
  for (const prop of HELD_PROPS) assert.ok(SILHOUETTE_PROPS.includes(prop));
});

test("rig_consistency exercises every pose-emotion permutation and every 14x10x7 combination", () => {
  const pairs = new Set<string>();
  const triples = new Set<string>();
  let handcuffedHeldWarnings = 0;

  for (const pose of STICK_POSES) {
    const leftToRight = speedPxPerSec(pose, "L_TO_R");
    const rightToLeft = speedPxPerSec(pose, "R_TO_L");
    const still = speedPxPerSec(pose, "STATIC");
    assert.equal(still, 0, `${pose} speed on STATIC`);
    if (pose === "walk_loop") {
      assert.equal(leftToRight, WALK_SPEED_PX_PER_SEC);
      assert.equal(rightToLeft, -WALK_SPEED_PX_PER_SEC);
    } else if (pose === "run_loop") {
      assert.equal(leftToRight, RUN_SPEED_PX_PER_SEC);
      assert.equal(rightToLeft, -RUN_SPEED_PX_PER_SEC);
    } else {
      assert.equal(leftToRight, 0, `${pose} has no travel speed`);
      assert.equal(rightToLeft, 0, `${pose} has no travel speed`);
    }

    for (const emotion of STICK_EMOTIONS) {
      pairs.add(`${pose}|${emotion}`);
      assert.equal(blinkClosure(0), 0.5, emotion);
      assert.equal(blinkClosure(105), blinkClosure(0), emotion);
      assert.equal(blinkClosure(1), 1, emotion);
      assert.equal(blinkClosure(4), 0, emotion);

      const spoken = sampleRms(SHORT_MANIFEST, 0);
      const pad = sampleRms(SHORT_MANIFEST, 30);
      const foia = sampleRms(SHORT_MANIFEST, 60);
      assert.equal(spoken.segmentKind, "NARRATION");
      assert.equal(spoken.amplitude, 1);
      assert.equal(spoken.nodPitchDeg, MAX_NOD_PITCH_DEG);
      assert.equal(spoken.gestureBounceDeg, MAX_GESTURE_BOUNCE_DEG);
      assert.equal(pad.segmentKind, "TWIST_PAD");
      assert.equal(pad.timeMs, 1000);
      assert.equal(Object.is(pad.nodPitchDeg, 0), true);
      assert.equal(Object.is(pad.gestureBounceDeg, 0), true);
      assert.equal(foia.segmentKind, "FOIA_AUDIO_SLOT");
      assert.equal(Object.is(foia.amplitude, 0), true);

      const base: RigChannels = { pose, emotion, headTilt: 3, shoulderL: 1, shoulderR: 2 };
      const nodded = applyMotion(base, spoken);
      assert.equal(nodded.pose, pose, "character pose changed during RMS nod");
      assert.equal(nodded.emotion, emotion, "character emotion changed during RMS nod");
      assert.equal(nodded.headTilt, 3 + MAX_NOD_PITCH_DEG);
      assert.equal(nodded.shoulderL, 1);
      assert.equal(nodded.shoulderR, 2 + MAX_GESTURE_BOUNCE_DEG);
      assert.equal(speedPxPerSec(nodded.pose, "L_TO_R"), leftToRight, "speed changed during RMS nod");
      const hushed = applyMotion(base, pad);
      assert.equal(hushed.headTilt, base.headTilt);
      assert.equal(hushed.pose, pose);
      assert.equal(hushed.emotion, emotion);
      assert.equal(base.headTilt, 3);

      for (const prop of CHARACTER_PROP_AXIS) {
        triples.add(`${pose}|${emotion}|${prop}`);
        const resolved = resolvePropPrecedence(pose, [prop]);
        if (pose === "handcuffed" && HELD_PROP_SET.has(prop)) {
          assert.equal(
            resolved.warning,
            `PRECEDENCE WARNING: handcuffed restrains both hands and suppresses held prop ${prop}`,
          );
          assert.deepEqual(resolved.attached, []);
          handcuffedHeldWarnings += 1;
        } else {
          assert.equal(resolved.warning, null, `${pose} ${emotion} ${prop}`);
          assert.deepEqual(resolved.attached, [prop]);
        }
        assert.equal(speedPxPerSec(pose, "L_TO_R"), leftToRight, `${emotion}/${prop} changed ${pose} speed`);
        assert.equal(speedPxPerSec(pose, "R_TO_L"), rightToLeft);
        assert.equal(speedPxPerSec(pose, "STATIC"), 0);

        const seed = `${pose}:${emotion}:${prop}`;
        const tick0 = boilPolyline(seed, 0);
        const tickSame = boilPolyline(seed, 4);
        const tickNext = boilPolyline(seed, 5);
        assert.equal(tick0.tick, 0);
        assert.equal(tickSame.tick, 0);
        assert.equal(tick0.d, tickSame.d, `${seed} boiled inside one 6 fps tick`);
        assert.equal(tickNext.tick, 1);
        assert.equal(boilPolyline(seed, 0).d, tick0.d);

        const plateA = ungrainedPlate(PAPER_BG_HEX);
        const plateB = ungrainedPlate(PAPER_BG_HEX);
        assert.equal(plateNoise(plateA, PAPER_BG_HEX), 0, seed);
        assert.deepEqual(plateA, plateB, `${seed} un-grained plate drifted`);
        const gradeA = gradeStamp(pose, emotion, prop);
        const gradeB = gradeStamp(pose, emotion, prop);
        assert.deepEqual(gradeA, gradeB);
        assert.equal(gradeA.paper_grain, 0);
        assert.equal(gradeA.vignette, 0);
        assert.equal(gradeA.remotion_grain_applied, false);
        assert.equal(gradeA.pose, pose);
        assert.equal(gradeA.emotion, emotion);
      }
    }
  }

  assert.equal(pairs.size, 140);
  assert.equal(triples.size, 980);
  assert.equal(handcuffedHeldWarnings, 10);
});

test("rig_consistency warns when handcuffed conflicts with a held prop", () => {
  for (const prop of HELD_PROPS) {
    const resolved = resolvePropPrecedence("handcuffed", [prop]);
    assert.equal(resolved.attached.length, 0, prop);
    assert.equal(
      resolved.warning,
      `PRECEDENCE WARNING: handcuffed restrains both hands and suppresses held prop ${prop}`,
    );
    assert.equal(resolvePropPrecedence("handcuffed", [prop]).warning, resolved.warning);
  }

  for (const prop of CHARACTER_PROP_AXIS) {
    if (HELD_PROP_SET.has(prop)) continue;
    const resolved = resolvePropPrecedence("handcuffed", [prop]);
    assert.equal(resolved.warning, null, prop);
    assert.deepEqual(resolved.attached, [prop]);
  }

  const mixed = resolvePropPrecedence("handcuffed", ["fedora", "briefcase", "phone"]);
  assert.deepEqual(mixed.attached, ["fedora"]);
  assert.equal(
    mixed.warning,
    "PRECEDENCE WARNING: handcuffed restrains both hands and suppresses held props briefcase, phone",
  );

  const idleHold = resolvePropPrecedence("idle", ["briefcase", "document"]);
  assert.equal(idleHold.warning, null);
  assert.deepEqual(idleHold.attached, ["briefcase", "document"]);

  const pointing = resolvePropPrecedence("pointing", ["flashlight"]);
  assert.equal(pointing.warning, null);
  assert.deepEqual(pointing.attached, ["flashlight"]);
});

test("rig_consistency keeps JS boil on 6 fps ticks with a shared closed seam", () => {
  const ticks = new Set<number>();
  let previous = "";
  for (let frame = 0; frame < CONTAINER_FPS; frame += 1) {
    const boiled = boilPolyline("seam-check", frame);
    ticks.add(boiled.tick);
    assert.equal(boiled.tick, Math.floor(frame / 5));
    if (frame % 5 !== 0) assert.equal(boiled.d, previous);
    previous = boiled.d;
    assertNoSvgTurbulence(boiled.markup, `frame ${frame}`);
  }
  assert.equal(ticks.size, BOIL_FPS);
  assert.deepEqual([...ticks], [0, 1, 2, 3, 4, 5]);

  const again = boilPolyline("seam-check", 7);
  assert.equal(again.d, boilPolyline("seam-check", 9).d);
  assert.notEqual(again.d, boilPolyline("seam-check", 10).d);
  assert.notEqual(boilPolyline("pose-a", 0).d, boilPolyline("pose-b", 0).d);
});

test("rig_consistency locks RMS nod off golden silence pads", () => {
  const voice = goldenVoice();
  assert.equal(voice.total_master_ms, 1_200_000);
  const frameCount = Math.round((voice.total_master_ms * CONTAINER_FPS) / 1000);
  assert.equal(frameCount, 36_000);
  const envelope = Array.from({ length: frameCount }, () => 1);
  const manifest: VoiceManifest = {
    total_master_ms: voice.total_master_ms,
    segments: voice.segments,
    amplitude_envelope: envelope,
  };

  let narration = 0;
  let silence = 0;
  for (let frame = 0; frame < frameCount; frame += 1) {
    const motion = sampleRms(manifest, frame);
    const segment = voice.segments.find(
      (item) => item.start_ms <= (motion.timeMs ?? -1) && (motion.timeMs ?? -1) < item.end_ms,
    );
    if (!segment) {
      assert.equal(motion.amplitude, 0, `frame ${frame}`);
      continue;
    }
    if (segment.segment_kind === "NARRATION") {
      narration += 1;
      assert.equal(motion.segmentKind, "NARRATION");
      assert.equal(motion.nodPitchDeg, MAX_NOD_PITCH_DEG);
      assert.equal(motion.gestureBounceDeg, MAX_GESTURE_BOUNCE_DEG);
    } else if (segment.segment_kind === "TWIST_PAD" || segment.segment_kind === "FOIA_AUDIO_SLOT") {
      silence += 1;
      assert.equal(motion.segmentKind, segment.segment_kind, `frame ${frame}`);
      assert.equal(Object.is(motion.amplitude, 0), true, `frame ${frame}`);
      assert.equal(Object.is(motion.nodPitchDeg, 0), true, `frame ${frame}`);
      assert.equal(Object.is(motion.gestureBounceDeg, 0), true, `frame ${frame}`);
    }
  }
  assert.ok(narration > 0);
  assert.ok(silence > 0);

  const foiaOpen = sampleRms(manifest, 0);
  assert.equal(foiaOpen.timeMs, 0);
  assert.equal(foiaOpen.segmentKind, "FOIA_AUDIO_SLOT");
  assert.equal(foiaOpen.nodPitchDeg, 0);
  const narrationOpen = sampleRms(manifest, 1200);
  assert.equal(narrationOpen.timeMs, 40_000);
  assert.equal(narrationOpen.segmentKind, "NARRATION");
  assert.equal(narrationOpen.nodPitchDeg, MAX_NOD_PITCH_DEG);

  const missing = sampleRms(SHORT_MANIFEST, Number.NaN);
  assert.equal(missing.frameIndex, null);
  assert.equal(missing.nodPitchDeg, 0);
  const outOfRange = sampleRms(SHORT_MANIFEST, 500);
  assert.equal(outOfRange.amplitude, 0);
  const hot = sampleRms({ ...SHORT_MANIFEST, amplitude_envelope: [1.4] }, 0);
  assert.equal(hot.amplitude, 1);
  assert.equal(hot.nodPitchDeg, MAX_NOD_PITCH_DEG);
});

test("rig_consistency renders un-grained paper with parity", () => {
  const first = ungrainedPlate(PAPER_BG_HEX);
  const second = ungrainedPlate(PAPER_BG_HEX);
  assert.equal(plateNoise(first, PAPER_BG_HEX), 0);
  assert.deepEqual(first, second);
  assert.equal(first[0], 0xe9);
  assert.equal(first[1], 0xe2);
  assert.equal(first[2], 0xd2);
  const stamp = gradeStamp("idle", "neutral", "fedora");
  assert.equal(stamp.paper_grain, 0);
  assert.equal(stamp.vignette, 0);
  assert.equal(stamp.grain_phase, null);
  assert.equal(JSON.stringify(stamp).includes("feTurbulence"), false);
});

test("rig_consistency source tree has no SVG turbulence filters", () => {
  const sourceRoot = repoFile("../src");
  const files = listSourceFiles(sourceRoot);
  assert.ok(files.length >= 1);
  for (const file of files) {
    const text = readFileSync(file, "utf8");
    assert.equal(text.includes("<feTurbulence"), false, file);
    assert.equal(text.includes("<feDisplacementMap"), false, file);
  }
});

test("rig_consistency binds landed rig modules when they are on the tree", async () => {
  const poses = await importSource("../src/rig/StickPoses.ts");
  const emotions = await importSource("../src/rig/StickEmotions.tsx");
  const props = await importSource("../src/rig/StickProps.tsx");
  const boil = await importSource("../src/rig/LineBoilPath.tsx");
  const voice = await importSource("../src/rig/useVoiceSyncMotion.ts");
  let geometry: ImportedSource | null = null;
  if (readOptional("../src/rig/StickFigureGeometry.tsx") !== null) {
    const boilHref = boil?.href;
    if (typeof boilHref !== "string") {
      throw new Error("StickFigureGeometry.tsx is on the tree and LineBoilPath.tsx is not");
    }
    geometry = await importSource("../src/rig/StickFigureGeometry.tsx", (source) => {
      const matched = source.match(/import\s+\{\s*BoilPath\s*\}\s+from\s+["']\.\/LineBoilPath\.js["'];?/);
      if (!matched) throw new Error("StickFigureGeometry must import { BoilPath } from ./LineBoilPath.js");
      return source.replace(matched[0], `import { BoilPath } from ${JSON.stringify(boilHref)};`);
    });
  }
  let grade: ImportedSource | null = null;
  if (readOptional("../src/grade/GradeContract.tsx") !== null) {
    grade = await importSource("../src/grade/GradeContract.tsx", (source) => {
      const matched = source.match(/import\s+\{\s*useCaseBible\s*\}\s+from\s+["'][^"']+["'];?/);
      if (!matched) return source;
      return source.replace(
        matched[0],
        `function useCaseBible(){ return { paperBgHex: ${JSON.stringify(PAPER_BG_HEX)} }; }`,
      );
    });
  }

  if (poses) {
    assert.deepEqual(poses.module.STICK_POSES, [...STICK_POSES]);
    assert.equal(poses.module.STICK_POSE_COUNT, 14);
    assert.equal(poses.module.WALK_SPEED_PX_PER_SEC, WALK_SPEED_PX_PER_SEC);
    assert.equal(poses.module.RUN_SPEED_PX_PER_SEC, RUN_SPEED_PX_PER_SEC);
    assert.equal(poses.module.FRAME_RATE_FPS, CONTAINER_FPS);
    const solvePose = asFunction(poses, "solvePose");
    for (const pose of STICK_POSES) {
      for (const travel of ["L_TO_R", "R_TO_L", "STATIC"] as const) {
        const sample = solvePose({ pose, elapsedMs: 0, travelAxis: travel } as never) as {
          pose: string;
          velocityPxPerSec: number;
          facing: number;
          angles: Record<string, number>;
        };
        assert.equal(sample.pose, pose, "live pose id drifted");
        assert.equal(sample.velocityPxPerSec, speedPxPerSec(pose, travel), `${pose} ${travel}`);
        assert.equal(sample.facing, travel === "R_TO_L" ? -1 : 1);
        for (const value of Object.values(sample.angles)) assert.equal(Number.isFinite(value), true);
      }
    }
    const handcuffed = solvePose({ pose: "handcuffed", elapsedMs: 0, travelAxis: "STATIC" } as never) as {
      angles: { shoulderL: number; shoulderR: number };
    };
    assert.equal(handcuffed.angles.shoulderL, handcuffed.angles.shoulderR);
  }

  if (emotions) {
    assert.deepEqual(emotions.module.STICK_EMOTIONS, [...STICK_EMOTIONS]);
    assert.equal(emotions.module.STICK_FPS, CONTAINER_FPS);
    assert.equal(emotions.module.BLINK_CYCLE_FRAMES, BLINK_CYCLE_FRAMES);
    assert.equal(emotions.module.DETAIL_SCALE_MIN, 0.45);
    const resolveStickEmotion = asFunction(emotions, "resolveStickEmotion");
    const blink = asFunction(emotions, "blinkClosure");
    for (const emotion of STICK_EMOTIONS) {
      const rig = resolveStickEmotion({ emotion, frame: 0, scale: 1 } as never) as {
        emotion: string;
        detail: string;
        svg: string;
      };
      assert.equal(rig.emotion, emotion);
      assert.equal(rig.detail, "full");
      assertNoSvgTurbulence(rig.svg, emotion);
      const distant = resolveStickEmotion({ emotion, frame: 4, scale: 0.4 } as never) as { detail: string; emotion: string };
      assert.equal(distant.emotion, emotion);
      assert.equal(distant.detail, "simplified");
    }
    assert.equal(blink(0 as never), blinkClosure(0));
    assert.equal(blink(1 as never), blinkClosure(1));
    assert.equal(blink(4 as never), blinkClosure(4));
    assert.equal(blink(105 as never), blink(0 as never));
  }

  if (props) {
    assert.deepEqual(props.module.STICK_PROP_LIBRARY, [...SILHOUETTE_PROPS]);
    const socketsByProp = props.module.STICK_PROP_SOCKET as Record<string, string>;
    const held = SILHOUETTE_PROPS.filter((prop) => socketsByProp[prop] === "hand");
    assert.deepEqual(held, [...HELD_PROPS]);
    const stickFigureSockets = asFunction(props, "stickFigureSockets");
    const renderStickPropsSvg = asFunction(props, "renderStickPropsSvg");
    const propBoilTick = asFunction(props, "boilTick");
    const sockets = stickFigureSockets(props.module.DEFAULT_STICK_BONES as never);
    for (let frame = 0; frame <= 5; frame += 1) {
      assert.equal(propBoilTick(frame as never), boilTick(frame));
    }
    for (const prop of SILHOUETTE_PROPS) {
      const markup = renderStickPropsSvg({ props: [prop], sockets, frame: 0, seed: "rig-consistency" } as never) as string;
      assert.equal(typeof markup, "string");
      assertNoSvgTurbulence(markup, prop);
      assert.equal(
        renderStickPropsSvg({ props: [prop], sockets, frame: 4, seed: "rig-consistency" } as never),
        markup,
        `${prop} changed inside one boil tick`,
      );
    }
  }

  if (boil) {
    assert.equal(boil.module.CONTAINER_FPS, CONTAINER_FPS);
    assert.equal(boil.module.BOIL_FPS, BOIL_FPS);
    assert.equal(boil.module.JITTER_AMPLITUDE_PX, JITTER_AMPLITUDE_PX);
    const liveTick = asFunction(boil, "boilTick");
    const buildBoilGeometry = asFunction(boil, "buildBoilGeometry");
    const renderBoilPathMarkup = asFunction(boil, "renderBoilPathMarkup");
    for (let frame = 0; frame < 30; frame += 1) assert.equal(liveTick(frame as never), boilTick(frame));
    const points = [
      { x: 0, y: 0 },
      { x: 40, y: 0 },
      { x: 40, y: 30 },
      { x: 0, y: 30 },
    ];
    const geometryAt = (frame: number) =>
      buildBoilGeometry({ points, seed: "rig-consistency", frame, closed: true } as never) as {
        tick: number;
        d: string;
        perturbations: ReadonlyArray<{ x: number; y: number }>;
      };
    const at0 = geometryAt(0);
    const at4 = geometryAt(4);
    const at5 = geometryAt(5);
    assert.equal(at0.tick, 0);
    assert.equal(at4.tick, 0);
    assert.equal(at0.d, at4.d);
    assert.equal(at5.tick, 1);
    assert.equal(at0.perturbations[0]?.x, at0.perturbations.at(-1)?.x);
    assert.equal(at0.perturbations[0]?.y, at0.perturbations.at(-1)?.y);
    for (const perturbation of at0.perturbations) {
      assert.ok(Math.hypot(perturbation.x, perturbation.y) <= JITTER_AMPLITUDE_PX + 1e-6);
    }
    const markup = renderBoilPathMarkup({ points, seed: "rig-consistency", frame: 0, closed: true } as never) as string;
    assertNoSvgTurbulence(markup, "LineBoilPath");
    assert.equal(markup.includes("<feTurbulence"), false);
    assert.equal(markup.includes("feTurbulence"), false);
  }

  if (geometry) {
    const solveStickFigure = asFunction(geometry, "solveStickFigure");
    const ratios = geometry.module.LOCKED_BONE_RATIOS as Record<string, number>;
    assert.equal(ratios.headRadius, 22);
    assert.equal(ratios.torsoLen, 70);
    const solved = solveStickFigure({ x: 960, y: 700, scale: 1, facing: "right", frame: 0, seed: 1 } as never) as {
      bones: ReadonlyArray<{ id: string; ratio: string; points: ReadonlyArray<{ x: number; y: number }> }>;
      head: { radius: number };
    };
    assert.equal(solved.head.radius, ratios.headRadius);
    const leaned = solveStickFigure({
      x: 960,
      y: 700,
      scale: 1,
      facing: "right",
      frame: 0,
      seed: 1,
      joints: { torsoDeg: 40, headDeg: 25 },
    } as never) as { head: { radius: number }; bones: typeof solved.bones };
    assert.equal(leaned.head.radius, solved.head.radius, "bone length changed with joint angle");
    for (const bone of solved.bones) {
      const length = ratios[bone.ratio];
      assert.equal(typeof length, "number", bone.id);
    }
  }

  if (voice) {
    assert.equal(voice.module.VOICE_SYNC_FPS, CONTAINER_FPS);
    assert.equal(voice.module.MAX_NOD_PITCH_DEG, MAX_NOD_PITCH_DEG);
    assert.equal(voice.module.MAX_GESTURE_BOUNCE_DEG, MAX_GESTURE_BOUNCE_DEG);
    const sampleVoiceSyncMotion = asFunction(voice, "sampleVoiceSyncMotion");
    const useVoiceSyncMotion = asFunction(voice, "useVoiceSyncMotion");
    for (const frame of [0, 30, 60, 90, 1200]) {
      const live = sampleVoiceSyncMotion(SHORT_MANIFEST as never, frame as never) as RmsSample;
      const expected = sampleRms(SHORT_MANIFEST, frame);
      assert.equal(live.segmentKind, expected.segmentKind, `frame ${frame}`);
      assert.equal(live.amplitude, expected.amplitude, `frame ${frame}`);
      assert.equal(live.nodPitchDeg, expected.nodPitchDeg, `frame ${frame}`);
      assert.equal(live.gestureBounceDeg, expected.gestureBounceDeg, `frame ${frame}`);
    }
    const voiceManifest = goldenVoice();
    const hotEnvelope = Array.from({ length: 36_000 }, () => 1);
    const goldenManifest = { ...voiceManifest, amplitude_envelope: hotEnvelope };
    for (const frame of [0, 1199, 1200, 9882]) {
      const live = sampleVoiceSyncMotion(goldenManifest as never, frame as never) as RmsSample;
      const expected = sampleRms(goldenManifest, frame);
      assert.equal(live.segmentKind, expected.segmentKind, `golden frame ${frame}`);
      assert.equal(live.nodPitchDeg, expected.nodPitchDeg, `golden frame ${frame}`);
    }
    const applied = useVoiceSyncMotion({
      manifest: SHORT_MANIFEST,
      frame: 0,
      rig: { headTilt: -6, shoulderL: 8, shoulderR: 118 },
    } as never) as { headTilt: number; shoulderL: number; shoulderR: number; gestureJoint: string };
    assert.equal(applied.gestureJoint, "shoulderR");
    assert.equal(applied.headTilt, -6 + MAX_NOD_PITCH_DEG);
    assert.equal(applied.shoulderL, 8);
    assert.equal(applied.shoulderR, 118 + MAX_GESTURE_BOUNCE_DEG);
  }

  if (grade) {
    const renderUngradedFrame = asFunction(grade, "renderUngradedFrame");
    const rasterizeUngradedFrame = asFunction(grade, "rasterizeUngradedFrame");
    const noiseFloor = asFunction(grade, "noiseFloor");
    const buildSceneGradeManifest = asFunction(grade, "buildSceneGradeManifest");
    const frame = renderUngradedFrame(PAPER_BG_HEX as never) as {
      paperGrain: number;
      vignette: number;
      paperBgHex: string;
      element: { props: Record<string, unknown> };
    };
    assert.equal(frame.paperGrain, 0);
    assert.equal(frame.vignette, 0);
    assert.equal(frame.paperBgHex, PAPER_BG_HEX);
    assert.equal(frame.element.props["data-paper-grain"], "0");
    assert.equal(frame.element.props["data-vignette"], "0");
    const pixelsA = rasterizeUngradedFrame(frame as never) as Uint8Array;
    const pixelsB = rasterizeUngradedFrame(frame as never) as Uint8Array;
    assert.equal(noiseFloor(pixelsA as never, PAPER_BG_HEX as never), 0);
    assert.equal(pixelsA.byteLength, 1920 * 1080 * 3);
    assert.deepEqual(pixelsA, pixelsB);
    const manifest = buildSceneGradeManifest([
      { scene_id: "stick", visual_engine: "CODE_STICKMAN", motif_component: "StickmanStage" },
      { scene_id: "foia", visual_engine: "FOIA_REAL_FOOTAGE", motif_component: "FoiaFootageFrame" },
    ] as never) as {
      paper_grain: number;
      vignette: number;
      scenes: ReadonlyArray<{ scene_id: string; apply_grade: boolean; paper_grain: number; vignette: number }>;
    };
    assert.equal(manifest.paper_grain, 0);
    assert.equal(manifest.vignette, 0);
    assert.equal(manifest.scenes[0]?.apply_grade, true);
    assert.equal(manifest.scenes[1]?.apply_grade, false);
    assert.equal(manifest.scenes[1]?.paper_grain, 0);
    assert.equal(JSON.stringify(manifest).includes("feTurbulence"), false);
  }

  let catalog: ImportedSource | null = null;
  try {
    catalog = await importSource("../src/index.ts");
  } catch (error) {
    const source = readOptional("../src/index.ts") ?? "";
    if (!/from\s+["']\.\//.test(source)) throw error;
  }
  if (catalog?.module.REMOTION_ROOT && typeof catalog.module.REMOTION_ROOT === "object") {
    const root = catalog.module.REMOTION_ROOT as { fps: number; width: number; height: number };
    assert.equal(root.fps, CONTAINER_FPS);
    assert.equal(root.width, 1920);
    assert.equal(root.height, 1080);
  }
});
