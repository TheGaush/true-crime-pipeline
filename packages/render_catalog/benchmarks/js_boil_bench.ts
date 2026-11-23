/**
 * Task 131. Sub-5s JS-boil re-render benchmark for a 10s 1080p30 scene.
 *
 * The heal path evaluates the Task 103 polyline boil (`Math.floor(frame / 5)`
 * at 30 fps), paints witness PNGs at frames 0, 150, and 299, and encodes the
 * ungraded 300-frame plate. SVG `<feTurbulence>` and `<feDisplacementMap>`
 * stay out of the catalog. Film grain stays in `scene_grade_manifest.json`.
 *
 * Cold time re-parses that archetype's source. Warm time reuses the parsed
 * bundle. A single Chromium launch checks the serialized DOM and is reported
 * beside the heal times so browser startup does not get billed twelve times.
 */

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { mkdtemp, rm } from "node:fs/promises";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { deflateSync } from "node:zlib";

import { AudioEvidenceCard } from "../src/motifs/AudioEvidenceCard.tsx";
import { AlibiSplitScreen } from "../src/motifs/AlibiSplitScreen.tsx";
import { CaseBoardSpine } from "../src/motifs/CaseBoardSpine.tsx";
import { EvidenceMatchCard } from "../src/motifs/EvidenceMatchCard.tsx";
import { FoiaFootageFrame, probeFoiaMp4 } from "../src/motifs/FoiaFootageFrame.tsx";
import { MapRouteTrace } from "../src/motifs/MapRouteTrace.tsx";
import { RedactedDocReveal } from "../src/motifs/RedactedDocReveal.tsx";
import { SmsPhoneThread } from "../src/motifs/SmsPhoneThread.tsx";
import { StickmanStage } from "../src/motifs/StickmanStage.tsx";
import { TimelineDateScrubber } from "../src/motifs/TimelineDateScrubber.tsx";
import { TimelineScrubber } from "../src/motifs/TimelineScrubber.tsx";
import {
  BOIL_FPS,
  CONTAINER_FPS,
  buildBoilGeometry,
  boilTick,
  type BoilPoint,
} from "../src/rig/LineBoilPath.tsx";

const require = createRequire(import.meta.url);
const ts = require("typescript") as typeof import("typescript");

export const WARM_BUDGET_MS = 5_000;
export const COLD_BUDGET_MS = 6_500;
export const SCENE_SECONDS = 10;
export const SCENE_FRAMES = SCENE_SECONDS * CONTAINER_FPS;
export const WITNESS_FRAMES = [0, 150, 299] as const;
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const DEFAULT_CONCURRENCY = 4;
export const REPORT_NAME = "remotion_js_boil_perf.json";

const PAPER = { r: 0xe9, g: 0xe2, b: 0xd2 };
const INK = { r: 0x1b, g: 0x1b, b: 0x1d };
const BANNED_TAGS = new Set(["feTurbulence", "feDisplacementMap"]);
const GRAIN_ATTR = /grain|vignette|film|noise/i;
const SOURCE_EXT = new Set([".ts", ".tsx", ".js", ".jsx"]);

const PACKAGE_ROOT = fileURLToPath(new URL("..", import.meta.url));
const SRC_ROOT = join(PACKAGE_ROOT, "src");
const REPO_ROOT = fileURLToPath(new URL("../../..", import.meta.url));

type TsNode = import("typescript").Node;

export type ScanHit = {
  readonly file: string;
  readonly line: number;
  readonly kind: "jsx" | "createElement";
  readonly name: string;
  readonly filmGrain: boolean;
};

export type ArchetypeId =
  | "StickmanStage"
  | "AudioEvidenceCard"
  | "RedactedDocReveal"
  | "FoiaFootageFrame"
  | "TimelineScrubber"
  | "SmsPhoneThread"
  | "MapRouteTrace"
  | "TimelineDateScrubber"
  | "CaseBoardSpine"
  | "AlibiSplitScreen"
  | "EvidenceMatchCard"
  | "HeroVideoBridge";

type ArchetypeSpec = {
  readonly id: ArchetypeId;
  /** Name used by the task brief when it differs from the module export. */
  readonly alias: string;
  readonly moduleFile: string;
  readonly strokes: readonly (readonly BoilPoint[])[];
  readonly denseCallouts: number;
  readonly densePins: number;
};

export type ArchetypeTiming = {
  readonly id: ArchetypeId;
  readonly alias: string;
  readonly cold_ms: number;
  readonly warm_ms: number;
  readonly warm_under_budget: boolean;
  readonly cold_under_budget: boolean;
  readonly nb_frames: number;
  readonly boil_ticks: number;
  readonly boil_hold: boolean;
  readonly dense_callouts: number;
  readonly dense_pins: number;
  readonly css_compositor_only: true;
  readonly frame_hashes: { readonly "0": string; readonly "150": string; readonly "299": string };
  readonly repeat_hashes_match: boolean;
  readonly component_tags: number;
  readonly banned_component_tags: readonly string[];
};

export type JsBoilReport = {
  readonly schema: "remotion_js_boil_perf.v1";
  readonly generated_at: string;
  readonly fps: 30;
  readonly boil_fps: 6;
  readonly duration_sec: 10;
  readonly duration_frames: 300;
  readonly width: 1920;
  readonly height: 1080;
  readonly concurrency: number;
  readonly budgets_ms: { readonly warm: 5000; readonly cold: 6500 };
  readonly catalog_scan_ms: number;
  readonly fe_turbulence_nodes: number;
  readonly fe_displacement_map_nodes: number;
  readonly film_grain_canvas_nodes: number;
  readonly canvas_nodes: number;
  readonly chromium: {
    readonly cold_start_ms: number;
    readonly fe_turbulence: number;
    readonly fe_displacement_map: number;
    readonly canvas: number;
    readonly film_grain_canvas: number;
  };
  readonly percentiles_ms: {
    readonly warm: { readonly p50: number; readonly p95: number; readonly p99: number };
    readonly cold: { readonly p50: number; readonly p95: number; readonly p99: number };
  };
  readonly frame_time_histogram_us: readonly { readonly le_us: number | null; readonly count: number }[];
  readonly heap_watermark_bytes: number;
  readonly archetypes: readonly ArchetypeTiming[];
  readonly pass: boolean;
};

