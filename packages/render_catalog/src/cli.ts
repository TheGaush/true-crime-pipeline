/**
 * Task 132. `render-catalog` entry for batch renders and one-scene heals.
 *
 * The input manifest is read once and never written. Flow and 2K scenes are
 * skipped unless `--scene` names one, in which case the process exits 2 and
 * leaves sibling clips alone. `--mvp-4-motifs` keeps the four MOTIF_REGISTRY_V1
 * motifs. Bundle files live under `.bundles/<episode_id>/<scene_id>` so two
 * heals do not share `/tmp/remotion-cache`.
 */

// @ts-expect-error node:child_process is provided by the runtime.
import { spawn } from "node:child_process";
// @ts-expect-error node:crypto is provided by the runtime.
import { createHash } from "node:crypto";
// @ts-expect-error node:fs/promises is provided by the runtime.
import { copyFile, mkdir, readFile, rename, writeFile } from "node:fs/promises";
// @ts-expect-error node:path is provided by the runtime.
import { dirname, join, resolve } from "node:path";
// @ts-expect-error node:url is provided by the runtime.
import { fileURLToPath } from "node:url";

import { RenderPool, sha256Hex } from "./renderer/RenderPool.js";

declare const process: {
  pid: number;
  argv: readonly string[];
  stdout: { write(chunk: string): void };
  stderr: { write(chunk: string): void };
  exitCode?: number;
};

export const MVP_MOTIF_IDS = ["StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame"] as const;
export const CODE_STICKMAN = "CODE_STICKMAN";
export const RENDER_REPORT_FILENAME = "render_report.json";
export const SCENE_GRADE_MANIFEST_FILENAME = "scene_grade_manifest.json";

const MVP_SET = new Set<string>(MVP_MOTIF_IDS);
const BANNED_SVG = [/feTurbulence/i, /feDisplacementMap/i];
const SCENE_ID = /^[A-Za-z0-9_-]+$/;

export class RenderCatalogCliError extends Error {
  readonly code: 1 | 2;
  readonly error: string;
  readonly sceneId: string | undefined;

  constructor(code: 1 | 2, error: string, message: string, sceneId?: string) {
    super(message);
    this.name = "RenderCatalogCliError";
    this.code = code;
    this.error = error;
    this.sceneId = sceneId;
  }
}

export type RenderCatalogArgs = {
  readonly manifestPath: string;
  readonly outDir: string;
  readonly mvp4Motifs: boolean;
  readonly sceneId?: string;
};

export type RenderedSceneReport = {
  readonly scene_id: string;
  readonly motif_component: string;
  readonly visual_engine: string;
  readonly duration_sec: number;
  readonly duration_frames: number;
  readonly nb_frames: number;
  readonly r_frame_rate: "30/1";
  readonly avg_frame_rate: "30/1";
  readonly mp4: string;
  readonly pcm_wav: string;
  readonly wall_clock_ms: number;
  readonly cache_hit: boolean;
  readonly svg_filters: 0;
};

export type RenderCatalogReport = {
  readonly ok: true;
  readonly manifest_path: string;
  readonly manifest_sha256: string;
  readonly manifest_unchanged: true;
  readonly schema_version: string;
  readonly episode_id: string;
  readonly mvp_4_motifs: boolean;
  readonly scene_filter: string | null;
  readonly bundle_reused: boolean;
  readonly cfr: "30/1";
  readonly svg_fe_turbulence: 0;
  readonly svg_fe_displacement_map: 0;
  readonly scenes: readonly RenderedSceneReport[];
};

export type RenderCatalogFailure = {
  readonly ok: false;
  readonly code: 1 | 2;
  readonly error: string;
  readonly message: string;
  readonly scene_id?: string;
};

type CatalogScene = {
  readonly sceneId: string;
  readonly episodeId: string;
  readonly visualEngine: string;
  readonly motif: string;
  readonly startMs: number;
  readonly endMs: number;
  readonly frames: number;
};

type LoadedManifest = {
  readonly schemaVersion: string;
  readonly episodeId: string;
  readonly scenes: readonly CatalogScene[];
};

type Probe = {
  readonly nbFrames: number;
  readonly rFrameRate: string;
  readonly avgFrameRate: string;
};

