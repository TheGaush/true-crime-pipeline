/**
 * Task 130. Chromium bounding-box audit for the CSS safe zone.
 *
 * SafeZoneLayout keeps type out of the YouTube exclusion bands:
 * top 108px (10% of 1080), bottom 194px (the 18% band), and the
 * bottom-right 22% by 14% box. A 12-word label that would wrap past
 * 885px stays inside that line because the label CSS clamps it.
 *
 * Motif modules are rendered as they exist on main. This file does not
 * modify their layout.
 */
// This package shell has no @types/node dependency. Node 22 provides these at runtime.
// @ts-expect-error node:child_process is provided by the runtime.
import { spawn } from "node:child_process";
// @ts-expect-error node:fs is provided by the runtime.
import { existsSync } from "node:fs";
// @ts-expect-error node:fs/promises is provided by the runtime.
import { mkdtemp, rm, writeFile } from "node:fs/promises";
// @ts-expect-error node:os is provided by the runtime.
import { tmpdir } from "node:os";
// @ts-expect-error node:path is provided by the runtime.
import { join } from "node:path";
// @ts-expect-error node:url is provided by the runtime.
import { pathToFileURL } from "node:url";

// Motif modules are .tsx. This package tsconfig has no jsx flag (Task 001).
// @ts-expect-error TS6142 — AlibiSplitScreen.tsx is imported without a jsx option.
import { AlibiSplitScreen } from "../motifs/AlibiSplitScreen.js";
// @ts-expect-error TS6142 — AudioEvidenceCard.tsx is imported without a jsx option.
import { AudioEvidenceCard } from "../motifs/AudioEvidenceCard.js";
// @ts-expect-error TS6142 — CaseBoardSpine.tsx is imported without a jsx option.
import { CaseBoardSpine } from "../motifs/CaseBoardSpine.js";
// @ts-expect-error TS6142 — EvidenceMatchCard.tsx is imported without a jsx option.
import { EvidenceMatchCard } from "../motifs/EvidenceMatchCard.js";
// @ts-expect-error TS6142 — FoiaFootageFrame.tsx is imported without a jsx option.
import { FoiaFootageFrame } from "../motifs/FoiaFootageFrame.js";
// @ts-expect-error TS6142 — HeroVideoBridge.tsx is imported without a jsx option.
import { HeroVideoBridge } from "../motifs/HeroVideoBridge.js";
// @ts-expect-error TS6142 — MapRouteTrace.tsx is imported without a jsx option.
import { MapRouteTrace } from "../motifs/MapRouteTrace.js";
// @ts-expect-error TS6142 — RedactedDocReveal.tsx is imported without a jsx option.
import { RedactedDocReveal } from "../motifs/RedactedDocReveal.js";
// @ts-expect-error TS6142 — SmsPhoneThread.tsx is imported without a jsx option.
import { SmsPhoneThread } from "../motifs/SmsPhoneThread.js";
// @ts-expect-error TS6142 — StickmanStage.tsx is imported without a jsx option.
import { StickmanStage } from "../motifs/StickmanStage.js";
// @ts-expect-error TS6142 — TimelineDateScrubber.tsx is imported without a jsx option.
import { TimelineDateScrubber } from "../motifs/TimelineDateScrubber.js";
// @ts-expect-error TS6142 — TimelineScrubber.tsx is imported without a jsx option.
import { TimelineScrubber } from "../motifs/TimelineScrubber.js";
import { REMOTION_ROOT } from "../parser.js";
// @ts-expect-error TS6142 — safe_zone.tsx is imported without a jsx option.
import { SAFE_ZONE_EXCLUSION_HEIGHT, SAFE_ZONE_EXCLUSION_WIDTH, SAFE_ZONE_LABEL_FONT_SIZE, SAFE_ZONE_LABEL_LINE_HEIGHT, SAFE_ZONE_LABEL_MAX_HEIGHT, SAFE_ZONE_LABEL_MAX_LINES, SAFE_ZONE_PADDING_BOTTOM_PX, SAFE_ZONE_PADDING_TOP_PX, SafeZoneLayout, resolveCssLength } from "../safe_zone.js";

export const FRAME_WIDTH = REMOTION_ROOT.width;
export const FRAME_HEIGHT = REMOTION_ROOT.height;
export const TOP_BAND_PX = SAFE_ZONE_PADDING_TOP_PX;
export const BOTTOM_BAND_PX = SAFE_ZONE_PADDING_BOTTOM_PX;
export const TOP_BAND_RATIO = 0.1;
export const BOTTOM_BAND_RATIO = 0.18;
export const EXCLUSION_WIDTH_RATIO = 0.22;
export const EXCLUSION_HEIGHT_RATIO = 0.14;
/** Wrap that would paint past this y must be clamped by the label CSS. */
export const WRAP_CLAMP_Y = 885;
export const BOUNDARY_EPSILON_PX = 1;

