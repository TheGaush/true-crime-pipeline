import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const themePath = path.resolve(here, "../src/theme/CaseBibleContext.tsx");
const sourcePath = path.resolve(here, "../src/grade/GradeContract.tsx");
const STUB_MARK = "TC-TASK-109-TEST-STUB";
const STUB_SOURCE = `/** ${STUB_MARK} — test double, not Task 102. Removed when the grade test finishes. */
export function useCaseBible(): { paperBgHex: string } {
  return { paperBgHex: "#E9E2D2" };
}
`;

const existingTheme = fs.existsSync(themePath) ? fs.readFileSync(themePath, "utf8") : null;
const stubOwned = existingTheme === null || existingTheme.includes(STUB_MARK);
if (stubOwned) {
  fs.mkdirSync(path.dirname(themePath), { recursive: true });
  fs.writeFileSync(themePath, STUB_SOURCE);
}

function removeStub(): void {
  if (!stubOwned) return;
  if (fs.existsSync(themePath) && fs.readFileSync(themePath, "utf8").includes(STUB_MARK)) {
    fs.rmSync(themePath, { force: true });
  }
  const dir = path.dirname(themePath);
  if (fs.existsSync(dir) && fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
}

process.on("exit", removeStub);

const grade = await import("../src/grade/GradeContract.tsx");

afterAll(removeStub);

const {
  FRAME_HEIGHT,
  FRAME_WIDTH,
  GradeContract,
  SCENE_GRADE_MANIFEST_FILENAME,
  buildSceneGradeManifest,
  gradeTargetAt,
  noiseFloor,
  rasterizeUngradedFrame,
  readPaperBgHex,
  renderUngradedFrame,
  sceneGradeManifestDocument,
  sceneNeedsGrade,
} = grade;

function independentNoise(pixels: Uint8Array, hex: string): number {
  const r = Number.parseInt(hex.slice(1, 3), 16);
  const g = Number.parseInt(hex.slice(3, 5), 16);
  const b = Number.parseInt(hex.slice(5, 7), 16);
  let max = 0;
  for (let index = 0; index < pixels.length; index += 3) {
    max = Math.max(
      max,
      Math.abs((pixels[index] ?? 0) - r),
      Math.abs((pixels[index + 1] ?? 0) - g),
      Math.abs((pixels[index + 2] ?? 0) - b),
    );
  }
  return max;
}

function pixelAt(pixels: Uint8Array, x: number, y: number): number[] {
  const offset = (y * FRAME_WIDTH + x) * 3;
  return [pixels[offset] ?? -1, pixels[offset + 1] ?? -1, pixels[offset + 2] ?? -1];
}

const timeline = [
  { scene_id: "code-01", visual_engine: "CODE_STICKMAN" as const, motif_component: "StickmanStage" },
  { scene_id: "still-01", visual_engine: "STILL_2K_PANZOOM" as const, motif_component: "Illustrative2KPanZoom" },
  { scene_id: "flow-01", visual_engine: "FLOW_HERO_VIDEO" as const, motif_component: "HeroVideoBridge" },
  { scene_id: "audio-01", visual_engine: "AUDIO_EVIDENCE_CARD" as const, motif_component: "AudioEvidenceCard" },
  { scene_id: "foia-01", visual_engine: "FOIA_REAL_FOOTAGE" as const, motif_component: "FoiaFootageFrame" },
];

describe("grade", () => {
  it("paints a flat un-grained paper plate from useCaseBible()", () => {
    const frame = stubOwned ? GradeContract() : renderUngradedFrame("#AABBCC");
    expect(frame.paperGrain).toBe(0);
    expect(frame.vignette).toBe(0);
    expect(frame.remotionGrainApplied).toBe(false);
    expect(frame.remotionVignetteApplied).toBe(false);
    expect(frame.element.type).toBe("div");
    expect(frame.element.props.children).toBeNull();
    expect(frame.element.props.style.filter).toBe("none");
    expect(frame.element.props.style.backgroundImage).toBe("none");
    expect(frame.element.props["data-paper-grain"]).toBe("0");
    expect(frame.element.props["data-vignette"]).toBe("0");
    expect(frame.paperBgHex).toBe(stubOwned ? "#E9E2D2" : "#AABBCC");
    expect(frame.element.props.style.backgroundColor).toBe(frame.paperBgHex);
  });

  it("matches CaseBible.paperBgHex on every pixel, including the corners", () => {
    const hex = "#102A3C";
    const frame = renderUngradedFrame(hex);
    const pixels = rasterizeUngradedFrame(frame);
    expect(pixels.length).toBe(FRAME_WIDTH * FRAME_HEIGHT * 3);
    expect(independentNoise(pixels, hex)).toBe(0);
    expect(noiseFloor(pixels, hex)).toBe(0);
    const corner = pixelAt(pixels, 0, 0);
    expect(pixelAt(pixels, FRAME_WIDTH - 1, 0)).toEqual(corner);
    expect(pixelAt(pixels, 0, FRAME_HEIGHT - 1)).toEqual(corner);
    expect(pixelAt(pixels, FRAME_WIDTH - 1, FRAME_HEIGHT - 1)).toEqual(corner);
    expect(pixelAt(pixels, 960, 540)).toEqual(corner);
    expect(corner).toEqual([0x10, 0x2a, 0x3c]);

    const grained = new Uint8Array(pixels);
    const last = grained.length - 1;
    grained[last] = (grained[last] ?? 0) + 1;
    expect(independentNoise(grained, hex)).toBe(1);
  });

  it("reads paperBgHex and the frozen v4 paper_bg_hex field", () => {
    expect(readPaperBgHex({ paperBgHex: "#E9E2D2" })).toBe("#E9E2D2");
    expect(readPaperBgHex({ style_dna_json: { paper_bg_hex: "#112233" } })).toBe("#112233");
    expect(() => readPaperBgHex({ paperBgHex: "#E9E2D2", paper_bg_hex: "#000000" })).toThrow(/disagrees/);
    expect(() => readPaperBgHex({ inkHex: "#1B1B1D" })).toThrow(/paperBgHex is missing/);
    expect(() => renderUngradedFrame("paper")).toThrow(/#RRGGBB/);
  });

  it("tags FOIA apply_grade false and stylized engines apply_grade true", () => {
    const manifest = buildSceneGradeManifest(timeline, "ep_golden_01");
    const byId = new Map(manifest.scenes.map((scene) => [scene.scene_id, scene]));
    for (const id of ["code-01", "still-01", "flow-01", "audio-01"]) {
      const scene = byId.get(id);
      expect(scene?.apply_grade).toBe(true);
      expect(scene?.needs_grade).toBe(true);
      expect(scene?.exempt_from_grain).toBe(false);
      expect(scene?.is_foia).toBe(false);
      expect(scene?.grade_owner).toBe("agent6_single_pass");
    }
    const foia = byId.get("foia-01");
    expect(foia?.apply_grade).toBe(false);
    expect(foia?.needs_grade).toBe(false);
    expect(foia?.exempt_from_grain).toBe(true);
    expect(foia?.is_foia).toBe(true);
    expect(foia?.grade_owner).toBe("none");
    expect(sceneNeedsGrade(timeline[4]!)).toBe(false);
    expect(manifest.remotion_grain_applied).toBe(false);
    expect(manifest.remotion_vignette_applied).toBe(false);
    expect(manifest.paper_grain).toBe(0);
    expect(manifest.vignette).toBe(0);
    expect(manifest.grain_phase).toBeNull();
    expect(manifest.scenes.every((scene) => scene.grain_phase === null)).toBe(true);
    expect(manifest.scenes.every((scene) => scene.remotion_grain_applied === false)).toBe(true);
    expect(manifest.scenes.every((scene) => scene.remotion_vignette_applied === false)).toBe(true);
  });

  it("keeps a bodycam inset raw when a stylized narrator border shares the FOIA frame", () => {
    const inset = { x: 1400, y: 700, width: 400, height: 300 };
    const pip = { x: 1360, y: 660, width: 480, height: 380 };
    const manifest = buildSceneGradeManifest([
      {
        scene_id: "foia-pip",
        visual_engine: "FOIA_REAL_FOOTAGE",
        motif_component: "FoiaFootageFrame",
        narrator_pip: pip,
        bodycam_inset: inset,
      },
    ]);
    const scene = manifest.scenes[0]!;
    expect(scene.apply_grade).toBe(false);
    expect(scene.needs_grade).toBe(false);
    expect(scene.ungraded_masks).toEqual([
      {
        kind: "bodycam_inset",
        apply_grade: false,
        needs_grade: false,
        exempt_from_grain: true,
        ...inset,
      },
    ]);
    expect(scene.stylized_overlays[0]?.apply_grade).toBe(true);
    expect(scene.stylized_overlays[0]?.ungraded_holes).toEqual([inset]);
    expect(gradeTargetAt(scene, 1500, 800)).toBe("exempt");
    expect(gradeTargetAt(scene, 1370, 670)).toBe("agent6");
    expect(gradeTargetAt(scene, 10, 10)).toBe("exempt");
    expect(scene.motif_component).toBe("FoiaFootageFrame");

    const mislabeled = buildSceneGradeManifest([
      {
        scene_id: "foia-motif",
        visual_engine: "CODE_STICKMAN",
        motif_component: "FoiaFootageFrame",
        bodycam_inset: inset,
      },
    ]).scenes[0]!;
    expect(mislabeled.apply_grade).toBe(false);
    expect(mislabeled.is_foia).toBe(true);
    expect(gradeTargetAt(mislabeled, 1500, 800)).toBe("exempt");
    expect(gradeTargetAt(mislabeled, 10, 10)).toBe("exempt");
  });

  it("does not reset a Remotion grain phase across scene cuts because Remotion has none", () => {
    const first = buildSceneGradeManifest(timeline);
    const second = buildSceneGradeManifest(timeline);
    expect(serialize(first)).toBe(serialize(second));
    const phases = first.scenes.map((scene) => scene.grain_phase);
    expect(new Set(phases).size).toBe(1);
    expect(phases[0]).toBeNull();
    expect(first.scenes.map((scene) => scene.timeline_index)).toEqual([0, 1, 2, 3, 4]);
  });

  it("writes scene_grade_manifest.json for Agent 6", () => {
    const document = sceneGradeManifestDocument(timeline, "ep_golden_01");
    expect(document.filename).toBe(SCENE_GRADE_MANIFEST_FILENAME);
    expect(document.filename).toBe("scene_grade_manifest.json");
    const parsed = JSON.parse(document.json) as { scenes: Array<{ apply_grade: boolean }>; remotion_grain_applied: boolean };
    expect(parsed.remotion_grain_applied).toBe(false);
    expect(parsed.scenes.map((scene) => scene.apply_grade)).toEqual([true, true, true, true, false]);
    expect(document.json.endsWith("\n")).toBe(true);
    const dir = fs.mkdtempSync(path.join(path.resolve("/tmp"), "tc-grade-"));
    const file = path.join(dir, document.filename);
    fs.writeFileSync(file, document.json);
    expect(JSON.parse(fs.readFileSync(file, "utf8"))).toEqual(JSON.parse(document.json));
    fs.rmSync(dir, { recursive: true, force: true });
  });

  it("rejects unknown engines, duplicate ids, and insets outside the frame", () => {
    expect(() =>
      buildSceneGradeManifest([{ scene_id: "x", visual_engine: "CRIME_SCENE" as "CODE_STICKMAN" }]),
    ).toThrow(/unknown visual_engine/);
    expect(() =>
      buildSceneGradeManifest([
        { scene_id: "same", visual_engine: "CODE_STICKMAN" },
        { scene_id: "same", visual_engine: "FLOW_HERO_VIDEO" },
      ]),
    ).toThrow(/duplicate scene_id/);
    expect(() =>
      buildSceneGradeManifest([
        {
          scene_id: "foia-bad",
          visual_engine: "FOIA_REAL_FOOTAGE",
          bodycam_inset: { x: 1800, y: 900, width: 200, height: 200 },
        },
      ]),
    ).toThrow(/inside the 1920x1080 frame/);
  });

  it("keeps film-grain filters out of the Remotion source", () => {
    const source = fs.readFileSync(sourcePath, "utf8");
    expect(source).toContain('from "../theme/CaseBibleContext.js"');
    expect(source).toContain("useCaseBible");
    for (const banned of ["<feTurbulence", "feDisplacementMap", "feGaussianBlur", "Math.random", "<canvas", "radial-gradient", "backdrop-filter"]) {
      expect(source.includes(banned)).toBe(false);
    }
    expect(source.includes("paperGrain: 1")).toBe(false);
    expect(source.includes("vignette: 1")).toBe(false);
  });
});

function serialize(manifest: unknown): string {
  return JSON.stringify(manifest);
}
