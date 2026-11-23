/**
 * Single-pass grade contract for Remotion.
 *
 * Remotion paints flat paper and never applies paper grain or vignette.
 * Agent 6 reads `scene_grade_manifest.json` and grades non-FOIA scenes once.
 * Task 102 owns `useCaseBible()`; this branch imports it and does not copy it.
 */
// @ts-ignore Task 102 ships CaseBibleContext.tsx on task/102-case-bible-theme-provider.
import { useCaseBible } from "../theme/CaseBibleContext.js";

export const SCENE_GRADE_MANIFEST_FILENAME = "scene_grade_manifest.json";
export const GRADE_MANIFEST_SCHEMA = "scene_grade_manifest.v1";
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const REMOTION_PAPER_GRAIN = 0;
export const REMOTION_VIGNETTE = 0;

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;
const SCENE_ID = /^[A-Za-z0-9_-]+$/;

export const VISUAL_ENGINES = [
  "CODE_STICKMAN",
  "STILL_2K_PANZOOM",
  "AUDIO_EVIDENCE_CARD",
  "FOIA_REAL_FOOTAGE",
  "FLOW_HERO_VIDEO",
] as const;

export type VisualEngine = (typeof VISUAL_ENGINES)[number];

const STYLIZED_ENGINES = new Set<VisualEngine>([
  "CODE_STICKMAN",
  "STILL_2K_PANZOOM",
  "AUDIO_EVIDENCE_CARD",
  "FLOW_HERO_VIDEO",
]);

export interface PixelRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GradeSceneInput {
  scene_id: string;
  visual_engine: VisualEngine;
  motif_component?: string | null;
  /** Stylized narrator PiP border drawn over a FOIA frame. */
  narrator_pip?: PixelRect | null;
  /** Raw bodycam pixels that must stay un-grained. */
  bodycam_inset?: PixelRect | null;
}

