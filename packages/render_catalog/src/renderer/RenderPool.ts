/**
 * Headless 1920x1080 @ 30 fps worker pool for `@tc/render_catalog`.
 *
 * One pool bundles the composition once, then renders changed scenes through
 * the JS 6 fps boil clock (`Math.floor(frame / 5)`). SVG `<feTurbulence>` and
 * `<feDisplacementMap>` are rejected. Scene MP4s are cached by
 * `SHA-256(canonical_scene_json + case_bible_hash)` with no separator.
 *
 * A crash can leave `{cacheKey}.tmp.mp4`. The next call ffprobes that file
 * and renames it onto `{cacheKey}.mp4` only when the probe succeeds.
 *
 * Task 101 owns `REMOTION_ROOT` on `../index.ts`. Task 103 owns
 * `../rig/LineBoilPath.tsx`. Task 109 owns `../grade/GradeContract.tsx`.
 * Those modules are read when they are present. This file does not copy them.
 * The default plate encoder is local ffmpeg (no provider call). Pass `render`
 * and `bundle` to swap in Remotion when that package is installed.
 */

import * as task101Catalog from "../index.js";

declare const process: {
  env: Record<string, string | undefined>;
  getBuiltinModule(id: string): unknown;
};
declare function setTimeout(handler: () => void, timeoutMs: number): unknown;
declare function clearTimeout(handle: unknown): void;

type Hash = {
  update(data: string, encoding: "utf8"): Hash;
  digest(encoding: "hex"): string;
};

type CryptoModule = {
  createHash(algorithm: string): Hash;
};

type FsModule = {
  existsSync(path: string): boolean;
};

type FsPromisesModule = {
  mkdir(path: string, options: { recursive: boolean }): Promise<void>;
  rename(from: string, to: string): Promise<void>;
  rm(path: string, options?: { force?: boolean }): Promise<void>;
  writeFile(path: string, data: string): Promise<void>;
};

type PathModule = {
  dirname(path: string): string;
  join(...parts: string[]): string;
  resolve(...parts: string[]): string;
};

type UrlModule = {
  fileURLToPath(url: string | URL): string;
  pathToFileURL(path: string): URL;
};

type SpawnPipe = {
  setEncoding(encoding: "utf8"): void;
  on(event: "data", listener: (chunk: string) => void): void;
};

type Spawned = {
  stdout: SpawnPipe;
  stderr: SpawnPipe;
  kill(signal: "SIGKILL"): boolean;
  on(event: "error", listener: (error: Error) => void): void;
  on(event: "close", listener: (code: number | null) => void): void;
};

type ChildProcessModule = {
  spawn(
    command: string,
    args: readonly string[],
    options: {
      stdio: ["ignore", "pipe", "pipe"];
      env: Record<string, string>;
      windowsHide: boolean;
    },
  ): Spawned;
};

export const SINGLE_SCENE_RERENDER_BUDGET_MS = 5_000;
export const CONTAINER_FPS = 30;
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const BOIL_FPS = 6;
export const BOIL_FRAME_STRIDE = 5;
export const DEFAULT_PAPER_BG_HEX = "#E9E2D2";
export const DEFAULT_CONCURRENCY = 2;
export const MAX_SCENE_FRAMES = 36_000;
const SPAWN_TIMEOUT_MS = 8_000;
const COMPOSITION_ID = "TrueCrimeEpisode";

const BANNED_SVG = [/feTurbulence/i, /feDisplacementMap/i];
const SAFE_ENV_KEYS = ["PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT"] as const;

export class RenderPoolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RenderPoolError";
  }
}

function nodeBuiltin<T>(id: string): T {
  const loaded = process.getBuiltinModule(id);
  if (!loaded || typeof loaded !== "object") {
    throw new RenderPoolError(`node builtin ${id} is unavailable`);
  }
  return loaded as T;
}

const nodeCrypto = nodeBuiltin<CryptoModule>("node:crypto");
const nodeFs = nodeBuiltin<FsModule>("node:fs");
const nodeFsPromises = nodeBuiltin<FsPromisesModule>("node:fs/promises");
const nodePath = nodeBuiltin<PathModule>("node:path");
const nodeUrl = nodeBuiltin<UrlModule>("node:url");
const nodeChild = nodeBuiltin<ChildProcessModule>("node:child_process");

export type LockedRoot = {
  id: string;
  fps: number;
  width: number;
  height: number;
};

export type BoilContract = {
  mode: "js-polyline-vertex-jitter";
  boilFps: 6;
  containerFps: 30;
  frameStride: 5;
  quantizer: "Math.floor(frame / 5)";
  svgTurbulence: false;
  svgDisplacementMap: false;
};

export type GradeContract = {
  paperGrain: 0;
  vignette: 0;
  sceneNeedsGrade: (scene: GradeSceneInput) => boolean;
  buildSceneGradeManifest: (scenes: readonly GradeSceneInput[], episodeId?: string) => unknown;
};

export type GradeSceneInput = {
  scene_id: string;
  visual_engine: string;
  motif_component: string | null;
};

export type BundleHandle = {
  compositionId: string;
  fps: number;
  width: number;
  height: number;
};

export type SceneRenderJob = {
  scene: unknown;
  caseBibleHash: string;
};

export type PlateSpec = {
  durationFrames: number;
  paperBgHex: string;
};

