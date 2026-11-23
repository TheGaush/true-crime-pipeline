import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import {
  CATALOG_12,
  FRAME_FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  MICRO_SFX_CUES_FILENAME,
  MOTIF_ROUTES,
  MVP_MOTIFS,
  SCENE_GRADE_MANIFEST_FILENAME,
  BatchCompilerError,
  compileTimelineBatch,
  encodeSceneMp4,
  sceneApplyGrade,
  type SceneGradeManifest,
  type MicroSfxDocument,
} from "../src/renderer/BatchCompiler.ts";

const PACKS = [
  "ep_golden_01_20min",
  "ep_golden_02_2strike_fallback",
  "ep_golden_03_2k_grid_heavy",
] as const;

const CATALOG_ENGINES: Record<(typeof CATALOG_12)[number], string> = {
  StickmanStage: "CODE_STICKMAN",
  AudioEvidenceCard: "AUDIO_EVIDENCE_CARD",
  RedactedDocReveal: "CODE_STICKMAN",
  FoiaFootageFrame: "FOIA_REAL_FOOTAGE",
  TimelineScrubber: "CODE_STICKMAN",
  AnimatedMapRoute: "CODE_STICKMAN",
  CellTowerTriangulation: "CODE_STICKMAN",
  SplitScreenComparison: "CODE_STICKMAN",
  CaseBoardSpine: "CODE_STICKMAN",
  QuotePullout: "CODE_STICKMAN",
  EvidenceGridMatrix: "CODE_STICKMAN",
  ChapterSlateTransition: "CODE_STICKMAN",
};

const SIGNATURES: Record<string, string | null> = {
  StickmanStage: null,
  AudioEvidenceCard: "tape_click",
  RedactedDocReveal: "highlighter_glide",
  FoiaFootageFrame: "radio_squelch",
  TimelineScrubber: "tick_sfx",
  AnimatedMapRoute: null,
  CellTowerTriangulation: "radio_squelch",
  SplitScreenComparison: "conflict_stamp",
  CaseBoardSpine: "pin_thud",
  QuotePullout: null,
  EvidenceGridMatrix: "camera_shutter",
  ChapterSlateTransition: null,
};

let dirs: string[] = [];

afterEach(async () => {
  await Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true })));
  dirs = [];
});

async function tempDir(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "tc-batch-compiler-"));
  dirs.push(dir);
  return dir;
}

function packPath(name: string): string {
  return fileURLToPath(new URL(`../../../fixtures/golden_manifests/${name}/pack.json`, import.meta.url));
}

async function loadPack(name: string): Promise<Record<string, unknown>> {
  return JSON.parse(await readFile(packPath(name), "utf8")) as Record<string, unknown>;
}

function catalogBatch(episodeId = "ep_catalog_12"): Record<string, unknown> {
  let frame = 0;
  const scenes = CATALOG_12.map((motif, index) => {
    const duration = 30;
    const row = {
      scene_id: `cat_${String(index + 1).padStart(2, "0")}`,
      seq_index: index + 1,
      motif_component: motif,
      visual_engine: CATALOG_ENGINES[motif],
      prompt_mode: "NONE",
      start_frame: frame,
      duration_frames: duration,
    };
    frame += duration;
    return row;
  });
  return {
    episode_id: episodeId,
    timeline_spec: {
      fps: 30,
      width: 1920,
      height: 1080,
      frame_count: frame,
      scenes,
    },
  };
}

function readU32(bytes: Uint8Array, offset: number): number {
  return (
    ((bytes[offset] ?? 0) << 24) |
    ((bytes[offset + 1] ?? 0) << 16) |
    ((bytes[offset + 2] ?? 0) << 8) |
    (bytes[offset + 3] ?? 0)
  ) >>> 0;
}

function boxType(bytes: Uint8Array, offset: number): string {
  return String.fromCharCode(bytes[offset + 4] ?? 0, bytes[offset + 5] ?? 0, bytes[offset + 6] ?? 0, bytes[offset + 7] ?? 0);
}

function walkBoxes(bytes: Uint8Array, start: number, end: number): Array<{ type: string; payload: number; next: number }> {
  const found = [];
  let offset = start;
  while (offset + 8 <= end) {
    const size = readU32(bytes, offset);
    if (size < 8 || offset + size > end) throw new Error(`bad box at ${offset}`);
    found.push({ type: boxType(bytes, offset), payload: offset + 8, next: offset + size });
    offset += size;
  }
  if (offset !== end) throw new Error(`boxes ended at ${offset}, expected ${end}`);
  return found;
}