export function parseRenderCatalogArgv(argv: readonly string[]): RenderCatalogArgs {
  let manifestPath: string | undefined;
  let outDir: string | undefined;
  let sceneId: string | undefined;
  let mvp4Motifs = false;
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--mvp-4-motifs") {
      mvp4Motifs = true;
      continue;
    }
    if (token === "--manifest" || token === "--out-dir" || token === "--scene") {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith("--")) {
        throw new RenderCatalogCliError(2, "MISSING_VALUE", `${token} needs a value`);
      }
      index += 1;
      if (token === "--manifest") manifestPath = value;
      else if (token === "--out-dir") outDir = value;
      else sceneId = value;
      continue;
    }
    throw new RenderCatalogCliError(2, "UNKNOWN_FLAG", `unknown argument ${String(token)}`);
  }
  if (manifestPath === undefined) throw new RenderCatalogCliError(2, "MISSING_MANIFEST", "--manifest is required");
  if (outDir === undefined) throw new RenderCatalogCliError(2, "MISSING_OUT_DIR", "--out-dir is required");
  if (sceneId !== undefined && !SCENE_ID.test(sceneId)) {
    throw new RenderCatalogCliError(2, "UNKNOWN_SCENE", `scene id ${sceneId} is not a catalog id`, sceneId);
  }
  return {
    manifestPath,
    outDir,
    mvp4Motifs,
    ...(sceneId !== undefined ? { sceneId } : {}),
  };
}

export async function runRenderCatalog(args: RenderCatalogArgs): Promise<RenderCatalogReport> {
  const manifestPath = resolve(args.manifestPath);
  const outDir = resolve(args.outDir);
  const before = await readFile(manifestPath).catch(() => {
    throw new RenderCatalogCliError(2, "MANIFEST_NOT_FOUND", `manifest not found: ${manifestPath}`);
  });
  const loaded = loadManifest(before.toString("utf8"));
  const selected = selectScenes(loaded, args);
  const bundleReused = await readBundleStamp(outDir, loaded);
  await mkdir(outDir, { recursive: true });
  const rendered: RenderedSceneReport[] = [];
  for (const scene of selected) {
    rendered.push(await renderOne(scene, outDir, loaded.schemaVersion));
  }
  const after = await readFile(manifestPath);
  if (!sameBytes(before, after)) {
    throw new RenderCatalogCliError(1, "MANIFEST_MUTATED", "the input manifest was modified");
  }
  await writeBundleStamp(outDir, loaded);
  const report: RenderCatalogReport = {
    ok: true,
    manifest_path: manifestPath,
    manifest_sha256: sha256(before),
    manifest_unchanged: true,
    schema_version: loaded.schemaVersion,
    episode_id: loaded.episodeId,
    mvp_4_motifs: args.mvp4Motifs,
    scene_filter: args.sceneId ?? null,
    bundle_reused: bundleReused,
    cfr: "30/1",
    svg_fe_turbulence: 0,
    svg_fe_displacement_map: 0,
    scenes: rendered,
  };
  const grade = gradeManifest(loaded, rendered);
  await atomicJson(join(outDir, SCENE_GRADE_MANIFEST_FILENAME), grade);
  await atomicJson(join(outDir, RENDER_REPORT_FILENAME), report);
  return report;
}

export async function cliMain(argv: readonly string[]): Promise<number> {
  try {
    const args = parseRenderCatalogArgv(argv);
    const report = await runRenderCatalog(args);
    process.stdout.write(`${JSON.stringify({ ok: true, scenes: report.scenes.length, report: RENDER_REPORT_FILENAME })}\n`);
    return 0;
  } catch (error) {
    const failure = toFailure(error);
    process.stderr.write(`${JSON.stringify(failure)}\n`);
    return failure.code;
  }
}

export function toFailure(error: unknown): RenderCatalogFailure {
  if (error instanceof RenderCatalogCliError) {
    return {
      ok: false,
      code: error.code,
      error: error.error,
      message: error.message,
      ...(error.sceneId !== undefined ? { scene_id: error.sceneId } : {}),
    };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { ok: false, code: 1, error: "RENDER_FAILED", message };
}

function loadManifest(text: string): LoadedManifest {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text) as unknown;
  } catch {
    throw new RenderCatalogCliError(2, "MANIFEST_JSON", "manifest is not JSON");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new RenderCatalogCliError(2, "MANIFEST_JSON", "manifest must be an object");
  }
  const root = parsed as Record<string, unknown>;
  assertNoSvg(text);
  const schemaVersion = readSchema(root);
  const episodeId = readEpisode(root);
  const rows = readRows(root);
  const seen = new Set<string>();
  const scenes: CatalogScene[] = [];
  for (const row of rows) {
    const scene = normalizeScene(row, episodeId);
    if (seen.has(scene.sceneId)) {
      throw new RenderCatalogCliError(2, "DUPLICATE_SCENE", `duplicate scene_id ${scene.sceneId}`, scene.sceneId);
    }
    seen.add(scene.sceneId);
    scenes.push(scene);
  }
  return { schemaVersion, episodeId, scenes };
}