export type HeadlessRenderRequest = PlateSpec & {
  bundle: BundleHandle;
  sceneId: string;
  cacheKey: string;
  canonicalSceneJson: string;
  caseBibleHash: string;
  outputPath: string;
  fps: 30;
  width: 1920;
  height: 1080;
  boil: BoilContract;
  grade: {
    paperGrain: 0;
    vignette: 0;
    remotionGrainApplied: false;
    remotionVignetteApplied: false;
    applyGrade: boolean;
    paperBgHex: string;
  };
};

export type FfprobeExpectation = {
  durationFrames: number;
};

export type FfprobeResult =
  | { ok: true; width: 1920; height: 1080; fps: 30 }
  | { ok: false; reason: string };

export type SceneRenderReceipt = {
  sceneId: string;
  cacheKey: string;
  outputPath: string;
  gradePath: string;
  cacheHit: boolean;
  recoveredFromTmp: boolean;
  elapsedMs: number;
  workMs: number;
  durationFrames: number;
  compositionId: string;
  fps: 30;
  width: 1920;
  height: 1080;
  boilFps: 6;
  svgTurbulence: false;
  svgDisplacementMap: false;
  paperGrain: 0;
  vignette: 0;
  applyGrade: boolean;
};

export type RenderPoolOptions = {
  cacheDir: string;
  concurrency?: number;
  paperBgHex?: string;
  remotionRoot?: LockedRoot;
  boilModulePath?: string;
  gradeModulePath?: string;
  ffmpegBin?: string;
  ffprobeBin?: string;
  now?: () => number;
  bundle?: () => BundleHandle | Promise<BundleHandle>;
  render?: (request: HeadlessRenderRequest) => Promise<void>;
  ffprobe?: (filePath: string, expected: FfprobeExpectation) => Promise<FfprobeResult>;
};

type Task101Module = {
  REMOTION_ROOT?: {
    fps: number;
    width: number;
    height: number;
    id?: string;
  };
};

type Identity = {
  sceneId: string;
  visualEngine: string | null;
  motifComponent: string | null;
  canonicalSceneJson: string;
  caseBibleHash: string;
  cacheKey: string;
  durationFrames: number;
  tmpPath: string;
  finalPath: string;
  gradePath: string;
  episodeId?: string;
};

type ResolvedContracts = {
  root: LockedRoot;
  boil: BoilContract;
  grade: GradeContract;
};

const DEFAULT_BOIL: BoilContract = {
  mode: "js-polyline-vertex-jitter",
  boilFps: 6,
  containerFps: 30,
  frameStride: 5,
  quantizer: "Math.floor(frame / 5)",
  svgTurbulence: false,
  svgDisplacementMap: false,
};

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isEnoent(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && (error as { code?: unknown }).code === "ENOENT");
}

export function monotonicNow(): number {
  const perf = (globalThis as { performance?: { now(): number } }).performance;
  return perf ? perf.now() : Date.now();
}

export function headlessChildEnv(source: Record<string, string | undefined> = process.env): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of SAFE_ENV_KEYS) {
    const value = source[key];
    if (typeof value === "string" && value.length > 0) env[key] = value;
  }
  return env;
}

export function sha256Hex(text: string): string {
  return nodeCrypto.createHash("sha256").update(text, "utf8").digest("hex");
}

export function assertSha256(value: string, label: string): void {
  if (!/^[0-9a-f]{64}$/.test(value)) {
    throw new RenderPoolError(`${label} must be a lowercase sha256 hex string`);
  }
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value: unknown): unknown {
  if (value === null) return null;
  const kind = typeof value;
  if (kind === "string" || kind === "boolean") return value;
  if (kind === "number") {
    if (!Number.isFinite(value)) throw new RenderPoolError("canonical scene JSON rejects non-finite numbers");
    return value;
  }
  if (kind === "bigint" || kind === "undefined" || kind === "function" || kind === "symbol") {
    throw new RenderPoolError(`canonical scene JSON rejects ${kind}`);
  }
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (item === undefined) throw new RenderPoolError("canonical scene JSON rejects undefined array entries");
      return canonicalize(item);
    });
  }
  if (kind === "object") {
    const proto = Object.getPrototypeOf(value);
    if (proto !== Object.prototype && proto !== null) {
      throw new RenderPoolError("canonical scene JSON rejects non-plain objects");
    }
    const source = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) {
      const item = source[key];
      if (item === undefined) throw new RenderPoolError(`canonical scene JSON rejects undefined at ${key}`);
      out[key] = canonicalize(item);
    }
    return out;
  }
  throw new RenderPoolError(`canonical scene JSON rejects ${kind}`);
}

export function hashCaseBible(value: unknown): string {
  return sha256Hex(canonicalJson(value));
}

/** `SHA-256` of the canonical scene JSON concatenated with the case-bible hash. No separator. */
export function sceneCacheKey(canonicalSceneJson: string, caseBibleHash: string): string {
  if (typeof canonicalSceneJson !== "string") {
    throw new RenderPoolError("canonical_scene_json must be a string");
  }
  assertSha256(caseBibleHash, "case_bible_hash");
  return sha256Hex(`${canonicalSceneJson}${caseBibleHash}`);
}

export function sceneArtifactPaths(cacheDir: string, cacheKey: string): { tmpPath: string; finalPath: string; gradePath: string } {
  assertSha256(cacheKey, "cache key");
  return {
    tmpPath: nodePath.join(cacheDir, `${cacheKey}.tmp.mp4`),
    finalPath: nodePath.join(cacheDir, `${cacheKey}.mp4`),
    gradePath: nodePath.join(cacheDir, `${cacheKey}.grade.json`),
  };
}