function findBox(bytes: Uint8Array, start: number, end: number, type: string): { payload: number; next: number } {
  const found = walkBoxes(bytes, start, end).find((box) => box.type === type);
  if (!found) throw new Error(`missing ${type}`);
  return found;
}

/** Independent of encodeSceneMp4. Reads mvhd timescale/duration and tkhd 16.16 size. */
function readContainer(bytes: Uint8Array): { timescale: number; duration: number; width: number; height: number; mdhdTimescale: number } {
  const top = walkBoxes(bytes, 0, bytes.length);
  const ftyp = top.find((box) => box.type === "ftyp");
  if (!ftyp) throw new Error("missing ftyp");
  const brand = String.fromCharCode(bytes[ftyp.payload] ?? 0, bytes[ftyp.payload + 1] ?? 0, bytes[ftyp.payload + 2] ?? 0, bytes[ftyp.payload + 3] ?? 0);
  if (brand !== "isom") throw new Error(`brand ${brand}`);
  const moov = top.find((box) => box.type === "moov");
  if (!moov) throw new Error("missing moov");
  const mvhd = findBox(bytes, moov.payload, moov.next, "mvhd");
  const trak = findBox(bytes, moov.payload, moov.next, "trak");
  const tkhd = findBox(bytes, trak.payload, trak.next, "tkhd");
  const mdia = findBox(bytes, trak.payload, trak.next, "mdia");
  const mdhd = findBox(bytes, mdia.payload, mdia.next, "mdhd");
  return {
    timescale: readU32(bytes, mvhd.payload + 12),
    duration: readU32(bytes, mvhd.payload + 16),
    width: readU32(bytes, tkhd.payload + 76) / 65536,
    height: readU32(bytes, tkhd.payload + 80) / 65536,
    mdhdTimescale: readU32(bytes, mdhd.payload + 12),
  };
}

describe("motif route table", () => {
  it("routes the authoritative 12-motif catalog plus the two foreign owners", () => {
    expect(CATALOG_12).toHaveLength(12);
    expect(MVP_MOTIFS).toEqual(["StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame"]);
    const byName = new Map(MOTIF_ROUTES.map((route) => [route.motif_component, route]));
    for (const motif of CATALOG_12) {
      const route = byName.get(motif);
      expect(route?.owner_package).toBe("render_catalog");
      expect(route?.catalog_12).toBe(true);
      expect(route?.visual_engine).toBe(CATALOG_ENGINES[motif]);
      expect(route?.signature_cue).toBe(SIGNATURES[motif]);
      expect(route?.is_mvp_4).toBe((MVP_MOTIFS as readonly string[]).includes(motif));
    }
    expect(byName.get("Illustrative2KPanZoom")).toMatchObject({
      owner_package: "crime_scene_2k",
      visual_engine: "STILL_2K_PANZOOM",
      catalog_12: false,
    });
    expect(byName.get("HeroVideoBridge")).toMatchObject({
      owner_package: "flow_adapter",
      visual_engine: "FLOW_HERO_VIDEO",
      catalog_12: false,
    });
    expect(byName.get("CustomDiagramScene")).toMatchObject({
      owner_package: "render_catalog",
      visual_engine: "CODE_STICKMAN",
      is_mvp_4: false,
      catalog_12: false,
    });
    expect(sceneApplyGrade("FOIA_REAL_FOOTAGE", "FoiaFootageFrame")).toBe(false);
    expect(sceneApplyGrade("CODE_STICKMAN", "StickmanStage")).toBe(true);
    expect(sceneApplyGrade("AUDIO_EVIDENCE_CARD", "AudioEvidenceCard")).toBe(true);
    expect(sceneApplyGrade("STILL_2K_PANZOOM", "Illustrative2KPanZoom")).toBe(true);
    expect(sceneApplyGrade("FLOW_HERO_VIDEO", "HeroVideoBridge")).toBe(true);
  });
});