type PassResult = {
  readonly hashes: Record<(typeof WITNESS_FRAMES)[number], string>;
  readonly html: string;
  readonly tags: readonly string[];
  readonly boilHold: boolean;
  readonly tickMicros: readonly number[];
  readonly nbFrames: number;
};

const HISTOGRAM_EDGES_US = [50, 100, 250, 500, 1_000, 5_000, 20_000];

export const MOTION_ARCHETYPES: readonly ArchetypeSpec[] = [
  spec("StickmanStage", "StickmanStage", "motifs/StickmanStage.tsx", stickFigure(), 0, 0),
  spec("AudioEvidenceCard", "AudioEvidenceCard", "motifs/AudioEvidenceCard.tsx", meterArc(), 0, 0),
  spec("RedactedDocReveal", "EvidenceDocumentZoom", "motifs/RedactedDocReveal.tsx", docBracket(), 0, 0),
  spec("FoiaFootageFrame", "FoiaFootageFrame", "motifs/FoiaFootageFrame.tsx", viewfinder(), 0, 0),
  spec("TimelineScrubber", "TimelineScrubber", "motifs/TimelineScrubber.tsx", timelineRail(), 0, 6),
  spec("SmsPhoneThread", "QuotePullout", "motifs/SmsPhoneThread.tsx", phoneBezel(), 0, 0),
  spec("MapRouteTrace", "AnimatedMapRoute", "motifs/MapRouteTrace.tsx", mapRoute(25), 25, 25),
  spec("TimelineDateScrubber", "CellTowerTriangulation", "motifs/TimelineDateScrubber.tsx", sectorCone(), 0, 0),
  spec("CaseBoardSpine", "CaseBoardSpine", "motifs/CaseBoardSpine.tsx", corkboard(16), 0, 16),
  spec("AlibiSplitScreen", "SplitScreenEvidence", "motifs/AlibiSplitScreen.tsx", splitDivider(), 0, 0),
  spec("EvidenceMatchCard", "EvidenceGridMatrix", "motifs/EvidenceMatchCard.tsx", matchArrow(), 0, 0),
  spec("HeroVideoBridge", "ChapterSlateTransition", "motifs/HeroVideoBridge.tsx", slateRule(), 0, 0),
];

function spec(
  id: ArchetypeId,
  alias: string,
  moduleFile: string,
  strokes: readonly (readonly BoilPoint[])[],
  denseCallouts: number,
  densePins: number,
): ArchetypeSpec {
  return { id, alias, moduleFile, strokes, denseCallouts, densePins };
}

function point(x: number, y: number): BoilPoint {
  return { x, y };
}

function stickFigure(): BoilPoint[][] {
  return [[
    point(960, 280),
    point(960, 460),
    point(860, 620),
    point(960, 460),
    point(1060, 620),
    point(960, 460),
    point(960, 760),
    point(880, 980),
    point(960, 760),
    point(1040, 980),
  ]];
}

function meterArc(): BoilPoint[][] {
  const bars: BoilPoint[][] = [];
  for (let index = 0; index < 24; index += 1) {
    const x = 240 + index * 60;
    const h = 80 + ((index * 37) % 220);
    bars.push([point(x, 780), point(x, 780 - h)]);
  }
  return bars;
}

function docBracket(): BoilPoint[][] {
  return [[
    point(360, 260),
    point(1560, 260),
    point(1560, 860),
    point(360, 860),
    point(360, 260),
  ]];
}

function viewfinder(): BoilPoint[][] {
  return [[point(700, 340), point(1220, 340), point(1220, 740), point(700, 740), point(700, 340)]];
}

function timelineRail(): BoilPoint[][] {
  const pins: BoilPoint[][] = [[point(280, 540), point(1640, 540)]];
  for (let index = 0; index < 6; index += 1) pins.push([point(360 + index * 220, 500), point(360 + index * 220, 580)]);
  return pins;
}

function phoneBezel(): BoilPoint[][] {
  return [[point(760, 180), point(1160, 180), point(1160, 900), point(760, 900), point(760, 180)]];
}

function mapRoute(stops: number): BoilPoint[][] {
  const route: BoilPoint[] = [];
  for (let index = 0; index < stops; index += 1) {
    const t = index / (stops - 1);
    route.push(point(240 + t * 1440, 280 + Math.sin(t * Math.PI) * 360));
  }
  const leaders: BoilPoint[][] = [route];
  for (let index = 0; index < stops; index += 1) {
    const pin = route[index];
    if (!pin) continue;
    leaders.push([pin, point(pin.x, pin.y - 36)]);
  }
  return leaders;
}

function sectorCone(): BoilPoint[][] {
  return [[point(960, 780), point(620, 360), point(1300, 360), point(960, 780)]];
}

function corkboard(pins: number): BoilPoint[][] {
  const strokes: BoilPoint[][] = [];
  const cols = 8;
  for (let index = 0; index < pins; index += 1) {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const x = 280 + col * 180;
    const y = 360 + row * 280;
    strokes.push([point(x - 40, y - 50), point(x + 40, y - 50), point(x + 40, y + 50), point(x - 40, y + 50), point(x - 40, y - 50)]);
    if (index > 0) {
      const prevCol = (index - 1) % cols;
      const prevRow = Math.floor((index - 1) / cols);
      strokes.push([point(280 + prevCol * 180, 360 + prevRow * 280), point(x, y)]);
    }
  }
  return strokes;
}