export function boilTick(frame: number): number {
  if (!Number.isFinite(frame)) throw new RenderPoolError("frame must be finite");
  return Math.floor(frame / BOIL_FRAME_STRIDE);
}

export function countBoilTicks(durationFrames: number): number {
  if (!Number.isInteger(durationFrames) || durationFrames <= 0 || durationFrames > MAX_SCENE_FRAMES) {
    throw new RenderPoolError(`durationFrames must be an integer from 1 to ${MAX_SCENE_FRAMES}`);
  }
  let ticks = 0;
  let last = -1;
  for (let frame = 0; frame < durationFrames; frame += 1) {
    const tick = boilTick(frame);
    if (tick !== last) {
      ticks += 1;
      last = tick;
    }
  }
  return ticks;
}

export function assertNoSvgTurbulence(canonicalSceneJson: string): void {
  for (const pattern of BANNED_SVG) {
    if (pattern.test(canonicalSceneJson)) {
      throw new RenderPoolError("SVG feTurbulence and feDisplacementMap are banned; use the JS 6 fps line boil");
    }
  }
}

export function normalizePaperHex(value: string): string {
  if (typeof value !== "string" || !/^#[0-9A-Fa-f]{6}$/.test(value)) {
    throw new RenderPoolError("paperBgHex must be a #RRGGBB color");
  }
  return value.toUpperCase();
}

export function importedRemotionRoot(): LockedRoot | null {
  const root = (task101Catalog as Task101Module).REMOTION_ROOT;
  if (!root) return null;
  assertLockedRoot(root, "Task 101 REMOTION_ROOT");
  return {
    id: typeof root.id === "string" && root.id.trim() !== "" ? root.id : COMPOSITION_ID,
    fps: 30,
    width: 1920,
    height: 1080,
  };
}

export function resolveRemotionRoot(override?: LockedRoot): LockedRoot {
  const imported = importedRemotionRoot();
  if (override) assertLockedRoot(override, "Remotion root");
  if (imported && override && imported.id !== override.id) {
    throw new RenderPoolError(
      `Remotion root id ${override.id} does not match Task 101 REMOTION_ROOT id ${imported.id}`,
    );
  }
  const chosen = override ?? imported;
  if (!chosen) return { id: COMPOSITION_ID, fps: 30, width: 1920, height: 1080 };
  return { id: chosen.id, fps: 30, width: 1920, height: 1080 };
}

function assertLockedRoot(root: { fps: number; width: number; height: number; id?: string }, source: string): void {
  if (root.fps !== CONTAINER_FPS || root.width !== FRAME_WIDTH || root.height !== FRAME_HEIGHT) {
    throw new RenderPoolError(
      `${source} is locked to ${FRAME_WIDTH}x${FRAME_HEIGHT} @ ${CONTAINER_FPS} fps, received ${root.width}x${root.height} @ ${root.fps} fps`,
    );
  }
  if (root.id !== undefined && (typeof root.id !== "string" || root.id.trim() === "")) {
    throw new RenderPoolError(`${source} id must be a non-empty string`);
  }
}

function moduleDir(): string {
  return nodePath.dirname(nodeUrl.fileURLToPath(import.meta.url));
}

function findSibling(rels: readonly string[]): string | null {
  for (const rel of rels) {
    const absolute = nodePath.join(moduleDir(), rel);
    if (nodeFs.existsSync(absolute)) return absolute;
  }
  return null;
}

async function importModule(filePath: string): Promise<Record<string, unknown>> {
  try {
    const loaded = (await import(nodeUrl.pathToFileURL(filePath).href)) as Record<string, unknown>;
    return loaded;
  } catch (error) {
    throw new RenderPoolError(`failed to import ${filePath}: ${messageOf(error)}`);
  }
}

function requiredNumber(mod: Record<string, unknown>, key: string, source: string): number {
  const value = mod[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new RenderPoolError(`${source} is missing ${key}`);
  }
  return value;
}

export async function resolveBoilContract(modulePath?: string): Promise<BoilContract> {
  const found = modulePath ?? findSibling(["../rig/LineBoilPath.tsx", "../rig/LineBoilPath.ts", "../rig/LineBoilPath.js"]);
  if (!found) return DEFAULT_BOIL;
  if (!nodeFs.existsSync(found)) throw new RenderPoolError(`Task 103 boil module was not found at ${found}`);
  const mod = await importModule(found);
  const boilFps = requiredNumber(mod, "BOIL_FPS", "Task 103");
  const containerFps = requiredNumber(mod, "CONTAINER_FPS", "Task 103");
  const stride = requiredNumber(mod, "BOIL_FRAME_STRIDE", "Task 103");
  if (boilFps !== BOIL_FPS || containerFps !== CONTAINER_FPS || stride !== BOIL_FRAME_STRIDE) {
    throw new RenderPoolError(
      `Task 103 boil contract must be ${BOIL_FPS} fps at ${CONTAINER_FPS} fps (stride ${BOIL_FRAME_STRIDE}), received ${boilFps} fps / ${containerFps} fps / stride ${stride}`,
    );
  }
  return DEFAULT_BOIL;
}

function localNeedsGrade(scene: GradeSceneInput): boolean {
  if (scene.visual_engine === "FOIA_REAL_FOOTAGE") return false;
  if (scene.motif_component === "FoiaFootageFrame") return false;
  return true;
}

