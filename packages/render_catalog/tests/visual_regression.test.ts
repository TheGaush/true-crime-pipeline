import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import {
  CRIMSON_HEX,
  DEPENDENCY_SPECIFIERS,
  END_SCREEN_FRAMES,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  FrameVerifierError,
  INK_HEX,
  PAPER_BG_HEX,
  SAMPLED_MOTIFS,
  SSIM_MIN,
  applySubpixelAntialiasNoise,
  auditExclusionBorders,
  hashFrame,
  isBlankFrame,
  loadFrameVerifierDeps,
  renderStill,
  structuralSimilarity,
  verifyStill,
  type FrameVerifierDeps,
  type GradeModule,
  type RgbaFrame,
  type SampledMotif,
  type StickEmotionModule,
} from "../src/renderer/FrameVerifier.js";

const EPISODE_FRAMES = 36_000;
const END_FRAME = EPISODE_FRAMES - END_SCREEN_FRAMES;

const LOCKED_HASHES: Record<string, string> = {
  "StickmanStage#0": "6c61603d9cbced4fa6ab62665247fc6acef8f292f2e21d12aca9154ce5b074ee",
  "StickmanStage#35400": "7b0428fae8449ea232d11582f9ead01316f46c19c363c159ffa54549c1d0ba79",
  "AudioEvidenceCard#0": "d0678ae56e0b16845ecee3891134057749c23204cc2dfc2890fc664c43547155",
  "AudioEvidenceCard#35400": "c7b167a252590ed728e233639a3dfb56195b35166e414f2760f0679a9baab55a",
  "RedactedDocReveal#0": "ffa38a9e8fea34d9fd022087fae5aeef36bdb4ec87d4529713fce2d3c2b48abe",
  "RedactedDocReveal#35400": "836458ae78e798a03be46c4ba8b1e8391830ee546c37bf42c99ee35485a20de9",
  "FoiaFootageFrame#0": "ec96e363fe992c4144935273a867dd227d1a0e35f659501a534965527672495b",
  "FoiaFootageFrame#35400": "ac77e96f6fef7345a9e50e3af4ff4681319afcad6ff171da968fab60200d483c",
};