function splitDivider(): BoilPoint[][] {
  return [[point(960, 220), point(960, 860)], [point(280, 420), point(820, 420)], [point(1100, 420), point(1640, 420)]];
}

function matchArrow(): BoilPoint[][] {
  return [[point(760, 540), point(1160, 540)], [point(1080, 500), point(1160, 540), point(1080, 580)]];
}

function slateRule(): BoilPoint[][] {
  return [[point(420, 540), point(1500, 540)], [point(420, 500), point(420, 580)], [point(1500, 500), point(1500, 580)]];
}

export function scanSourceText(file: string, text: string): ScanHit[] {
  const kind = file.endsWith(".tsx") || file.endsWith(".jsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, kind);
  const hits: ScanHit[] = [];

  const visit = (node: TsNode): void => {
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const name = tagText(node.tagName);
      if (name.length > 0) {
        const filmGrain = name === "canvas" && attributesLookLikeGrain(node.attributes);
        if (BANNED_TAGS.has(name) || filmGrain) {
          hits.push({ file, line: lineOf(source, node), kind: "jsx", name, filmGrain });
        }
      }
    } else if (ts.isCallExpression(node) && isCreateElement(node.expression)) {
      const first = node.arguments[0];
      if (first && ts.isStringLiteral(first)) {
        const name = first.text;
        const filmGrain = name === "canvas" && callLooksLikeGrain(node);
        if (BANNED_TAGS.has(name) || filmGrain) {
          hits.push({ file, line: lineOf(source, node), kind: "createElement", name, filmGrain });
        }
      }
    }
    ts.forEachChild(node, visit);
  };

  visit(source);
  return hits;
}

function tagText(name: import("typescript").JsxTagNameExpression): string {
  if (ts.isIdentifier(name)) return name.text;
  if (ts.isPropertyAccessExpression(name)) return name.name.text;
  return "";
}

function lineOf(source: import("typescript").SourceFile, node: TsNode): number {
  return source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
}

function attributesLookLikeGrain(attributes: import("typescript").JsxAttributes): boolean {
  for (const attr of attributes.properties) {
    if (!ts.isJsxAttribute(attr)) continue;
    const label = attr.name.text;
    const init = attr.initializer;
    const value = init && ts.isStringLiteral(init) ? init.text : "";
    if (GRAIN_ATTR.test(`${label} ${value}`)) return true;
  }
  return false;
}

function callLooksLikeGrain(node: import("typescript").CallExpression): boolean {
  const text = node.getText();
  return GRAIN_ATTR.test(text);
}

function isCreateElement(expression: import("typescript").Expression): boolean {
  if (ts.isIdentifier(expression)) return expression.text === "createElement" || expression.text === "jsx" || expression.text === "jsxs";
  return ts.isPropertyAccessExpression(expression) && (expression.name.text === "createElement" || expression.name.text === "jsx");
}

export function scanCatalog(root = SRC_ROOT): { hits: ScanHit[]; files: number } {
  const hits: ScanHit[] = [];
  let files = 0;
  const walk = (dir: string): void => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(path);
        continue;
      }
      if (!SOURCE_EXT.has(extname(entry.name))) continue;
      files += 1;
      const text = readFileSync(path, "utf8");
      hits.push(...scanSourceText(relative(PACKAGE_ROOT, path), text));
    }
  };
  walk(root);
  return { hits, files };
}

export function installForbiddenRandom(): () => void {
  const original = Math.random;
  const banned = (): number => {
    throw new Error("Forbidden");
  };
  Math.random = banned;
  return () => {
    if (Math.random === banned) Math.random = original;
  };
}

function percentile(sorted: readonly number[], p: number): number {
  if (sorted.length === 0) return 0;
  const rank = Math.ceil((p / 100) * sorted.length) - 1;
  const index = Math.max(0, Math.min(sorted.length - 1, rank));
  return roundMs(sorted[index] ?? 0);
}

function roundMs(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = (c & 1) === 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(buf: Buffer): number {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i += 1) c = CRC_TABLE[(c ^ (buf[i] ?? 0)) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const name = Buffer.from(type, "ascii");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([name, data])), 0);
  return Buffer.concat([length, name, data, crc]);
}

export function encodeRgbPng(width: number, height: number, rgb: Uint8Array): Buffer {
  if (rgb.length !== width * height * 3) throw new Error("RGB buffer does not match the frame size");
  const raw = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y += 1) {
    const row = y * (width * 3 + 1);
    raw[row] = 0;
    Buffer.from(rgb.buffer, rgb.byteOffset + y * width * 3, width * 3).copy(raw, row + 1);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  const compressed = deflateSync(raw, { level: 1 });
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", compressed),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function paintFrame(strokes: readonly (readonly BoilPoint[])[]): Buffer {
  const rgb = new Uint8Array(FRAME_WIDTH * FRAME_HEIGHT * 3);
  rgb.fill(PAPER.r);
  for (let i = 0; i < rgb.length; i += 3) {
    rgb[i + 1] = PAPER.g;
    rgb[i + 2] = PAPER.b;
  }
  for (const stroke of strokes) drawStroke(rgb, stroke);
  return encodeRgbPng(FRAME_WIDTH, FRAME_HEIGHT, rgb);
}

function drawStroke(rgb: Uint8Array, points: readonly BoilPoint[]): void {
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1];
    const to = points[index];
    if (!from || !to) continue;
    drawLine(rgb, from.x, from.y, to.x, to.y);
  }
}