export interface UngradedMask {
  kind: "bodycam_inset";
  apply_grade: false;
  needs_grade: false;
  exempt_from_grain: true;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface StylizedOverlay {
  kind: "narrator_pip_border";
  apply_grade: true;
  needs_grade: true;
  exempt_from_grain: false;
  x: number;
  y: number;
  width: number;
  height: number;
  /** Bodycam pixels inside this border stay raw. */
  ungraded_holes: PixelRect[];
}

export interface SceneGradeRecord {
  timeline_index: number;
  scene_id: string;
  visual_engine: VisualEngine;
  motif_component: string | null;
  apply_grade: boolean;
  needs_grade: boolean;
  is_foia: boolean;
  exempt_from_grain: boolean;
  remotion_grain_applied: false;
  remotion_vignette_applied: false;
  paper_grain: 0;
  vignette: 0;
  grain_phase: null;
  grade_owner: "agent6_single_pass" | "none";
  ungraded_masks: UngradedMask[];
  stylized_overlays: StylizedOverlay[];
}

export interface SceneGradeManifest {
  filename: typeof SCENE_GRADE_MANIFEST_FILENAME;
  schema: typeof GRADE_MANIFEST_SCHEMA;
  contract_version: "v4";
  fps: typeof FRAME_FPS;
  width_px: typeof FRAME_WIDTH;
  height_px: typeof FRAME_HEIGHT;
  remotion_grain_applied: false;
  remotion_vignette_applied: false;
  paper_grain: 0;
  vignette: 0;
  grain_phase: null;
  grade_owner: "agent6_single_pass";
  episode_id?: string;
  scenes: SceneGradeRecord[];
}

export interface FlatPaperElement {
  type: "div";
  props: {
    "data-tc-role": "ungraded-paper-bg";
    "data-paper-grain": "0";
    "data-vignette": "0";
    style: {
      backgroundColor: string;
      width: typeof FRAME_WIDTH;
      height: typeof FRAME_HEIGHT;
      position: "absolute";
      inset: 0;
      filter: "none";
      backgroundImage: "none";
      opacity: 1;
    };
    children: null;
  };
}

export interface UngradedFrame {
  width: typeof FRAME_WIDTH;
  height: typeof FRAME_HEIGHT;
  fps: typeof FRAME_FPS;
  paperBgHex: string;
  paperGrain: 0;
  vignette: 0;
  remotionGrainApplied: false;
  remotionVignetteApplied: false;
  element: FlatPaperElement;
}

export type GradeTarget = "exempt" | "agent6";

function assertHex(hex: string, label: string): void {
  if (!HEX_COLOR.test(hex)) throw new Error(`${label} must be a #RRGGBB color`);
}

function hexChannels(hex: string): { r: number; g: number; b: number } {
  assertHex(hex, "paper color");
  return {
    r: Number.parseInt(hex.slice(1, 3), 16),
    g: Number.parseInt(hex.slice(3, 5), 16),
    b: Number.parseInt(hex.slice(5, 7), 16),
  };
}

function nestedPaper(theme: object): string | null {
  const style = (theme as { style_dna_json?: unknown }).style_dna_json;
  if (!style || typeof style !== "object") return null;
  const hex = (style as { paper_bg_hex?: unknown }).paper_bg_hex;
  return typeof hex === "string" ? hex : null;
}

/** Reads Task 102's camelCase theme, or the frozen v4 `paper_bg_hex` field. */
export function readPaperBgHex(theme: unknown): string {
  if (!theme || typeof theme !== "object") {
    throw new Error("useCaseBible() returned no CaseBible theme");
  }
  const record = theme as { paperBgHex?: unknown; paper_bg_hex?: unknown };
  const camel = typeof record.paperBgHex === "string" ? record.paperBgHex : null;
  const snake = typeof record.paper_bg_hex === "string" ? record.paper_bg_hex : null;
  const nested = nestedPaper(theme);
  const chosen = camel ?? snake ?? nested;
  if (!chosen) throw new Error("CaseBible.paperBgHex is missing");
  assertHex(chosen, "CaseBible.paperBgHex");
  for (const other of [snake, nested]) {
    if (other && other.toLowerCase() !== chosen.toLowerCase()) {
      throw new Error("CaseBible.paperBgHex disagrees with paper_bg_hex");
    }
  }
  return chosen;
}

function assertRect(rect: PixelRect, label: string): void {
  if (!rect || typeof rect !== "object") throw new Error(`${label} must be a rectangle`);
  const { x, y, width, height } = rect;
  if (![x, y, width, height].every((value) => typeof value === "number" && Number.isFinite(value))) {
    throw new Error(`${label} has a non-finite edge`);
  }
  if (x < 0 || y < 0 || width <= 0 || height <= 0) {
    throw new Error(`${label} must sit inside the ${FRAME_WIDTH}x${FRAME_HEIGHT} frame`);
  }
  if (x + width > FRAME_WIDTH || y + height > FRAME_HEIGHT) {
    throw new Error(`${label} must sit inside the ${FRAME_WIDTH}x${FRAME_HEIGHT} frame`);
  }
}

function intersection(a: PixelRect, b: PixelRect): PixelRect | null {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  if (right <= x || bottom <= y) return null;
  return { x, y, width: right - x, height: bottom - y };
}

function contains(rect: PixelRect, x: number, y: number): boolean {
  return x >= rect.x && y >= rect.y && x < rect.x + rect.width && y < rect.y + rect.height;
}

function isFoia(scene: GradeSceneInput): boolean {
  return scene.visual_engine === "FOIA_REAL_FOOTAGE" || scene.motif_component === "FoiaFootageFrame";
}

function assertScene(scene: GradeSceneInput): void {
  if (!scene || typeof scene !== "object") throw new Error("scene must be an object");
  if (typeof scene.scene_id !== "string" || !SCENE_ID.test(scene.scene_id)) {
    throw new Error("scene_id must match ^[A-Za-z0-9_-]+$");
  }
  if (!STYLIZED_ENGINES.has(scene.visual_engine) && scene.visual_engine !== "FOIA_REAL_FOOTAGE") {
    throw new Error(`unknown visual_engine ${String(scene.visual_engine)}`);
  }
  if (scene.motif_component != null) {
    if (typeof scene.motif_component !== "string" || scene.motif_component.trim() === "") {
      throw new Error("motif_component must be a non-empty string or null");
    }
  }
  if (scene.bodycam_inset) assertRect(scene.bodycam_inset, "bodycam_inset");
  if (scene.narrator_pip) assertRect(scene.narrator_pip, "narrator_pip");
}

/** FOIA footage and FoiaFootageFrame stay raw. Code, 2K, Flow, and other stylized engines need one Agent 6 pass. */
export function sceneNeedsGrade(scene: GradeSceneInput): boolean {
  assertScene(scene);
  if (isFoia(scene)) return false;
  return true;
}

function masksFor(scene: GradeSceneInput): UngradedMask[] {
  if (!scene.bodycam_inset) return [];
  const inset = scene.bodycam_inset;
  return [
    {
      kind: "bodycam_inset",
      apply_grade: false,
      needs_grade: false,
      exempt_from_grain: true,
      x: inset.x,
      y: inset.y,
      width: inset.width,
      height: inset.height,
    },
  ];
}

function overlaysFor(scene: GradeSceneInput): StylizedOverlay[] {
  if (!scene.narrator_pip) return [];
  const pip = scene.narrator_pip;
  const hole = scene.bodycam_inset ? intersection(pip, scene.bodycam_inset) : null;
  return [
    {
      kind: "narrator_pip_border",
      apply_grade: true,
      needs_grade: true,
      exempt_from_grain: false,
      x: pip.x,
      y: pip.y,
      width: pip.width,
      height: pip.height,
      ungraded_holes: hole ? [hole] : [],
    },
  ];
}

export function buildSceneGradeManifest(
  scenes: readonly GradeSceneInput[],
  episodeId?: string,
): SceneGradeManifest {
  if (!Array.isArray(scenes)) throw new Error("scenes must be an array");
  const seen = new Set<string>();
  const records: SceneGradeRecord[] = scenes.map((scene, timeline_index) => {
    assertScene(scene);
    if (seen.has(scene.scene_id)) throw new Error(`duplicate scene_id ${scene.scene_id}`);
    seen.add(scene.scene_id);
    const applyGrade = sceneNeedsGrade(scene);
    return {
      timeline_index,
      scene_id: scene.scene_id,
      visual_engine: scene.visual_engine,
      motif_component: scene.motif_component ?? null,
      apply_grade: applyGrade,
      needs_grade: applyGrade,
      is_foia: isFoia(scene),
      exempt_from_grain: !applyGrade,
      remotion_grain_applied: false,
      remotion_vignette_applied: false,
      paper_grain: 0,
      vignette: 0,
      grain_phase: null,
      grade_owner: applyGrade ? "agent6_single_pass" : "none",
      ungraded_masks: masksFor(scene),
      stylized_overlays: overlaysFor(scene),
    };
  });
  const manifest: SceneGradeManifest = {
    filename: SCENE_GRADE_MANIFEST_FILENAME,
    schema: GRADE_MANIFEST_SCHEMA,
    contract_version: "v4",
    fps: FRAME_FPS,
    width_px: FRAME_WIDTH,
    height_px: FRAME_HEIGHT,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
    grain_phase: null,
    grade_owner: "agent6_single_pass",
    scenes: records,
  };
  if (episodeId !== undefined) {
    if (typeof episodeId !== "string" || !SCENE_ID.test(episodeId)) {
      throw new Error("episode_id must match ^[A-Za-z0-9_-]+$");
    }
    manifest.episode_id = episodeId;
  }
  return manifest;
}

export function serializeSceneGradeManifest(manifest: SceneGradeManifest): string {
  return `${JSON.stringify(manifest, null, 2)}\n`;
}

export function sceneGradeManifestDocument(
  scenes: readonly GradeSceneInput[],
  episodeId?: string,
): { filename: typeof SCENE_GRADE_MANIFEST_FILENAME; json: string; manifest: SceneGradeManifest } {
  const manifest = buildSceneGradeManifest(scenes, episodeId);
  return {
    filename: SCENE_GRADE_MANIFEST_FILENAME,
    json: serializeSceneGradeManifest(manifest),
    manifest,
  };
}

/** Where Agent 6 may grade. Remotion itself never paints that grade. */
export function gradeTargetAt(record: SceneGradeRecord, x: number, y: number): GradeTarget {
  for (const mask of record.ungraded_masks) {
    if (contains(mask, x, y)) return "exempt";
  }
  for (const overlay of record.stylized_overlays) {
    if (!contains(overlay, x, y)) continue;
    if (overlay.ungraded_holes.some((hole) => contains(hole, x, y))) return "exempt";
    return overlay.apply_grade ? "agent6" : "exempt";
  }
  return record.apply_grade ? "agent6" : "exempt";
}

export function renderUngradedFrame(paperBgHex: string): UngradedFrame {
  assertHex(paperBgHex, "CaseBible.paperBgHex");
  return {
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT,
    fps: FRAME_FPS,
    paperBgHex,
    paperGrain: REMOTION_PAPER_GRAIN,
    vignette: REMOTION_VIGNETTE,
    remotionGrainApplied: false,
    remotionVignetteApplied: false,
    element: {
      type: "div",
      props: {
        "data-tc-role": "ungraded-paper-bg",
        "data-paper-grain": "0",
        "data-vignette": "0",
        style: {
          backgroundColor: paperBgHex,
          width: FRAME_WIDTH,
          height: FRAME_HEIGHT,
          position: "absolute",
          inset: 0,
          filter: "none",
          backgroundImage: "none",
          opacity: 1,
        },
        children: null,
      },
    },
  };
}

/** Flat RGB frame. Every pixel is `paperBgHex`. Grain and vignette stay at zero. */
export function rasterizeUngradedFrame(frame: UngradedFrame): Uint8Array {
  if (frame.paperGrain !== 0 || frame.vignette !== 0) {
    throw new Error("Remotion frame must apply zero paper grain and zero vignette");
  }
  if (frame.remotionGrainApplied || frame.remotionVignetteApplied) {
    throw new Error("Remotion frame must apply zero paper grain and zero vignette");
  }
  if (frame.element.props.children !== null) {
    throw new Error("Remotion paper plate cannot stack grade overlays");
  }
  if (frame.element.props.style.filter !== "none" || frame.element.props.style.backgroundImage !== "none") {
    throw new Error("Remotion paper plate cannot stack grade overlays");
  }
  if (frame.element.props["data-paper-grain"] !== "0" || frame.element.props["data-vignette"] !== "0") {
    throw new Error("Remotion paper plate cannot stack grade overlays");
  }
  const { r, g, b } = hexChannels(frame.paperBgHex);
  const count = frame.width * frame.height;
  const pixels = new Uint8Array(count * 3);
  for (let index = 0; index < count; index += 1) {
    const offset = index * 3;
    pixels[offset] = r;
    pixels[offset + 1] = g;
    pixels[offset + 2] = b;
  }
  return pixels;
}

export function noiseFloor(pixels: Uint8Array, paperBgHex: string): number {
  const { r, g, b } = hexChannels(paperBgHex);
  let max = 0;
  for (let index = 0; index < pixels.length; index += 3) {
    const delta = Math.max(
      Math.abs((pixels[index] ?? 0) - r),
      Math.abs((pixels[index + 1] ?? 0) - g),
      Math.abs((pixels[index + 2] ?? 0) - b),
    );
    if (delta > max) max = delta;
  }
  return max;
}

/** Remotion composition entry. Palette comes from Task 102; grade does not. */
export function GradeContract(): UngradedFrame {
  return renderUngradedFrame(readPaperBgHex(useCaseBible()));
}