const EMOTIONS = [
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

function sample(motif: SampledMotif, frame: number) {
  return renderStill({ motif, frame, durationInFrames: EPISODE_FRAMES });
}

function pixel(frame: RgbaFrame, x: number, y: number): string {
  const offset = (y * frame.width + x) * 4;
  const channel = (index: number) => (frame.data[offset + index] ?? 0).toString(16).padStart(2, "0");
  return `#${channel(0)}${channel(1)}${channel(2)}`.toUpperCase();
}

function minInkY(frame: RgbaFrame, plate = PAPER_BG_HEX): number {
  const red = Number.parseInt(plate.slice(1, 3), 16);
  const green = Number.parseInt(plate.slice(3, 5), 16);
  const blue = Number.parseInt(plate.slice(5, 7), 16);
  for (let y = 0; y < frame.height; y += 1) {
    for (let x = 0; x < frame.width; x += 1) {
      const offset = (y * frame.width + x) * 4;
      const delta = Math.max(
        Math.abs((frame.data[offset] ?? 0) - red),
        Math.abs((frame.data[offset + 1] ?? 0) - green),
        Math.abs((frame.data[offset + 2] ?? 0) - blue),
      );
      if (delta > 24) return y;
    }
  }
  return frame.height;
}

function emotionsModule(pathsFor: (emotion: string, frame: number) => string): StickEmotionModule {
  return {
    STICK_EMOTIONS: EMOTIONS,
    resolveStickEmotion: ({ emotion, frame }) => ({
      paths: [{ feature: "spine", d: pathsFor(emotion, frame) }],
    }),
  };
}

function gradeModule(plateHex: string, grain = 0): GradeModule {
  const red = Number.parseInt(plateHex.slice(1, 3), 16);
  const green = Number.parseInt(plateHex.slice(3, 5), 16);
  const blue = Number.parseInt(plateHex.slice(5, 7), 16);
  const rgb = new Uint8Array(FRAME_WIDTH * FRAME_HEIGHT * 3);
  for (let index = 0; index < rgb.length; index += 3) {
    rgb[index] = red;
    rgb[index + 1] = green;
    rgb[index + 2] = blue;
  }
  return {
    REMOTION_PAPER_GRAIN: grain,
    REMOTION_VIGNETTE: 0,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    sceneNeedsGrade: (scene) => scene.visual_engine !== "FOIA_REAL_FOOTAGE" && scene.motif_component !== "FoiaFootageFrame",
    renderUngradedFrame: () => ({
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      paperBgHex: plateHex,
      paperGrain: grain,
      vignette: 0,
      remotionGrainApplied: false,
      remotionVignetteApplied: false,
    }),
    rasterizeUngradedFrame: () => rgb,
  };
}

describe("visual regression stills", () => {
  it("samples the four MVP motifs", () => {
    expect([...SAMPLED_MOTIFS]).toEqual([
      "StickmanStage",
      "AudioEvidenceCard",
      "RedactedDocReveal",
      "FoiaFootageFrame",
    ]);
  });

  it("locks deterministic frame hashes for contained stills", () => {
    const actual: Record<string, string> = {};
    for (const motif of SAMPLED_MOTIFS) {
      for (const frame of [0, END_FRAME]) {
        const first = sample(motif, frame);
        const second = sample(motif, frame);
        const key = `${motif}#${frame}`;
        actual[key] = first.hash;
        expect(second.hash, key).toBe(first.hash);
        expect(first.blank, key).toBe(false);
        expect(first.audit.clean, key).toBe(true);
        expect(first.audit.plateDelta, key).toBe(0);
        expect(first.audit.intrusionCount, key).toBe(0);
        expect(first.paperGrain).toBe(0);
        expect(first.vignette).toBe(0);
        expect(first.endScreen).toBe(frame === END_FRAME);
        expect(pixel(first.frame, 4, 4)).toBe(PAPER_BG_HEX);
        const verdict = verifyStill(first.frame, second.frame, {
          paperBgHex: first.paperBgHex,
          borders: first.borders,
          exemptSafeZoneFoia: first.exemptSafeZoneFoia,
          requireHashMatch: true,
        });
        expect(verdict.ssim).toBe(1);
        expect(verdict.pass).toBe(true);
      }
    }
    expect(actual).toEqual(LOCKED_HASHES);
  });

  it("keeps an end-screen card out of the caption bar", () => {
    const early = sample("RedactedDocReveal", END_FRAME - 1);
    const card = sample("RedactedDocReveal", END_FRAME);
    expect(early.endScreen).toBe(false);
    expect(card.endScreen).toBe(true);
    expect(card.hash).not.toBe(early.hash);
    expect(card.audit.clean).toBe(true);
  });

  it("treats a short composition as an end screen the way the 20s guard does", () => {
    const still = renderStill({ motif: "StickmanStage", frame: 0, durationInFrames: 30 });
    expect(still.endScreen).toBe(true);
    expect(still.audit.clean).toBe(true);
  });

  it("accepts one-level font antialias noise and rejects a different motif", () => {
    const stick = sample("StickmanStage", 0);
    const noisy = applySubpixelAntialiasNoise(stick.frame, stick.paperBgHex);
    expect(hashFrame(noisy)).not.toBe(stick.hash);
    const tolerant = verifyStill(noisy, stick.frame, {
      paperBgHex: stick.paperBgHex,
      borders: stick.borders,
      exemptSafeZoneFoia: false,
    });
    expect(tolerant.ssim).toBeGreaterThanOrEqual(SSIM_MIN);
    expect(tolerant.ssim).toBeLessThan(1);
    expect(tolerant.hashMatches).toBe(false);
    expect(tolerant.borderClean).toBe(true);
    expect(tolerant.nonBlank).toBe(true);
    expect(tolerant.pass).toBe(true);
    expect(verifyStill(noisy, stick.frame, { requireHashMatch: true }).pass).toBe(false);

    const document = sample("RedactedDocReveal", 0);
    const structural = structuralSimilarity(stick.frame, document.frame);
    expect(structural).toBeLessThan(SSIM_MIN);
    expect(verifyStill(stick.frame, document.frame, { borders: stick.borders }).pass).toBe(false);
  });

  it("ignores parchment drift in the border and flags an ink pixel", () => {
    const still = sample("AudioEvidenceCard", 12);
    const drifted = new Uint8Array(still.frame.data);
    for (let x = 0; x < 32; x += 1) {
      drifted[x * 4] = Math.min(255, (drifted[x * 4] ?? 0) + 8);
    }
    const driftAudit = auditExclusionBorders(
      { width: FRAME_WIDTH, height: FRAME_HEIGHT, data: drifted },
      PAPER_BG_HEX,
      { borders: still.borders },
    );
    expect(driftAudit.clean).toBe(true);
    expect(driftAudit.plateDelta).toBe(8);

    const inked = new Uint8Array(still.frame.data);
    inked[0] = Number.parseInt(INK_HEX.slice(1, 3), 16);
    inked[1] = Number.parseInt(INK_HEX.slice(3, 5), 16);
    inked[2] = Number.parseInt(INK_HEX.slice(5, 7), 16);
    const inkAudit = auditExclusionBorders(
      { width: FRAME_WIDTH, height: FRAME_HEIGHT, data: inked },
      PAPER_BG_HEX,
      { borders: still.borders },
    );
    expect(inkAudit.clean).toBe(false);
    expect(inkAudit.intrusions[0]?.border).toBe("top");
    expect(inkAudit.intrusions[0]?.hex).toBe(INK_HEX);
  });

  it("rejects high-contrast marks in each exclusion border", () => {
    for (const placement of ["top-border", "bottom-border", "bottom-right"] as const) {
      const still = renderStill({
        motif: "StickmanStage",
        frame: 0,
        durationInFrames: EPISODE_FRAMES,
        placement,
      });
      expect(still.blank, placement).toBe(false);
      expect(still.audit.clean, placement).toBe(false);
      expect(still.audit.intrusions[0]?.border, placement).toBe(placement === "bottom-right" ? "bottom-right" : placement === "top-border" ? "top" : "bottom");
      expect(verifyStill(still.frame, sample("StickmanStage", 0).frame, { borders: still.borders }).pass).toBe(false);
    }
  });

  it("fails a blank plate and a flat field", () => {
    const blank = renderStill({
      motif: "FoiaFootageFrame",
      frame: 3,
      durationInFrames: EPISODE_FRAMES,
      placement: "blank",
    });
    expect(blank.blank).toBe(true);
    expect(blank.audit.clean).toBe(true);
    expect(isBlankFrame(blank.frame, blank.borders.content, blank.paperBgHex)).toBe(true);
    expect(verifyStill(blank.frame, blank.frame, { borders: blank.borders }).pass).toBe(false);
  });

  it("exempts a FOIA corner stamp and still rejects crimson there", () => {
    const stamped = renderStill({
      motif: "FoiaFootageFrame",
      frame: 0,
      durationInFrames: EPISODE_FRAMES,
      placement: "foia-stamp",
    });
    expect(stamped.exemptSafeZoneFoia).toBe(true);
    expect(stamped.audit.clean).toBe(true);
    expect(stamped.audit.plateDelta).toBeGreaterThan(24);

    const stylized = renderStill({
      motif: "StickmanStage",
      frame: 0,
      durationInFrames: EPISODE_FRAMES,
      placement: "foia-stamp",
    });
    expect(stylized.exemptSafeZoneFoia).toBe(false);
    expect(stylized.audit.clean).toBe(false);
    expect(stylized.audit.intrusions[0]?.border).toBe("top");

    const crimson = renderStill({
      motif: "FoiaFootageFrame",
      frame: 0,
      durationInFrames: EPISODE_FRAMES,
      placement: "crimson-border",
    });
    expect(crimson.audit.clean).toBe(false);
    expect(crimson.audit.intrusions[0]?.hex).toBe(CRIMSON_HEX);
  });

  it("rejects frames that are not inside the composition", () => {
    expect(() => renderStill({ motif: "StickmanStage", frame: 8, durationInFrames: 8 })).toThrow(FrameVerifierError);
    expect(() => renderStill({ motif: "StickmanStage", frame: 1.5, durationInFrames: 8 })).toThrow(/non-negative integer/);
    expect(() => renderStill({
      motif: "TimelineScrubber" as SampledMotif,
      frame: 0,
      durationInFrames: 8,
    })).toThrow(/motif/);
    expect(() => renderStill({
      motif: "AudioEvidenceCard",
      frame: 0,
      durationInFrames: 8,
      emotion: "angry",
    })).toThrow(/StickmanStage/);
    expect(() => structuralSimilarity(sample("StickmanStage", 0).frame, {
      width: 16,
      height: 16,
      data: new Uint8Array(16 * 16 * 4),
    })).toThrow(/same size/);
  });
});

describe("task 107 and 109 imports", () => {
  it("finds no dependency modules on this branch", async () => {
    const deps = await loadFrameVerifierDeps();
    expect(deps).toEqual({ emotions: null, grade: null, safeZone: null });
    const offline = sample("StickmanStage", 0);
    const loaded = renderStill(
      { motif: "StickmanStage", frame: 0, durationInFrames: EPISODE_FRAMES },
      deps,
    );
    expect(loaded.hash).toBe(offline.hash);
  });

  it("treats a missing module as absent", async () => {
    const deps = await loadFrameVerifierDeps(async () => {
      const error = new Error("Cannot find module");
      Object.assign(error, { code: "ERR_MODULE_NOT_FOUND" });
      throw error;
    });
    expect(deps.emotions).toBeNull();
    expect(deps.grade).toBeNull();
    expect(deps.safeZone).toBeNull();
  });

  it("draws Task 107 paths and refuses a grain plate from Task 109", async () => {
    const emotions = emotionsModule((emotion, frame) => {
      if (emotion === "angry") return "M 0 0 L 0 -40 L 80 -40";
      if (frame % 5 >= 4) return "M 0 0 L 80 0";
      return "M 0 0 L 80 0 L 80 -40";
    });
    const deps: FrameVerifierDeps = { emotions, grade: null, safeZone: null };
    const neutral = renderStill({ motif: "StickmanStage", frame: 0, durationInFrames: EPISODE_FRAMES, emotion: "neutral" }, deps);
    const angry = renderStill({ motif: "StickmanStage", frame: 0, durationInFrames: EPISODE_FRAMES, emotion: "angry" }, deps);
    const builtin = sample("StickmanStage", 0);
    expect(neutral.audit.clean).toBe(true);
    expect(neutral.blank).toBe(false);
    expect(neutral.audit.plateDelta).toBe(0);
    expect(angry.audit.clean).toBe(true);
    expect(angry.hash).not.toBe(neutral.hash);
    expect(neutral.hash).not.toBe(builtin.hash);
    expect(structuralSimilarity(neutral.frame, angry.frame)).toBeLessThan(SSIM_MIN);
    const blinked = renderStill({ motif: "StickmanStage", frame: 4, durationInFrames: EPISODE_FRAMES, emotion: "neutral" }, deps);
    expect(blinked.hash).not.toBe(neutral.hash);

    const plate = "#112233";
    const graded = renderStill(
      { motif: "AudioEvidenceCard", frame: 0, durationInFrames: EPISODE_FRAMES },
      { emotions: null, grade: gradeModule(plate), safeZone: null },
    );
    expect(pixel(graded.frame, 2, 2)).toBe(plate);
    expect(graded.audit.plateDelta).toBe(0);
    expect(graded.paperGrain).toBe(0);
    expect(graded.exemptSafeZoneFoia).toBe(false);
    const foia = renderStill(
      { motif: "FoiaFootageFrame", frame: 0, durationInFrames: EPISODE_FRAMES, placement: "foia-stamp" },
      { emotions: null, grade: gradeModule(PAPER_BG_HEX), safeZone: null },
    );
    expect(foia.exemptSafeZoneFoia).toBe(true);
    expect(foia.audit.clean).toBe(true);

    await expect(loadFrameVerifierDeps(async (specifier) => {
      if (specifier !== DEPENDENCY_SPECIFIERS.grade) return null;
      return { ...gradeModule(PAPER_BG_HEX), REMOTION_PAPER_GRAIN: 1 };
    })).rejects.toThrow(/grain or vignette/);
    expect(() => renderStill(
      { motif: "StickmanStage", frame: 0, durationInFrames: 90 },
      { emotions: null, grade: gradeModule(PAPER_BG_HEX, 1), safeZone: null },
    )).toThrow(/grain or vignette/);
  });

  it("clips motif ink to a measured safe zone", () => {
    const deps: FrameVerifierDeps = {
      emotions: null,
      grade: null,
      safeZone: {
        SAFE_ZONE_PADDING_TOP_PX: null,
        SAFE_ZONE_PADDING_BOTTOM_PX: null,
        SAFE_ZONE_EXCLUSION_WIDTH: null,
        SAFE_ZONE_EXCLUSION_HEIGHT: null,
        measureSafeZone: () => ({
          content: { x: 0, y: 400, width: FRAME_WIDTH, height: FRAME_HEIGHT - 400 - 194 },
          exclusion: { x: FRAME_WIDTH * 0.78, y: FRAME_HEIGHT * 0.86, width: FRAME_WIDTH * 0.22, height: FRAME_HEIGHT * 0.14 },
          captionBar: { x: 0, y: FRAME_HEIGHT - 194, width: FRAME_WIDTH, height: 194 },
        }),
      },
    };
    const still = renderStill({ motif: "StickmanStage", frame: 0, durationInFrames: EPISODE_FRAMES }, deps);
    expect(still.borders.content.y).toBe(400);
    expect(minInkY(still.frame)).toBeGreaterThanOrEqual(400);
    expect(still.audit.clean).toBe(true);
    expect(still.audit.plateDelta).toBe(0);
    expect(minInkY(sample("StickmanStage", 0).frame)).toBeLessThan(400);
  });

  it("refuses a drifted safe-zone contract", async () => {
    await expect(loadFrameVerifierDeps(async (specifier) => {
      if (specifier !== DEPENDENCY_SPECIFIERS.safeZone) return null;
      return { SAFE_ZONE_PADDING_TOP_PX: 96 };
    })).rejects.toThrow(/paddingTop/);
  });

  it("imports StickEmotions from disk when Task 107 is present", async () => {
    const directory = join(process.cwd(), "packages/render_catalog/src/rig");
    const file = join(directory, "StickEmotions.tsx");
    mkdirSync(directory, { recursive: true });
    writeFileSync(
      file,
      `export const STICK_EMOTIONS = ${JSON.stringify([...EMOTIONS])};\nexport function resolveStickEmotion() {\n  return { paths: [{ feature: "spine", d: "M 0 0 L 40 -20" }] };\n}\n`,
    );
    try {
      const deps = await loadFrameVerifierDeps();
      expect(deps.emotions?.STICK_EMOTIONS[9]).toBe("guilty");
      const still = renderStill(
        { motif: "StickmanStage", frame: 0, durationInFrames: EPISODE_FRAMES },
        deps,
      );
      expect(still.audit.clean).toBe(true);
      expect(still.blank).toBe(false);
      expect(still.hash).not.toBe(sample("StickmanStage", 0).hash);
    } finally {
      rmSync(file, { force: true });
    }
  });
});