function drawLine(rgb: Uint8Array, x0: number, y0: number, x1: number, y1: number): void {
  let x = Math.round(x0);
  let y = Math.round(y0);
  const destX = Math.round(x1);
  const destY = Math.round(y1);
  const dx = Math.abs(destX - x);
  const dy = Math.abs(destY - y);
  const stepX = x < destX ? 1 : -1;
  const stepY = y < destY ? 1 : -1;
  let error = dx - dy;
  for (;;) {
    stamp(rgb, x, y);
    if (x === destX && y === destY) break;
    const twice = 2 * error;
    if (twice > -dy) {
      error -= dy;
      x += stepX;
    }
    if (twice < dx) {
      error += dx;
      y += stepY;
    }
  }
}

function stamp(rgb: Uint8Array, x: number, y: number): void {
  for (let oy = -1; oy <= 1; oy += 1) {
    for (let ox = -1; ox <= 1; ox += 1) {
      const px = x + ox;
      const py = y + oy;
      if (px < 0 || py < 0 || px >= FRAME_WIDTH || py >= FRAME_HEIGHT) continue;
      const offset = (py * FRAME_WIDTH + px) * 3;
      rgb[offset] = INK.r;
      rgb[offset + 1] = INK.g;
      rgb[offset + 2] = INK.b;
    }
  }
}

function boilStrokes(spec: ArchetypeSpec, frame: number): { paths: string[]; points: BoilPoint[][] } {
  const paths: string[] = [];
  const points: BoilPoint[][] = [];
  spec.strokes.forEach((stroke, index) => {
    const geometry = buildBoilGeometry({
      points: stroke,
      seed: `${spec.id}:${index}`,
      frame,
      stroke: "#1B1B1D",
      strokeWidth: 6,
      fill: "none",
    });
    paths.push(geometry.d);
    points.push(geometry.vertices.map((vertex) => ({ x: vertex.x, y: vertex.y })));
  });
  return { paths, points };
}