function selectScenes(loaded: LoadedManifest, args: RenderCatalogArgs): readonly CatalogScene[] {
  if (args.sceneId !== undefined) {
    const found = loaded.scenes.find((scene) => scene.sceneId === args.sceneId);
    if (!found) {
      throw new RenderCatalogCliError(2, "UNKNOWN_SCENE", `unknown scene ${args.sceneId}`, args.sceneId);
    }
    if (args.mvp4Motifs && !MVP_SET.has(found.motif)) {
      throw new RenderCatalogCliError(2, "OUT_OF_MVP_SLICE", `${found.sceneId} is outside the 4-motif slice`, found.sceneId);
    }
    if (!args.mvp4Motifs && found.visualEngine !== CODE_STICKMAN) {
      throw new RenderCatalogCliError(2, "NOT_CODE_STICKMAN", `${found.sceneId} is ${found.visualEngine}`, found.sceneId);
    }
    return [found];
  }
  if (args.mvp4Motifs) return loaded.scenes.filter((scene) => MVP_SET.has(scene.motif));
  return loaded.scenes.filter((scene) => scene.visualEngine === CODE_STICKMAN);
}

function normalizeScene(row: Record<string, unknown>, episodeId: string): CatalogScene {
  const sceneId = readId(row.scene_id, "scene_id");
  const visualEngine = readText(row.visual_engine, "visual_engine", sceneId);
  const motif = readText(row.motif_component, "motif_component", sceneId);
  const clock = readClock(row, sceneId);
  const rowEpisode = typeof row.episode_id === "string" && SCENE_ID.test(row.episode_id) ? row.episode_id : episodeId;
  return { sceneId, episodeId: rowEpisode, visualEngine, motif, ...clock };
}

function readClock(row: Record<string, unknown>, sceneId: string): { startMs: number; endMs: number; frames: number } {
  const start = firstNumber(row, ["timing_start_ms", "start_ms"]);
  const end = firstNumber(row, ["timing_end_ms", "end_ms"]);
  if (start !== null && end !== null) return clockFromSpan(start, end, sceneId);
  const durationMs = firstNumber(row, ["duration_ms"]);
  if (durationMs !== null) return clockFromSpan(0, durationMs, sceneId);
  const durationSec = firstNumber(row, ["duration_sec"]);
  if (durationSec !== null) return clockFromSpan(0, Math.round(durationSec * 1000), sceneId);
  throw new RenderCatalogCliError(2, "SCENE_CLOCK", `${sceneId} needs a duration`, sceneId);
}

function clockFromSpan(startMs: number, endMs: number, sceneId: string): { startMs: number; endMs: number; frames: number } {
  if (!Number.isInteger(startMs) || !Number.isInteger(endMs) || endMs <= startMs) {
    throw new RenderCatalogCliError(2, "SCENE_CLOCK", `${sceneId} clock must be integer milliseconds`, sceneId);
  }
  const span = (endMs - startMs) * 30;
  if (span % 1000 !== 0) {
    throw new RenderCatalogCliError(2, "SCENE_CLOCK", `${sceneId} does not land on a 30 fps frame`, sceneId);
  }
  return { startMs, endMs, frames: span / 1000 };
}

function readRows(root: Record<string, unknown>): Record<string, unknown>[] {
  const plans = root.scene_plans;
  if (Array.isArray(plans)) return plans.map((row, index) => asRow(row, index));
  const scenes = root.scenes;
  if (Array.isArray(scenes)) return scenes.map((row, index) => asRow(row, index));
  throw new RenderCatalogCliError(2, "MANIFEST_SCENES", "manifest needs scene_plans or scenes");
}

function asRow(value: unknown, index: number): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RenderCatalogCliError(2, "MANIFEST_SCENES", `scene ${index} must be an object`);
  }
  return value as Record<string, unknown>;
}

function readSchema(root: Record<string, unknown>): string {
  const value = root.schema_version ?? root.contract_version ?? "v4";
  if (typeof value !== "string" && typeof value !== "number") {
    throw new RenderCatalogCliError(2, "MANIFEST_SCHEMA", "schema version must be a string");
  }
  const text = String(value);
  return text === "4" ? "v4" : text;
}

