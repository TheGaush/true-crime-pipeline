import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import {
  SINGLE_SCENE_RERENDER_BUDGET_MS,
  RenderPool,
  boilTick,
  canonicalJson,
  countBoilTicks,
  ffprobeVerify,
  hashCaseBible,
  headlessChildEnv,
  identifyScene,
  importedRemotionRoot,
  sceneArtifactPaths,
  sceneCacheKey,
  sha256Hex,
  ungradedPlateArgs,
  writeUngradedPlate,
  type FfprobeResult,
  type HeadlessRenderRequest,
  type SceneRenderJob,
} from "../src/renderer/RenderPool.ts";

const BIBLE = { episode_id: "ep_test", paper_bg_hex: "#E9E2D2" };
const PACK_PATH = fileURLToPath(
  new URL("../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url),
);

let dirs: string[] = [];

afterEach(async () => {
  await Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true })));
  dirs = [];
});

async function tempDir(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "tc-render-pool-"));
  dirs.push(dir);
  return dir;
}

function bibleHash(): string {
  return hashCaseBible(BIBLE);
}

function stickScene(id: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    scene_id: id,
    visual_engine: "CODE_STICKMAN",
    motif_component: "StickmanStage",
    timeline_spec_json: { fps: 30, duration_frames: 3 },
    start_ms: 0,
    end_ms: 100,
    ...extra,
  };
}

function job(scene: Record<string, unknown>, caseBibleHash = bibleHash()): SceneRenderJob {
  return { scene, caseBibleHash };
}

async function markerProbe(filePath: string): Promise<FfprobeResult> {
  const text = await readFile(filePath, "utf8");
  if (text !== "plate-ok") return { ok: false, reason: "marker" };
  return { ok: true, width: 1920, height: 1080, fps: 30 };
}

async function writeMarker(request: HeadlessRenderRequest): Promise<void> {
  await writeFile(request.outputPath, "plate-ok");
}

function delay(ms: number): Promise<void> {
  return new Promise((resolvePromise) => {
    setTimeout(resolvePromise, ms);
  });
}

describe("canonical scene cache key", () => {
  it("hashes canonical scene JSON concatenated with the case bible hash", () => {
    const scene = stickScene("scene_key", { b: 1, a: { d: 2, c: 3 } });
    const reversed = {
      a: { c: 3, d: 2 },
      b: 1,
      end_ms: 100,
      motif_component: "StickmanStage",
      scene_id: "scene_key",
      start_ms: 0,
      timeline_spec_json: { duration_frames: 3, fps: 30 },
      visual_engine: "CODE_STICKMAN",
    };
    const json = canonicalJson(scene);
    expect(canonicalJson(reversed)).toBe(json);
    expect(json.startsWith('{"a":')).toBe(true);
    const hash = bibleHash();
    const key = sceneCacheKey(json, hash);
    const independent = createHash("sha256").update(`${json}${hash}`, "utf8").digest("hex");
    expect(key).toBe(independent);
    expect(key).toBe(sha256Hex(`${json}${hash}`));
    expect(sceneCacheKey(json, hashCaseBible({ paper_bg_hex: "#111111", episode_id: "ep_test" }))).not.toBe(key);
    expect(sceneCacheKey(canonicalJson(stickScene("scene_other")), hash)).not.toBe(key);
  });

  it("rejects non-finite scene numbers and SVG turbulence filters", () => {
    expect(() => canonicalJson({ value: Number.NaN })).toThrow(/non-finite/);
    expect(() => identifyScene({ scene_id: "s", note: "<feTurbulence>" }, bibleHash(), "/tmp")).toThrow(/feTurbulence/);
    expect(() => identifyScene({ scene_id: "s", note: "feDisplacementMap" }, bibleHash(), "/tmp")).toThrow(/feDisplacementMap/);
  });

  it("holds the JS boil on a 6 fps tick at 30 fps", () => {
    expect(boilTick(0)).toBe(0);
    expect(boilTick(4)).toBe(0);
    expect(boilTick(5)).toBe(1);
    expect(boilTick(9)).toBe(1);
    expect(boilTick(10)).toBe(2);
    expect(countBoilTicks(3)).toBe(1);
    expect(countBoilTicks(6)).toBe(2);
  });
});