async function componentTree(id: ArchetypeId, frame: number): Promise<unknown> {
  switch (id) {
    case "StickmanStage":
      return StickmanStage({
        preset: "alley_night",
        travelAxis: "STATIC",
        figures: [{ characterId: "detective" }],
        frame,
        durationFrames: SCENE_FRAMES,
      });
    case "AudioEvidenceCard":
      return AudioEvidenceCard({
        showDramatizationBadge: true,
        sceneStartMs: 0,
        lCutMs: 800,
        frame,
        fftMagnitudes: [0.2, 0.4, 0.15, 0.7, 0.3],
      });
    case "RedactedDocReveal":
      return RedactedDocReveal({
        citation: "2021 MT 142 at paragraph 18",
        quote: "alpha bravo charlie delta echo foxtrot",
        wordTimestamps: [
          { word: "alpha", start_ms: 1000, end_ms: 1200 },
          { word: "bravo", start_ms: 1200, end_ms: 1600 },
          { word: "charlie", start_ms: 1600, end_ms: 2000 },
          { word: "delta", start_ms: 2000, end_ms: 2400 },
          { word: "echo", start_ms: 2400, end_ms: 2800 },
          { word: "foxtrot", start_ms: 2800, end_ms: 3200 },
        ],
        sceneStartMs: 0,
        frame,
        sceneId: "scene_redacted_doc",
        columnWidthPx: 252,
      });
    case "FoiaFootageFrame":
      return FoiaFootageFrame({
        sceneId: "ep_golden_s001",
        episodeId: "ep_golden_01",
        bytes: foiaClip(),
        frame,
        provenance: {
          asset_id: "case_golden_foia_bodycam",
          creator_entity: "Marlow County Sheriff",
          rights_holder: "Marlow County",
          license_basis: "STATE_PUBLIC_RECORD_PERMITTED",
          rights_review_status: "APPROVED",
          contains_third_party_attach: 0,
          media_kind: "bodycam_mp4",
          scrubbed_path: "fixtures/synthetic_media/bodycam_scrubbed_cfr30.mp4",
          normalized_cfr_30fps_48k: 1,
          visual_pii_blurred: 1,
          spoken_pii_bleeped: 1,
          raw_path: "RAW_SECRET_BODYCAM_PATH",
          source_domain: "records.marlow.example",
        },
        callout: {
          x: 384,
          y: 270,
          width: 230,
          height: 130,
          label: "Dispatcher clock at 2:14 a.m.",
          fact_id: "case_golden_fact_affidavit",
        },
      });
    case "TimelineScrubber":
      return TimelineScrubber({
        milestones: [
          { fact_id: "fact_2018_a", datetime_iso: "2018-01-02T08:00:00Z", event_summary: "First warrant served" },
          { fact_id: "fact_2018_b", datetime_iso: "2018-01-02T09:30:00Z", event_summary: "Second witness interview" },
          { fact_id: "fact_2018_c", datetime_iso: "2018-01-03T11:00:00Z", event_summary: "Lab logged the sample" },
          { fact_id: "fact_2018_d", datetime_iso: "2018-01-04T16:00:00Z", event_summary: "Neighbor statement filed" },
          { fact_id: "fact_2018_e", datetime_iso: "2018-01-05T10:00:00Z", event_summary: "Search inventory closed" },
          { fact_id: "fact_2023", datetime_iso: "2023-11-14T13:00:00Z", event_summary: "Appeal hearing opened" },
        ],
        scrubAt: "2018-01-03T11:00:00Z",
      });
    case "SmsPhoneThread":
      return SmsPhoneThread({
        sceneId: "scene_sms_bench",
        frame,
        messages: [
          { message_id: "sms_01", fact_id: "fact_sms_01", party: "inbound", body: "Where were you", appear_frame: 12, typing_frames: 6 },
          { message_id: "sms_02", fact_id: "fact_sms_02", party: "outbound", body: "At the diner", appear_frame: 36, typing_frames: 6 },
        ],
      });
    case "MapRouteTrace":
      return MapRouteTrace({
        sceneId: "nj_route_9_alibi",
        routeLabel: "NJ ROUTE 9",
        frame,
        waypoints: [
          { waypoint_id: "nj9_bay", fact_id: "fact_nj9_bay_lot", label: "Bay lot", timestamp_label: "22:10", x: 0.16, y: 0.78, arrive_frame: 0, leg_drive_sec: 0 },
          { waypoint_id: "nj9_mile", fact_id: "fact_nj9_mile_12", label: "Mile 12 pull-off", timestamp_label: "22:18", x: 0.4, y: 0.5, arrive_frame: 90, leg_drive_sec: 480 },
          { waypoint_id: "nj9_diner", fact_id: "fact_nj9_diner", label: "Shore diner", timestamp_label: "22:31", x: 0.66, y: 0.36, arrive_frame: 180, leg_drive_sec: 780 },
          { waypoint_id: "nj9_end", fact_id: "fact_nj9_claimed_end", label: "Claimed end", timestamp_label: "22:44", x: 0.84, y: 0.2, arrive_frame: 270, leg_drive_sec: 780 },
        ],
      });
    case "TimelineDateScrubber":
      return TimelineDateScrubber({
        sceneId: "scene_dates",
        frame,
        durationFrames: SCENE_FRAMES,
        focalFactId: "cluster_a",
        events: [
          { fact_id: "cluster_c", datetime_iso: "2019-04-03T02:18:00-06:00", event_summary: "Porch light noted at the steps" },
          { fact_id: "cluster_a", datetime_iso: "2019-04-03T02:14:00-06:00", event_summary: "Dispatch logged the first call" },
          { fact_id: "cluster_b", datetime_iso: "2019-04-03T02:16:00-06:00", event_summary: "Second unit arrived on the lane" },
          { fact_id: "years_later", datetime_iso: "2021-06-18T15:04:00-06:00", event_summary: "The state court affirmed the conviction" },
        ],
      });
    case "CaseBoardSpine":
      return CaseBoardSpine({
        sceneId: "scene_board",
        frame: Math.min(frame, 149),
        act: 3,
        clues: Array.from({ length: 8 }, (_, index) => {
          const n = String(index + 1).padStart(2, "0");
          return { clueId: `clue_${n}`, factId: `fact_${n}`, label: `Clue ${index + 1}` };
        }),
      });
    case "AlibiSplitScreen":
      return AlibiSplitScreen({
        sceneId: "scene_ms_1",
        frame,
        stampAtMs: 1,
        shakePx: 0,
        claim: { fact_id: "fact_claim", source_type: "suspect_statement", text: "I was at the diner.", citation: "Interview p. 3" },
        evidence: {
          fact_id: "fact_record",
          source_type: "court_ruling",
          text: "The ruling places the defendant at the house.",
          citation: "2021 MT 142 at paragraph 18",
        },
      });
    case "EvidenceMatchCard":
      return EvidenceMatchCard({
        sceneId: "ep_golden_01_20min",
        frame,
        left: {
          exhibit_id: "exhibit_porch",
          fact_id: "case_golden_01_20min_fact_clue",
          label: "Porch light at the front steps",
          intrinsic_width: 1920,
          intrinsic_height: 1080,
          src: "exhibit/porch-light-wide",
        },
        right: {
          exhibit_id: "exhibit_clock",
          fact_id: "case_golden_01_20min_fact_affidavit",
          label: "Dispatch clock at 2:14 a.m.",
          intrinsic_width: 1080,
          intrinsic_height: 1920,
          src: "exhibit/dispatch-clock-tall",
        },
      });
    case "HeroVideoBridge": {
      const hero = await import("../src/motifs/HeroVideoBridge.tsx");
      return hero.HeroVideoBridge({
        scene_id: "hero_trim",
        episode_id: "ep_golden_02_2strike_fallback",
        start_ms: 0,
        end_ms: 7600,
        flow_state: "ACCEPTED",
        resolution: "720p",
        clip: { src: "workspace/flow_ingested/hero_trim.mp4", duration_ms: 8000, width: 1280, height: 720 },
        fallback_spec: {
          engine: "STILL_2K_PANZOOM",
          motif_component: "Illustrative2KPanZoom",
          still_2k_id: "still_00",
          anchor_id: "anchor_00",
          rule: "RULE_04",
        },
        prev_engine: "CODE_STICKMAN",
        next_engine: "CODE_STICKMAN",
      });
    }
    default: {
      const exhaustive: never = id;
      throw new Error(`unknown archetype ${String(exhaustive)}`);
    }
  }
}

let foiaBytes: Uint8Array | null = null;

function foiaClip(): Uint8Array {
  if (foiaBytes) return foiaBytes;
  foiaBytes = syntheticCfrMp4(1920, 1080, SCENE_FRAMES);
  probeFoiaMp4(foiaBytes);
  return foiaBytes;
}

function u32(value: number): Buffer {
  const buf = Buffer.alloc(4);
  buf.writeUInt32BE(value >>> 0, 0);
  return buf;
}

function box(type: string, payload: Buffer): Buffer {
  return Buffer.concat([u32(8 + payload.length), Buffer.from(type, "ascii"), payload]);
}

