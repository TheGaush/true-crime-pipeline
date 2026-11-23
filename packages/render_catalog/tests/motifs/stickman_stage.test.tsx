/**
 * Task 115 StickmanStage tests.
 *
 * Tasks 101 and 104 own SafeZoneLayout and StickFigureGeometry. Those files are
 * not on this branch. The suite rewrites the two imports and supplies stand-ins
 * so the stage solver runs offline without copying either module.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { beforeEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const ts = require("typescript") as typeof import("typescript");

interface HeadCircle {
  characterId: string;
  centerX: number;
  centerY: number;
  radius: number;
}

interface SolvedFigure {
  characterId: string;
  pose: string;
  facing: "left" | "right";
  scale: number;
  screenX: number;
  screenY: number;
  worldX: number;
  seed: number;
  head: HeadCircle;
}

interface Segment {
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface SolvedStage {
  preset: string;
  travelAxis: "L_TO_R" | "R_TO_L" | "STATIC";
  pose: string;
  frame: number;
  progress: number;
  appliedScale: number;
  isEndScreen: boolean;
  entryWorldX: number;
  exitWorldX: number;
  signedTravelPx: number;
  cameraOffsetPx: number;
  cameraWorldX: number;
  figures: SolvedFigure[];
  segments: Segment[];
}

interface StageNode {
  type: string;
  dataset: Record<string, string>;
  props: {
    transform?: string;
    children?: StageNode | readonly StageNode[];
    [key: string]: unknown;
  };
}

interface FigureProps {
  x: number;
  y: number;
  scale: number;
  facing: "left" | "right";
  seed: number;
  frame: number;
  isEndScreen: boolean;
}

interface ZoneProps {
  isEndScreen: boolean;
  label?: string;
  children: StageNode;
}

interface StageModule {
  MOTIF_COMPONENT: string;
  NOIR_ARCHITECTURAL_PRESETS: readonly string[];
  TRAVEL_AXES: readonly string[];
  MIN_FIGURE_SPACING_PX: number;
  FRAME_WIDTH: number;
  FRAME_HEIGHT: number;
  SAFE_PADDING_TOP: number;
  SAFE_PADDING_BOTTOM: number;
  STROKE_BLEED_PX: number;
  HORIZONTAL_REACH_PX: number;
  HEAD_RADIUS_PX: number;
  STAGE_FPS: number;
  END_SCREEN_SECONDS: number;
  StickmanStageError: new (code: string, message: string) => Error & { code: string };
  cubicEaseInOut: (t: number) => number;
  contentInterval: (scale: number) => { left: number; right: number; top: number; bottom: number };
  horizontalSpacing: (figures: readonly { screenX: number }[]) => number[];
  assertNoHeadCollision: (heads: readonly HeadCircle[]) => void;
  axisContinuityViolations: (beats: readonly { travelAxis: string; signedTravelPx: number }[]) => string[];
  chainCameraEntries: (beats: readonly { travelAxis: string; signedTravelPx: number }[], initial?: number) => number[];
  travelAxesForSceneRuns: (seqIndexes: readonly number[]) => string[];
  presetForSceneIndex: (index: number) => string;
  frameIsEndScreen: (absoluteFrame: number, totalFrames: number) => boolean;
  solveStickmanStage: (input: Record<string, unknown>) => SolvedStage;
  StickmanStage: (input: Record<string, unknown>) => StageNode;
  noirPreset: (id: string) => { travelPx: number; pose: string; segments: Segment[] };
}

const SOURCE_URL = new URL("../../src/motifs/StickmanStage.tsx", import.meta.url);
const SOURCE = readFileSync(SOURCE_URL, "utf8");
const SAFE_ZONE_IMPORT = 'import { SafeZoneLayout } from "../safe_zone.js";';
const FIGURE_IMPORT = 'import { StickFigureGeometry } from "../rig/StickFigureGeometry.js";';

const figureCalls: FigureProps[] = [];
const zoneCalls: ZoneProps[] = [];

function SafeZoneLayout(props: ZoneProps): StageNode {
  zoneCalls.push(props);
  return { type: "SafeZoneLayout", dataset: { "safe-zone": "stub" }, props };
}

function StickFigureGeometry(props: FigureProps): StageNode {
  figureCalls.push(props);
  return { type: "StickFigure", dataset: { rig: "stub" }, props: { ...props } };
}

function loadStage(): StageModule {
  if (!SOURCE.includes(SAFE_ZONE_IMPORT) || !SOURCE.includes(FIGURE_IMPORT)) {
    throw new Error("StickmanStage must import SafeZoneLayout and StickFigureGeometry");
  }
  const rewritten = SOURCE.replace(SAFE_ZONE_IMPORT, "").replace(FIGURE_IMPORT, "");
  const printed = ts.transpileModule(rewritten, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: "StickmanStage.tsx",
  }).outputText;
  const exports: Record<string, unknown> = {};
  const runner = new Function(
    "SafeZoneLayout",
    "StickFigureGeometry",
    "exports",
    printed,
  ) as (zone: typeof SafeZoneLayout, figure: typeof StickFigureGeometry, exports: Record<string, unknown>) => void;
  runner(SafeZoneLayout, StickFigureGeometry, exports);
  return exports as unknown as StageModule;
}

const stage = loadStage();

const PACK_URL = new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url);

interface PackScene {
  scene_id: string;
  seq_index: number;
  motif_component: string;
  visual_engine: string;
  end_ms: number;
  timeline_spec_json: { fps: number; duration_frames: number; start_frame: number; motif_component: string };
}

interface GoldenPack {
  pack_id: string;
  motif_registry_v1: { motif_component: string; owner_package: string; is_mvp_4: number }[];
  case_bible: { characters_json: { role_id?: string; character_id?: string }[] };
  runtime_split: { total_master_ms: number };
  scenes: PackScene[];
}

function castOf(pack: GoldenPack): { characterId: string }[] {
  return pack.case_bible.characters_json.map((character) => {
    const characterId = character.character_id ?? character.role_id;
    if (!characterId) throw new Error("golden character is missing an id");
    return { characterId };
  });
}

function childList(node: StageNode): StageNode[] {
  const children = node.props.children;
  if (children === undefined) return [];
  return Array.isArray(children) ? [...children] : [children];
}

function walk(node: StageNode, into: StageNode[] = []): StageNode[] {
  into.push(node);
  for (const child of childList(node)) walk(child, into);
  return into;
}

function baseInput(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    preset: "alley_night",
    travelAxis: "L_TO_R",
    figures: [{ characterId: "narrator" }],
    frame: 0,
    durationFrames: 31,
    ...overrides,
  };
}

beforeEach(() => {
  figureCalls.length = 0;
  zoneCalls.length = 0;
});

describe("StickmanStage", () => {
  it("keeps the safe-zone and stick-figure modules as imports", () => {
    expect(process.env.GEMINI_API_KEY).toBeUndefined();
    expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
    expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
    expect(SOURCE.includes("feTurbulence")).toBe(false);
    expect(SOURCE.includes("feDisplacementMap")).toBe(false);
    expect(SOURCE.includes("#C92A2A")).toBe(false);
    expect(SOURCE.includes(SAFE_ZONE_IMPORT)).toBe(true);
    expect(SOURCE.includes(FIGURE_IMPORT)).toBe(true);
    expect(stage.MOTIF_COMPONENT).toBe("StickmanStage");
    expect(stage.NOIR_ARCHITECTURAL_PRESETS).toEqual([
      "alley_night",
      "precinct_hallway",
      "interrogation_room",
      "courthouse_steps",
      "apartment_doorway",
      "evidence_desk",
    ]);
    expect(stage.MIN_FIGURE_SPACING_PX).toBe(180);
  });

  it("renders one through five figures inside SafeZoneLayout", () => {
    for (let count = 1; count <= 5; count += 1) {
      figureCalls.length = 0;
      zoneCalls.length = 0;
      const figures = Array.from({ length: count }, (_, index) => ({ characterId: `witness_${index}` }));
      const tree = stage.StickmanStage(baseInput({ figures, label: "Porch light on", isEndScreen: false }));
      expect(tree.type).toBe("SafeZoneLayout");
      expect(zoneCalls).toHaveLength(1);
      expect(zoneCalls[0]?.isEndScreen).toBe(false);
      expect(zoneCalls[0]?.label).toBe("Porch light on");
      expect(figureCalls).toHaveLength(count);
      const nodes = walk(zoneCalls[0]?.children as StageNode);
      const motif = nodes.find((node) => node.dataset.motif === "StickmanStage");
      expect(motif?.dataset["figure-count"]).toBe(String(count));
      expect(motif?.dataset.preset).toBe("alley_night");
      expect(nodes.some((node) => JSON.stringify(node).includes("feTurbulence"))).toBe(false);
      const solved = stage.solveStickmanStage(baseInput({ figures }));
      const gaps = stage.horizontalSpacing(solved.figures);
      for (const gap of gaps) expect(gap).toBeGreaterThanOrEqual(180);
      expect(() => stage.assertNoHeadCollision(solved.figures.map((figure) => figure.head))).not.toThrow();
    }
  });

  it("rejects an empty cast and a sixth figure", () => {
    expect(() => stage.solveStickmanStage(baseInput({ figures: [] }))).toThrow(stage.StickmanStageError);
    try {
      stage.solveStickmanStage(baseInput({ figures: [] }));
    } catch (error) {
      expect((error as { code: string }).code).toBe("COUNT");
    }
    const six = Array.from({ length: 6 }, (_, index) => ({ characterId: `witness_${index}` }));
    expect(() => stage.solveStickmanStage(baseInput({ figures: six }))).toThrow(stage.StickmanStageError);
  });

  it("spreads five crowded figures to at least 180px and keeps the heads apart", () => {
    const figures = [0, 1, 2, 3, 4].map((x, index) => ({ characterId: `witness_${index}`, x }));
    const solved = stage.solveStickmanStage(baseInput({ figures, frame: 0, durationFrames: 11 }));
    const gaps = stage.horizontalSpacing(solved.figures);
    expect(gaps).toHaveLength(4);
    for (const gap of gaps) expect(gap).toBeCloseTo(180, 6);
    const band = stage.contentInterval(solved.appliedScale);
    for (const figure of solved.figures) {
      expect(figure.screenX).toBeGreaterThanOrEqual(band.left - 1e-6);
      expect(figure.screenX).toBeLessThanOrEqual(band.right + 1e-6);
      expect(figure.head.centerY - figure.head.radius).toBeGreaterThanOrEqual(stage.SAFE_PADDING_TOP - 1e-6);
      expect(figure.screenY).toBeLessThanOrEqual(stage.FRAME_HEIGHT - stage.SAFE_PADDING_BOTTOM);
    }
    expect(solved.appliedScale).toBe(1);
    const bunchedRight = [1900, 1910, 1920, 1930, 1940].map((x, index) => ({
      characterId: `witness_${index}`,
      x,
    }));
    const right = stage.solveStickmanStage(baseInput({ figures: bunchedRight }));
    for (const gap of stage.horizontalSpacing(right.figures)) expect(gap).toBeCloseTo(180, 6);
    expect(Math.max(...right.figures.map((figure) => figure.screenX))).toBeCloseTo(
      stage.contentInterval(1).right,
      5,
    );
  });

  it("flags overlapping head circles even when a caller builds them by hand", () => {
    expect(() =>
      stage.assertNoHeadCollision([
        { characterId: "narrator", centerX: 0, centerY: 0, radius: 22 },
        { characterId: "defendant", centerX: 10, centerY: 0, radius: 22 },
      ]),
    ).toThrow(stage.StickmanStageError);
    expect(() =>
      stage.assertNoHeadCollision([
        { characterId: "narrator", centerX: 0, centerY: 0, radius: 22 },
        { characterId: "defendant", centerX: 180, centerY: 0, radius: 22 },
      ]),
    ).not.toThrow();
  });

  it("shrinks a huge cast until the safe zone can hold five heads", () => {
    const figures = Array.from({ length: 5 }, (_, index) => ({ characterId: `witness_${index}` }));
    const solved = stage.solveStickmanStage(baseInput({ figures, scale: 40 }));
    expect(solved.appliedScale).toBeLessThan(40);
    expect(solved.appliedScale).toBeGreaterThan(0);
    for (const gap of stage.horizontalSpacing(solved.figures)) {
      expect(gap).toBeGreaterThanOrEqual(180);
    }
    for (const figure of solved.figures) {
      expect(figure.head.centerY - figure.head.radius).toBeGreaterThanOrEqual(stage.SAFE_PADDING_TOP - 1e-6);
      const feet = figure.screenY + 88 * solved.appliedScale;
      expect(feet).toBeLessThanOrEqual(stage.FRAME_HEIGHT - stage.SAFE_PADDING_BOTTOM + 1e-6);
    }
  });

  it("pans the set on a cubic curve and keeps figure spacing locked to the axis", () => {
    const figures = [{ characterId: "narrator" }, { characterId: "defendant" }];
    const durationFrames = 11;
    for (const travelAxis of ["L_TO_R", "R_TO_L", "STATIC"] as const) {
      const samples: number[] = [];
      let first: SolvedStage | undefined;
      let last: SolvedStage | undefined;
      for (let frame = 0; frame < durationFrames; frame += 1) {
        const solved = stage.solveStickmanStage(
          baseInput({ preset: "precinct_hallway", travelAxis, figures, frame, durationFrames }),
        );
        samples.push(solved.cameraOffsetPx);
        const expected = stage.cubicEaseInOut(frame / (durationFrames - 1)) * solved.signedTravelPx;
        expect(solved.cameraOffsetPx).toBeCloseTo(expected, 8);
        if (frame === 0) first = solved;
        if (frame === durationFrames - 1) last = solved;
        if (first) {
          expect(solved.figures.map((figure) => figure.screenX)).toEqual(first.figures.map((figure) => figure.screenX));
        }
      }
      if (!first || !last) throw new Error("missing cubic samples");
      expect(samples[0]).toBe(0);
      expect(last.cameraOffsetPx).toBeCloseTo(last.signedTravelPx, 8);
      expect(last.exitWorldX).toBeCloseTo(first.entryWorldX + last.signedTravelPx, 8);
      for (let i = 1; i < samples.length; i += 1) {
        const previous = samples[i - 1] ?? 0;
        const current = samples[i] ?? 0;
        if (travelAxis === "L_TO_R") expect(current).toBeGreaterThanOrEqual(previous - 1e-9);
        if (travelAxis === "R_TO_L") expect(current).toBeLessThanOrEqual(previous + 1e-9);
        if (travelAxis === "STATIC") expect(current).toBe(0);
      }
      const startStep = Math.abs((samples[1] ?? 0) - (samples[0] ?? 0));
      const midStep = Math.abs((samples[6] ?? 0) - (samples[5] ?? 0));
      if (travelAxis !== "STATIC") expect(startStep).toBeLessThan(midStep);
      expect(last.figures[0]?.worldX).toBeCloseTo((last.figures[0]?.screenX ?? 0) + last.cameraWorldX, 8);
    }
  });

  it("draws a distinct architectural preset and slides only the set, not the figures", () => {
    const names = new Set<string>();
    for (const preset of stage.NOIR_ARCHITECTURAL_PRESETS) {
      const spec = stage.noirPreset(preset);
      expect(spec.segments.length).toBeGreaterThanOrEqual(4);
      const signature = spec.segments.map((segment) => segment.name).join("|");
      expect(names.has(signature)).toBe(false);
      names.add(signature);
      const tree = stage.StickmanStage(
        baseInput({ preset, travelAxis: "L_TO_R", frame: 10, durationFrames: 11, figures: [{ characterId: "narrator" }] }),
      );
      const nodes = walk((zoneCalls.at(-1)?.children ?? tree) as StageNode);
      const architecture = nodes.find((node) => node.dataset.layer === "architecture");
      const motif = nodes.find((node) => node.dataset.motif === "StickmanStage");
      expect(motif?.dataset.preset).toBe(preset);
      expect(architecture?.props.transform).toBe(`translate(${-spec.travelPx} 0)`);
      expect(nodes.filter((node) => node.type === "path").length).toBe(spec.segments.length);
      expect(figureCalls.at(-1)?.x).toBeTypeOf("number");
    }
    const held = stage.StickmanStage(baseInput({ travelAxis: "STATIC", frame: 4, durationFrames: 9 }));
    const heldNodes = walk(zoneCalls.at(-1)?.children ?? held);
    const heldSet = heldNodes.find((node) => node.dataset.layer === "architecture");
    expect(heldSet?.props.transform).toBe("translate(0 0)");
    expect(heldNodes.find((node) => node.dataset.motif === "StickmanStage")?.dataset.pose).toBe("idle");
  });

  it("continues a tracking axis and refuses a reversal", () => {
    const beats = [
      { travelAxis: "L_TO_R", signedTravelPx: 420 },
      { travelAxis: "L_TO_R", signedTravelPx: 420 },
      { travelAxis: "STATIC", signedTravelPx: 0 },
    ];
    expect(stage.axisContinuityViolations(beats)).toEqual([]);
    expect(stage.chainCameraEntries(beats)).toEqual([0, 420, 840]);
    expect(
      stage.axisContinuityViolations([
        { travelAxis: "L_TO_R", signedTravelPx: 420 },
        { travelAxis: "R_TO_L", signedTravelPx: -420 },
      ]),
    ).toHaveLength(1);

    const exit = stage.solveStickmanStage(baseInput({ frame: 10, durationFrames: 11 }));
    const next = stage.solveStickmanStage(
      baseInput({
        preset: "courthouse_steps",
        frame: 0,
        durationFrames: 11,
        entryWorldX: exit.exitWorldX,
        previousAxis: "L_TO_R",
      }),
    );
    expect(next.cameraWorldX).toBeCloseTo(exit.exitWorldX, 8);
    expect(() =>
      stage.solveStickmanStage(baseInput({ travelAxis: "R_TO_L", previousAxis: "L_TO_R" })),
    ).toThrow(stage.StickmanStageError);
    try {
      stage.solveStickmanStage(baseInput({ travelAxis: "R_TO_L", previousAxis: "L_TO_R" }));
    } catch (error) {
      expect((error as { code: string }).code).toBe("AXIS_CONTINUITY");
    }
    expect(() =>
      stage.solveStickmanStage(baseInput({ travelAxis: "STATIC", previousAxis: "L_TO_R" })),
    ).not.toThrow();
  });

  it("faces the cast with the axis and forwards the rig props", () => {
    stage.StickmanStage(baseInput({ travelAxis: "R_TO_L", isEndScreen: true, frame: 3, durationFrames: 8 }));
    expect(zoneCalls.at(-1)?.isEndScreen).toBe(true);
    expect(figureCalls.at(-1)?.facing).toBe("left");
    expect(figureCalls.at(-1)?.isEndScreen).toBe(true);
    expect(figureCalls.at(-1)?.frame).toBe(3);
    const seated = stage.solveStickmanStage(
      baseInput({ preset: "interrogation_room", travelAxis: "STATIC", figures: [{ characterId: "defendant" }] }),
    );
    expect(seated.pose).toBe("seated");
    expect(seated.figures[0]?.facing).toBe("right");
    const doorway = stage.solveStickmanStage(
      baseInput({ preset: "apartment_doorway", travelAxis: "L_TO_R", figures: [{ characterId: "caller" }] }),
    );
    expect(doorway.pose).toBe("doorway_entry");
    expect(() => stage.solveStickmanStage(baseInput({ preset: "crime_scene" }))).toThrow(stage.StickmanStageError);
    expect(() => stage.solveStickmanStage(baseInput({ travelAxis: "UP" }))).toThrow(stage.StickmanStageError);
    expect(() =>
      stage.solveStickmanStage(
        baseInput({ figures: [{ characterId: "narrator" }, { characterId: "narrator" }] }),
      ),
    ).toThrow(stage.StickmanStageError);
  });

  it("blocks every StickmanStage scene in ep_golden_01_20min", () => {
    const pack = JSON.parse(readFileSync(PACK_URL, "utf8")) as GoldenPack;
    expect(pack.pack_id).toBe("ep_golden_01_20min");
    const registry = pack.motif_registry_v1.find((entry) => entry.motif_component === "StickmanStage");
    expect(registry).toMatchObject({ owner_package: "render_catalog", is_mvp_4: 1 });
    const stickman = pack.scenes.filter(
      (scene) => scene.motif_component === "StickmanStage" && scene.visual_engine === "CODE_STICKMAN",
    );
    expect(stickman).toHaveLength(10);
    const cast = castOf(pack);
    expect(cast.map((figure) => figure.characterId)).toEqual(["narrator", "defendant", "caller"]);
    const axes = stage.travelAxesForSceneRuns(stickman.map((scene) => scene.seq_index));
    const presets = new Set<string>();
    const totalFrames = (pack.runtime_split.total_master_ms / 1000) * stage.STAGE_FPS;
    expect(axes).toEqual([
      "L_TO_R",
      "R_TO_L",
      "STATIC",
      "L_TO_R",
      "R_TO_L",
      "STATIC",
      "L_TO_R",
      "R_TO_L",
      "STATIC",
      "L_TO_R",
    ]);
    for (let index = 0; index < stickman.length; index += 1) {
      const scene = stickman[index];
      const axis = axes[index];
      const preset = stage.presetForSceneIndex(index);
      if (!scene || !axis) throw new Error("missing golden scene");
      presets.add(preset);
      expect(scene.timeline_spec_json.fps).toBe(30);
      expect(scene.timeline_spec_json.duration_frames).toBe(1200);
      expect(scene.timeline_spec_json.motif_component).toBe("StickmanStage");
      const previous = index === 0 ? undefined : stickman[index - 1];
      expect(previous === undefined || scene.seq_index !== previous.seq_index + 1).toBe(true);
      const frames = [0, 599, 1199];
      let previousOffset = Number.NEGATIVE_INFINITY;
      if (axis === "R_TO_L") previousOffset = Number.POSITIVE_INFINITY;
      if (axis === "STATIC") previousOffset = 0;
      for (const frame of frames) {
        const absolute = scene.timeline_spec_json.start_frame + frame;
        const solved = stage.solveStickmanStage({
          preset,
          travelAxis: axis,
          figures: cast,
          frame,
          durationFrames: scene.timeline_spec_json.duration_frames,
          isEndScreen: stage.frameIsEndScreen(absolute, totalFrames),
        });
        expect(solved.isEndScreen).toBe(false);
        expect(stage.frameIsEndScreen(absolute, totalFrames)).toBe(false);
        expect(solved.figures).toHaveLength(3);
        for (const gap of stage.horizontalSpacing(solved.figures)) expect(gap).toBeGreaterThanOrEqual(180);
        expect(solved.figures.every((figure) => figure.pose === solved.pose)).toBe(true);
        if (axis === "L_TO_R") expect(solved.cameraOffsetPx).toBeGreaterThanOrEqual(previousOffset - 1e-9);
        if (axis === "R_TO_L") expect(solved.cameraOffsetPx).toBeLessThanOrEqual(previousOffset + 1e-9);
        if (axis === "STATIC") expect(solved.cameraOffsetPx).toBe(0);
        previousOffset = solved.cameraOffsetPx;
        for (const figure of solved.figures) {
          expect(figure.worldX - figure.screenX).toBeCloseTo(solved.cameraWorldX, 6);
          expect(figure.head.centerY - figure.head.radius).toBeGreaterThanOrEqual(stage.SAFE_PADDING_TOP - 1e-6);
        }
      }
      figureCalls.length = 0;
      zoneCalls.length = 0;
      stage.StickmanStage({
        preset,
        travelAxis: axis,
        figures: cast,
        frame: 0,
        durationFrames: 1200,
        isEndScreen: false,
      });
      expect(figureCalls).toHaveLength(3);
      expect(zoneCalls[0]?.isEndScreen).toBe(false);
      const motif = walk(zoneCalls[0]?.children as StageNode).find((node) => node.dataset.motif === "StickmanStage");
      expect(motif?.dataset["travel-axis"]).toBe(axis);
      expect(motif?.dataset["apply-grade"]).toBe("true");
    }
    expect(presets).toEqual(new Set(stage.NOIR_ARCHITECTURAL_PRESETS));
    expect(stage.frameIsEndScreen(totalFrames - 1, totalFrames)).toBe(true);
    expect(stage.frameIsEndScreen(totalFrames - stage.END_SCREEN_SECONDS * stage.STAGE_FPS, totalFrames)).toBe(true);
    expect(stage.frameIsEndScreen(totalFrames - stage.END_SCREEN_SECONDS * stage.STAGE_FPS - 1, totalFrames)).toBe(false);
    expect(stage.travelAxesForSceneRuns([12, 13, 15])).toEqual(["L_TO_R", "L_TO_R", "R_TO_L"]);
  });
});