describe("full catalog and mvp slice", () => {
  it("compiles all 12 motifs to 1080p30 mp4s and one ungraded manifest", async () => {
    const dir = await tempDir();
    const result = await compileTimelineBatch(catalogBatch(), { outDir: dir });
    expect(result.mode).toBe("full");
    expect(result.fps).toBe(30);
    expect(result.width_px).toBe(1920);
    expect(result.height_px).toBe(1080);
    expect(result.mp4s).toHaveLength(12);
    expect(result.grade_manifest.single_grade_pass).toBe(true);
    expect(result.grade_manifest.remotion_grain_applied).toBe(false);
    expect(result.grade_manifest.remotion_vignette_applied).toBe(false);
    expect(result.grade_manifest.paper_grain).toBe(0);
    expect(result.grade_manifest.vignette).toBe(0);
    expect(result.grade_manifest.grade_owner).toBe("agent6_single_pass");
    expect(result.grade_manifest.scenes).toHaveLength(12);
    expect(result.grade_manifest.scenes.map((scene) => scene.motif_component)).toEqual([...CATALOG_12]);
    expect(result.grade_manifest.scenes.every((scene) => scene.routed && scene.compile_status === "compiled")).toBe(true);
    expect(result.grade_manifest.scenes.every((scene) => scene.remotion_grain_applied === false && scene.paper_grain === 0 && scene.vignette === 0)).toBe(true);
    const foia = result.grade_manifest.scenes.find((scene) => scene.motif_component === "FoiaFootageFrame");
    const audio = result.grade_manifest.scenes.find((scene) => scene.motif_component === "AudioEvidenceCard");
    expect(foia?.apply_grade).toBe(false);
    expect(foia?.needs_grade).toBe(false);
    expect(foia?.is_foia).toBe(true);
    expect(foia?.exempt_from_grain).toBe(true);
    expect(foia?.grade_owner).toBe("none");
    expect(audio?.apply_grade).toBe(true);
    expect(audio?.grade_owner).toBe("agent6_single_pass");
    expect(result.grade_manifest.scenes.filter((scene) => scene.apply_grade)).toHaveLength(11);
    expect(new Set(result.micro_sfx.cues.map((cue) => cue.cue))).toEqual(
      new Set(["tape_click", "highlighter_glide", "radio_squelch", "tick_sfx", "conflict_stamp", "pin_thud", "camera_shutter"]),
    );
    const onDisk = JSON.parse(await readFile(result.grade_manifest_path, "utf8")) as SceneGradeManifest;
    expect(onDisk.filename).toBe(SCENE_GRADE_MANIFEST_FILENAME);
    expect(onDisk.scenes.map((scene) => scene.apply_grade)).toEqual(result.grade_manifest.scenes.map((scene) => scene.apply_grade));
    const sfx = JSON.parse(await readFile(result.micro_sfx_path, "utf8")) as MicroSfxDocument;
    expect(sfx.filename).toBe(MICRO_SFX_CUES_FILENAME);
    expect(sfx.cooldown_ms).toBe(60);
    expect(sfx.sample_rate_hz).toBe(48000);
    for (const receipt of result.mp4s) {
      const bytes = await readFile(receipt.path);
      const container = readContainer(bytes);
      expect(container).toEqual({
        timescale: FRAME_FPS,
        duration: receipt.duration_frames,
        width: FRAME_WIDTH,
        height: FRAME_HEIGHT,
        mdhdTimescale: FRAME_FPS,
      });
      const text = Buffer.from(bytes).toString("latin1").toLowerCase();
      expect(text).not.toContain("feturbulence");
      expect(text).not.toContain("fedisplacementmap");
      expect(text).not.toContain("vignette");
    }
  });

  it("keeps --mvp-4-motifs to the four MVP motifs and still records the other eight", async () => {
    const fullDir = await tempDir();
    const mvpDir = await tempDir();
    const source = catalogBatch();
    const full = await compileTimelineBatch(source, { outDir: fullDir });
    const mvp = await compileTimelineBatch(source, { outDir: mvpDir, mvp4Motifs: true });
    expect(mvp.mode).toBe("mvp-4-motifs");
    expect(mvp.mp4s.map((item) => item.scene_id)).toEqual(["cat_01", "cat_02", "cat_03", "cat_04"]);
    expect(mvp.grade_manifest.scenes).toHaveLength(12);
    const outside = mvp.grade_manifest.scenes.filter((scene) => scene.compile_status === "out_of_slice");
    expect(outside).toHaveLength(8);
    expect(outside.every((scene) => scene.mp4_relpath === null && scene.owner_package === "render_catalog")).toBe(true);
    expect(mvp.grade_manifest.scenes.filter((scene) => scene.motif_component === "FoiaFootageFrame")[0]?.apply_grade).toBe(false);
    expect(mvp.grade_manifest.scenes.filter((scene) => scene.motif_component === "StickmanStage")[0]?.apply_grade).toBe(true);
    expect(mvp.micro_sfx.cues.map((cue) => cue.cue).sort()).toEqual(["highlighter_glide", "radio_squelch", "tape_click"]);
    expect(full.mp4s).toHaveLength(12);
    const names = await readdir(mvpDir);
    expect(names.filter((name) => name.endsWith(".mp4"))).toHaveLength(4);
    expect(names).toContain(SCENE_GRADE_MANIFEST_FILENAME);
    expect(names).toContain(MICRO_SFX_CUES_FILENAME);
  });

  it("compiles CustomDiagramScene in the full catalog and leaves it out of the mvp slice", async () => {
    const source = {
      episode_id: "ep_diagram",
      timeline_spec: {
        fps: 30,
        width: 1920,
        height: 1080,
        frame_count: 30,
        scenes: [
          {
            scene_id: "diagram_1",
            seq_index: 1,
            motif_component: "CustomDiagramScene",
            visual_engine: "CODE_STICKMAN",
            prompt_mode: "NONE",
            start_frame: 0,
            duration_frames: 30,
          },
        ],
      },
    };
    const full = await compileTimelineBatch(source, { outDir: await tempDir() });
    expect(full.mp4s).toHaveLength(1);
    expect(full.grade_manifest.scenes[0]).toMatchObject({
      motif_component: "CustomDiagramScene",
      compile_status: "compiled",
      apply_grade: true,
      owner_package: "render_catalog",
    });
    const mvp = await compileTimelineBatch(source, { outDir: await tempDir(), mvp4Motifs: true });
    expect(mvp.mp4s).toHaveLength(0);
    expect(mvp.grade_manifest.scenes[0]?.compile_status).toBe("out_of_slice");
  });
});