function readEpisode(root: Record<string, unknown>): string {
  const value = root.episode_id ?? root.pack_id ?? "episode";
  if (typeof value !== "string" || !SCENE_ID.test(value)) {
    throw new RenderCatalogCliError(2, "EPISODE_ID", "episode_id must match ^[A-Za-z0-9_-]+$");
  }
  return value;
}

function readId(value: unknown, label: string): string {
  if (typeof value !== "string" || !SCENE_ID.test(value)) {
    throw new RenderCatalogCliError(2, "SCENE_ID", `${label} must match ^[A-Za-z0-9_-]+$`);
  }
  return value;
}

function readText(value: unknown, label: string, sceneId: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new RenderCatalogCliError(2, "SCENE_FIELD", `${sceneId} ${label} must be a non-empty string`, sceneId);
  }
  return value;
}

function firstNumber(row: Record<string, unknown>, keys: readonly string[]): number | null {
  for (const key of keys) {
    const value = row[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function assertNoSvg(text: string): void {
  for (const pattern of BANNED_SVG) {
    if (pattern.test(text)) {
      throw new RenderCatalogCliError(1, "SVG_FILTER", `manifest contains ${pattern.source}`);
    }
  }
}

async function renderOne(scene: CatalogScene, outDir: string, schemaVersion: string): Promise<RenderedSceneReport> {
  const cacheDir = join(outDir, ".bundles", scene.episodeId, scene.sceneId);
  await mkdir(cacheDir, { recursive: true });
  const gradeModulePath = join(cacheDir, "grade-contract.mjs");
  await writeFile(gradeModulePath, GRADE_MODULE, "utf8");
  const started = nowMs();
  const pool = new RenderPool({ cacheDir, concurrency: 1, gradeModulePath });
  const receipt = await pool.renderScene({
    scene: poolScene(scene),
    caseBibleHash: sha256Hex(schemaVersion),
  });
  const mp4Path = join(outDir, `${scene.sceneId}.mp4`);
  await copyFile(receipt.outputPath, mp4Path);
  const probe = await probeMp4(mp4Path);
  if (probe.rFrameRate !== "30/1" || probe.avgFrameRate !== "30/1" || probe.nbFrames !== scene.frames) {
    throw new RenderCatalogCliError(
      1,
      "FRAME_CLOCK",
      `${scene.sceneId} probe ${probe.rFrameRate} ${probe.avgFrameRate} frames ${probe.nbFrames}, expected 30/1 and ${scene.frames}`,
      scene.sceneId,
    );
  }
  const wavPath = join(outDir, `${scene.sceneId}.wav`);
  await writeFile(wavPath, silentWav(scene.frames));
  return {
    scene_id: scene.sceneId,
    motif_component: scene.motif,
    visual_engine: scene.visualEngine,
    duration_sec: scene.frames / 30,
    duration_frames: scene.frames,
    nb_frames: probe.nbFrames,
    r_frame_rate: "30/1",
    avg_frame_rate: "30/1",
    mp4: mp4Path,
    pcm_wav: wavPath,
    wall_clock_ms: Math.round(nowMs() - started),
    cache_hit: receipt.cacheHit,
    svg_filters: 0,
  };
}

function poolScene(scene: CatalogScene): Record<string, unknown> {
  return {
    scene_id: scene.sceneId,
    episode_id: scene.episodeId,
    visual_engine: scene.visualEngine,
    motif_component: scene.motif,
    start_ms: scene.startMs,
    end_ms: scene.endMs,
    timeline_spec_json: { fps: 30, duration_frames: scene.frames },
  };
}

function gradeManifest(loaded: LoadedManifest, rendered: readonly RenderedSceneReport[]): unknown {
  return {
    schema: "scene_grade_manifest.v1",
    episode_id: loaded.episodeId,
    fps: 30,
    width: 1920,
    height: 1080,
    paper_grain: 0,
    vignette: 0,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    svg_fe_turbulence: 0,
    svg_fe_displacement_map: 0,
    scenes: rendered.map((scene) => ({
      scene_id: scene.scene_id,
      visual_engine: scene.visual_engine,
      motif_component: scene.motif_component,
      duration_frames: scene.duration_frames,
      duration_sec: scene.duration_sec,
      apply_grade: scene.motif_component !== "FoiaFootageFrame" && scene.visual_engine !== "FOIA_REAL_FOOTAGE",
      cfr: "30/1",
      nb_frames: scene.nb_frames,
    })),
  };
}

function stampPath(outDir: string, episodeId: string): string {
  return join(outDir, ".bundles", episodeId, "stamp.json");
}

async function readBundleStamp(outDir: string, loaded: LoadedManifest): Promise<boolean> {
  try {
    const text = await readFile(stampPath(outDir, loaded.episodeId), "utf8");
    const parsed = JSON.parse(text) as { schema_version?: string; episode_id?: string };
    return parsed.schema_version === loaded.schemaVersion && parsed.episode_id === loaded.episodeId;
  } catch {
    return false;
  }
}

async function writeBundleStamp(outDir: string, loaded: LoadedManifest): Promise<void> {
  const path = stampPath(outDir, loaded.episodeId);
  await mkdir(dirname(path), { recursive: true });
  await atomicJson(path, {
    schema_version: loaded.schemaVersion,
    episode_id: loaded.episodeId,
    composition: "1920x1080@30",
    isolated_per_scene: true,
  });
}

async function atomicJson(path: string, value: unknown): Promise<void> {
  const tmp = `${path}.${process.pid}.tmp`;
  await writeFile(tmp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(tmp, path);
}

const GRADE_MODULE = [
  "export const REMOTION_PAPER_GRAIN = 0;",
  "export const REMOTION_VIGNETTE = 0;",
  "export const FRAME_FPS = 30;",
  "export const FRAME_WIDTH = 1920;",
  "export const FRAME_HEIGHT = 1080;",
  "export function sceneNeedsGrade(scene) {",
  "  return scene.visual_engine !== \"FOIA_REAL_FOOTAGE\" && scene.motif_component !== \"FoiaFootageFrame\";",
  "}",
  "export function buildSceneGradeManifest(scenes, episodeId) {",
  "  return { schema: \"scene_grade_manifest.v1\", episode_id: episodeId ?? null, paper_grain: 0, vignette: 0, scenes };",
  "}",
  "",
].join("\n");

function nowMs(): number {
  const perf = (globalThis as { performance?: { now(): number } }).performance;
  return perf ? perf.now() : Date.now();
}

function sameBytes(left: Uint8Array, right: Uint8Array): boolean {
  if (left.byteLength !== right.byteLength) return false;
  for (let index = 0; index < left.byteLength; index += 1) {
    if (left[index] !== right[index]) return false;
  }
  return true;
}

function silentWav(frames: number): Uint8Array {
  const samples = Math.round((frames / 30) * 48_000);
  const dataBytes = samples * 2;
  const header = new Uint8Array(44);
  const view = new DataView(header.buffer);
  writeAscii(header, 0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(header, 8, "WAVE");
  writeAscii(header, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 48_000, true);
  view.setUint32(28, 96_000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(header, 36, "data");
  view.setUint32(40, dataBytes, true);
  const wav = new Uint8Array(44 + dataBytes);
  wav.set(header, 0);
  return wav;
}

function writeAscii(target: Uint8Array, offset: number, text: string): void {
  for (let index = 0; index < text.length; index += 1) target[offset + index] = text.charCodeAt(index);
}

function probeMp4(file: string): Promise<Probe> {
  return new Promise((resolveProbe, reject) => {
    const child = spawn(
      "ffprobe",
      ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,avg_frame_rate,nb_frames", "-of", "json", file],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let out = "";
    let err = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      out += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      err += chunk;
    });
    child.on("error", reject);
    child.on("close", (code: number | null) => {
      if (code !== 0) {
        reject(new RenderCatalogCliError(1, "FFPROBE", err.slice(-400) || `ffprobe exit ${code ?? "null"}`));
        return;
      }
      const parsed = JSON.parse(out) as { streams?: { r_frame_rate?: string; avg_frame_rate?: string; nb_frames?: string }[] };
      const stream = parsed.streams?.[0];
      const nbFrames = Number.parseInt(stream?.nb_frames ?? "", 10);
      if (!stream?.r_frame_rate || !stream.avg_frame_rate || !Number.isInteger(nbFrames)) {
        reject(new RenderCatalogCliError(1, "FFPROBE", "ffprobe did not return a 30 fps stream"));
        return;
      }
      resolveProbe({ nbFrames, rFrameRate: stream.r_frame_rate, avgFrameRate: stream.avg_frame_rate });
    });
  });
}

function sha256(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

const invokedDirectly = process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  cliMain(process.argv.slice(2))
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error: unknown) => {
      process.stderr.write(`${JSON.stringify(toFailure(error))}\n`);
      process.exitCode = 1;
    });
}