function assertZeroExport(mod: Record<string, unknown>, key: string): void {
  if (!(key in mod)) return;
  if (mod[key] !== 0) throw new RenderPoolError(`${key} must be 0 for a Remotion plate`);
}

function assertLockedExport(mod: Record<string, unknown>, key: string, expected: number): void {
  if (!(key in mod)) return;
  if (mod[key] !== expected) {
    throw new RenderPoolError(`Task 109 ${key} must be ${expected}, received ${String(mod[key])}`);
  }
}

export async function resolveGradeContract(modulePath?: string): Promise<GradeContract> {
  const found = modulePath ?? findSibling(["../grade/GradeContract.tsx", "../grade/GradeContract.ts", "../grade/GradeContract.js"]);
  if (modulePath && !nodeFs.existsSync(modulePath)) {
    throw new RenderPoolError(`Task 109 grade module was not found at ${modulePath}`);
  }
  if (!found) return localGradeContract();
  const mod = await importModule(found);
  assertZeroExport(mod, "REMOTION_PAPER_GRAIN");
  assertZeroExport(mod, "REMOTION_VIGNETTE");
  assertLockedExport(mod, "FRAME_FPS", CONTAINER_FPS);
  assertLockedExport(mod, "FRAME_WIDTH", FRAME_WIDTH);
  assertLockedExport(mod, "FRAME_HEIGHT", FRAME_HEIGHT);
  const needs = mod.sceneNeedsGrade;
  const build = mod.buildSceneGradeManifest;
  const sceneNeedsGrade =
    typeof needs === "function"
      ? (scene: GradeSceneInput) => Boolean((needs as (input: GradeSceneInput) => unknown)(scene))
      : localNeedsGrade;
  const buildSceneGradeManifest =
    typeof build === "function"
      ? (scenes: readonly GradeSceneInput[], episodeId?: string) => {
          const fn = build as (input: readonly GradeSceneInput[], episode?: string) => unknown;
          return episodeId === undefined ? fn(scenes) : fn(scenes, episodeId);
        }
      : (scenes: readonly GradeSceneInput[], episodeId?: string) => manifestFor(scenes, episodeId, sceneNeedsGrade);
  return {
    paperGrain: 0,
    vignette: 0,
    sceneNeedsGrade,
    buildSceneGradeManifest,
  };
}

function manifestFor(
  scenes: readonly GradeSceneInput[],
  episodeId: string | undefined,
  needsGrade: (scene: GradeSceneInput) => boolean,
): Record<string, unknown> {
  const document: Record<string, unknown> = {
    filename: "scene_grade_manifest.json",
    schema: "scene_grade_manifest.v1",
    contract_version: "v4",
    fps: CONTAINER_FPS,
    width_px: FRAME_WIDTH,
    height_px: FRAME_HEIGHT,
    remotion_grain_applied: false,
    remotion_vignette_applied: false,
    paper_grain: 0,
    vignette: 0,
    grain_phase: null,
    grade_owner: "agent6_single_pass",
    scenes: scenes.map((scene) => {
      const applyGrade = needsGrade(scene);
      return {
        scene_id: scene.scene_id,
        visual_engine: scene.visual_engine,
        motif_component: scene.motif_component,
        apply_grade: applyGrade,
        needs_grade: applyGrade,
        remotion_grain_applied: false,
        remotion_vignette_applied: false,
        paper_grain: 0,
        vignette: 0,
        exempt_from_grain: !applyGrade,
        grade_owner: applyGrade ? "agent6_single_pass" : "none",
      };
    }),
  };
  if (episodeId !== undefined) document.episode_id = episodeId;
  return document;
}

function localGradeContract(): GradeContract {
  return {
    paperGrain: 0,
    vignette: 0,
    sceneNeedsGrade: localNeedsGrade,
    buildSceneGradeManifest: (scenes, episodeId) => manifestFor(scenes, episodeId, localNeedsGrade),
  };
}

export function bundleHeadlessComposition(root: LockedRoot = resolveRemotionRoot()): BundleHandle {
  assertLockedRoot(root, "bundle");
  return {
    compositionId: root.id,
    fps: 30,
    width: 1920,
    height: 1080,
  };
}

export function ungradedPlateArgs(filePath: string, spec: PlateSpec): string[] {
  const hex = normalizePaperHex(spec.paperBgHex).slice(1);
  if (!Number.isInteger(spec.durationFrames) || spec.durationFrames <= 0 || spec.durationFrames > MAX_SCENE_FRAMES) {
    throw new RenderPoolError(`durationFrames must be an integer from 1 to ${MAX_SCENE_FRAMES}`);
  }
  if (filePath.length === 0 || filePath.includes("\0")) throw new RenderPoolError("output path is invalid");
  const args = [
    "-nostdin",
    "-hide_banner",
    "-y",
    "-loglevel",
    "error",
    "-f",
    "lavfi",
    "-i",
    `color=c=0x${hex}:s=${FRAME_WIDTH}x${FRAME_HEIGHT}:r=${CONTAINER_FPS}`,
    "-frames:v",
    String(spec.durationFrames),
    "-an",
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-pix_fmt",
    "yuv420p",
    "-movflags",
    "+faststart",
    filePath,
  ];
  assertCleanPlateArgs(args);
  return args;
}