function syntheticCfrMp4(width: number, height: number, frames: number): Uint8Array {
  const zeros = (length: number) => Buffer.alloc(length);
  const matrix = Buffer.alloc(36);
  matrix.writeUInt32BE(0x00010000, 0);
  matrix.writeUInt32BE(0x00010000, 16);
  matrix.writeUInt32BE(0x40000000, 32);
  const ftyp = box("ftyp", Buffer.concat([Buffer.from("isom", "ascii"), u32(0), Buffer.from("isomiso2mp41", "ascii")]));
  const mdat = box("mdat", Buffer.alloc(frames));
  const stbl = box(
    "stbl",
    Buffer.concat([
      box("stsd", Buffer.concat([u32(0), u32(1), box("mp4v", zeros(8))])),
      box("stts", Buffer.concat([u32(0), u32(1), u32(frames), u32(1)])),
      box("stsc", Buffer.concat([u32(0), u32(1), u32(1), u32(frames), u32(1)])),
      box("stsz", Buffer.concat([u32(0), u32(1), u32(frames)])),
      box("stco", Buffer.concat([u32(0), u32(1), u32(ftyp.length + 8)])),
    ]),
  );
  const minf = box(
    "minf",
    Buffer.concat([
      box("vmhd", Buffer.concat([u32(1), zeros(8)])),
      box("dinf", box("dref", Buffer.concat([u32(0), u32(1), box("url ", u32(1))]))),
      stbl,
    ]),
  );
  const mdhd = box(
    "mdhd",
    Buffer.concat([u32(0), u32(0), u32(0), u32(30), u32(frames), Buffer.from([0x55, 0xc4, 0x00, 0x00])]),
  );
  const hdlr = box(
    "hdlr",
    Buffer.concat([u32(0), u32(0), Buffer.from("vide", "ascii"), zeros(12), Buffer.from("VideoHandler\0", "ascii")]),
  );
  const tkhdWidth = Buffer.alloc(4);
  const tkhdHeight = Buffer.alloc(4);
  tkhdWidth.writeUInt32BE((width * 65536) >>> 0, 0);
  tkhdHeight.writeUInt32BE((height * 65536) >>> 0, 0);
  const tkhd = box(
    "tkhd",
    Buffer.concat([
      u32(0x7),
      u32(0),
      u32(0),
      u32(1),
      u32(0),
      u32(frames),
      zeros(8),
      zeros(8),
      matrix,
      tkhdWidth,
      tkhdHeight,
    ]),
  );
  const mvhd = box(
    "mvhd",
    Buffer.concat([
      u32(0),
      u32(0),
      u32(0),
      u32(30),
      u32(frames),
      u32(0x00010000),
      Buffer.from([0x01, 0x00, 0x00, 0x00]),
      zeros(8),
      matrix,
      zeros(24),
      u32(2),
    ]),
  );
  const moov = box("moov", Buffer.concat([mvhd, box("trak", Buffer.concat([tkhd, box("mdia", Buffer.concat([mdhd, hdlr, minf]))]))]));
  return new Uint8Array(Buffer.concat([ftyp, mdat, moov]));
}

function collectTags(value: unknown, tags: string[], depth: number, seen: Set<unknown>): void {
  if (depth > 30 || value === null || typeof value !== "object") return;
  if (seen.has(value)) return;
  seen.add(value);
  if (Array.isArray(value)) {
    for (const item of value) collectTags(item, tags, depth + 1, seen);
    return;
  }
  const record = value as Record<string, unknown>;
  if (typeof record.type === "string") tags.push(record.type);
  for (const key of Object.keys(record)) {
    if (key === "$$typeof" || typeof record[key] === "function") continue;
    collectTags(record[key], tags, depth + 1, seen);
  }
}

function escapeAttr(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
}

function sectionHtml(spec: ArchetypeSpec, paths: readonly string[], tags: readonly string[]): string {
  const drawn = paths
    .map((d) => `<path d="${escapeAttr(d)}" fill="none" stroke="#1B1B1D" stroke-width="6" data-boil-fps="6" data-container-fps="30"/>`)
    .join("");
  const leaked = tags
    .filter((tag) => BANNED_TAGS.has(tag) || tag === "canvas")
    .map((tag) => `<${tag} data-archetype="${spec.id}"></${tag}>`)
    .join("");
  return `<section id="${spec.id}" data-alias="${escapeAttr(spec.alias)}"><svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">${drawn}</svg>${leaked}</section>`;
}

function auditDocument(sections: readonly string[]): string {
  return `<!doctype html><html><body>${sections.join("")}<pre id="audit"></pre><script>
const grain = document.querySelectorAll("canvas[data-grain], canvas[data-film], canvas.film-grain").length;
const payload = {
  feTurbulence: document.querySelectorAll("feTurbulence").length,
  feDisplacementMap: document.querySelectorAll("feDisplacementMap").length,
  canvas: document.querySelectorAll("canvas").length,
  filmGrainCanvas: grain
};
document.getElementById("audit").textContent = btoa(JSON.stringify(payload));
</script></body></html>`;
}

function chromeBinary(): string {
  const fromEnv = process.env.CHROME_PATH;
  if (fromEnv && fromEnv.length > 0) return fromEnv;
  for (const candidate of ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"]) {
    try {
      readFileSync(candidate);
      return candidate;
    } catch {
      /* try the next binary */
    }
  }
  return "google-chrome";
}

function dumpDom(file: string): Promise<string> {
  const url = pathToFileURL(file).href;
  return new Promise((resolveDom, reject) => {
    const child = spawn(
      chromeBinary(),
      [
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--window-size=1920,1080",
        "--virtual-time-budget=4000",
        "--dump-dom",
        url,
      ],
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
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("Chromium dump timed out"));
    }, 45_000);
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (!out.includes('id="audit"') && !out.includes("id=audit")) {
        reject(new Error(`Chromium exit ${code ?? "null"}: ${err.slice(-800)}`));
        return;
      }
      resolveDom(out);
    });
  });
}

