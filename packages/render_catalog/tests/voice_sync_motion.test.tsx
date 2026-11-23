import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "vitest";

import {
  MAX_GESTURE_BOUNCE_DEG,
  MAX_NOD_PITCH_DEG,
  SILENCE_SEGMENT_KINDS,
  TASK_106_POSE_MODULE,
  TASK_107_EMOTION_MODULE,
  VOICE_SYNC_FPS,
  activeGestureJoint,
  applyVoiceSyncToRig,
  importStickEmotions,
  importStickPoses,
  loadStickRigModules,
  sampleVoiceSyncMotion,
  useVoiceSyncMotion,
  voiceSyncFrameStartMs,
  type VoiceSyncManifest,
  type VoiceSyncSegment,
} from "../src/rig/useVoiceSyncMotion.ts";

const GOLDEN_PACKS = [
  "ep_golden_01_20min",
  "ep_golden_02_2strike_fallback",
  "ep_golden_03_2k_grid_heavy",
] as const;

interface GoldenVoice {
  episode_id: string;
  total_master_ms: number;
  segments: VoiceSyncSegment[];
}

function readJson(relativePath: string): unknown {
  const url = new URL(relativePath, import.meta.url);
  return JSON.parse(readFileSync(url, "utf8")) as unknown;
}

function goldenVoice(packId: string): GoldenVoice {
  const pack = readJson(`../../../fixtures/golden_manifests/${packId}/pack.json`) as {
    voice_track_manifest: GoldenVoice;
  };
  return pack.voice_track_manifest;
}

function contractVector(id: string): VoiceSyncManifest & { total_master_ms: number } {
  const document = readJson("../../../packages/shared_contracts/fixtures/vectors.json") as {
    valid: Array<{ id: string; model: string; canonical: VoiceSyncManifest & { total_master_ms: number } }>;
  };
  const vector = document.valid.find((item) => item.id === id && item.model === "VoiceTrackManifest");
  assert.ok(vector, `missing VoiceTrackManifest vector ${id}`);
  return vector.canonical;
}

function frameCount(totalMasterMs: number): number {
  return Math.round((totalMasterMs * VOICE_SYNC_FPS) / 1000);
}

function segmentAt(segments: readonly VoiceSyncSegment[], timeMs: number): VoiceSyncSegment | null {
  let found: VoiceSyncSegment | null = null;
  for (const segment of segments) {
    if (segment.start_ms <= timeMs && timeMs < segment.end_ms) found = segment;
  }
  return found;
}

/** Narration frames carry `speech`. Silence frames carry 1 so a leak would show up. */
function plantedEnvelope(manifest: VoiceSyncManifest & { total_master_ms: number }, speech: number): number[] {
  const count = frameCount(manifest.total_master_ms);
  const envelope = new Array<number>(count).fill(0);
  for (let index = 0; index < count; index += 1) {
    const segment = segmentAt(manifest.segments, Math.floor((index * 1000) / 30));
    if (!segment) continue;
    envelope[index] = segment.segment_kind === "NARRATION" ? speech : 1;
  }
  return envelope;
}

test("voice_sync_motion stays on the offline zero-spend guard", async () => {
  assert.equal(process.env.GEMINI_API_KEY, undefined);
  assert.equal(process.env.DEEPSEEK_API_KEY, undefined);
  assert.equal(process.env.ELEVENLABS_API_KEY, undefined);
  await assert.rejects(fetch("http://example.com/voice"), /ZERO_SPEND_GUARD/);
});

test("voice_sync_motion keeps the nod and the bounce subtle", () => {
  assert.equal(VOICE_SYNC_FPS, 30);
  assert.equal(MAX_NOD_PITCH_DEG, 4.5);
  assert.equal(MAX_GESTURE_BOUNCE_DEG, 6);
  assert.ok(MAX_NOD_PITCH_DEG <= 8);
  assert.ok(MAX_GESTURE_BOUNCE_DEG <= 8);
  assert.deepEqual([...SILENCE_SEGMENT_KINDS], ["TWIST_PAD", "FOIA_AUDIO_SLOT"]);
});