describe("worker pool", () => {
  it("bundles once and keeps input order under the concurrency cap", async () => {
    const dir = await tempDir();
    let bundles = 0;
    let active = 0;
    let maxActive = 0;
    const seen: HeadlessRenderRequest[] = [];
    const pool = new RenderPool({
      cacheDir: dir,
      concurrency: 2,
      bundle: async () => {
        bundles += 1;
        await delay(15);
        return { compositionId: "TrueCrimeEpisode", fps: 30, width: 1920, height: 1080 };
      },
      render: async (request) => {
        active += 1;
        maxActive = Math.max(maxActive, active);
        seen.push(request);
        await delay(request.sceneId === "scene_a" ? 40 : 10);
        active -= 1;
        await writeMarker(request);
      },
      ffprobe: markerProbe,
    });
    const receipts = await pool.renderScenes([
      job(stickScene("scene_a")),
      job(stickScene("scene_b")),
      job(stickScene("scene_c")),
      job(stickScene("scene_d")),
    ]);
    expect(receipts.map((receipt) => receipt.sceneId)).toEqual(["scene_a", "scene_b", "scene_c", "scene_d"]);
    expect(bundles).toBe(1);
    expect(maxActive).toBe(2);
    expect(new Set(receipts.map((receipt) => receipt.compositionId))).toEqual(new Set(["TrueCrimeEpisode"]));
    expect(seen.every((request) => request.outputPath.endsWith(".tmp.mp4"))).toBe(true);
    expect(seen.every((request) => request.fps === 30 && request.width === 1920 && request.height === 1080)).toBe(true);
    expect(seen.every((request) => request.boil.boilFps === 6 && request.boil.frameStride === 5)).toBe(true);
    expect(seen.every((request) => request.boil.quantizer === "Math.floor(frame / 5)")).toBe(true);
    expect(seen.every((request) => request.boil.svgTurbulence === false && request.boil.svgDisplacementMap === false)).toBe(true);
    expect(seen.every((request) => request.grade.paperGrain === 0 && request.grade.vignette === 0)).toBe(true);
    expect(receipts.every((receipt) => existsSync(receipt.outputPath) && !existsSync(receipt.outputPath.replace(/\.mp4$/, ".tmp.mp4")))).toBe(true);
  });

  it("renders one in-flight scene once and misses the cache when the scene changes", async () => {
    const dir = await tempDir();
    let renders = 0;
    const pool = new RenderPool({
      cacheDir: dir,
      render: async (request) => {
        renders += 1;
        await delay(20);
        await writeMarker(request);
      },
      ffprobe: markerProbe,
    });
    const original = stickScene("scene_once");
    const [first, second] = await Promise.all([
      pool.renderScene(job(original)),
      pool.renderScene(job(original)),
    ]);
    expect(renders).toBe(1);
    expect(first.cacheKey).toBe(second.cacheKey);
    expect(first.outputPath).toBe(second.outputPath);
    const changed = stickScene("scene_once", { emotional_peak_score: 0.2 });
    const third = await pool.renderScene(job(changed));
    expect(renders).toBe(2);
    expect(third.cacheKey).not.toBe(first.cacheKey);
    expect(third.cacheHit).toBe(false);
    const replay = await pool.renderScene(job(original));
    expect(replay.cacheHit).toBe(true);
    expect(renders).toBe(2);
    const otherBible = await pool.renderScene(job(original, hashCaseBible({ episode_id: "ep_test", paper_bg_hex: "#111111" })));
    expect(otherBible.cacheHit).toBe(false);
    expect(renders).toBe(3);
  });

  it("ffprobes the tmp mp4 before renaming it", async () => {
    const dir = await tempDir();
    const scene = stickScene("scene_order");
    const paths = sceneArtifactPaths(dir, sceneCacheKey(canonicalJson(scene), bibleHash()));
    const events: string[] = [];
    const pool = new RenderPool({
      cacheDir: dir,
      render: async (request) => {
        events.push("render");
        expect(request.outputPath).toBe(paths.tmpPath);
        expect(existsSync(paths.finalPath)).toBe(false);
        await writeMarker(request);
      },
      ffprobe: async (filePath) => {
        events.push(filePath === paths.tmpPath ? "probe-tmp" : "probe-final");
        if (filePath === paths.tmpPath) expect(existsSync(paths.finalPath)).toBe(false);
        return markerProbe(filePath);
      },
    });
    const receipt = await pool.renderScene(job(scene));
    expect(events).toEqual(["render", "probe-tmp"]);
    expect(receipt.cacheHit).toBe(false);
    expect(receipt.recoveredFromTmp).toBe(false);
    expect(existsSync(paths.finalPath)).toBe(true);
    expect(existsSync(paths.tmpPath)).toBe(false);
    const grade = JSON.parse(await readFile(receipt.gradePath, "utf8")) as { scenes: Array<{ apply_grade: boolean; paper_grain: number; vignette: number }> };
    expect(grade.scenes[0]?.apply_grade).toBe(true);
    expect(grade.scenes[0]?.paper_grain).toBe(0);
    expect(grade.scenes[0]?.vignette).toBe(0);
    const again = await pool.renderScene(job(scene));
    expect(again.cacheHit).toBe(true);
    expect(events).toEqual(["render", "probe-tmp", "probe-final"]);
  });

  it("does not publish a scene that misses the 5s budget", async () => {
    const dir = await tempDir();
    let clock = 0;
    const scene = stickScene("scene_budget");
    const paths = sceneArtifactPaths(dir, sceneCacheKey(canonicalJson(scene), bibleHash()));
    const pool = new RenderPool({
      cacheDir: dir,
      now: () => clock,
      render: async (request) => {
        clock += SINGLE_SCENE_RERENDER_BUDGET_MS;
        await writeMarker(request);
      },
      ffprobe: markerProbe,
    });
    await expect(pool.renderScene(job(scene))).rejects.toThrow(/budget is 5000 ms/);
    expect(existsSync(paths.finalPath)).toBe(false);
    expect(existsSync(paths.tmpPath)).toBe(false);
  });

  it("drops a failed render and accepts the retry", async () => {
    const dir = await tempDir();
    let fail = true;
    const pool = new RenderPool({
      cacheDir: dir,
      render: async (request) => {
        if (fail) {
          fail = false;
          throw new Error("interrupted");
        }
        await writeMarker(request);
      },
      ffprobe: markerProbe,
    });
    await expect(pool.renderScene(job(stickScene("scene_retry")))).rejects.toThrow(/interrupted/);
    const receipt = await pool.renderScene(job(stickScene("scene_retry")));
    expect(receipt.cacheHit).toBe(false);
    expect(existsSync(receipt.outputPath)).toBe(true);
  });

  it("rejects a renderer that writes the final path directly", async () => {
    const dir = await tempDir();
    const pool = new RenderPool({
      cacheDir: dir,
      render: async (request) => {
        await writeFile(request.outputPath.replace(/\.tmp\.mp4$/, ".mp4"), "plate-ok");
        await writeMarker(request);
      },
      ffprobe: markerProbe,
    });
    await expect(pool.renderScene(job(stickScene("scene_direct")))).rejects.toThrow(/rename/);
  });

  it("rejects a 60 fps root, a bad boil module, grain, and SVG scenes before rendering", async () => {
    const dir = await tempDir();
    let renders = 0;
    const render = async () => {
      renders += 1;
    };
    expect(() => new RenderPool({
      cacheDir: dir,
      remotionRoot: { id: "TrueCrimeEpisode", fps: 60, width: 1920, height: 1080 },
      render,
    })).toThrow(/30 fps/);
    expect(importedRemotionRoot()).toBeNull();

    const boilPath = join(dir, "boil-bad.mjs");
    await writeFile(boilPath, "export const BOIL_FPS = 12;\nexport const CONTAINER_FPS = 30;\nexport const BOIL_FRAME_STRIDE = 5;\n");
    const boilPool = new RenderPool({ cacheDir: dir, boilModulePath: boilPath, render, ffprobe: markerProbe });
    await expect(boilPool.renderScene(job(stickScene("scene_boil")))).rejects.toThrow(/6 fps/);

    const gradePath = join(dir, "grade-grain.mjs");
    await writeFile(gradePath, "export const REMOTION_PAPER_GRAIN = 1;\nexport const REMOTION_VIGNETTE = 0;\n");
    const gradePool = new RenderPool({ cacheDir: dir, gradeModulePath: gradePath, render, ffprobe: markerProbe });
    await expect(gradePool.renderScene(job(stickScene("scene_grain")))).rejects.toThrow(/REMOTION_PAPER_GRAIN/);

    const clean = new RenderPool({ cacheDir: dir, render, ffprobe: markerProbe });
    await expect(clean.renderScene(job(stickScene("scene_svg", { note: "<feTurbulence>" })))).rejects.toThrow(/feTurbulence/);
    expect(renders).toBe(0);
  });

  it("uses a Task 109 grade module for apply_grade and keeps FOIA ungraded", async () => {
    const dir = await tempDir();
    const gradePath = join(dir, "grade-ok.mjs");
    await writeFile(
      gradePath,
      [
        "export const REMOTION_PAPER_GRAIN = 0;",
        "export const REMOTION_VIGNETTE = 0;",
        "export const FRAME_FPS = 30;",
        "export const FRAME_WIDTH = 1920;",
        "export const FRAME_HEIGHT = 1080;",
        "export function sceneNeedsGrade(scene) { return scene.scene_id === 'needs_grade'; }",
        "export function buildSceneGradeManifest(scenes, episodeId) {",
        "  return { schema: 'scene_grade_manifest.v1', from: 'task-109', episode_id: episodeId ?? null, paper_grain: 0, vignette: 0,",
        "    scenes: scenes.map((scene) => ({ scene_id: scene.scene_id, apply_grade: scene.scene_id === 'needs_grade', needs_grade: scene.scene_id === 'needs_grade', remotion_grain_applied: false, remotion_vignette_applied: false, paper_grain: 0, vignette: 0 })) };",
        "}",
        "",
      ].join("\n"),
    );
    const pool = new RenderPool({
      cacheDir: dir,
      gradeModulePath: gradePath,
      render: writeMarker,
      ffprobe: markerProbe,
    });
    const graded = await pool.renderScene(job(stickScene("needs_grade", { episode_id: "ep_grade" })));
    const raw = await pool.renderScene(job(stickScene("plain_scene")));
    expect(graded.applyGrade).toBe(true);
    expect(raw.applyGrade).toBe(false);
    const sidecar = JSON.parse(await readFile(graded.gradePath, "utf8")) as { from: string; paper_grain: number; vignette: number };
    expect(sidecar.from).toBe("task-109");
    expect(sidecar.paper_grain).toBe(0);
    expect(sidecar.vignette).toBe(0);

    const foia = new RenderPool({ cacheDir: join(dir, "foia"), render: writeMarker, ffprobe: markerProbe });
    const foiaReceipt = await foia.renderScene(job({
      scene_id: "scene_foia",
      visual_engine: "FOIA_REAL_FOOTAGE",
      motif_component: "FoiaFootageFrame",
      timeline_spec_json: { fps: 30, duration_frames: 3 },
      start_ms: 0,
      end_ms: 100,
    }));
    expect(foiaReceipt.applyGrade).toBe(false);
    const foiaGrade = JSON.parse(await readFile(foiaReceipt.gradePath, "utf8")) as { scenes: Array<{ apply_grade: boolean; paper_grain: number }> };
    expect(foiaGrade.scenes[0]?.apply_grade).toBe(false);
    expect(foiaGrade.scenes[0]?.paper_grain).toBe(0);
  });

  it("does not pass provider keys to the headless encoder", () => {
    const provider = ["GEMINI", "API_KEY"].join("_");
    const env = headlessChildEnv({ PATH: "/usr/bin", HOME: "/tmp", [provider]: "abcdefghij" });
    expect(env.PATH).toBe("/usr/bin");
    expect(env[provider]).toBeUndefined();
    expect(JSON.stringify(env)).not.toContain("abcdefghij");
    const args = ungradedPlateArgs("/tmp/scene.tmp.mp4", { durationFrames: 3, paperBgHex: "#E9E2D2" });
    expect(args.join("\n")).toContain("color=c=0xE9E2D2:s=1920x1080:r=30");
    expect(args.join("\n").toLowerCase()).not.toContain("feturbulence");
    expect(args.join("\n").toLowerCase()).not.toContain("noise");
    expect(args.join("\n").toLowerCase()).not.toContain("vignette");
  });
});