export function assertCleanPlateArgs(args: readonly string[]): void {
  const filter = args.find((arg) => arg.startsWith("color=")) ?? "";
  const bannedFilters = ["feturbulence", "fedisplacementmap", "noise", "vignette", "gblur", "boxblur", "eq=", "curves"];
  const lower = filter.toLowerCase();
  for (const token of bannedFilters) {
    if (lower.includes(token)) throw new RenderPoolError(`ungraded plate filter includes ${token}`);
  }
  const withoutPath = args.slice(0, -1).join("\n").toLowerCase();
  if (withoutPath.includes("feturbulence") || withoutPath.includes("fedisplacementmap")) {
    throw new RenderPoolError("ungraded plate args include an SVG turbulence filter");
  }
}

export async function writeUngradedPlate(
  filePath: string,
  spec: PlateSpec,
  ffmpegBin = "ffmpeg",
): Promise<void> {
  const args = ungradedPlateArgs(filePath, spec);
  let result: { code: number; stderr: string };
  try {
    result = await spawnCaptured(ffmpegBin, args);
  } catch (error) {
    if (isEnoent(error)) {
      throw new RenderPoolError("ffmpeg is not on PATH. Pass render() to supply a headless encoder.");
    }
    throw new RenderPoolError(messageOf(error));
  }
  if (result.code !== 0) {
    throw new RenderPoolError(`ffmpeg exited ${result.code}: ${result.stderr.trim().slice(0, 180)}`);
  }
}

export async function ffprobeVerify(
  filePath: string,
  durationFrames?: number,
  ffprobeBin = "ffprobe",
): Promise<FfprobeResult> {
  let result: { code: number; stdout: string; stderr: string };
  try {
    result = await spawnCaptured(ffprobeBin, [
      "-hide_banner",
      "-v",
      "error",
      "-print_format",
      "json",
      "-show_streams",
      filePath,
    ]);
  } catch (error) {
    if (isEnoent(error)) return { ok: false, reason: "ffprobe is not on PATH" };
    return { ok: false, reason: messageOf(error) };
  }
  if (result.code !== 0) {
    return { ok: false, reason: result.stderr.trim().slice(0, 180) || `ffprobe exited ${result.code}` };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(result.stdout);
  } catch {
    return { ok: false, reason: "ffprobe did not return JSON" };
  }
  const streams = parsed && typeof parsed === "object" && Array.isArray((parsed as { streams?: unknown }).streams)
    ? (parsed as { streams: unknown[] }).streams
    : [];
  const video = streams.find((stream) => {
    return Boolean(stream && typeof stream === "object" && (stream as { codec_type?: unknown }).codec_type === "video");
  }) as { width?: unknown; height?: unknown; r_frame_rate?: unknown; avg_frame_rate?: unknown; nb_frames?: unknown } | undefined;
  if (!video) return { ok: false, reason: "ffprobe found no video stream" };
  if (video.width !== FRAME_WIDTH || video.height !== FRAME_HEIGHT) {
    return { ok: false, reason: `ffprobe geometry ${String(video.width)}x${String(video.height)}` };
  }
  const rate = typeof video.r_frame_rate === "string" ? video.r_frame_rate : video.avg_frame_rate;
  if (!isThirtyFps(rate)) return { ok: false, reason: `ffprobe fps ${String(rate)}` };
  if (durationFrames !== undefined && video.nb_frames !== undefined) {
    const reported = Number(video.nb_frames);
    if (Number.isFinite(reported) && reported !== durationFrames) {
      return { ok: false, reason: `ffprobe nb_frames ${String(video.nb_frames)} != ${durationFrames}` };
    }
  }
  return { ok: true, width: 1920, height: 1080, fps: 30 };
}

function isThirtyFps(rate: unknown): boolean {
  if (typeof rate !== "string") return false;
  const [rawNum, rawDen] = rate.split("/");
  const num = Number(rawNum);
  const den = rawDen === undefined ? 1 : Number(rawDen);
  if (!Number.isFinite(num) || !Number.isFinite(den) || den === 0) return false;
  return Math.abs(num / den - CONTAINER_FPS) < 1e-6;
}

type SpawnResult = { code: number; stdout: string; stderr: string };

function spawnCaptured(bin: string, args: readonly string[]): Promise<SpawnResult> {
  return new Promise((resolvePromise, reject) => {
    const child = nodeChild.spawn(bin, args, {
      stdio: ["ignore", "pipe", "pipe"],
      env: headlessChildEnv(),
      windowsHide: true,
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(() => reject(new RenderPoolError(`${bin} timed out after ${SPAWN_TIMEOUT_MS} ms`)));
    }, SPAWN_TIMEOUT_MS);
    function finish(fn: () => void): void {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn();
    }
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      if (stdout.length < 1_000_000) stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      if (stderr.length < 4096) stderr += chunk;
    });
    child.on("error", (error) => finish(() => reject(error)));
    child.on("close", (code) => finish(() => resolvePromise({ code: code ?? 1, stdout, stderr })));
  });
}

async function rmQuiet(filePath: string): Promise<void> {
  await nodeFsPromises.rm(filePath, { force: true });
}

async function atomicWrite(filePath: string, body: string): Promise<void> {
  const tmp = `${filePath}.tmp`;
  await nodeFsPromises.writeFile(tmp, body);
  await nodeFsPromises.rename(tmp, filePath);
}

function asJsonFile(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return text.endsWith("\n") ? text : `${text}\n`;
}