test("voice_sync_motion scales narration and clamps out-of-bounds frames to 0", () => {
  const canonical = contractVector("v021");
  assert.deepEqual(
    canonical.segments.map((segment) => [segment.segment_kind, segment.start_ms, segment.end_ms]),
    [
      ["NARRATION", 0, 4000],
      ["TWIST_PAD", 4000, 4500],
      ["FOIA_AUDIO_SLOT", 4500, 6500],
    ],
  );
  assert.equal(canonical.total_master_ms, 6500);
  assert.deepEqual(canonical.amplitude_envelope, [0, 0.5, 1]);

  const silent = useVoiceSyncMotion({ manifest: canonical, frame: 0 });
  assert.equal(silent.segmentKind, "NARRATION");
  assert.equal(silent.timeMs, 0);
  assert.equal(silent.amplitude, 0);
  assert.equal(Object.is(silent.nodPitchDeg, 0), true);
  assert.equal(Object.is(silent.gestureBounceDeg, 0), true);

  const half = useVoiceSyncMotion({ manifest: canonical, frame: 1 });
  assert.equal(half.frameIndex, 1);
  assert.equal(half.timeMs, 33);
  assert.equal(half.segmentKind, "NARRATION");
  assert.equal(half.amplitude, 0.5);
  assert.equal(half.nodPitchDeg, 2.25);
  assert.equal(half.gestureBounceDeg, 3);
  assert.equal(half.gestureJoint, "shoulderR");
  assert.equal(half.headTilt, 2.25);
  assert.equal(half.shoulderL, 0);
  assert.equal(half.shoulderR, 3);

  const full = sampleVoiceSyncMotion(canonical, 2);
  assert.equal(full.timeMs, 66);
  assert.equal(full.amplitude, 1);
  assert.equal(full.nodPitchDeg, MAX_NOD_PITCH_DEG);
  assert.equal(full.gestureBounceDeg, MAX_GESTURE_BOUNCE_DEG);

  const rounded = useVoiceSyncMotion({ manifest: canonical, frame: 1.4 });
  assert.equal(rounded.frameIndex, 1);
  assert.equal(rounded.amplitude, 0.5);

  const outOfRange = useVoiceSyncMotion({ manifest: canonical, frame: 2.6 });
  assert.equal(outOfRange.frameIndex, 3);
  assert.equal(outOfRange.segmentKind, "NARRATION");
  assert.equal(outOfRange.timeMs, 100);
  assert.equal(outOfRange.amplitude, 0);
  assert.equal(outOfRange.nodPitchDeg, 0);
  assert.equal(outOfRange.gestureBounceDeg, 0);

  for (const frame of [-1, -10, 10_000, Number.NaN, Number.POSITIVE_INFINITY]) {
    const motion = useVoiceSyncMotion({ manifest: canonical, frame });
    assert.equal(motion.amplitude, 0, `frame ${frame}`);
    assert.equal(motion.nodPitchDeg, 0, `frame ${frame}`);
    assert.equal(motion.gestureBounceDeg, 0, `frame ${frame}`);
  }
  assert.equal(useVoiceSyncMotion({ manifest: canonical, frame: Number.NaN }).frameIndex, null);
});

test("voice_sync_motion locks pads even when the envelope is hot", () => {
  const canonical = contractVector("v021");
  const count = frameCount(canonical.total_master_ms);
  assert.equal(count, 195);
  const envelope = new Array<number>(count).fill(1);
  const manifest: VoiceSyncManifest = { ...canonical, amplitude_envelope: envelope };

  const narration = useVoiceSyncMotion({ manifest, frame: 119 });
  assert.equal(narration.timeMs, 3966);
  assert.equal(narration.segmentKind, "NARRATION");
  assert.equal(narration.amplitude, 1);
  assert.equal(narration.nodPitchDeg, MAX_NOD_PITCH_DEG);

  const padStart = useVoiceSyncMotion({ manifest, frame: 119.5 });
  assert.equal(padStart.frameIndex, 120);
  assert.equal(padStart.timeMs, 4000);
  assert.equal(padStart.segmentKind, "TWIST_PAD");
  assert.equal(Object.is(padStart.amplitude, 0), true);
  assert.equal(Object.is(padStart.nodPitchDeg, 0), true);
  assert.equal(Object.is(padStart.gestureBounceDeg, 0), true);

  const padEnd = useVoiceSyncMotion({ manifest, frame: 134 });
  assert.equal(padEnd.timeMs, 4466);
  assert.equal(padEnd.segmentKind, "TWIST_PAD");
  assert.equal(padEnd.nodPitchDeg, 0);

  const foiaStart = useVoiceSyncMotion({ manifest, frame: 135 });
  assert.equal(foiaStart.timeMs, 4500);
  assert.equal(foiaStart.segmentKind, "FOIA_AUDIO_SLOT");
  assert.equal(foiaStart.gestureBounceDeg, 0);
  assert.equal(foiaStart.amplitude, 0);

  const foiaEnd = useVoiceSyncMotion({ manifest, frame: 194 });
  assert.equal(foiaEnd.timeMs, 6466);
  assert.equal(foiaEnd.segmentKind, "FOIA_AUDIO_SLOT");
  assert.equal(foiaEnd.nodPitchDeg, 0);

  const pastTimeline = useVoiceSyncMotion({
    manifest: { ...manifest, amplitude_envelope: new Array<number>(300).fill(1) },
    frame: 195,
  });
  assert.equal(pastTimeline.timeMs, 6500);
  assert.equal(pastTimeline.segmentKind, "NONE");
  assert.equal(pastTimeline.amplitude, 0);

  const over = useVoiceSyncMotion({
    manifest: { ...canonical, amplitude_envelope: [1.25] },
    frame: 0,
  });
  assert.equal(over.amplitude, 1);
  assert.equal(over.nodPitchDeg, MAX_NOD_PITCH_DEG);

  const corrupt = useVoiceSyncMotion({
    manifest: { ...canonical, amplitude_envelope: [-0.2, Number.NaN, Number.POSITIVE_INFINITY] },
    frame: 0,
  });
  assert.equal(corrupt.amplitude, 0);
  assert.equal(useVoiceSyncMotion({
    manifest: { ...canonical, amplitude_envelope: [-0.2, Number.NaN, Number.POSITIVE_INFINITY] },
    frame: 1,
  }).amplitude, 0);
  assert.equal(useVoiceSyncMotion({
    manifest: { ...canonical, amplitude_envelope: [-0.2, Number.NaN, Number.POSITIVE_INFINITY] },
    frame: 2,
  }).amplitude, 0);
});