describe("default headless encoder", () => {
  it("bundles once, encodes a 1920x1080 @ 30 fps plate, and serves the cache", async () => {
    const dir = await tempDir();
    const pool = new RenderPool({ cacheDir: dir, concurrency: 1 });
    expect(await pool.renderScenes([])).toEqual([]);
    const receipt = await pool.renderScene(job(stickScene("scene_default")));
    expect(receipt.compositionId).toBe("TrueCrimeEpisode");
    expect(receipt.cacheHit).toBe(false);
    expect(receipt.durationFrames).toBe(3);
    expect(receipt.fps).toBe(30);
    expect(receipt.paperGrain).toBe(0);
    expect(receipt.vignette).toBe(0);
    expect(receipt.svgTurbulence).toBe(false);
    expect(receipt.workMs).toBeLessThan(SINGLE_SCENE_RERENDER_BUDGET_MS);
    expect((await ffprobeVerify(receipt.outputPath, 3)).ok).toBe(true);
    const cached = await pool.renderScene(job(stickScene("scene_default")));
    expect(cached.cacheHit).toBe(true);
    expect(cached.outputPath).toBe(receipt.outputPath);
  });
});

describe("ffprobe publish", () => {
  it("renames a leftover valid tmp mp4 and re-renders a corrupt one", async () => {
    const dir = await tempDir();
    const scene = stickScene("scene_recover");
    const hash = bibleHash();
    const paths = sceneArtifactPaths(dir, sceneCacheKey(canonicalJson(scene), hash));
    await writeUngradedPlate(paths.tmpPath, { durationFrames: 3, paperBgHex: "#E9E2D2" });
    let renders = 0;
    const recovered = await new RenderPool({
      cacheDir: dir,
      render: async () => {
        renders += 1;
      },
    }).renderScene(job(scene, hash));
    expect(renders).toBe(0);
    expect(recovered.recoveredFromTmp).toBe(true);
    expect(recovered.cacheHit).toBe(false);
    expect(existsSync(paths.finalPath)).toBe(true);
    expect(existsSync(paths.tmpPath)).toBe(false);
    const probed = await ffprobeVerify(paths.finalPath, 3);
    expect(probed.ok).toBe(true);

    const corruptScene = stickScene("scene_corrupt");
    const corruptPaths = sceneArtifactPaths(dir, sceneCacheKey(canonicalJson(corruptScene), hash));
    await writeFile(corruptPaths.tmpPath, "not-an-mp4");
    const rendered = await new RenderPool({
      cacheDir: dir,
      render: async (request) => {
        renders += 1;
        await writeUngradedPlate(request.outputPath, {
          durationFrames: request.durationFrames,
          paperBgHex: request.grade.paperBgHex,
        });
      },
    }).renderScene(job(corruptScene, hash));
    expect(renders).toBe(1);
    expect(rendered.recoveredFromTmp).toBe(false);
    expect(existsSync(corruptPaths.finalPath)).toBe(true);
    expect(existsSync(corruptPaths.tmpPath)).toBe(false);
    expect((await ffprobeVerify(corruptPaths.finalPath, 3)).ok).toBe(true);
  });
});