function readSceneRecord(scene: unknown): Record<string, unknown> {
  if (!scene || typeof scene !== "object" || Array.isArray(scene)) {
    throw new RenderPoolError("scene must be a plain object");
  }
  const proto = Object.getPrototypeOf(scene);
  if (proto !== Object.prototype && proto !== null) {
    throw new RenderPoolError("scene must be a plain object");
  }
  return scene as Record<string, unknown>;
}

function readSceneId(scene: Record<string, unknown>): string {
  const id = scene.scene_id;
  if (typeof id !== "string" || !/^[A-Za-z0-9_-]+$/.test(id)) {
    throw new RenderPoolError("scene_id must match ^[A-Za-z0-9_-]+$");
  }
  return id;
}

function readOptionalId(scene: Record<string, unknown>, key: string): string | null {
  const value = scene[key];
  if (value === undefined || value === null) return null;
  if (typeof value !== "string" || value.trim() === "") {
    throw new RenderPoolError(`${key} must be a non-empty string or null`);
  }
  return value;
}

function readEpisodeId(scene: Record<string, unknown>): string | undefined {
  const value = scene.episode_id;
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new RenderPoolError("episode_id must match ^[A-Za-z0-9_-]+$");
  }
  return value;
}

function readDurationFrames(scene: Record<string, unknown>): number {
  const timeline = scene.timeline_spec_json;
  const record = timeline && typeof timeline === "object" && !Array.isArray(timeline)
    ? (timeline as Record<string, unknown>)
    : null;
  if (record && record.fps !== undefined && record.fps !== CONTAINER_FPS) {
    throw new RenderPoolError("scene timeline fps must be 30");
  }
  let frames: number | null = null;
  if (record && record.duration_frames !== undefined) {
    if (!Number.isInteger(record.duration_frames) || (record.duration_frames as number) <= 0) {
      throw new RenderPoolError("duration_frames must be a positive integer");
    }
    frames = record.duration_frames as number;
  }
  if (scene.start_ms !== undefined || scene.end_ms !== undefined) {
    if (!Number.isInteger(scene.start_ms) || !Number.isInteger(scene.end_ms) || (scene.end_ms as number) <= (scene.start_ms as number)) {
      throw new RenderPoolError("start_ms and end_ms must be integers with end_ms > start_ms");
    }
    const span = ((scene.end_ms as number) - (scene.start_ms as number)) * CONTAINER_FPS;
    if (span % 1000 !== 0) throw new RenderPoolError("start_ms and end_ms must land on a 30 fps frame");
    const clockFrames = span / 1000;
    if (frames !== null && frames !== clockFrames) {
      throw new RenderPoolError("duration_frames does not match start_ms and end_ms at 30 fps");
    }
    frames = clockFrames;
  }
  if (frames === null) throw new RenderPoolError("scene needs duration_frames or start_ms and end_ms");
  if (frames > MAX_SCENE_FRAMES) {
    throw new RenderPoolError(`duration_frames ${frames} exceeds ${MAX_SCENE_FRAMES}`);
  }
  return frames;
}

export function identifyScene(scene: unknown, caseBibleHash: string, cacheDir: string): Identity {
  const record = readSceneRecord(scene);
  const canonicalSceneJson = canonicalJson(record);
  assertNoSvgTurbulence(canonicalSceneJson);
  const cacheKey = sceneCacheKey(canonicalSceneJson, caseBibleHash);
  const episodeId = readEpisodeId(record);
  return {
    sceneId: readSceneId(record),
    visualEngine: readOptionalId(record, "visual_engine"),
    motifComponent: readOptionalId(record, "motif_component"),
    canonicalSceneJson,
    caseBibleHash,
    cacheKey,
    durationFrames: readDurationFrames(record),
    ...sceneArtifactPaths(cacheDir, cacheKey),
    ...(episodeId !== undefined ? { episodeId } : {}),
  };
}

function gradeInput(identity: Identity): GradeSceneInput {
  return {
    scene_id: identity.sceneId,
    visual_engine: identity.visualEngine ?? "",
    motif_component: identity.motifComponent,
  };
}

function lockedMedia(): {
  fps: 30;
  width: 1920;
  height: 1080;
  boilFps: 6;
  svgTurbulence: false;
  svgDisplacementMap: false;
  paperGrain: 0;
  vignette: 0;
} {
  return {
    fps: 30,
    width: 1920,
    height: 1080,
    boilFps: 6,
    svgTurbulence: false,
    svgDisplacementMap: false,
    paperGrain: 0,
    vignette: 0,
  };
}

class Semaphore {
  private active = 0;
  private readonly waiting: Array<() => void> = [];

  constructor(private readonly limit: number) {
    if (!Number.isInteger(limit) || limit < 1) {
      throw new RenderPoolError("concurrency must be a positive integer");
    }
  }

  async use<T>(fn: () => Promise<T>): Promise<T> {
    await this.acquire();
    try {
      return await fn();
    } finally {
      this.release();
    }
  }

  private acquire(): Promise<void> {
    if (this.active < this.limit) {
      this.active += 1;
      return Promise.resolve();
    }
    return new Promise((resolvePromise) => {
      this.waiting.push(() => {
        this.active += 1;
        resolvePromise();
      });
    });
  }

  private release(): void {
    this.active -= 1;
    const next = this.waiting.shift();
    if (next) next();
  }
}