describe("fallback swaps and grade metadata", () => {
  it("swaps SWITCHED_TO_FALLBACK onto StickmanStage without a timeline gap", async () => {
    const source = {
      episode_id: "ep_swap",
      timeline_spec: {
        fps: 30,
        width: 1920,
        height: 1080,
        frame_count: 90,
        scenes: [
          { scene_id: "raw_before", seq_index: 1, motif_component: "FoiaFootageFrame", visual_engine: "FOIA_REAL_FOOTAGE", prompt_mode: "NONE", start_frame: 0, duration_frames: 30 },
          { scene_id: "hero_mid", seq_index: 2, motif_component: "HeroVideoBridge", visual_engine: "FLOW_HERO_VIDEO", prompt_mode: "TEXT_TO_VIDEO", start_frame: 30, duration_frames: 30 },
          { scene_id: "raw_after", seq_index: 3, motif_component: "FoiaFootageFrame", visual_engine: "FOIA_REAL_FOOTAGE", prompt_mode: "NONE", start_frame: 60, duration_frames: 30 },
        ],
      },
      flow_job_cards: [
        {
          scene_id: "hero_mid",
          state: "SWITCHED_TO_FALLBACK",
          fallback_spec_json: { engine: "CODE_STICKMAN", motif_component: "StickmanStage", reason: "strike 2" },
        },
      ],
    };
    const result = await compileTimelineBatch(source, { outDir: await tempDir() });
    expect(result.mp4s.map((item) => item.scene_id)).toEqual(["raw_before", "hero_mid", "raw_after"]);
    const swapped = result.grade_manifest.scenes[1];
    expect(swapped).toMatchObject({
      requested_motif_component: "HeroVideoBridge",
      requested_visual_engine: "FLOW_HERO_VIDEO",
      motif_component: "StickmanStage",
      visual_engine: "CODE_STICKMAN",
      fallback_applied: true,
      gap_ms: 0,
      apply_grade: true,
      compile_status: "compiled",
      owner_package: "render_catalog",
      duration_frames: 30,
      start_frame: 30,
    });
    expect(result.grade_manifest.scenes[0]?.apply_grade).toBe(false);
    expect(result.grade_manifest.scenes[2]?.apply_grade).toBe(false);
    expect(result.grade_manifest.scenes.filter((scene) => scene.apply_grade).map((scene) => scene.scene_id)).toEqual(["hero_mid"]);
  });

  it("does not swap an accepted hero that still carries a latent fallback", async () => {
    const source = {
      episode_id: "ep_accepted",
      timeline_spec: {
        fps: 30,
        width: 1920,
        height: 1080,
        frame_count: 30,
        scenes: [
          { scene_id: "hero_ok", seq_index: 1, motif_component: "HeroVideoBridge", visual_engine: "FLOW_HERO_VIDEO", prompt_mode: "FIRST_FRAME", start_frame: 0, duration_frames: 30 },
        ],
      },
      flow_job_cards: [
        {
          scene_id: "hero_ok",
          state: "ACCEPTED",
          fallback_spec_json: { engine: "CODE_STICKMAN", motif_component: "StickmanStage" },
        },
      ],
    };
    const result = await compileTimelineBatch(source, { outDir: await tempDir() });
    expect(result.mp4s).toHaveLength(0);
    expect(result.grade_manifest.scenes[0]).toMatchObject({
      motif_component: "HeroVideoBridge",
      visual_engine: "FLOW_HERO_VIDEO",
      fallback_applied: false,
      compile_status: "delegated",
      owner_package: "flow_adapter",
      apply_grade: true,
      mp4_relpath: null,
    });
  });

  it("rejects a fallback that matches a neighboring engine", async () => {
    const source = {
      episode_id: "ep_neighbor",
      timeline_spec: {
        fps: 30,
        width: 1920,
        height: 1080,
        frame_count: 90,
        scenes: [
          { scene_id: "still_before", seq_index: 1, motif_component: "Illustrative2KPanZoom", visual_engine: "STILL_2K_PANZOOM", prompt_mode: "NONE", start_frame: 0, duration_frames: 30 },
          { scene_id: "hero_mid", seq_index: 2, motif_component: "HeroVideoBridge", visual_engine: "FLOW_HERO_VIDEO", prompt_mode: "TEXT_TO_VIDEO", start_frame: 30, duration_frames: 30 },
          { scene_id: "stage_after", seq_index: 3, motif_component: "StickmanStage", visual_engine: "CODE_STICKMAN", prompt_mode: "NONE", start_frame: 60, duration_frames: 30 },
        ],
      },
      flow_job_cards: [
        {
          scene_id: "hero_mid",
          state: "SWITCHED_TO_FALLBACK",
          fallback_spec_json: { visual_engine: "STILL_2K_PANZOOM", motif_component: "Illustrative2KPanZoom", rule: "RULE_04" },
        },
      ],
    };
    const dir = await tempDir();
    await expect(compileTimelineBatch(source, { outDir: dir })).rejects.toThrow(/RULE_04: fallback engine matches the previous scene/);
    expect(await readdir(dir)).toEqual([]);
  });

  it("rejects an unknown motif, an engine mismatch, a banned SVG filter, and a broken clock", async () => {
    const base = catalogBatch("ep_bad");
    const scenes = (base.timeline_spec as { scenes: Array<Record<string, unknown>> }).scenes;
    const drifted = structuredClone(base);
    (drifted.timeline_spec as { scenes: Array<Record<string, unknown>> }).scenes[0] = {
      ...scenes[0],
      motif_component: "SmsPhoneThread",
      visual_engine: "CODE_STICKMAN",
    };
    await expect(compileTimelineBatch(drifted, { outDir: await tempDir() })).rejects.toMatchObject({
      code: "UNKNOWN_MOTIF",
    });

    const mismatch = structuredClone(base);
    (mismatch.timeline_spec as { scenes: Array<Record<string, unknown>> }).scenes[0] = {
      ...scenes[0],
      visual_engine: "FOIA_REAL_FOOTAGE",
    };
    await expect(compileTimelineBatch(mismatch, { outDir: await tempDir() })).rejects.toMatchObject({
      code: "ENGINE_MISMATCH",
    });

    const svg = structuredClone(base);
    (svg.timeline_spec as { scenes: Array<Record<string, unknown>> }).scenes[0] = {
      ...scenes[0],
      note: "<feTurbulence>",
    };
    const svgDir = await tempDir();
    await expect(compileTimelineBatch(svg, { outDir: svgDir })).rejects.toBeInstanceOf(BatchCompilerError);
    await expect(compileTimelineBatch(svg, { outDir: svgDir })).rejects.toThrow(/SVG_FILTER/);
    expect(await readdir(svgDir)).toEqual([]);

    const gap = structuredClone(base);
    const gapScenes = (gap.timeline_spec as { scenes: Array<Record<string, unknown>> }).scenes;
    gapScenes[1] = { ...gapScenes[1], start_frame: 90 };
    await expect(compileTimelineBatch(gap, { outDir: await tempDir() })).rejects.toThrow(/FRAME_CLOCK/);
  });

  it("suppresses a second micro-SFX inside the 60 ms cooldown", async () => {
    const source = {
      episode_id: "ep_sfx",
      timeline_spec: {
        fps: 30,
        width: 1920,
        height: 1080,
        frame_count: 30,
        scenes: [
          { scene_id: "stage_1", seq_index: 1, motif_component: "StickmanStage", visual_engine: "CODE_STICKMAN", prompt_mode: "NONE", start_frame: 0, duration_frames: 30 },
        ],
      },
      micro_sfx: [
        { scene_id: "stage_1", cue: "tape_click", offset_ms: 0 },
        { scene_id: "stage_1", cue: "typing_tap", offset_ms: 10 },
      ],
    };
    const result = await compileTimelineBatch(source, { outDir: await tempDir() });
    expect(result.micro_sfx.cues).toHaveLength(1);
    expect(result.micro_sfx.cues[0]).toMatchObject({
      cue: "tape_click",
      scene_id: "stage_1",
      start_sample: 0,
      offset_ms: 0,
      cooldown_ms: 60,
      sample_rate_hz: 48000,
      tapered: false,
    });
    expect(result.micro_sfx.suppressed).toEqual([
      { cue: "typing_tap", scene_id: "stage_1", start_sample: 480, reason: "cooldown" },
    ]);
    await expect(compileTimelineBatch({ ...source, micro_sfx: [{ scene_id: "stage_1", cue: "room_tone", offset_ms: 0 }] }, { outDir: await tempDir() })).rejects.toMatchObject({
      code: "UNKNOWN_CUE",
    });
  });
});