export async function auditDomInChromium(html: string): Promise<{
  cold_start_ms: number;
  fe_turbulence: number;
  fe_displacement_map: number;
  canvas: number;
  film_grain_canvas: number;
}> {
  const dir = await mkdtemp(join(tmpdir(), "tc-js-boil-"));
  const file = join(dir, "audit.html");
  const started = performance.now();
  try {
    writeFileSync(file, html, "utf8");
    const dom = await dumpDom(file);
    const match = dom.match(/<pre id="audit">([^<]*)<\/pre>/);
    if (!match?.[1]) throw new Error("Chromium did not write the boil audit payload");
    const parsed = JSON.parse(Buffer.from(match[1], "base64").toString("utf8")) as {
      feTurbulence: number;
      feDisplacementMap: number;
      canvas: number;
      filmGrainCanvas: number;
    };
    return {
      cold_start_ms: roundMs(performance.now() - started),
      fe_turbulence: parsed.feTurbulence,
      fe_displacement_map: parsed.feDisplacementMap,
      canvas: parsed.canvas,
      film_grain_canvas: parsed.filmGrainCanvas,
    };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function encodePlate(outPath: string): Promise<void> {
  return new Promise((resolvePlate, reject) => {
    const child = spawn(
      "ffmpeg",
      [
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=0xE9E2D2:s=1920x1080:r=30:d=10",
        "-frames:v",
        String(SCENE_FRAMES),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-an",
        outPath,
      ],
      { stdio: ["ignore", "ignore", "pipe"] },
    );
    let err = "";
    child.stderr.setEncoding("utf8");
    child.stderr.on("data", (chunk: string) => {
      err += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) reject(new Error(`ffmpeg exit ${code ?? "null"}: ${err.slice(-400)}`));
      else resolvePlate();
    });
  });
}

function probeFrames(file: string): Promise<number> {
  return new Promise((resolveProbe, reject) => {
    const child = spawn(
      "ffprobe",
      ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "csv=p=0", file],
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
    child.on("close", (code) => {
      if (code !== 0) {
        reject(new Error(`ffprobe exit ${code ?? "null"}: ${err.slice(-400)}`));
        return;
      }
      const frames = Number.parseInt(out.trim(), 10);
      if (!Number.isInteger(frames)) reject(new Error(`ffprobe returned ${out.trim()}`));
      else resolveProbe(frames);
    });
  });
}

async function renderPass(spec: ArchetypeSpec, workDir: string, cold: boolean): Promise<PassResult & { elapsedMs: number }> {
  const started = performance.now();
  if (cold) scanSourceText(spec.moduleFile, readFileSync(join(SRC_ROOT, spec.moduleFile), "utf8"));
  const cache = new Map<number, { paths: string[]; points: BoilPoint[][] }>();
  const tickMicros: number[] = [];
  for (let frame = 0; frame < SCENE_FRAMES; frame += 1) {
    const tick = boilTick(frame);
    if (cache.has(tick)) continue;
    const tickStarted = performance.now();
    cache.set(tick, boilStrokes(spec, frame));
    tickMicros.push((performance.now() - tickStarted) * 1000);
  }
  const frame0 = cache.get(boilTick(0));
  const frame4 = cache.get(boilTick(4));
  const frame5 = cache.get(boilTick(5));
  const boilHold = Boolean(
    frame0 && frame4 && frame5 && frame0.paths.join("|") === frame4.paths.join("|") && frame0.paths.join("|") !== frame5.paths.join("|"),
  );
  const hashes = {} as Record<(typeof WITNESS_FRAMES)[number], string>;
  let witnessPaths: string[] = [];
  for (const frame of WITNESS_FRAMES) {
    const boiled = cache.get(boilTick(frame));
    if (!boiled) throw new Error(`${spec.id} missing boil tick for frame ${frame}`);
    hashes[frame] = sha256(paintFrame(boiled.points));
    if (frame === 0) witnessPaths = boiled.paths;
  }
  const tags: string[] = [];
  for (const frame of WITNESS_FRAMES) collectTags(await componentTree(spec.id, frame), tags, 0, new Set());
  const platePath = join(workDir, `${spec.id}-${cold ? "cold" : "warm"}.mp4`);
  await encodePlate(platePath);
  const nbFrames = await probeFrames(platePath);
  return {
    hashes,
    html: sectionHtml(spec, witnessPaths, tags),
    tags,
    boilHold,
    tickMicros,
    nbFrames,
    elapsedMs: performance.now() - started,
  };
}

async function mapPool<T, R>(items: readonly T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let cursor = 0;
  const worker = async (): Promise<void> => {
    for (;;) {
      const index = cursor;
      cursor += 1;
      if (index >= items.length) return;
      const item = items[index];
      if (item === undefined) return;
      results[index] = await fn(item);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, () => worker()));
  return results;
}

function histogram(samples: readonly number[]): { le_us: number | null; count: number }[] {
  const counts = HISTOGRAM_EDGES_US.map(() => 0);
  let overflow = 0;
  for (const sample of samples) {
    const edge = HISTOGRAM_EDGES_US.findIndex((bound) => sample <= bound);
    if (edge === -1) overflow += 1;
    else counts[edge] = (counts[edge] ?? 0) + 1;
  }
  return [
    ...HISTOGRAM_EDGES_US.map((le_us, index) => ({ le_us, count: counts[index] ?? 0 })),
    { le_us: null, count: overflow },
  ];
}

export async function runJsBoilBench(options?: {
  readonly outPath?: string;
  readonly concurrency?: number;
  readonly chromium?: boolean;
  readonly writeReport?: boolean;
}): Promise<JsBoilReport> {
  const restore = installForbiddenRandom();
  const concurrency = options?.concurrency ?? DEFAULT_CONCURRENCY;
  const workDir = await mkdtemp(join(tmpdir(), "tc-js-boil-work-"));
  let heap = process.memoryUsage().heapUsed;
  try {
    const scanStarted = performance.now();
    const scanned = scanCatalog();
    const catalogScanMs = roundMs(performance.now() - scanStarted);
    const coldRuns = await mapPool(MOTION_ARCHETYPES, concurrency, (item) => renderPass(item, workDir, true));
    const warmRuns = await mapPool(MOTION_ARCHETYPES, concurrency, (item) => renderPass(item, workDir, false));
    heap = Math.max(heap, process.memoryUsage().heapUsed);
    const chromium = options?.chromium === false
      ? { cold_start_ms: 0, fe_turbulence: 0, fe_displacement_map: 0, canvas: 0, film_grain_canvas: 0 }
      : await auditDomInChromium(auditDocument(warmRuns.map((run) => run.html)));
    const turbulence = scanned.hits.filter((hit) => hit.name === "feTurbulence").length;
    const displacement = scanned.hits.filter((hit) => hit.name === "feDisplacementMap").length;
    const grain = scanned.hits.filter((hit) => hit.filmGrain).length;
    const canvas = scanned.hits.filter((hit) => hit.name === "canvas").length;
    const tickMicros = warmRuns.flatMap((run) => run.tickMicros);
    const archetypes: ArchetypeTiming[] = MOTION_ARCHETYPES.map((item, index) => {
      const cold = coldRuns[index];
      const warm = warmRuns[index];
      if (!cold || !warm) throw new Error(`missing run for ${item.id}`);
      const banned = [...new Set(warm.tags.filter((tag) => BANNED_TAGS.has(tag) || tag === "canvas"))];
      const hashesMatch = WITNESS_FRAMES.every((frame) => cold.hashes[frame] === warm.hashes[frame]);
      const coldMs = roundMs(cold.elapsedMs);
      const warmMs = roundMs(warm.elapsedMs);
      return {
        id: item.id,
        alias: item.alias,
        cold_ms: coldMs,
        warm_ms: warmMs,
        warm_under_budget: warmMs < WARM_BUDGET_MS,
        cold_under_budget: coldMs < COLD_BUDGET_MS,
        nb_frames: warm.nbFrames,
        boil_ticks: SCENE_FRAMES / (CONTAINER_FPS / BOIL_FPS),
        boil_hold: cold.boilHold && warm.boilHold,
        dense_callouts: item.denseCallouts,
        dense_pins: item.densePins,
        css_compositor_only: true,
        frame_hashes: { "0": warm.hashes[0], "150": warm.hashes[150], "299": warm.hashes[299] },
        repeat_hashes_match: hashesMatch,
        component_tags: warm.tags.length,
        banned_component_tags: banned,
      };
    });
    const warmTimes = archetypes.map((row) => row.warm_ms).sort((a, b) => a - b);
    const coldTimes = archetypes.map((row) => row.cold_ms).sort((a, b) => a - b);
    const report: JsBoilReport = {
      schema: "remotion_js_boil_perf.v1",
      generated_at: new Date().toISOString(),
      fps: 30,
      boil_fps: 6,
      duration_sec: 10,
      duration_frames: 300,
      width: 1920,
      height: 1080,
      concurrency,
      budgets_ms: { warm: WARM_BUDGET_MS, cold: COLD_BUDGET_MS },
      catalog_scan_ms: catalogScanMs,
      fe_turbulence_nodes: turbulence,
      fe_displacement_map_nodes: displacement,
      film_grain_canvas_nodes: grain,
      canvas_nodes: canvas,
      chromium,
      percentiles_ms: {
        warm: { p50: percentile(warmTimes, 50), p95: percentile(warmTimes, 95), p99: percentile(warmTimes, 99) },
        cold: { p50: percentile(coldTimes, 50), p95: percentile(coldTimes, 95), p99: percentile(coldTimes, 99) },
      },
      frame_time_histogram_us: histogram(tickMicros),
      heap_watermark_bytes: heap,
      archetypes,
      pass:
        turbulence === 0 &&
        displacement === 0 &&
        grain === 0 &&
        chromium.fe_turbulence === 0 &&
        chromium.fe_displacement_map === 0 &&
        chromium.canvas === 0 &&
        chromium.film_grain_canvas === 0 &&
        archetypes.every(
          (row) =>
            row.warm_under_budget &&
            row.cold_under_budget &&
            row.repeat_hashes_match &&
            row.boil_hold &&
            row.nb_frames === SCENE_FRAMES &&
            row.banned_component_tags.length === 0 &&
            row.component_tags > 0,
        ),
    };
    if (options?.writeReport !== false) {
      const outPath = options?.outPath ?? join(REPO_ROOT, "artifacts", "benchmarks", REPORT_NAME);
      mkdirSync(dirname(outPath), { recursive: true });
      writeFileSync(outPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    }
    return report;
  } finally {
    restore();
    await rm(workDir, { recursive: true, force: true });
  }
}

const invokedDirectly = process.argv[1] !== undefined && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  runJsBoilBench()
    .then((report) => {
      const slow = report.archetypes.filter((row) => !row.warm_under_budget || !row.cold_under_budget);
      console.log(JSON.stringify({ pass: report.pass, percentiles_ms: report.percentiles_ms, slow }, null, 2));
      if (!report.pass) process.exitCode = 1;
    })
    .catch((error: unknown) => {
      console.error(error instanceof Error ? error.message : error);
      process.exitCode = 1;
    });
}