async function defaultRender(request: HeadlessRenderRequest, ffmpegBin: string): Promise<void> {
  if (request.boil.svgTurbulence !== false || request.boil.svgDisplacementMap !== false) {
    throw new RenderPoolError("SVG feTurbulence and feDisplacementMap are banned");
  }
  if (request.grade.paperGrain !== 0 || request.grade.vignette !== 0) {
    throw new RenderPoolError("Remotion plate must stay ungrained");
  }
  if (request.fps !== CONTAINER_FPS || request.width !== FRAME_WIDTH || request.height !== FRAME_HEIGHT) {
    throw new RenderPoolError("plate is locked to 1920x1080 @ 30 fps");
  }
  if (countBoilTicks(request.durationFrames) < 1) {
    throw new RenderPoolError("6 fps boil clock produced no ticks");
  }
  await writeUngradedPlate(request.outputPath, {
    durationFrames: request.durationFrames,
    paperBgHex: request.grade.paperBgHex,
  }, ffmpegBin);
}

export class RenderPool {
  private readonly cacheDir: string;
  private readonly paperBgHex: string;
  private readonly root: LockedRoot;
  private readonly semaphore: Semaphore;
  private readonly now: () => number;
  private readonly ffmpegBin: string;
  private readonly ffprobeBin: string;
  private bundleTask: Promise<BundleHandle> | null = null;
  private resolved: ResolvedContracts | null = null;
  private readonly inflight = new Map<string, Promise<SceneRenderReceipt>>();

  constructor(private readonly options: RenderPoolOptions) {
    if (typeof options.cacheDir !== "string" || options.cacheDir.trim() === "") {
      throw new RenderPoolError("cacheDir must be a non-empty path");
    }
    this.cacheDir = nodePath.resolve(options.cacheDir);
    this.paperBgHex = normalizePaperHex(options.paperBgHex ?? DEFAULT_PAPER_BG_HEX);
    this.root = resolveRemotionRoot(options.remotionRoot);
    this.semaphore = new Semaphore(options.concurrency ?? DEFAULT_CONCURRENCY);
    this.now = options.now ?? monotonicNow;
    this.ffmpegBin = options.ffmpegBin ?? "ffmpeg";
    this.ffprobeBin = options.ffprobeBin ?? "ffprobe";
  }

  async renderScene(job: SceneRenderJob): Promise<SceneRenderReceipt> {
    const started = this.now();
    const identity = identifyScene(job.scene, job.caseBibleHash, this.cacheDir);
    let pending = this.inflight.get(identity.cacheKey);
    if (!pending) {
      pending = this.produce(identity);
      this.inflight.set(identity.cacheKey, pending);
      const current = pending;
      void current.then(
        () => undefined,
        () => undefined,
      ).finally(() => {
        if (this.inflight.get(identity.cacheKey) === current) this.inflight.delete(identity.cacheKey);
      });
    }
    const receipt = await pending;
    return {
      ...receipt,
      sceneId: identity.sceneId,
      elapsedMs: this.now() - started,
    };
  }

  async renderScenes(jobs: readonly SceneRenderJob[]): Promise<SceneRenderReceipt[]> {
    if (!Array.isArray(jobs)) throw new RenderPoolError("jobs must be an array");
    return Promise.all(jobs.map((job) => this.renderScene(job)));
  }

  private async produce(identity: Identity): Promise<SceneRenderReceipt> {
    await nodeFsPromises.mkdir(this.cacheDir, { recursive: true });
    const contracts = await this.contracts();
    const cached = await this.readCache(identity, contracts);
    if (cached) return cached;
    return this.semaphore.use(async () => {
      const again = await this.readCache(identity, contracts);
      if (again) return again;
      const bundle = await this.bundleOnce();
      return this.renderMiss(identity, bundle, contracts);
    });
  }

  private async contracts(): Promise<ResolvedContracts> {
    if (this.resolved) return this.resolved;
    const [boil, grade] = await Promise.all([
      resolveBoilContract(this.options.boilModulePath),
      resolveGradeContract(this.options.gradeModulePath),
    ]);
    this.resolved = { root: this.root, boil, grade };
    return this.resolved;
  }

  private bundleOnce(): Promise<BundleHandle> {
    if (!this.bundleTask) {
      const task = Promise.resolve()
        .then(() => this.options.bundle?.() ?? bundleHeadlessComposition(this.root))
        .then((handle) => {
          if (!handle || typeof handle !== "object") throw new RenderPoolError("bundle() returned no composition");
          if (typeof handle.compositionId !== "string" || handle.compositionId.trim() === "") {
            throw new RenderPoolError("bundle() compositionId must be a non-empty string");
          }
          if (handle.fps !== CONTAINER_FPS || handle.width !== FRAME_WIDTH || handle.height !== FRAME_HEIGHT) {
            throw new RenderPoolError(
              `bundle is locked to ${FRAME_WIDTH}x${FRAME_HEIGHT} @ ${CONTAINER_FPS} fps, received ${handle.width}x${handle.height} @ ${handle.fps} fps`,
            );
          }
          return handle;
        });
      this.bundleTask = task;
      void task.then(
        () => undefined,
        () => {
          if (this.bundleTask === task) this.bundleTask = null;
        },
      );
    }
    return this.bundleTask;
  }