describe("golden packs", () => {
  it("routes every scene in all three packs, including the two-strike fallback", async () => {
    const outputs: string[] = [];
    for (const name of PACKS) {
      const pack = await loadPack(name);
      const first = await compileTimelineBatch(pack, { outDir: await tempDir() });
      const second = await compileTimelineBatch(pack, { outDir: await tempDir() });
      const mvp = await compileTimelineBatch(pack, { outDir: await tempDir(), mvp4Motifs: true });
      expect(first.episode_id).toBe(name);
      expect(first.grade_manifest.scenes).toHaveLength(36);
      expect(first.grade_manifest.scenes.every((scene) => scene.routed)).toBe(true);
      expect(new Set(first.grade_manifest.scenes.map((scene) => scene.scene_id)).size).toBe(36);
      expect(first.grade_manifest.fps).toBe(30);
      expect(first.grade_manifest.width_px).toBe(1920);
      expect(first.grade_manifest.height_px).toBe(1080);
      expect(first.grade_manifest.remotion_grain_applied).toBe(false);
      expect(first.grade_manifest.paper_grain).toBe(0);
      expect(first.grade_manifest.vignette).toBe(0);
      expect(first.grade_manifest.single_grade_pass).toBe(true);
      const compiled = first.grade_manifest.scenes.filter((scene) => scene.compile_status === "compiled");
      expect(compiled).toHaveLength(19);
      expect(new Set(compiled.map((scene) => scene.motif_component))).toEqual(new Set(MVP_MOTIFS));
      expect(compiled.every((scene) => scene.mp4_relpath === `${scene.scene_id}.mp4`)).toBe(true);
      expect(first.mp4s).toHaveLength(19);
      expect(mvp.mp4s.map((item) => item.scene_id)).toEqual(first.mp4s.map((item) => item.scene_id));
      expect(mvp.grade_manifest.scenes.map((scene) => [scene.scene_id, scene.apply_grade, scene.compile_status])).toEqual(
        first.grade_manifest.scenes.map((scene) => [scene.scene_id, scene.apply_grade, scene.compile_status]),
      );
      const foia = first.grade_manifest.scenes.filter((scene) => scene.visual_engine === "FOIA_REAL_FOOTAGE");
      const stylized = first.grade_manifest.scenes.filter((scene) => scene.visual_engine !== "FOIA_REAL_FOOTAGE");
      expect(foia.length).toBeGreaterThan(0);
      expect(stylized.length).toBeGreaterThan(0);
      expect(foia.every((scene) => scene.apply_grade === false && scene.is_foia === true && scene.grade_owner === "none")).toBe(true);
      expect(stylized.every((scene) => scene.apply_grade === true && scene.grade_owner === "agent6_single_pass")).toBe(true);
      const delegated = first.grade_manifest.scenes.filter((scene) => scene.compile_status === "delegated");
      expect(delegated.every((scene) => scene.owner_package !== "render_catalog" && scene.mp4_relpath === null)).toBe(true);
      expect(first.micro_sfx.cues.map((cue) => cue.cue).sort()).toEqual(
        ["highlighter_glide", "highlighter_glide", "highlighter_glide", "radio_squelch", "radio_squelch", "radio_squelch", "tape_click", "tape_click", "tape_click"],
      );
      expect(first.micro_sfx.cues.every((cue) => cue.peak_dbtp <= -1 && cue.cooldown_ms === 60)).toBe(true);
      const gradeText = await readFile(first.grade_manifest_path, "utf8");
      const gradeAgain = await readFile(second.grade_manifest_path, "utf8");
      expect(gradeAgain).toBe(gradeText);
      const sfxText = await readFile(first.micro_sfx_path, "utf8");
      expect(await readFile(second.micro_sfx_path, "utf8")).toBe(sfxText);
      const sample = first.mp4s[0];
      if (!sample) throw new Error("missing compiled mp4");
      const mirror = second.mp4s.find((item) => item.scene_id === sample.scene_id);
      expect(Buffer.from(await readFile(sample.path)).equals(Buffer.from(await readFile(mirror?.path ?? "")))).toBe(true);
      const container = readContainer(await readFile(sample.path));
      expect(container.width).toBe(1920);
      expect(container.height).toBe(1080);
      expect(container.timescale).toBe(30);
      expect(container.duration).toBe(sample.duration_frames);
      outputs.push(name);
    }
    expect(outputs).toEqual([...PACKS]);

    const fallbackPack = await loadPack("ep_golden_02_2strike_fallback");
    const fallback = await compileTimelineBatch(fallbackPack, { outDir: await tempDir() });
    const swapped = fallback.grade_manifest.scenes.find((scene) => scene.scene_id === "ep_golden_02_2strike_fallback_s029");
    const strike = fallback.grade_manifest.scenes.find((scene) => scene.scene_id === "ep_golden_02_2strike_fallback_s008");
    expect(swapped).toMatchObject({
      requested_motif_component: "HeroVideoBridge",
      requested_visual_engine: "FLOW_HERO_VIDEO",
      motif_component: "Illustrative2KPanZoom",
      visual_engine: "STILL_2K_PANZOOM",
      owner_package: "crime_scene_2k",
      compile_status: "delegated",
      fallback_applied: true,
      gap_ms: 0,
      apply_grade: true,
      flow_state: "SWITCHED_TO_FALLBACK",
      mp4_relpath: null,
    });
    expect(fallback.mp4s.some((item) => item.scene_id === swapped?.scene_id)).toBe(false);
    expect(strike).toMatchObject({
      motif_component: "HeroVideoBridge",
      visual_engine: "FLOW_HERO_VIDEO",
      compile_status: "withheld",
      fallback_applied: false,
      apply_grade: true,
      flow_state: "STRIKE_1_RETRY_SAFE",
      mp4_relpath: null,
    });
    const accepted = fallback.grade_manifest.scenes.filter((scene) => scene.flow_state === "ACCEPTED");
    expect(accepted).toHaveLength(8);
    expect(accepted.every((scene) => scene.fallback_applied === false && scene.motif_component === "HeroVideoBridge")).toBe(true);
  });
});

describe("scene container", () => {
  it("encodes a 1080p30 box that a separate parser can read", () => {
    const bytes = encodeSceneMp4(1200);
    expect(readContainer(bytes)).toEqual({
      timescale: 30,
      duration: 1200,
      width: 1920,
      height: 1080,
      mdhdTimescale: 30,
    });
  });
});