describe("golden single-scene re-render", () => {
  it("re-renders one CODE_STICKMAN scene from ep_golden_01_20min in under 5s", async () => {
    const pack = JSON.parse(readFileSync(PACK_PATH, "utf8")) as {
      case_bible: unknown;
      scenes: Array<Record<string, unknown>>;
    };
    const scene = pack.scenes.find((item) => item.visual_engine === "CODE_STICKMAN" && item.motif_component === "StickmanStage");
    const foia = pack.scenes.find((item) => item.visual_engine === "FOIA_REAL_FOOTAGE");
    if (!scene || !foia) throw new Error("golden pack is missing a stickman or FOIA scene");
    const hash = hashCaseBible(pack.case_bible);
    const dir = await tempDir();
    let bundles = 0;
    let renders = 0;
    const pool = new RenderPool({
      cacheDir: dir,
      concurrency: 1,
      bundle: () => {
        bundles += 1;
        return { compositionId: "TrueCrimeEpisode", fps: 30, width: 1920, height: 1080 };
      },
      render: async (request) => {
        renders += 1;
        expect(request.boil.svgTurbulence).toBe(false);
        expect(request.boil.boilFps).toBe(6);
        expect(request.grade.paperGrain).toBe(0);
        expect(request.grade.vignette).toBe(0);
        expect(countBoilTicks(request.durationFrames)).toBeGreaterThan(0);
        await writeUngradedPlate(request.outputPath, {
          durationFrames: request.durationFrames,
          paperBgHex: request.grade.paperBgHex,
        });
      },
    });

    const first = await pool.renderScene({ scene, caseBibleHash: hash });
    expect(first.sceneId).toBe("ep_golden_01_20min_s012");
    expect(first.durationFrames).toBe(1200);
    expect(first.cacheHit).toBe(false);
    expect(first.applyGrade).toBe(true);
    expect(first.fps).toBe(30);
    expect(first.width).toBe(1920);
    expect(first.height).toBe(1080);
    expect(first.boilFps).toBe(6);
    expect(first.svgTurbulence).toBe(false);
    expect(first.paperGrain).toBe(0);
    expect(first.workMs).toBeLessThan(SINGLE_SCENE_RERENDER_BUDGET_MS);
    expect(first.elapsedMs).toBeLessThan(SINGLE_SCENE_RERENDER_BUDGET_MS);
    expect((await ffprobeVerify(first.outputPath, 1200)).ok).toBe(true);

    const cached = await pool.renderScene({ scene, caseBibleHash: hash });
    expect(cached.cacheHit).toBe(true);
    expect(cached.outputPath).toBe(first.outputPath);
    expect(cached.elapsedMs).toBeLessThan(SINGLE_SCENE_RERENDER_BUDGET_MS);
    expect(renders).toBe(1);
    expect(bundles).toBe(1);

    const changed = { ...scene, emotional_peak_score: 0.91 };
    const edited = await pool.renderScene({ scene: changed, caseBibleHash: hash });
    expect(edited.cacheHit).toBe(false);
    expect(edited.cacheKey).not.toBe(first.cacheKey);
    expect(edited.workMs).toBeLessThan(SINGLE_SCENE_RERENDER_BUDGET_MS);
    expect(edited.elapsedMs).toBeLessThan(SINGLE_SCENE_RERENDER_BUDGET_MS);
    expect(renders).toBe(2);
    expect(bundles).toBe(1);
    expect((await ffprobeVerify(edited.outputPath, 1200)).ok).toBe(true);

    const foiaReceipt = await new RenderPool({
      cacheDir: join(dir, "foia"),
      render: writeMarker,
      ffprobe: markerProbe,
    }).renderScene({ scene: foia, caseBibleHash: hash });
    expect(foiaReceipt.applyGrade).toBe(false);
    expect(foiaReceipt.sceneId).toBe(foia.scene_id);
  }, 30_000);
});