test("voice_sync_motion on v2 golden segmented VoiceTrackManifest", () => {
  const signatures: string[] = [];
  for (const packId of GOLDEN_PACKS) {
    const voice = goldenVoice(packId);
    assert.equal(voice.total_master_ms, 1_200_000);
    assert.equal(voice.segments[0]?.start_ms, 0);
    assert.equal(voice.segments.at(-1)?.end_ms, voice.total_master_ms);
    const signature = voice.segments
      .map((segment) => `${segment.segment_kind}:${segment.start_ms}:${segment.end_ms}`)
      .join("|");
    signatures.push(signature);

    const raw = useVoiceSyncMotion({
      manifest: { total_master_ms: voice.total_master_ms, segments: voice.segments },
      frame: 1200,
    });
    assert.equal(raw.timeMs, 40000);
    assert.equal(raw.segmentKind, "NARRATION");
    assert.equal(raw.amplitude, 0);
    assert.equal(raw.nodPitchDeg, 0);
    assert.equal(raw.gestureBounceDeg, 0);

    const envelope = plantedEnvelope(voice, 0.5);
    const manifest: VoiceSyncManifest = {
      total_master_ms: voice.total_master_ms,
      segments: voice.segments,
      amplitude_envelope: envelope,
    };
    const before = envelope.slice();
    for (let index = 0; index < envelope.length; index += 1) {
      const motion = useVoiceSyncMotion({ manifest, frame: index });
      const kind = segmentAt(voice.segments, motion.timeMs ?? -1)?.segment_kind;
      if (kind === "TWIST_PAD" || kind === "FOIA_AUDIO_SLOT") {
        assert.equal(motion.segmentKind, kind, `${packId} frame ${index}`);
        assert.equal(Object.is(motion.amplitude, 0), true, `${packId} frame ${index}`);
        assert.equal(Object.is(motion.nodPitchDeg, 0), true, `${packId} frame ${index}`);
        assert.equal(Object.is(motion.gestureBounceDeg, 0), true, `${packId} frame ${index}`);
      } else if (kind === "NARRATION") {
        assert.equal(motion.segmentKind, "NARRATION", `${packId} frame ${index}`);
        assert.equal(motion.amplitude, 0.5, `${packId} frame ${index}`);
        assert.equal(motion.nodPitchDeg, 2.25, `${packId} frame ${index}`);
        assert.equal(motion.gestureBounceDeg, 3, `${packId} frame ${index}`);
      } else {
        assert.equal(motion.amplitude, 0, `${packId} frame ${index}`);
      }
    }
    assert.deepEqual(envelope, before);

    const foia = useVoiceSyncMotion({ manifest, frame: 1199 });
    assert.equal(foia.timeMs, 39966);
    assert.equal(foia.segmentKind, "FOIA_AUDIO_SLOT");
    assert.equal(foia.nodPitchDeg, 0);
    const narration = useVoiceSyncMotion({ manifest, frame: 1200 });
    assert.equal(narration.timeMs, 40000);
    assert.equal(narration.segmentKind, "NARRATION");
    assert.equal(narration.nodPitchDeg, 2.25);
    const pad = useVoiceSyncMotion({ manifest, frame: 9882 });
    assert.equal(pad.timeMs, 329400);
    assert.equal(pad.segmentKind, "TWIST_PAD");
    assert.equal(pad.gestureBounceDeg, 0);
  }
  assert.equal(signatures[1], signatures[0]);
  assert.equal(signatures[2], signatures[0]);
  assert.equal(voiceSyncFrameStartMs(9882), 329400);
});