export const ADVERSARIAL_LABEL_WORDS = [
  "Unbroken",
  "warehouse",
  "ledger",
  "showing",
  "twelve",
  "maximal",
  "caption",
  "tokens",
  "before",
  "the",
  "safe",
  "clamp",
] as const;

export const ADVERSARIAL_LABEL = ADVERSARIAL_LABEL_WORDS.join(" ");

/** Twelve motif modules on main. CustomDiagramScene is the sandbox, not one of these. */
export const AUDITED_MOTIFS = [
  "StickmanStage",
  "AudioEvidenceCard",
  "RedactedDocReveal",
  "FoiaFootageFrame",
  "TimelineScrubber",
  "SmsPhoneThread",
  "MapRouteTrace",
  "TimelineDateScrubber",
  "CaseBoardSpine",
  "AlibiSplitScreen",
  "EvidenceMatchCard",
  "HeroVideoBridge",
] as const;

export type AuditedMotif = (typeof AUDITED_MOTIFS)[number];

export type Box = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type SafeZoneBands = {
  readonly top: Box;
  readonly bottom: Box;
  readonly exclusion: Box;
  readonly contentBottom: number;
};

export type StageKind = "motif" | "contract" | "probe";

export type MeasuredNode = {
  readonly tag: string;
  readonly text: string;
  readonly data: Readonly<Record<string, string>>;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type MeasuredStage = {
  readonly id: string;
  readonly kind: StageKind;
  readonly labelWords: number;
  readonly width: number;
  readonly height: number;
  readonly nodes: readonly MeasuredNode[];
};

export type ProbeMeasurement = {
  readonly unclamped: Box;
  readonly clamped: Box;
};

export type ChromiumPayload = {
  readonly stages: readonly MeasuredStage[];
  readonly probe: ProbeMeasurement;
};

export type ZoneLeak = {
  readonly stage: string;
  readonly tag: string;
  readonly text: string;
  readonly zone: "top" | "bottom" | "bottom-right";
  readonly box: Box;
};

export type SafeZoneAudit = {
  readonly leaks: readonly ZoneLeak[];
  readonly motifs: readonly AuditedMotif[];
  readonly measuredText: number;
  readonly probe: {
    readonly unclampedBottom: number;
    readonly clampedBottom: number;
    readonly clampedHeight: number;
    readonly maxHeight: number;
  };
  readonly bands: SafeZoneBands;
};

const SVG_TAGS = new Set(["svg", "g", "path", "rect", "circle", "line", "polyline", "polygon", "text"]);
const PX_STYLE = new Set([
  "width",
  "height",
  "top",
  "left",
  "right",
  "bottom",
  "minWidth",
  "minHeight",
  "maxWidth",
  "maxHeight",
  "padding",
  "paddingTop",
  "paddingRight",
  "paddingBottom",
  "paddingLeft",
  "margin",
  "marginTop",
  "marginRight",
  "marginBottom",
  "marginLeft",
  "fontSize",
  "borderWidth",
  "borderRadius",
  "outlineOffset",
  "flexBasis",
  "gap",
  "rowGap",
  "columnGap",
  "letterSpacing",
  "strokeWidth",
]);

export function assertSafeZoneContract(): void {
  if (FRAME_WIDTH !== 1920 || FRAME_HEIGHT !== 1080) {
    throw new Error(`safe-zone frame drifted from 1920x1080 (${FRAME_WIDTH}x${FRAME_HEIGHT})`);
  }
  if (TOP_BAND_PX !== 108 || TOP_BAND_PX !== FRAME_HEIGHT * TOP_BAND_RATIO) {
    throw new Error("SafeZoneLayout paddingTop drifted from 108px / 10%");
  }
  if (BOTTOM_BAND_PX !== 194) {
    throw new Error("SafeZoneLayout paddingBottom drifted from 194px");
  }
  if (Math.abs(BOTTOM_BAND_PX - FRAME_HEIGHT * BOTTOM_BAND_RATIO) >= 1) {
    throw new Error("SafeZoneLayout paddingBottom drifted from the 18% band");
  }
  if (SAFE_ZONE_EXCLUSION_WIDTH !== "22%" || SAFE_ZONE_EXCLUSION_HEIGHT !== "14%") {
    throw new Error("SafeZoneLayout exclusion drifted from 22% by 14%");
  }
}

export function safeZoneBands(): SafeZoneBands {
  assertSafeZoneContract();
  const exclusionWidth = FRAME_WIDTH * EXCLUSION_WIDTH_RATIO;
  const exclusionHeight = FRAME_HEIGHT * EXCLUSION_HEIGHT_RATIO;
  return {
    top: { x: 0, y: 0, width: FRAME_WIDTH, height: TOP_BAND_PX },
    bottom: { x: 0, y: FRAME_HEIGHT - BOTTOM_BAND_PX, width: FRAME_WIDTH, height: BOTTOM_BAND_PX },
    exclusion: {
      x: FRAME_WIDTH - exclusionWidth,
      y: FRAME_HEIGHT - exclusionHeight,
      width: exclusionWidth,
      height: exclusionHeight,
    },
    contentBottom: FRAME_HEIGHT - BOTTOM_BAND_PX,
  };
}

export function boxesOverlap(a: Box, b: Box, epsilon = BOUNDARY_EPSILON_PX): boolean {
  const left = Math.max(a.x, b.x);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const top = Math.max(a.y, b.y);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  return right - left > epsilon && bottom - top > epsilon;
}

export function labelMaxHeightPx(): number {
  return resolveCssLength(SAFE_ZONE_LABEL_MAX_HEIGHT, FRAME_WIDTH);
}

export function labelFontPx(): number {
  return resolveCssLength(SAFE_ZONE_LABEL_FONT_SIZE, FRAME_WIDTH);
}

function wrapWords(): string {
  return Array.from({ length: ADVERSARIAL_LABEL_WORDS.length }, (_, index) => {
    return `Superlongtoken${String(index + 1).padStart(2, "0")}warehouse`;
  }).join(" ");
}

function boxOf(node: MeasuredNode): Box {
  return { x: node.x, y: node.y, width: node.width, height: node.height };
}

function hasArea(box: Box): boolean {
  return box.width > 0.5 && box.height > 0.5;
}

export function classifyMeasurements(payload: ChromiumPayload): SafeZoneAudit {
  const bands = safeZoneBands();
  const leaks: ZoneLeak[] = [];
  let measuredText = 0;
  const seen = new Set<string>();
  for (const stage of payload.stages) {
    if (stage.kind === "probe") continue;
    seen.add(stage.id);
    for (const node of stage.nodes) {
      if (node.data.exclusion) continue;
      if (node.data["safe-zone-exempt"] === "background") continue;
      if (node.data["audit-svg-frame"] === "true") continue;
      const text = node.text.trim();
      const content = node.data.slot === "content";
      if (!text && !content) continue;
      const box = boxOf(node);
      if (!hasArea(box)) continue;
      if (text) measuredText += 1;
      const zones = [
        ["top", bands.top],
        ["bottom", bands.bottom],
        ["bottom-right", bands.exclusion],
      ] as const;
      for (const [zone, band] of zones) {
        if (!boxesOverlap(box, band)) continue;
        leaks.push({ stage: stage.id, tag: node.tag, text: text.slice(0, 80), zone, box });
      }
    }
  }
  const motifs = AUDITED_MOTIFS.filter((id) => seen.has(id));
  if (motifs.length !== AUDITED_MOTIFS.length) {
    const missing = AUDITED_MOTIFS.filter((id) => !seen.has(id));
    throw new Error(`safe-zone audit missed motifs: ${missing.join(", ")}`);
  }
  const maxHeight = labelMaxHeightPx();
  const clampedBottom = payload.probe.clamped.y + payload.probe.clamped.height;
  const unclampedBottom = payload.probe.unclamped.y + payload.probe.unclamped.height;
  if (!(unclampedBottom > WRAP_CLAMP_Y)) {
    throw new Error(`unclamped 12-word wrap bottom ${unclampedBottom} did not pass ${WRAP_CLAMP_Y}px`);
  }
  if (clampedBottom > WRAP_CLAMP_Y + 0.5) {
    throw new Error(`clamped 12-word wrap bottom ${clampedBottom} passed ${WRAP_CLAMP_Y}px`);
  }
  if (!(payload.probe.clamped.height <= maxHeight + 0.75)) {
    throw new Error(`clamped height ${payload.probe.clamped.height} exceeded max-height ${maxHeight}`);
  }
  if (!(clampedBottom < unclampedBottom)) {
    throw new Error("CSS containment did not shorten the wrapping label");
  }
  return {
    leaks,
    motifs,
    measuredText,
    probe: {
      unclampedBottom,
      clampedBottom,
      clampedHeight: payload.probe.clamped.height,
      maxHeight,
    },
    bands,
  };
}

type VirtualNode = {
  readonly type?: unknown;
  readonly dataset?: unknown;
  readonly props?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isVirtual(value: unknown): value is VirtualNode {
  return isRecord(value) && typeof value.type === "string";
}

function kebab(key: string): string {
  return key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`).replace(/^-/, "");
}

function cssName(key: string): string {
  if (key.startsWith("Webkit")) return `-webkit-${kebab(key.slice(6))}`;
  return kebab(key);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function styleText(style: unknown): string {
  if (!isRecord(style)) return "";
  const parts: string[] = [];
  for (const [key, value] of Object.entries(style)) {
    if (typeof value !== "string" && typeof value !== "number") continue;
    const rendered = typeof value === "number" && PX_STYLE.has(key) ? `${value}px` : String(value);
    parts.push(`${cssName(key)}:${rendered}`);
  }
  return parts.join(";");
}

function datasetOf(node: VirtualNode): Record<string, string> {
  const data: Record<string, string> = {};
  if (isRecord(node.dataset)) {
    for (const [key, value] of Object.entries(node.dataset)) {
      if (typeof value === "string" || typeof value === "number") data[key] = String(value);
    }
  }
  if (!isRecord(node.props)) return data;
  for (const [key, value] of Object.entries(node.props)) {
    if (!key.startsWith("data-")) continue;
    if (typeof value !== "string" && typeof value !== "number") continue;
    data[key.slice(5)] = String(value);
  }
  return data;
}

function childrenOf(node: VirtualNode): readonly unknown[] {
  if (!isRecord(node.props)) return [];
  const children = node.props.children;
  if (children === undefined || children === null) return [];
  return Array.isArray(children) ? children : [children];
}

const GEOMETRY_KEYS = [
  "d",
  "fill",
  "stroke",
  "strokeWidth",
  "strokeDasharray",
  "strokeDashoffset",
  "transform",
  "cx",
  "cy",
  "r",
  "x",
  "y",
  "x1",
  "y1",
  "x2",
  "y2",
  "width",
  "height",
  "points",
  "viewBox",
  "preserveAspectRatio",
  "opacity",
] as const;

function geometryAttrs(node: VirtualNode): Record<string, string> {
  const attrs: Record<string, string> = {};
  if (!isRecord(node.props)) return attrs;
  const nested = node.props.attrs;
  if (isRecord(nested)) {
    for (const [key, value] of Object.entries(nested)) {
      if (typeof value === "string" || typeof value === "number") attrs[key] = String(value);
    }
  }
  for (const key of GEOMETRY_KEYS) {
    const value = node.props[key];
    if (typeof value === "string" || typeof value === "number") attrs[key] = String(value);
  }
  return attrs;
}

function attrList(attrs: Record<string, string>): string {
  return Object.entries(attrs)
    .map(([key, value]) => {
      const name = key === "viewBox" ? "viewBox" : kebab(key);
      return ` ${name}="${escapeHtml(value)}"`;
    })
    .join("");
}

function dataAttrs(data: Record<string, string>): string {
  return Object.entries(data)
    .map(([key, value]) => ` data-${escapeHtml(key)}="${escapeHtml(value)}"`)
    .join("");
}

function renderNode(node: VirtualNode): string {
  const type = typeof node.type === "string" ? node.type : "div";
  const data = datasetOf(node);
  const style = isRecord(node.props) ? styleText(node.props.style) : "";
  const styleAttr = style ? ` style="${escapeHtml(style)}"` : "";
  const kids = childrenOf(node);
  if (SVG_TAGS.has(type)) {
    const inner = kids.map((child) => renderChild(child)).join("");
    return `<${type}${dataAttrs(data)}${attrList(geometryAttrs(node))}${styleAttr}>${inner}</${type}>`;
  }
  const tag = type === "mark" || type === "span" || type === "video" ? type : "div";
  return `<${tag}${dataAttrs(data)}${styleAttr}>${renderChildren(kids)}</${tag}>`;
}

function renderChild(child: unknown): string {
  if (typeof child === "string" || typeof child === "number") return escapeHtml(String(child));
  if (!isVirtual(child)) return "";
  return renderNode(child);
}

function isSvgFragment(child: unknown): child is VirtualNode {
  return isVirtual(child) && typeof child.type === "string" && child.type !== "svg" && SVG_TAGS.has(child.type);
}

function renderChildren(children: readonly unknown[]): string {
  let html = "";
  let svg: VirtualNode[] = [];
  const flush = (): void => {
    if (svg.length === 0) return;
    const inner = svg.map((node) => renderNode(node)).join("");
    html += `<svg data-audit-svg-frame="true" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${FRAME_WIDTH} ${FRAME_HEIGHT}" width="${FRAME_WIDTH}" height="${FRAME_HEIGHT}" style="position:absolute;left:0;top:0;width:${FRAME_WIDTH}px;height:${FRAME_HEIGHT}px;overflow:visible">${inner}</svg>`;
    svg = [];
  };
  for (const child of children) {
    if (isSvgFragment(child)) {
      svg.push(child);
      continue;
    }
    flush();
    html += renderChild(child);
  }
  flush();
  return html;
}

function stageHtml(id: string, kind: StageKind, labelWords: number, body: string): string {
  return `<section data-audit-stage="${id}" data-audit-kind="${kind}" data-audit-label-words="${labelWords}">${body}</section>`;
}

function renderTree(value: unknown): string {
  if (!isVirtual(value)) throw new Error("motif did not return an element tree");
  return renderNode(value);
}

function concatBytes(parts: readonly Uint8Array[]): Uint8Array {
  const size = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function asciiBytes(value: string): Uint8Array {
  const out = new Uint8Array(value.length);
  for (let index = 0; index < value.length; index += 1) out[index] = value.charCodeAt(index);
  return out;
}

function u32be(value: number): Uint8Array {
  const out = new Uint8Array(4);
  new DataView(out.buffer).setUint32(0, value >>> 0, false);
  return out;
}

function mp4Box(type: string, payload: Uint8Array): Uint8Array {
  return concatBytes([u32be(8 + payload.length), asciiBytes(type), payload]);
}

function zeroBytes(length: number): Uint8Array {
  return new Uint8Array(length);
}

function syntheticCfrMp4(): Uint8Array {
  const width = 1920;
  const height = 1080;
  const timescale = 30;
  const frames = 30;
  const matrix = new Uint8Array(36);
  new DataView(matrix.buffer).setUint32(0, 0x00010000, false);
  new DataView(matrix.buffer).setUint32(16, 0x00010000, false);
  new DataView(matrix.buffer).setUint32(32, 0x40000000, false);
  const ftyp = mp4Box("ftyp", concatBytes([asciiBytes("isom"), u32be(0), asciiBytes("isomiso2mp41")]));
  const mdat = mp4Box("mdat", zeroBytes(frames));
  const stbl = mp4Box(
    "stbl",
    concatBytes([
      mp4Box("stsd", concatBytes([u32be(0), u32be(1), mp4Box("mp4v", zeroBytes(8))])),
      mp4Box("stts", concatBytes([u32be(0), u32be(1), u32be(frames), u32be(1)])),
      mp4Box("stsc", concatBytes([u32be(0), u32be(1), u32be(1), u32be(frames), u32be(1)])),
      mp4Box("stsz", concatBytes([u32be(0), u32be(1), u32be(frames)])),
      mp4Box("stco", concatBytes([u32be(0), u32be(1), u32be(ftyp.length + 8)])),
    ]),
  );
  const minf = mp4Box(
    "minf",
    concatBytes([
      mp4Box("vmhd", concatBytes([u32be(1), zeroBytes(8)])),
      mp4Box("dinf", mp4Box("dref", concatBytes([u32be(0), u32be(1), mp4Box("url ", u32be(1))]))),
      stbl,
    ]),
  );
  const mdhd = mp4Box(
    "mdhd",
    concatBytes([u32be(0), u32be(0), u32be(0), u32be(timescale), u32be(frames), Uint8Array.from([0x55, 0xc4, 0x00, 0x00])]),
  );
  const hdlr = mp4Box(
    "hdlr",
    concatBytes([u32be(0), u32be(0), asciiBytes("vide"), zeroBytes(12), asciiBytes("VideoHandler\0")]),
  );
  const wide = new Uint8Array(4);
  const high = new Uint8Array(4);
  new DataView(wide.buffer).setUint32(0, (width * 65536) >>> 0, false);
  new DataView(high.buffer).setUint32(0, (height * 65536) >>> 0, false);
  const tkhd = mp4Box(
    "tkhd",
    concatBytes([
      u32be(0x7),
      u32be(0),
      u32be(0),
      u32be(1),
      u32be(0),
      u32be(frames),
      zeroBytes(8),
      zeroBytes(8),
      matrix,
      wide,
      high,
    ]),
  );
  const mvhd = mp4Box(
    "mvhd",
    concatBytes([
      u32be(0),
      u32be(0),
      u32be(0),
      u32be(timescale),
      u32be(frames),
      u32be(0x00010000),
      Uint8Array.from([0x01, 0x00, 0x00, 0x00]),
      zeroBytes(8),
      matrix,
      zeroBytes(24),
      u32be(2),
    ]),
  );
  const trak = mp4Box("trak", concatBytes([tkhd, mp4Box("mdia", concatBytes([mdhd, hdlr, minf]))]));
  return concatBytes([ftyp, mdat, mp4Box("moov", concatBytes([mvhd, trak]))]);
}

function quoteStamps(): { word: string; start_ms: number; end_ms: number }[] {
  return ADVERSARIAL_LABEL_WORDS.map((word, index) => ({
    word,
    start_ms: index * 200,
    end_ms: index * 200 + 160,
  }));
}

function motifBody(id: AuditedMotif): unknown {
  switch (id) {
    case "StickmanStage":
      return StickmanStage({
        preset: "evidence_desk",
        travelAxis: "STATIC",
        figures: [{ characterId: "detective" }],
        frame: 0,
        durationFrames: 30,
        label: ADVERSARIAL_LABEL,
      });
    case "AudioEvidenceCard":
      return AudioEvidenceCard({
        showDramatizationBadge: true,
        sceneStartMs: 0,
        lCutMs: 800,
        frame: 0,
        fftMagnitudes: [0.05, 0.2, 0.45, 1],
      });
    case "RedactedDocReveal":
      return RedactedDocReveal({
        citation: "State v. Hale affidavit page 12",
        quote: ADVERSARIAL_LABEL,
        wordTimestamps: quoteStamps(),
        sceneStartMs: 0,
        frame: 0,
        sceneId: "scene_redacted",
        affidavitBarCount: 0,
      });
    case "FoiaFootageFrame":
      return FoiaFootageFrame({
        sceneId: "scene_foia",
        episodeId: "ep_audit",
        bytes: syntheticCfrMp4(),
        frame: 0,
        provenance: {
          asset_id: "foia_bodycam",
          creator_entity: "County Sheriff",
          rights_holder: "County",
          license_basis: "STATE_PUBLIC_RECORD_PERMITTED",
          rights_review_status: "APPROVED",
          contains_third_party_attach: 0,
          media_kind: "bodycam_mp4",
          scrubbed_path: "fixtures/synthetic_media/bodycam_scrubbed_cfr30.mp4",
          normalized_cfr_30fps_48k: 1,
          visual_pii_blurred: 1,
          spoken_pii_bleeped: 1,
        },
        callout: {
          x: 480,
          y: 270,
          width: 280,
          height: 180,
          label: ADVERSARIAL_LABEL,
          fact_id: "fact_foia_callout",
        },
      }).element;
    case "TimelineScrubber":
      return TimelineScrubber({
        milestones: [
          {
            fact_id: "fact_alpha",
            datetime_iso: "2019-03-02T08:00:00Z",
            event_summary: ADVERSARIAL_LABEL,
          },
          {
            fact_id: "fact_omega",
            datetime_iso: "2021-11-04T15:30:00Z",
            event_summary: ADVERSARIAL_LABEL,
          },
        ],
      });
    case "SmsPhoneThread":
      return SmsPhoneThread({
        sceneId: "scene_sms",
        frame: 12,
        messages: [
          {
            message_id: "msg_inbound",
            fact_id: "fact_sms",
            party: "inbound",
            body: ADVERSARIAL_LABEL,
            appear_frame: 12,
            typing_frames: 0,
          },
        ],
      });
    case "MapRouteTrace":
      return MapRouteTrace({
        sceneId: "scene_map",
        frame: 30,
        waypoints: [
          {
            waypoint_id: "stop_a",
            fact_id: "fact_stop_a",
            label: ADVERSARIAL_LABEL,
            timestamp_label: "02:14",
            x: 0.22,
            y: 0.38,
            arrive_frame: 0,
            leg_drive_sec: 0,
          },
          {
            waypoint_id: "stop_b",
            fact_id: "fact_stop_b",
            label: ADVERSARIAL_LABEL,
            timestamp_label: "03:02",
            x: 0.7,
            y: 0.58,
            arrive_frame: 60,
            leg_drive_sec: 8,
          },
        ],
      });
    case "TimelineDateScrubber":
      return TimelineDateScrubber({
        sceneId: "scene_dates",
        frame: 0,
        durationFrames: 90,
        events: [
          {
            fact_id: "fact_date",
            datetime_iso: "2020-06-15T12:00:00Z",
            event_summary: ADVERSARIAL_LABEL,
          },
        ],
      });
    case "CaseBoardSpine":
      return CaseBoardSpine({
        sceneId: "scene_board",
        frame: 149,
        act: 3,
        label: ADVERSARIAL_LABEL,
        clues: [
          { clueId: "clue_01", factId: "fact_01", label: ADVERSARIAL_LABEL },
          { clueId: "clue_02", factId: "fact_02", label: ADVERSARIAL_LABEL },
        ],
      });
    case "AlibiSplitScreen":
      return AlibiSplitScreen({
        sceneId: "scene_alibi",
        frame: 0,
        stampAtMs: 0,
        claim: {
          fact_id: "fact_claim",
          source_type: "suspect_statement",
          text: ADVERSARIAL_LABEL,
          citation: "Interview transcript page 4",
        },
        evidence: {
          fact_id: "fact_evidence",
          source_type: "police_affidavit",
          text: ADVERSARIAL_LABEL,
          citation: "Affidavit exhibit B",
        },
      });
    case "EvidenceMatchCard":
      return EvidenceMatchCard({
        sceneId: "scene_match",
        frame: 4,
        left: {
          exhibit_id: "exhibit_wide",
          fact_id: "fact_wide",
          label: ADVERSARIAL_LABEL,
          intrinsic_width: 1920,
          intrinsic_height: 1080,
          src: "exhibit/porch-wide",
        },
        right: {
          exhibit_id: "exhibit_tall",
          fact_id: "fact_tall",
          label: ADVERSARIAL_LABEL,
          intrinsic_width: 1080,
          intrinsic_height: 1920,
          src: "exhibit/clock-tall",
        },
      });
    case "HeroVideoBridge":
      return HeroVideoBridge({
        scene_id: "scene_hero",
        episode_id: "ep_audit",
        start_ms: 0,
        end_ms: 7600,
        flow_state: "ACCEPTED",
        resolution: "720p",
        clip: {
          src: "workspace/flow_ingested/hero_trim.mp4",
          duration_ms: 8000,
          width: 1280,
          height: 720,
        },
        fallback_spec: {
          engine: "STILL_2K_PANZOOM",
          motif_component: "Illustrative2KPanZoom",
          still_2k_id: "still_00",
          anchor_id: "anchor_00",
          rule: "RULE_04",
        },
        prev_engine: "CODE_STICKMAN",
        next_engine: "CODE_STICKMAN",
      }).element;
    default: {
      const neverId: never = id;
      throw new Error(`unknown motif ${String(neverId)}`);
    }
  }
}

function labelWordsFor(id: AuditedMotif): number {
  if (id === "AudioEvidenceCard" || id === "HeroVideoBridge") return 0;
  return ADVERSARIAL_LABEL_WORDS.length;
}

function probeHtml(): string {
  const top = WRAP_CLAMP_Y - labelMaxHeightPx();
  const font = labelFontPx();
  const maxHeight = labelMaxHeightPx();
  const text = escapeHtml(wrapWords());
  const shared = `left:64px;width:180px;top:${top}px;font-size:${font}px;line-height:${SAFE_ZONE_LABEL_LINE_HEIGHT};font-family:Arial,sans-serif;overflow-wrap:anywhere;position:absolute`;
  const unclamped = `<div data-audit-probe="unclamped" style="${shared};overflow:visible">${text}</div>`;
  const clamped = `<div data-audit-probe="clamped" style="${shared};left:420px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:${SAFE_ZONE_LABEL_MAX_LINES};-webkit-box-orient:vertical;max-height:${maxHeight}px">${text}</div>`;
  return stageHtml("wrap-clamp", "probe", ADVERSARIAL_LABEL_WORDS.length, unclamped + clamped);
}

export function buildAuditHtml(): string {
  assertSafeZoneContract();
  if (ADVERSARIAL_LABEL_WORDS.length !== 12) {
    throw new Error("adversarial label must be 12 words");
  }
  const sections = AUDITED_MOTIFS.map((id) => {
    return stageHtml(id, "motif", labelWordsFor(id), renderTree(motifBody(id)));
  });
  sections.push(
    stageHtml(
      "SafeZoneLayout",
      "contract",
      12,
      renderTree(SafeZoneLayout({ isEndScreen: false, label: ADVERSARIAL_LABEL })),
    ),
  );
  sections.push(
    stageHtml(
      "SafeZoneLayoutEnd",
      "contract",
      12,
      renderTree(SafeZoneLayout({ isEndScreen: true, label: ADVERSARIAL_LABEL })),
    ),
  );
  sections.push(probeHtml());
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: #000; }
  [data-audit-stage] { position: relative; width: ${FRAME_WIDTH}px; height: ${FRAME_HEIGHT}px; overflow: hidden; }
</style>
</head>
<body>
${sections.join("\n")}
<pre id="audit"></pre>
<script>
${AUDIT_SCRIPT}
</script>
</body>
</html>`;
}

const AUDIT_SCRIPT = `
function paintedRect(el) {
  const raw = el.getBoundingClientRect();
  let left = raw.left;
  let top = raw.top;
  let right = raw.right;
  let bottom = raw.bottom;
  let node = el.parentElement;
  while (node) {
    const style = getComputedStyle(node);
    const clipX = style.overflowX === "hidden" || style.overflowX === "clip" || style.overflowX === "scroll" || style.overflowX === "auto";
    const clipY = style.overflowY === "hidden" || style.overflowY === "clip" || style.overflowY === "scroll" || style.overflowY === "auto";
    if (clipX || clipY) {
      const host = node.getBoundingClientRect();
      const borderLeft = clipX ? host.left + (parseFloat(style.borderLeftWidth) || 0) : -1e9;
      const borderRight = clipX ? host.right - (parseFloat(style.borderRightWidth) || 0) : 1e9;
      const borderTop = clipY ? host.top + (parseFloat(style.borderTopWidth) || 0) : -1e9;
      const borderBottom = clipY ? host.bottom - (parseFloat(style.borderBottomWidth) || 0) : 1e9;
      left = Math.max(left, borderLeft);
      right = Math.min(right, borderRight);
      top = Math.max(top, borderTop);
      bottom = Math.min(bottom, borderBottom);
    }
    node = node.parentElement;
  }
  return { left: left, top: top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}
const stages = [];
for (const stage of document.querySelectorAll("[data-audit-stage]")) {
  const origin = stage.getBoundingClientRect();
  const nodes = [];
  for (const el of stage.querySelectorAll("*")) {
    let text = "";
    for (const child of el.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) text += child.textContent || "";
    }
    text = text.replace(/\\s+/g, " ").trim();
    const data = {};
    for (const attr of el.attributes) {
      if (attr.name.startsWith("data-")) data[attr.name.slice(5)] = attr.value;
    }
    const rect = paintedRect(el);
    nodes.push({
      tag: el.tagName.toLowerCase(),
      text,
      data,
      x: rect.left - origin.left,
      y: rect.top - origin.top,
      width: rect.width,
      height: rect.height,
    });
  }
  stages.push({
    id: stage.getAttribute("data-audit-stage"),
    kind: stage.getAttribute("data-audit-kind"),
    labelWords: Number(stage.getAttribute("data-audit-label-words")),
    width: origin.width,
    height: origin.height,
    nodes,
  });
}
function probeBox(name) {
  const el = document.querySelector('[data-audit-probe="' + name + '"]');
  const stage = el.closest("[data-audit-stage]");
  const origin = stage.getBoundingClientRect();
  const rect = el.getBoundingClientRect();
  return {
    x: rect.left - origin.left,
    y: rect.top - origin.top,
    width: rect.width,
    height: rect.height,
  };
}
const payload = { stages, probe: { unclamped: probeBox("unclamped"), clamped: probeBox("clamped") } };
document.getElementById("audit").textContent = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
`;

declare const process: { env: { CHROME_PATH?: string } };

function chromeBinary(): string {
  const fromEnv = process.env.CHROME_PATH;
  if (fromEnv && existsSync(fromEnv)) return fromEnv;
  for (const candidate of ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/local/bin/google-chrome"]) {
    if (existsSync(candidate)) return candidate;
  }
  throw new Error("Chromium is not installed");
}

function dumpDom(file: string): Promise<string> {
  const url = pathToFileURL(file).href;
  return new Promise((resolve, reject) => {
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
    child.on("error", (error: unknown) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code: number | null) => {
      clearTimeout(timer);
      if (!out.includes('id="audit"') && !out.includes("id=audit")) {
        reject(new Error(`Chromium exit ${code ?? "null"}: ${err.slice(-1500)}`));
        return;
      }
      resolve(out);
    });
  });
}

function decodeBase64Ascii(value: string): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  const clean = value.replace(/\s+/g, "");
  const chars: string[] = [];
  for (let index = 0; index < clean.length; index += 4) {
    const a = alphabet.indexOf(clean[index] ?? "A");
    const b = alphabet.indexOf(clean[index + 1] ?? "A");
    const cChar = clean[index + 2] ?? "=";
    const dChar = clean[index + 3] ?? "=";
    const c = cChar === "=" ? -1 : alphabet.indexOf(cChar);
    const d = dChar === "=" ? -1 : alphabet.indexOf(dChar);
    chars.push(String.fromCharCode((a << 2) | (b >> 4)));
    if (c >= 0) chars.push(String.fromCharCode(((b & 15) << 4) | (c >> 2)));
    if (d >= 0 && c >= 0) chars.push(String.fromCharCode(((c & 3) << 6) | d));
  }
  return chars.join("");
}

export function decodeAuditDom(dom: string): ChromiumPayload {
  const match = dom.match(/<pre id="audit">([^<]*)<\/pre>/);
  if (!match?.[1]) throw new Error("Chromium did not write the safe-zone audit payload");
  const json = decodeBase64Ascii(match[1]);
  const parsed = JSON.parse(json) as ChromiumPayload;
  if (!Array.isArray(parsed.stages) || !parsed.probe?.clamped || !parsed.probe?.unclamped) {
    throw new Error("safe-zone audit payload is missing stages or the wrap probe");
  }
  return parsed;
}

export async function auditSafeZoneInChromium(): Promise<SafeZoneAudit> {
  const html = buildAuditHtml();
  const dir = await mkdtemp(join(tmpdir(), "tc-safezone-"));
  const file = join(dir, "audit.html");
  try {
    await writeFile(file, html, "utf8");
    const dom = await dumpDom(file);
    return classifyMeasurements(decodeAuditDom(dom));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
