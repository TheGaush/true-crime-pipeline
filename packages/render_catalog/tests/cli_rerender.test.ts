/**
 * Task 132. CLI contracts for a full CODE_STICKMAN batch, the 4-motif slice,
 * a single-scene heal, and the exit-2 unknown-scene path.
 */

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { spawnSync } from "node:child_process";
import { expect, test } from "vitest";

import {
  MVP_MOTIF_IDS,
  RENDER_REPORT_FILENAME,
  SCENE_GRADE_MANIFEST_FILENAME,
  cliMain,
  runRenderCatalog,
} from "../src/index.ts";

type Scene = {
  scene_id: string;
  episode_id: string;
  visual_engine: string;
  motif_component: string;
  timing_start_ms: number;
  timing_end_ms: number;
  provider_operation_id?: string;
  prompt_mode?: string;
};

function scene(id: string, engine: string, motif: string, extra: Partial<Scene> = {}): Scene {
  return {
    scene_id: id,
    episode_id: "ep_cli",
    visual_engine: engine,
    motif_component: motif,
    timing_start_ms: 0,
    timing_end_ms: 1000,
    ...extra,
  };
}

function writeManifest(dir: string, scenes: readonly Scene[]): string {
  const path = join(dir, "manifest.json");
  const body = {
    contract_version: "4",
    episode_id: "ep_cli",
    scene_plans: scenes,
  };
  writeFileSync(path, `${JSON.stringify(body, null, 2)}\n`);
  return path;
}

