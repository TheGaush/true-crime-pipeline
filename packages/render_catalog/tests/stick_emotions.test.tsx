import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, test } from "node:test";

import {
  BLINK_CYCLE_FRAMES,
  BLINK_DURATION_FRAMES,
  BLINK_PERIOD_SEC,
  DETAIL_SCALE_MIN,
  DRAW_SCALE_MIN,
  STICK_EMOTIONS,
  STICK_EMOTION_INK,
  STICK_FPS,
  StickEmotionError,
  StickEmotions,
  assertStickEmotionCoverage,
  blinkClosure,
  blinkPhase,
  isStickEmotion,
  serializeStickEmotion,
  stickEmotionChannels,
} from "../src/rig/StickEmotions.tsx";

const EXPECTED_EMOTIONS = [
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

const EXPECTED_CHANNELS = {
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
} as const;

const OPEN_FRAME = 30;

function rig(emotion: string, frame = OPEN_FRAME, scale?: number, blinkOffsetFrames?: number) {
  return StickEmotions({ emotion, frame, ...(scale === undefined ? {} : { scale }), ...(blinkOffsetFrames === undefined ? {} : { blinkOffsetFrames }) });
}

function features(emotion: string, frame = OPEN_FRAME, scale = 1): string[] {
  return rig(emotion, frame, scale).paths.map((path) => path.feature);
}

function sha(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

describe("stick emotion coverage", () => {
  test("locks ten emotions from neutral through guilty", () => {
    assert.deepEqual(STICK_EMOTIONS, EXPECTED_EMOTIONS);
    assert.equal(STICK_EMOTIONS.length, 10);
    assert.equal(new Set(STICK_EMOTIONS).size, 10);
    assert.equal(STICK_EMOTIONS[0], "neutral");
    assert.equal(STICK_EMOTIONS[9], "guilty");
    assert.doesNotThrow(() => assertStickEmotionCoverage());
    assert.throws(() => assertStickEmotionCoverage(["neutral"]), StickEmotionError);
    assert.throws(() => assertStickEmotionCoverage([...STICK_EMOTIONS].reverse()), StickEmotionError);
  });

  test("rejects emotions outside the enum", () => {
    for (const emotion of STICK_EMOTIONS) assert.equal(isStickEmotion(emotion), true);
    for (const emotion of ["happy", "Neutral", "guilty ", "", "sad"]) {
      assert.equal(isStickEmotion(emotion), false);
      assert.throws(() => rig(emotion), StickEmotionError);
    }
    assert.throws(() => StickEmotions({ emotion: 4 as unknown as string, frame: 0 }), (error: unknown) => {
      assert.ok(error instanceof StickEmotionError);
      assert.match(error.message, /unknown stick emotion/);
      return true;
    });
  });

  test("snapshots base face and posture channels for every emotion", () => {
    const seenFaces = new Set<string>();
    const seenPostures = new Set<string>();
    for (const emotion of EXPECTED_EMOTIONS) {
      const channels = stickEmotionChannels(emotion);
      assert.equal(channels.emotion, emotion);
      assert.deepEqual(channels.face, EXPECTED_CHANNELS[emotion].face);
      assert.deepEqual(channels.posture, EXPECTED_CHANNELS[emotion].posture);
      const faceKey = JSON.stringify(channels.face);
      const postureKey = JSON.stringify(channels.posture);
      assert.equal(seenFaces.has(faceKey), false, emotion);
      assert.equal(seenPostures.has(postureKey), false, emotion);
      seenFaces.add(faceKey);
      seenPostures.add(postureKey);
    }
  });

  test("keeps the investigative posture order", () => {
    const pitch = (emotion: string) => stickEmotionChannels(emotion).posture.headPitch;
    assert.ok(pitch("guilty") > pitch("ashamed"));
    assert.ok(pitch("ashamed") > pitch("grieving"));
    assert.ok(pitch("grieving") > pitch("concerned"));
    assert.ok(pitch("concerned") > pitch("neutral"));
    assert.ok(pitch("neutral") > pitch("attentive"));
    assert.ok(pitch("attentive") > pitch("surprised"));
    assert.ok(pitch("surprised") > pitch("angry"));

    const postures = STICK_EMOTIONS.map((emotion) => stickEmotionChannels(emotion).posture);
    const faces = STICK_EMOTIONS.map((emotion) => stickEmotionChannels(emotion).face);
    assert.equal(Math.max(...postures.map((row) => row.spineCurl)), stickEmotionChannels("guilty").posture.spineCurl);
    assert.equal(Math.max(...postures.map((row) => row.shoulderRaise)), stickEmotionChannels("fearful").posture.shoulderRaise);
    assert.equal(Math.max(...postures.map((row) => row.torsoLean)), stickEmotionChannels("angry").posture.torsoLean);
    assert.equal(Math.min(...postures.map((row) => row.torsoLean)), stickEmotionChannels("fearful").posture.torsoLean);
    assert.equal(Math.max(...faces.map((row) => row.mouthOpen)), stickEmotionChannels("surprised").face.mouthOpen);
    assert.equal(Math.min(...faces.map((row) => row.browInner)), stickEmotionChannels("angry").face.browInner);
    assert.equal(Math.max(...faces.map((row) => row.browAsymmetry)), stickEmotionChannels("skeptical").face.browAsymmetry);
    assert.equal(Math.min(...faces.map((row) => row.gazeY)), stickEmotionChannels("guilty").face.gazeY);
    assert.deepEqual(stickEmotionChannels("neutral").posture, {
      headPitch: 0, headYaw: 0, headRoll: 0, shoulderRaise: 0, torsoLean: 0, weightShift: 0, spineCurl: 0,
    });
  });

  test("returns channel copies", () => {
    const channels = stickEmotionChannels("angry");
    channels.face.browInner = 9;
    channels.posture.headPitch = 9;
    assert.equal(stickEmotionChannels("angry").face.browInner, -0.85);
    assert.equal(stickEmotionChannels("angry").posture.headPitch, -0.2);
  });
});

describe("deterministic 3.5s blinks", () => {
  test("uses a 105-frame cycle at 30 fps", () => {
    assert.equal(STICK_FPS, 30);
    assert.equal(BLINK_PERIOD_SEC, 3.5);
    assert.equal(BLINK_CYCLE_FRAMES, 105);
    assert.equal(BLINK_DURATION_FRAMES, 4);
    assert.equal(BLINK_CYCLE_FRAMES, BLINK_PERIOD_SEC * STICK_FPS);
  });

  test("closes for four frames and holds the rest of the cycle", () => {
    assert.deepEqual(
      [0, 1, 2, 3, 4, 104].map((frame) => blinkClosure(frame)),
      [0.5, 1, 1, 0.5, 0, 0],
    );
    for (const offset of [0, 1, 7, 104, -3, 210]) {
      let closed = 0;
      for (let frame = 0; frame < BLINK_CYCLE_FRAMES; frame += 1) {
        const closure = blinkClosure(frame, offset);
        assert.equal(blinkClosure(frame + BLINK_CYCLE_FRAMES, offset), closure);
        assert.equal(blinkClosure(frame + BLINK_CYCLE_FRAMES * 3, offset), closure);
        assert.ok(closure === 0 || closure === 0.5 || closure === 1);
        if (closure > 0) closed += 1;
      }
      assert.equal(closed, BLINK_DURATION_FRAMES);
    }
    for (let frame = -210; frame <= 420; frame += 1) {
      assert.equal(blinkClosure(frame), blinkClosure(frame + BLINK_CYCLE_FRAMES));
      assert.equal(blinkPhase(frame), blinkPhase(frame + BLINK_CYCLE_FRAMES));
    }
    assert.equal(blinkClosure(1.9), blinkClosure(1));
    assert.equal(blinkPhase(-105), 0);
    assert.equal(blinkClosure(10, 10), blinkClosure(0));
  });

  test("blink changes the eyes and leaves posture channels alone", () => {
    for (const emotion of STICK_EMOTIONS) {
      const open = rig(emotion, OPEN_FRAME);
      const half = rig(emotion, 0);
      const shut = rig(emotion, 1);
      const held = rig(emotion, OPEN_FRAME + 1);
      assert.equal(open.blink.closure, 0);
      assert.equal(half.blink.closure, 0.5);
      assert.equal(shut.blink.closure, 1);
      assert.equal(open.blink.periodSec, 3.5);
      assert.equal(open.blink.periodFrames, 105);
      assert.equal(open.blink.durationFrames, 4);
      assert.deepEqual(open.posture, shut.posture);
      assert.deepEqual(open.posture, stickEmotionChannels(emotion).posture);
      assert.equal(open.face.eyeOpen, stickEmotionChannels(emotion).face.eyeOpen);
      assert.equal(shut.face.eyeOpen, 0);
      assert.equal(half.face.eyeOpen, stickEmotionChannels(emotion).face.eyeOpen * 0.5);
      assert.equal(open.svg, held.svg);
      assert.equal(open.svg, rig(emotion, OPEN_FRAME + BLINK_CYCLE_FRAMES).svg);
      assert.notEqual(open.svg, shut.svg);
      assert.notEqual(half.svg, shut.svg);
      assert.equal(shut.svg, rig(emotion, 2).svg);
      const shutEye = shut.paths.find((path) => path.feature === "eye-left");
      const openEye = open.paths.find((path) => path.feature === "eye-left");
      assert.ok(shutEye && openEye);
      assert.equal(shutEye.d.includes(" H "), true);
      assert.equal(openEye.d.includes(" Q "), true);
    }
  });

  test("an offset shifts the blink without changing its period", () => {
    assert.equal(rig("neutral", 40, 1, 10).svg, rig("neutral", OPEN_FRAME).svg);
    assert.equal(rig("fearful", 10, 1, 10).svg, rig("fearful", 0).svg);
    assert.equal(rig("guilty", 106, 1, 1).blink.phase, rig("guilty", 0).blink.phase);
  });

  test("floors fractional frames and rejects non-finite timing", () => {
    const whole = rig("neutral", OPEN_FRAME);
    const fraction = rig("neutral", OPEN_FRAME + 0.9);
    assert.equal(fraction.svg, whole.svg);
    assert.equal(fraction.frame, OPEN_FRAME + 0.9);
    assert.equal(fraction.blink.phase, OPEN_FRAME);
    assert.throws(() => rig("neutral", Number.NaN), StickEmotionError);
    assert.throws(() => rig("neutral", Number.POSITIVE_INFINITY), StickEmotionError);
    assert.throws(() => StickEmotions({ emotion: "neutral", frame: 0, blinkOffsetFrames: Number.NaN }), StickEmotionError);
    assert.throws(() => blinkClosure(Number.NaN), StickEmotionError);
    assert.throws(() => blinkPhase(0, Number.POSITIVE_INFINITY), StickEmotionError);
  });
});

describe("scale-aware simplification", () => {
  test("keeps detail at 0.45 and drops brows below it", () => {
    assert.equal(DETAIL_SCALE_MIN, 0.45);
    assert.equal(DRAW_SCALE_MIN, 0.05);
    const full = rig("guilty", OPEN_FRAME, 0.45);
    const far = rig("guilty", OPEN_FRAME, 0.449);
    const mirrored = rig("guilty", OPEN_FRAME, -0.449);
    assert.equal(full.detail, "full");
    assert.equal(far.detail, "simplified");
    assert.equal(mirrored.detail, "simplified");
    assert.equal(rig("guilty", OPEN_FRAME, -0.45).detail, "full");
    assert.ok(features("surprised", OPEN_FRAME, 0.45).includes("brow-left"));
    assert.ok(features("surprised", OPEN_FRAME, 0.45).includes("brow-right"));
    assert.ok(features("surprised", OPEN_FRAME, 0.45).includes("mouth-inner"));
    assert.equal(features("surprised", OPEN_FRAME, 0.449).includes("brow-left"), false);
    assert.equal(features("surprised", OPEN_FRAME, 0.449).includes("brow-right"), false);
    assert.equal(features("surprised", OPEN_FRAME, 0.449).includes("mouth-inner"), false);
    assert.deepEqual(far.posture, full.posture);
    assert.equal(far.face.browInner, 0);
    assert.equal(far.face.browOuter, 0);
    assert.equal(far.face.browAsymmetry, 0);
    assert.equal(far.face.mouthOpen, 0);
    assert.equal(far.face.mouthTight, 0);
    assert.equal(far.face.mouthCurve, stickEmotionChannels("guilty").face.mouthCurve * 0.5);
    assert.equal(far.face.gazeY, stickEmotionChannels("guilty").face.gazeY);
    assert.equal(far.face.eyeOpen, full.face.eyeOpen);
    assert.deepEqual(mirrored.paths, far.paths);
    assert.notEqual(mirrored.svg, far.svg);
  });

  test("only surprised and fearful open an inner mouth at full scale", () => {
    for (const emotion of STICK_EMOTIONS) {
      const open = features(emotion);
      assert.deepEqual(open.slice(0, 4), ["spine", "shoulders", "neck", "head"]);
      assert.equal(open.includes("brow-left"), true);
      assert.equal(open.includes("brow-right"), true);
      assert.equal(open.includes("eye-left"), true);
      assert.equal(open.includes("eye-right"), true);
      assert.equal(open.includes("mouth"), true);
      assert.equal(open.includes("mouth-inner"), emotion === "surprised" || emotion === "fearful");
      assert.equal(new Set(open).size, open.length);
      const far = features(emotion, OPEN_FRAME, 0.2);
      assert.deepEqual(far, ["spine", "shoulders", "neck", "head", "eye-left", "eye-right", "mouth"]);
    }
  });

  test("floors a zero scale without collapsing posture", () => {
    const hidden = rig("ashamed", OPEN_FRAME, 0);
    assert.equal(hidden.detail, "simplified");
    assert.equal(hidden.scale, 0);
    assert.equal(hidden.drawScale, DRAW_SCALE_MIN);
    assert.deepEqual(hidden.paths, rig("ashamed", OPEN_FRAME, DRAW_SCALE_MIN).paths);
    assert.notEqual(hidden.svg, rig("neutral", OPEN_FRAME, 0).svg);
    assert.throws(() => rig("neutral", 0, Number.NaN), StickEmotionError);
  });
});

describe("svg snapshots", () => {
  test("draws ten distinct unfiltered rigs", () => {
    const near = new Set<string>();
    const far = new Set<string>();
    const serial = new Set<string>();
    for (const emotion of STICK_EMOTIONS) {
      for (const scale of [0.2, 0.45, 1, 2]) {
        for (const frame of [0, 1, 2, 3, 4, 30, 104, 105]) {
          const drawn = rig(emotion, frame, scale);
          assert.equal(drawn.svg.includes("feTurbulence"), false);
          assert.equal(drawn.svg.includes("feDisplacementMap"), false);
          assert.equal(drawn.svg.includes("<filter"), false);
          assert.equal(drawn.svg.includes("#C92A2A"), false);
          assert.equal(drawn.svg.includes(STICK_EMOTION_INK), true);
          assert.equal(drawn.svg.includes(`data-emotion="${emotion}"`), true);
          assert.equal(drawn.svg.includes('data-rig="stick-emotion"'), true);
          assert.equal(drawn.paths.length, (drawn.svg.match(/data-feature="/g) ?? []).length);
        }
      }
      const open = rig(emotion);
      const distant = rig(emotion, OPEN_FRAME, 0.4);
      assert.equal(near.has(open.svg), false, emotion);
      assert.equal(far.has(distant.svg), false, emotion);
      assert.equal(serial.has(serializeStickEmotion(open)), false, emotion);
      near.add(open.svg);
      far.add(distant.svg);
      serial.add(serializeStickEmotion(open));
      assert.equal(serializeStickEmotion(open), serializeStickEmotion(rig(emotion)));
    }
    assert.equal(near.size, 10);
    assert.equal(far.size, 10);
  });

  test("byte snapshots of the open, shut, and distant rigs", () => {
    const actual = {
      open: Object.fromEntries(STICK_EMOTIONS.map((emotion) => [emotion, sha(rig(emotion).svg)])),
      shut: sha(rig("neutral", 1).svg),
      distantGuilty: sha(rig("guilty", OPEN_FRAME, 0.4).svg),
    };
    assert.deepEqual(actual, SNAPSHOTS);
  });

  test("source stays free of svg filter primitives and network calls", () => {
    const source = readFileSync(new URL("../src/rig/StickEmotions.tsx", import.meta.url), "utf8");
    assert.equal(source.includes("feTurbulence"), false);
    assert.equal(source.includes("feDisplacementMap"), false);
    assert.equal(source.includes("<filter"), false);
    assert.equal(source.includes("Math.random"), false);
    assert.equal(source.includes("fetch("), false);
    assert.equal(source.includes("GEMINI_API_KEY"), false);
  });

  test("keeps the neck above the spine for every emotion", () => {
    for (const emotion of STICK_EMOTIONS) {
      const neck = rig(emotion).paths.find((path) => path.feature === "neck");
      assert.ok(neck, emotion);
      const coords = neck.d.match(/-?\d+\.\d+/g)?.map(Number) ?? [];
      assert.equal(coords.length, 4, emotion);
      assert.ok((coords[3] ?? 0) <= (coords[1] ?? 0), emotion);
    }
  });

  test("does not mutate the caller props", () => {
    const props = { emotion: "angry", frame: 4, scale: 1, blinkOffsetFrames: 0 };
    const before = { ...props };
    const drawn = StickEmotions(props);
    assert.deepEqual(props, before);
    assert.equal(drawn.emotion, "angry");
    assert.equal(rig("neutral").scale, 1);
    assert.equal(rig("neutral").drawScale, 1);
    assert.equal(rig("neutral").detail, "full");
  });
});

const SNAPSHOTS = {
  open: {
    neutral: "be7e0802e5724d16c97ad525a04e6aaf382ddd4edcb8bff7a2853d74f67dd322",
    attentive: "b41d57457ed1b2934240a6695e92866e6199fee4a22beca441721682f543b810",
    skeptical: "88bb76348bf0a9118e2870190f18e4b6ed0ec4ac52abe10a9e5e59aa23d860f3",
    concerned: "4064e1ef4fbf2447ea660a03d54bfe7bfc7d9f79adfd675adbe3f7aeb86491a1",
    surprised: "88ae408099002cf525ef7308f9bfeed5af3fcebf90498660bd74caa867b95454",
    fearful: "d39d720323f853cf544e522e453019e7cca53b5aff75ce6a0bd55c36ac6ad4d8",
    angry: "0b7f6f16fc8b35327b209c269e3ffdf6dc2950a3998b64074d38b0732b794faa",
    grieving: "ea7860734acf53d76202a93bff40778c9824c14cdff1b9be1872693364bf92e8",
    ashamed: "ce29dd4ed39a399ff1d02bc1b16cc13ed0e5d23b95afd74e7f83ff1d36c307d7",
    guilty: "2aeace8ad7689177f19e756398f43a7109a895bb32061822b3a9fce267cff18d",
  },
  shut: "2c01057015177bf55772ff4081b1673ce015f6fe100ad74d0ff0ad1c93c41620",
  distantGuilty: "746e5f1ffb70f34d29e66ae308946bea8440b180cead2f4987f8264f7a2068b6",
};