test("voice_sync_motion adds offsets onto the pose and emotion rig without mutating it", () => {
  const manifest: VoiceSyncManifest = {
    segments: [
      { segment_kind: "NARRATION", start_ms: 0, end_ms: 1000 },
      { segment_kind: "TWIST_PAD", start_ms: 1000, end_ms: 1500 },
    ],
    amplitude_envelope: [1, 1, 1],
  };
  const pointing = { headTilt: -6, shoulderL: 8, shoulderR: 118, pose: "pointing" };
  const speaking = useVoiceSyncMotion({ manifest, frame: 0, rig: pointing });
  assert.equal(speaking.gestureJoint, "shoulderR");
  assert.equal(speaking.headTilt, -6 + MAX_NOD_PITCH_DEG);
  assert.equal(speaking.shoulderL, 8);
  assert.equal(speaking.shoulderR, 118 + MAX_GESTURE_BOUNCE_DEG);
  assert.equal(pointing.headTilt, -6);
  assert.equal(pointing.shoulderR, 118);

  const phone = { headTilt: 10, shoulderL: 108, shoulderR: 4, pose: "phone_call" };
  const phoneMotion = useVoiceSyncMotion({ manifest, frame: 0, rig: phone });
  assert.equal(activeGestureJoint(phone), "shoulderL");
  assert.equal(phoneMotion.gestureJoint, "shoulderL");
  assert.equal(phoneMotion.headTilt, 10 + MAX_NOD_PITCH_DEG);
  assert.equal(phoneMotion.shoulderL, 108 + MAX_GESTURE_BOUNCE_DEG);
  assert.equal(phoneMotion.shoulderR, 4);
  assert.equal(phone.shoulderL, 108);

  const pad = useVoiceSyncMotion({ manifest, frame: 30, rig: pointing });
  assert.equal(pad.timeMs, 1000);
  assert.equal(pad.segmentKind, "TWIST_PAD");
  assert.equal(pad.headTilt, -6);
  assert.equal(pad.shoulderL, 8);
  assert.equal(pad.shoulderR, 118);

  const composed = applyVoiceSyncToRig(pointing, speaking);
  assert.equal(composed.headTilt, speaking.headTilt);
  assert.equal(composed.shoulderR, speaking.shoulderR);
  assert.equal(composed.pose, "pointing");
  assert.equal(pointing.headTilt, -6);

  const gap = useVoiceSyncMotion({
    manifest: {
      segments: [{ segment_kind: "NARRATION", start_ms: 0, end_ms: 500 }],
      amplitude_envelope: [1, 1, 1],
    },
    frame: 20,
  });
  assert.equal(gap.timeMs, 666);
  assert.equal(gap.segmentKind, "NONE");
  assert.equal(gap.amplitude, 0);
});

test("voice_sync_motion imports task 106 and 107 without vendoring their files", async () => {
  const source = readFileSync(new URL("../src/rig/useVoiceSyncMotion.ts", import.meta.url), "utf8");
  assert.match(source, /StickPoses\.ts/);
  assert.match(source, /STICK_POSES/);
  assert.match(source, /StickEmotions\.tsx/);
  assert.equal(source.includes("feTurbulence"), false);
  assert.equal(TASK_106_POSE_MODULE, "StickPoses.ts");
  assert.equal(TASK_107_EMOTION_MODULE, "StickEmotions.tsx");

  const poseUrl = new URL(`../src/rig/${TASK_106_POSE_MODULE}`, import.meta.url);
  const emotionUrl = new URL(`../src/rig/${TASK_107_EMOTION_MODULE}`, import.meta.url);
  let poseOnBranch = true;
  let emotionOnBranch = true;
  try {
    readFileSync(poseUrl);
  } catch {
    poseOnBranch = false;
  }
  try {
    readFileSync(emotionUrl);
  } catch {
    emotionOnBranch = false;
  }

  if (!poseOnBranch) {
    await assert.rejects(importStickPoses(), /Task 106 module StickPoses\.ts/);
  } else {
    const poses = await importStickPoses();
    assert.equal(typeof poses, "object");
  }
  if (!emotionOnBranch) {
    await assert.rejects(importStickEmotions(), /Task 107 module StickEmotions\.tsx/);
  } else {
    const emotions = await importStickEmotions();
    assert.equal(typeof emotions, "object");
  }
  if (!poseOnBranch || !emotionOnBranch) {
    await assert.rejects(loadStickRigModules(), /Task 10[67] module Stick/);
  } else {
    const rig = await loadStickRigModules();
    assert.equal(typeof rig.poses, "object");
    assert.equal(typeof rig.emotions, "object");
  }
});