function sha(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

const MIXED: Scene[] = [
  scene("scene_stick", "CODE_STICKMAN", "StickmanStage"),
  scene("scene_doc", "CODE_STICKMAN", "RedactedDocReveal"),
  scene("scene_flow", "FLOW_HERO_VIDEO", "HeroVideoBridge", {
    provider_operation_id: "op_flow_1",
    prompt_mode: "TEXT_TO_VIDEO",
  }),
  scene("scene_still", "STILL_2K_PANZOOM", "Illustrative2KPanZoom"),
  scene("scene_audio", "AUDIO_EVIDENCE_CARD", "AudioEvidenceCard"),
  scene("scene_foia", "FOIA_REAL_FOOTAGE", "FoiaFootageFrame"),
  scene("scene_map", "CODE_STICKMAN", "AnimatedMapRoute"),
];

test("a full batch renders only CODE_STICKMAN clips and leaves the manifest untouched", async () => {
  const dir = mkdtempSync(join(tmpdir(), "tc-cli-full-"));
  const manifest = writeManifest(dir, MIXED);
  const before = sha(manifest);
  const outDir = join(dir, "out");
  const report = await runRenderCatalog({ manifestPath: manifest, outDir, mvp4Motifs: false });
  expect(sha(manifest)).toBe(before);
  expect(report.manifest_sha256).toBe(before);
  expect(report.manifest_unchanged).toBe(true);
  expect(report.schema_version).toBe("v4");
  expect(report.bundle_reused).toBe(false);
  expect(report.svg_fe_turbulence).toBe(0);
  expect(report.scenes.map((row) => row.scene_id)).toEqual(["scene_stick", "scene_doc", "scene_map"]);
  for (const row of report.scenes) {
    expect(row.r_frame_rate).toBe("30/1");
    expect(row.avg_frame_rate).toBe("30/1");
    expect(row.nb_frames).toBe(30);
    expect(row.duration_sec).toBe(1);
    expect(row.wall_clock_ms).toBeLessThan(5_000);
    expect(row.svg_filters).toBe(0);
    const probed = spawnSync(
      "ffprobe",
      ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_frames", "-of", "json", row.mp4],
      { encoding: "utf8" },
    );
    expect(probed.status).toBe(0);
    const stream = JSON.parse(probed.stdout).streams[0] as { r_frame_rate: string; avg_frame_rate: string; nb_frames: string };
    expect(stream.r_frame_rate).toBe("30/1");
    expect(stream.avg_frame_rate).toBe("30/1");
    expect(stream.nb_frames).toBe("30");
    const wav = readFileSync(row.pcm_wav);
    expect(wav.subarray(0, 4).toString("utf8")).toBe("RIFF");
    expect(wav.subarray(20, 22).readUInt16LE(0)).toBe(1);
  }
  expect(existsSync(join(outDir, "scene_flow.mp4"))).toBe(false);
  expect(existsSync(join(outDir, "scene_still.mp4"))).toBe(false);
  const grade = JSON.parse(readFileSync(join(outDir, SCENE_GRADE_MANIFEST_FILENAME), "utf8")) as {
    paper_grain: number;
    scenes: { scene_id: string }[];
  };
  expect(grade.paper_grain).toBe(0);
  expect(grade.scenes.map((row) => row.scene_id)).toEqual(["scene_stick", "scene_doc", "scene_map"]);
  const written = JSON.parse(readFileSync(join(outDir, RENDER_REPORT_FILENAME), "utf8")) as { ok: boolean };
  expect(written.ok).toBe(true);
});

test("--mvp-4-motifs pre-warms only the four registry motifs", async () => {
  const dir = mkdtempSync(join(tmpdir(), "tc-cli-mvp-"));
  const manifest = writeManifest(dir, MIXED);
  const outDir = join(dir, "out");
  const report = await runRenderCatalog({ manifestPath: manifest, outDir, mvp4Motifs: true });
  expect(report.mvp_4_motifs).toBe(true);
  expect(report.scenes.map((row) => row.motif_component)).toEqual([
    "StickmanStage",
    "RedactedDocReveal",
    "AudioEvidenceCard",
    "FoiaFootageFrame",
  ]);
  expect(new Set(report.scenes.map((row) => row.motif_component))).toEqual(new Set(MVP_MOTIF_IDS));
  expect(report.scenes.some((row) => row.motif_component === "AnimatedMapRoute")).toBe(false);
  expect(report.scenes.some((row) => row.visual_engine === "FLOW_HERO_VIDEO")).toBe(false);
  const foia = report.scenes.find((row) => row.motif_component === "FoiaFootageFrame");
  expect(foia?.nb_frames).toBe(30);
  const grade = JSON.parse(readFileSync(join(outDir, SCENE_GRADE_MANIFEST_FILENAME), "utf8")) as {
    scenes: { motif_component: string; apply_grade: boolean }[];
  };
  expect(grade.scenes.find((row) => row.motif_component === "FoiaFootageFrame")?.apply_grade).toBe(false);
  expect(grade.scenes.find((row) => row.motif_component === "StickmanStage")?.apply_grade).toBe(true);
});

test("--scene renders one CODE_STICKMAN heal and reuses the bundle stamp", async () => {
  const dir = mkdtempSync(join(tmpdir(), "tc-cli-scene-"));
  const manifest = writeManifest(dir, MIXED);
  const outDir = join(dir, "out");
  mkdirSync(outDir);
  writeFileSync(join(outDir, "scene_doc.mp4"), "sibling-keep");
  const first = await runRenderCatalog({ manifestPath: manifest, outDir, mvp4Motifs: false, sceneId: "scene_stick" });
  expect(first.scenes.map((row) => row.scene_id)).toEqual(["scene_stick"]);
  expect(first.bundle_reused).toBe(false);
  expect(readFileSync(join(outDir, "scene_doc.mp4"), "utf8")).toBe("sibling-keep");
  const second = await runRenderCatalog({ manifestPath: manifest, outDir, mvp4Motifs: false, sceneId: "scene_stick" });
  expect(second.bundle_reused).toBe(true);
  expect(second.scenes[0]?.cache_hit).toBe(true);
  expect(readFileSync(join(outDir, "scene_doc.mp4"), "utf8")).toBe("sibling-keep");
});

test("an unknown --scene exits 2 and does not touch sibling clips", async () => {
  const dir = mkdtempSync(join(tmpdir(), "tc-cli-miss-"));
  const manifest = writeManifest(dir, MIXED);
  const before = sha(manifest);
  const outDir = join(dir, "out");
  mkdirSync(outDir);
  const sibling = join(outDir, "scene_stick.mp4");
  writeFileSync(sibling, "do-not-touch");
  const stamp = statSync(sibling).mtimeMs;
  const code = await cliMain(["--manifest", manifest, "--out-dir", outDir, "--scene", "missing_scene"]);
  expect(code).toBe(2);
  expect(readFileSync(sibling, "utf8")).toBe("do-not-touch");
  expect(statSync(sibling).mtimeMs).toBe(stamp);
  expect(sha(manifest)).toBe(before);
  expect(() => statSync(join(outDir, RENDER_REPORT_FILENAME))).toThrow();
});

test("naming a Flow scene without the mvp flag exits 2", async () => {
  const dir = mkdtempSync(join(tmpdir(), "tc-cli-flow-"));
  const manifest = writeManifest(dir, MIXED);
  const outDir = join(dir, "out");
  const code = await cliMain(["--manifest", manifest, "--out-dir", outDir, "--scene", "scene_flow"]);
  expect(code).toBe(2);
});