  private async readCache(identity: Identity, contracts: ResolvedContracts): Promise<SceneRenderReceipt | null> {
    if (nodeFs.existsSync(identity.finalPath)) {
      const probed = await this.probe(identity.finalPath, identity.durationFrames);
      if (probed.ok) {
        await this.ensureGrade(identity, contracts);
        return this.receipt(identity, contracts, {
          cacheHit: true,
          recoveredFromTmp: false,
          workMs: 0,
          compositionId: this.root.id,
        });
      }
      await rmQuiet(identity.finalPath);
    }
    if (nodeFs.existsSync(identity.tmpPath)) {
      const probed = await this.probe(identity.tmpPath, identity.durationFrames);
      if (probed.ok) {
        await nodeFsPromises.rename(identity.tmpPath, identity.finalPath);
        await this.ensureGrade(identity, contracts);
        return this.receipt(identity, contracts, {
          cacheHit: false,
          recoveredFromTmp: true,
          workMs: 0,
          compositionId: this.root.id,
        });
      }
      await rmQuiet(identity.tmpPath);
    }
    return null;
  }

  private async renderMiss(
    identity: Identity,
    bundle: BundleHandle,
    contracts: ResolvedContracts,
  ): Promise<SceneRenderReceipt> {
    const workStart = this.now();
    const applyGrade = contracts.grade.sceneNeedsGrade(gradeInput(identity));
    const gradeBody = this.manifest(identity, contracts);
    const request = this.requestFor(identity, bundle, contracts.boil, applyGrade);
    try {
      const render = this.options.render ?? ((job: HeadlessRenderRequest) => defaultRender(job, this.ffmpegBin));
      await render(request);
    } catch (error) {
      await rmQuiet(identity.tmpPath);
      if (error instanceof RenderPoolError) throw error;
      throw new RenderPoolError(messageOf(error));
    }
    if (nodeFs.existsSync(identity.finalPath)) {
      await rmQuiet(identity.finalPath);
      await rmQuiet(identity.tmpPath);
      throw new RenderPoolError("renderer wrote the final mp4 directly; publish must ffprobe the tmp file and rename it");
    }
    if (!nodeFs.existsSync(identity.tmpPath)) {
      throw new RenderPoolError(`renderer did not write ${identity.tmpPath}`);
    }
    const probed = await this.probe(identity.tmpPath, identity.durationFrames);
    const workMs = this.now() - workStart;
    if (!probed.ok) {
      await rmQuiet(identity.tmpPath);
      throw new RenderPoolError(`ffprobe rejected ${identity.sceneId}: ${probed.reason}`);
    }
    if (workMs >= SINGLE_SCENE_RERENDER_BUDGET_MS) {
      await rmQuiet(identity.tmpPath);
      throw new RenderPoolError(
        `single-scene re-render took ${workMs.toFixed(1)} ms; budget is ${SINGLE_SCENE_RERENDER_BUDGET_MS} ms`,
      );
    }
    await nodeFsPromises.rename(identity.tmpPath, identity.finalPath);
    await atomicWrite(identity.gradePath, gradeBody);
    return this.receipt(identity, contracts, {
      cacheHit: false,
      recoveredFromTmp: false,
      workMs,
      compositionId: bundle.compositionId,
      applyGrade,
    });
  }

  private requestFor(
    identity: Identity,
    bundle: BundleHandle,
    boil: BoilContract,
    applyGrade: boolean,
  ): HeadlessRenderRequest {
    return {
      bundle,
      sceneId: identity.sceneId,
      cacheKey: identity.cacheKey,
      canonicalSceneJson: identity.canonicalSceneJson,
      caseBibleHash: identity.caseBibleHash,
      outputPath: identity.tmpPath,
      durationFrames: identity.durationFrames,
      paperBgHex: this.paperBgHex,
      fps: 30,
      width: 1920,
      height: 1080,
      boil,
      grade: {
        paperGrain: 0,
        vignette: 0,
        remotionGrainApplied: false,
        remotionVignetteApplied: false,
        applyGrade,
        paperBgHex: this.paperBgHex,
      },
    };
  }

  private manifest(identity: Identity, contracts: ResolvedContracts): string {
    const scenes = [gradeInput(identity)];
    const value = identity.episodeId === undefined
      ? contracts.grade.buildSceneGradeManifest(scenes)
      : contracts.grade.buildSceneGradeManifest(scenes, identity.episodeId);
    return asJsonFile(value);
  }

  private async ensureGrade(identity: Identity, contracts: ResolvedContracts): Promise<void> {
    if (nodeFs.existsSync(identity.gradePath)) return;
    await atomicWrite(identity.gradePath, this.manifest(identity, contracts));
  }

  private async probe(filePath: string, durationFrames: number): Promise<FfprobeResult> {
    if (this.options.ffprobe) return this.options.ffprobe(filePath, { durationFrames });
    return ffprobeVerify(filePath, durationFrames, this.ffprobeBin);
  }

  private receipt(
    identity: Identity,
    contracts: ResolvedContracts,
    flags: {
      cacheHit: boolean;
      recoveredFromTmp: boolean;
      workMs: number;
      compositionId: string;
      applyGrade?: boolean;
    },
  ): SceneRenderReceipt {
    const applyGrade = flags.applyGrade ?? contracts.grade.sceneNeedsGrade(gradeInput(identity));
    return {
      sceneId: identity.sceneId,
      cacheKey: identity.cacheKey,
      outputPath: identity.finalPath,
      gradePath: identity.gradePath,
      cacheHit: flags.cacheHit,
      recoveredFromTmp: flags.recoveredFromTmp,
      elapsedMs: flags.workMs,
      workMs: flags.workMs,
      durationFrames: identity.durationFrames,
      compositionId: flags.compositionId,
      applyGrade,
      ...lockedMedia(),
    };
  }
}
