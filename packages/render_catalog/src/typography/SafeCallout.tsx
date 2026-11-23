/**
 * Task 111. CSS-contained kinetic callouts and safe subtitles.
 *
 * Location, timestamp, and action callouts render inside Task 101
 * `<SafeZoneLayout>`, clamp to 12 words, and cite a fact_ledger id.
 * Overlapping Y slots move by 64px steps until they fit in the safe zone.
 * Word highlight follows global `WordTimestamp[]` on the 30 fps clock from
 * Task 108. `TWIST_PAD` and `FOIA_AUDIO_SLOT` do not highlight.
 * Ink, paper, slate, and evidence crimson come from Task 102 `useCaseBible()`.
 *
 * Those modules are imported. Their files are not copied onto this branch.
 */
// @ts-ignore Task 101 ships safe_zone.tsx on task/101-remotion-30fps-css-safezone.
import { measureSafeZone as loadMeasureSafeZone, SafeZoneLayout as loadSafeZoneLayout } from "../safe_zone.js";
// @ts-ignore Task 102 ships CaseBibleContext.tsx on task/102-case-bible-theme-provider.
import { useCaseBible as loadUseCaseBible } from "../theme/CaseBibleContext.js";
// @ts-ignore Task 108 ships useVoiceSyncMotion.ts on task/108-amplitude-nod-sync.
import { sampleVoiceSyncMotion as loadSampleVoiceSyncMotion } from "../rig/useVoiceSyncMotion.js";
import { createElement, isValidElement, type CSSProperties, type ReactElement, type ReactNode } from "react";

export const MAX_CALLOUT_WORDS = 12;
/** Greedy vertical pitch when two callout slots would overlap. */
export const Y_SLOT_STEP_PX = 64;
/** Matches the Task 101 label clamp ceiling at 1920px (`clamp(24px, 2.2vw, 42px)`). */
export const CALLOUT_FONT_PX = 42;
export const CALLOUT_CHAR_PX = 21;
export const CALLOUT_LINE_HEIGHT = 1.15;
export const CALLOUT_MAX_LINES = 3;

const CALLOUT_KINDS = ["location", "timestamp", "action", "subtitle"] as const;
const FACT_KINDS = ["location", "timestamp", "action"] as const;
const ID_PATTERN = /^[A-Za-z0-9_-]+$/;

export type CalloutKind = (typeof CALLOUT_KINDS)[number];

export interface WordStamp {
  segment_id: string;
  word: string;
  start_ms: number;
  end_ms: number;
}

export interface VoiceSegmentRef {
  segment_id?: string;
  segment_kind: string;
  start_ms: number;
  end_ms: number;
}

/** Structural subset of `VoiceTrackManifest` that Task 108 samples. */
export interface KineticManifest {
  segments: readonly VoiceSegmentRef[];
  amplitude_envelope?: readonly number[] | null;
  total_master_ms?: number;
  word_timestamps?: readonly WordStamp[];
}

export interface CalloutRequest {
  id: string;
  kind: CalloutKind;
  text: string;
  factId?: string;
  preferredY?: number;
}

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PlacedCallout {
  id: string;
  kind: CalloutKind;
  text: string;
  words: readonly string[];
  stamps: readonly WordStamp[];
  factId: string | null;
  clamped: boolean;
  startMs: number;
  endMs: number;
  activeIndex: number;
  box: Rect;
}

export interface CalloutLayout {
  kinetic: boolean;
  timeMs: number | null;
  segmentKind: string;
  bounds: Rect;
  placed: readonly PlacedCallout[];
}

export interface SafeCalloutProps {
  callouts?: readonly CalloutRequest[];
  wordTimestamps?: readonly WordStamp[];
  manifest: KineticManifest;
  frame: number;
  isEndScreen?: boolean;
}

export class SafeCalloutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SafeCalloutError";
  }
}

interface ThemeInk {
  paperBgHex: string;
  inkHex: string;
  slateHex: string;
  evidenceCrimsonHex: string;
}

interface ZoneMeasurement {
  content: Rect;
  exclusion: Rect;
  captionBar: Rect;
  endScreenCard: Rect | null;
}

/** `1.0 + 0.3 * word_count` seconds, in milliseconds. Fact callouts hold at least this long. */
export function minCalloutHoldMs(wordCount: number): number {
  if (!Number.isInteger(wordCount) || wordCount < 1) {
    throw new SafeCalloutError("word count must be a positive integer");
  }
  return snap((1 + 0.3 * wordCount) * 1000);
}

export function clampCalloutWords(text: string): { text: string; words: string[]; clamped: boolean } {
  if (typeof text !== "string") throw new SafeCalloutError("callout text must be a string");
  const words = text.trim().split(/\s+/).filter((word) => word.length > 0);
  if (words.length < 1) throw new SafeCalloutError("callout text must contain a word");
  for (const word of words) {
    if (word.length > 80) throw new SafeCalloutError("callout word exceeds 80 characters");
  }
  const clamped = words.length > MAX_CALLOUT_WORDS;
  const kept = clamped ? words.slice(0, MAX_CALLOUT_WORDS) : words;
  return { text: kept.join(" "), words: kept, clamped };
}

export function measureCalloutText(text: string, maxWidth: number): { width: number; height: number; lineCount: number } {
  if (!Number.isFinite(maxWidth) || maxWidth <= 0) {
    throw new SafeCalloutError("callout max width must be positive");
  }
  const words = text.trim().split(/\s+/).filter((word) => word.length > 0);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (current && next.length * CALLOUT_CHAR_PX > maxWidth) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  const visible = lines.slice(0, CALLOUT_MAX_LINES);
  const longest = visible.reduce((max, line) => Math.max(max, line.length * CALLOUT_CHAR_PX), 0);
  const width = snap(Math.min(maxWidth, Math.max(longest, 1)));
  const height = snap(Math.max(visible.length, 1) * CALLOUT_FONT_PX * CALLOUT_LINE_HEIGHT);
  return { width, height, lineCount: Math.max(visible.length, 1) };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

export function rectInside(inner: Rect, outer: Rect): boolean {
  const epsilon = 0.001;
  return (
    inner.x >= outer.x - epsilon &&
    inner.y >= outer.y - epsilon &&
    inner.x + inner.width <= outer.x + outer.width + epsilon &&
    inner.y + inner.height <= outer.y + outer.height + epsilon
  );
}

export function usableCalloutBounds(content: Rect, endScreenCard: Rect | null): Rect {
  if (!endScreenCard) return content;
  if (endScreenCard.y <= content.y) {
    throw new SafeCalloutError("end-screen card covers the safe zone");
  }
  if (endScreenCard.y >= content.y + content.height) return content;
  return { x: content.x, y: content.y, width: content.width, height: snap(endScreenCard.y - content.y) };
}

export interface SlotRequest {
  id: string;
  preferredY: number;
  width: number;
  height: number;
}

/** Separate overlapping bands by `Y_SLOT_STEP_PX`, staying inside `bounds`. */
export function deconflictYSlots(slots: readonly SlotRequest[], bounds: Rect): Array<SlotRequest & Rect> {
  assertRect(bounds, "safe-zone bounds");
  const ordered = [...slots].sort((left, right) => left.preferredY - right.preferredY || left.id.localeCompare(right.id));
  const placed: Array<SlotRequest & Rect> = [];
  for (const slot of ordered) {
    if (!Number.isFinite(slot.preferredY)) throw new SafeCalloutError(`callout ${slot.id} preferredY must be finite`);
    if (!Number.isFinite(slot.height) || slot.height <= 0) {
      throw new SafeCalloutError(`callout ${slot.id} height must be positive`);
    }
    if (!Number.isFinite(slot.width) || slot.width <= 0) {
      throw new SafeCalloutError(`callout ${slot.id} width must be positive`);
    }
    const height = snap(slot.height);
    const width = snap(Math.min(slot.width, bounds.width));
    const maxY = snap(bounds.y + bounds.height - height);
    if (width <= 0 || maxY < bounds.y) {
      throw new SafeCalloutError(`callout ${slot.id} is taller than the safe zone`);
    }
    const y = resolveSlotY(slot.id, snap(slot.preferredY), height, width, bounds, maxY, placed);
    const box = { ...slot, x: bounds.x, y, width, height };
    if (!rectInside(box, bounds) || placed.some((prev) => rectsOverlap(prev, box))) {
      throw new SafeCalloutError(`callout ${slot.id} overlaps another label inside the safe zone`);
    }
    placed.push(box);
  }
  return placed;
}

export function layoutKineticCallouts(input: {
  callouts: readonly CalloutRequest[];
  wordTimestamps: readonly WordStamp[];
  segments: readonly VoiceSegmentRef[];
  timeMs: number | null;
  segmentKind: string;
  bounds: Rect;
  obstacles: readonly Rect[];
}): CalloutLayout {
  const stamps = input.wordTimestamps.map((stamp, index) => assertStamp(stamp, index));
  const requests = input.callouts.map((callout, index) => assertRequest(callout, index));
  const seen = new Set<string>();
  for (const request of requests) {
    if (seen.has(request.id)) throw new SafeCalloutError(`duplicate callout id ${request.id}`);
    seen.add(request.id);
  }
  const narration = narrationStamps(stamps, input.segments);
  const kinetic = input.segmentKind === "NARRATION" && input.timeMs !== null;
  const timeMs = input.timeMs;
  const pending: Array<Omit<PlacedCallout, "box"> & { preferredY: number | null }> = [];

  for (const request of requests) {
    if (request.kind === "subtitle") continue;
    const clamped = clampCalloutWords(request.text);
    const matched = matchWords(request.id, clamped.words, narration);
    const startMs = matched[0]?.start_ms ?? 0;
    const spokenEnd = matched[matched.length - 1]?.end_ms ?? startMs;
    const endMs = snap(Math.max(spokenEnd, startMs + minCalloutHoldMs(clamped.words.length)));
    const visible = timeMs !== null && startMs <= timeMs && timeMs < endMs;
    if (!visible) continue;
    pending.push({
      id: request.id,
      kind: request.kind,
      text: clamped.text,
      words: clamped.words,
      stamps: matched,
      factId: request.factId ?? null,
      clamped: clamped.clamped,
      startMs,
      endMs,
      activeIndex: kinetic ? activeIndex(matched, timeMs) : -1,
      preferredY: request.preferredY ?? null,
    });
  }

  if (kinetic && timeMs !== null) {
    const page = subtitlePageAt(narration, input.segments, timeMs);
    const anchor = requests.find((request) => request.kind === "subtitle");
    if (page) {
      const id = anchor?.id ?? page.id;
      if (requests.some((request) => request.kind !== "subtitle" && request.id === id) || pending.some((item) => item.id === id)) {
        throw new SafeCalloutError(`duplicate callout id ${id}`);
      }
      pending.push({
        id,
        kind: "subtitle",
        text: page.stamps.map((stamp) => stamp.word).join(" "),
        words: page.stamps.map((stamp) => stamp.word),
        stamps: page.stamps,
        factId: null,
        clamped: false,
        startMs: page.startMs,
        endMs: page.endMs,
        activeIndex: activeIndex(page.stamps, timeMs),
        preferredY: anchor?.preferredY ?? null,
      });
    }
  }

  const slots: SlotRequest[] = pending.map((item) => {
    const measured = measureCalloutText(item.factId ? `${item.text} ${item.factId}` : item.text, input.bounds.width);
    const preferredY =
      item.preferredY ??
      (item.kind === "subtitle"
        ? snap(input.bounds.y + input.bounds.height - measured.height)
        : snap(input.bounds.y + kindRow(item.kind) * Y_SLOT_STEP_PX));
    return { id: item.id, preferredY, width: measured.width, height: measured.height };
  });
  const resolved = deconflictYSlots(slots, input.bounds);
  const byId = new Map(resolved.map((slot) => [slot.id, slot]));
  const placed: PlacedCallout[] = pending.map((item) => {
    const slot = byId.get(item.id);
    if (!slot) throw new SafeCalloutError(`callout ${item.id} was not placed`);
    const box: Rect = { x: slot.x, y: slot.y, width: slot.width, height: slot.height };
    for (const obstacle of input.obstacles) {
      if (rectsOverlap(box, obstacle)) {
        throw new SafeCalloutError(`callout ${item.id} intersects a safe-zone exclusion`);
      }
    }
    return {
      id: item.id,
      kind: item.kind,
      text: item.text,
      words: item.words,
      stamps: item.stamps,
      factId: item.factId,
      clamped: item.clamped,
      startMs: item.startMs,
      endMs: item.endMs,
      activeIndex: item.activeIndex,
      box,
    };
  });

  return {
    kinetic,
    timeMs,
    segmentKind: input.segmentKind,
    bounds: input.bounds,
    placed,
  };
}

export function SafeCallout(props: SafeCalloutProps): ReactElement {
  const theme = readTheme(loadUseCaseBible());
  const motion = readMotion(loadSampleVoiceSyncMotion(props.manifest, props.frame));
  const isEndScreen = props.isEndScreen === true;
  const measured = readMeasurement(loadMeasureSafeZone({ isEndScreen }));
  const bounds = usableCalloutBounds(measured.content, measured.endScreenCard);
  const obstacles = [measured.exclusion, measured.captionBar];
  if (measured.endScreenCard) obstacles.push(measured.endScreenCard);
  const wordTimestamps = props.wordTimestamps ?? props.manifest.word_timestamps ?? [];
  const layout = layoutKineticCallouts({
    callouts: props.callouts ?? [],
    wordTimestamps,
    segments: props.manifest.segments,
    timeMs: motion.timeMs,
    segmentKind: motion.segmentKind,
    bounds,
    obstacles,
  });
  const callouts = layout.placed.map((item) => renderCallout(item, theme));
  const layer = createElement(
    "div",
    {
      "data-component": "SafeCallout",
      "data-slot": "callouts",
      "data-kinetic": layout.kinetic ? "on" : "off",
      "data-content-x": String(bounds.x),
      "data-content-y": String(bounds.y),
      "data-content-width": String(bounds.width),
      "data-content-height": String(bounds.height),
      style: { width: "100%", height: "100%" },
    },
    callouts,
  );
  return mountInSafeZone(isEndScreen, layer);
}

function renderCallout(item: PlacedCallout, theme: ThemeInk): ReactElement {
  const words = item.words.map((word, index) =>
    createElement(
      "span",
      {
        key: `${item.id}:${index}`,
        "data-word": word,
        "data-active": index === item.activeIndex ? "true" : "false",
        "data-start-ms": String(item.stamps[index]?.start_ms ?? ""),
        "data-end-ms": String(item.stamps[index]?.end_ms ?? ""),
        style: { color: index === item.activeIndex ? theme.evidenceCrimsonHex : theme.inkHex },
      },
      index === 0 ? word : ` ${word}`,
    ),
  );
  const citation = item.factId
    ? createElement(
        "span",
        { "data-citation": item.factId, style: { color: theme.slateHex } },
        ` ${item.factId}`,
      )
    : null;
  const attrs: Record<string, string> = {
    "data-callout-id": item.id,
    "data-callout-kind": item.kind,
    "data-word-count": String(item.words.length),
    "data-clamped": item.clamped ? "true" : "false",
    "data-x": String(item.box.x),
    "data-y": String(item.box.y),
    "data-width": String(item.box.width),
    "data-height": String(item.box.height),
    "data-hold-start-ms": String(item.startMs),
    "data-hold-end-ms": String(item.endMs),
  };
  if (item.factId) attrs["data-fact-id"] = item.factId;
  const style: CSSProperties = {
    position: "absolute",
    left: item.box.x,
    top: item.box.y,
    width: item.box.width,
    height: item.box.height,
    maxHeight: item.box.height,
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: CALLOUT_MAX_LINES,
    WebkitBoxOrient: "vertical",
    boxSizing: "border-box",
    backgroundColor: theme.paperBgHex,
    color: theme.inkHex,
    fontSize: CALLOUT_FONT_PX,
    lineHeight: CALLOUT_LINE_HEIGHT,
    margin: 0,
  };
  return createElement("div", { key: item.id, ...attrs, style }, ...words, citation);
}

/**
 * `top`/`left` are frame pixels. The safe-zone root is the positioned ancestor
 * (`position: relative`); the content slot stays static so padding is not added twice.
 */
function mountInSafeZone(isEndScreen: boolean, child: ReactElement): ReactElement {
  const tree = (loadSafeZoneLayout as (props: { isEndScreen: boolean; children?: unknown }) => unknown)({
    isEndScreen,
    children: child,
  });
  const react = toReact(tree);
  if (!isValidElement(react)) throw new SafeCalloutError("SafeZoneLayout did not return a frame");
  return react;
}

function toReact(node: unknown, key?: string): ReactNode {
  if (node == null || typeof node === "boolean") return null;
  if (typeof node === "string" || typeof node === "number") return node;
  if (isValidElement(node)) return node;
  if (!node || typeof node !== "object") return null;
  const record = node as {
    type?: unknown;
    dataset?: Record<string, string>;
    props?: { style?: CSSProperties; children?: unknown };
  };
  if (record.type !== "div" || !record.props) return null;
  const data: Record<string, string> = {};
  for (const [name, value] of Object.entries(record.dataset ?? {})) data[`data-${name}`] = value;
  const children = record.props.children;
  const list = children === undefined ? [] : Array.isArray(children) ? children : [children];
  return createElement(
    "div",
    {
      ...data,
      style: record.props.style ?? {},
      ...(key !== undefined ? { key } : {}),
    },
    ...list.map((entry, index) => toReact(entry, `zone-${index}`)),
  );
}

function resolveSlotY(
  id: string,
  preferredY: number,
  height: number,
  width: number,
  bounds: Rect,
  maxY: number,
  placed: readonly Rect[],
): number {
  let y = snap(Math.min(Math.max(preferredY, bounds.y), maxY));
  const seen = new Set<string>();
  for (let guard = 0; guard < 64; guard += 1) {
    if (!hits(bounds.x, y, width, height, placed)) return y;
    if (seen.has(String(y))) break;
    seen.add(String(y));
    const down = snap(y + Y_SLOT_STEP_PX);
    if (down <= maxY + 0.001) {
      y = down;
      continue;
    }
    const up = snap(y - Y_SLOT_STEP_PX);
    if (up >= bounds.y - 0.001) {
      y = up;
      continue;
    }
    break;
  }
  for (let cursor = bounds.y; cursor <= maxY + 0.001; cursor = snap(cursor + Y_SLOT_STEP_PX)) {
    if (!hits(bounds.x, cursor, width, height, placed)) return snap(cursor);
  }
  if (!hits(bounds.x, maxY, width, height, placed)) return maxY;
  throw new SafeCalloutError(`callout ${id} overlaps another label inside the safe zone`);
}

function hits(x: number, y: number, width: number, height: number, placed: readonly Rect[]): boolean {
  const box = { x, y, width, height };
  return placed.some((prev) => rectsOverlap(prev, box));
}

function kindRow(kind: CalloutKind): number {
  if (kind === "timestamp") return 1;
  if (kind === "action") return 2;
  return 0;
}

function activeIndex(stamps: readonly WordStamp[], timeMs: number): number {
  return stamps.findIndex((stamp) => stamp.start_ms <= timeMs && timeMs < stamp.end_ms);
}

function matchWords(id: string, words: readonly string[], stamps: readonly WordStamp[]): WordStamp[] {
  const matched: WordStamp[] = [];
  let cursor = 0;
  for (const word of words) {
    let found = -1;
    for (let index = cursor; index < stamps.length; index += 1) {
      if (stamps[index]?.word === word) {
        found = index;
        break;
      }
    }
    if (found < 0 || !stamps[found]) {
      throw new SafeCalloutError(`callout ${id} word "${word}" is not in WordTimestamp[]`);
    }
    matched.push(stamps[found]);
    cursor = found + 1;
  }
  return matched;
}

interface SubtitlePage {
  id: string;
  stamps: WordStamp[];
  startMs: number;
  endMs: number;
}

function subtitlePageAt(stamps: readonly WordStamp[], segments: readonly VoiceSegmentRef[], timeMs: number): SubtitlePage | null {
  const groups = new Map<string, WordStamp[]>();
  for (const stamp of stamps) {
    const segment = segmentFor(stamp, segments);
    const key = segment?.segment_id ?? `${segment?.start_ms ?? 0}:${segment?.end_ms ?? 0}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(stamp);
    else groups.set(key, [stamp]);
  }
  let pageNumber = 0;
  for (const [key, group] of groups) {
    for (let index = 0; index < group.length; index += MAX_CALLOUT_WORDS) {
      const slice = group.slice(index, index + MAX_CALLOUT_WORDS);
      const first = slice[0];
      const last = slice[slice.length - 1];
      if (!first || !last) continue;
      const page: SubtitlePage = {
        id: `subtitle:${key}:${pageNumber}`,
        stamps: slice,
        startMs: first.start_ms,
        endMs: last.end_ms,
      };
      pageNumber += 1;
      if (page.startMs <= timeMs && timeMs < page.endMs) return page;
    }
  }
  return null;
}

function narrationStamps(stamps: readonly WordStamp[], segments: readonly VoiceSegmentRef[]): WordStamp[] {
  return [...stamps]
    .filter((stamp) => segmentFor(stamp, segments)?.segment_kind === "NARRATION")
    .sort((left, right) => left.start_ms - right.start_ms || left.end_ms - right.end_ms);
}

function segmentFor(stamp: WordStamp, segments: readonly VoiceSegmentRef[]): VoiceSegmentRef | null {
  if (stamp.segment_id) {
    const byId = segments.find((segment) => segment.segment_id === stamp.segment_id);
    if (byId) return byId;
  }
  return (
    segments.find((segment) => segment.start_ms <= stamp.start_ms && stamp.end_ms <= segment.end_ms) ?? null
  );
}

function assertRequest(callout: CalloutRequest, index: number): CalloutRequest {
  if (!callout || typeof callout !== "object") throw new SafeCalloutError(`callouts[${index}] must be an object`);
  if (typeof callout.id !== "string" || !ID_PATTERN.test(callout.id) || callout.id.length > 128) {
    throw new SafeCalloutError(`callouts[${index}].id must be a fact-safe id`);
  }
  if (!CALLOUT_KINDS.includes(callout.kind)) {
    throw new SafeCalloutError(`callouts[${index}].kind must be location, timestamp, action, or subtitle`);
  }
  if ((FACT_KINDS as readonly string[]).includes(callout.kind)) {
    if (typeof callout.factId !== "string" || !ID_PATTERN.test(callout.factId) || callout.factId.length > 128) {
      throw new SafeCalloutError(`callout ${callout.id} requires a fact_ledger id`);
    }
    if (typeof callout.text !== "string") throw new SafeCalloutError(`callout ${callout.id} text must be a string`);
  }
  if (callout.preferredY !== undefined && !Number.isFinite(callout.preferredY)) {
    throw new SafeCalloutError(`callout ${callout.id} preferredY must be finite`);
  }
  return callout;
}

function assertStamp(stamp: WordStamp, index: number): WordStamp {
  if (!stamp || typeof stamp !== "object") throw new SafeCalloutError(`wordTimestamps[${index}] must be an object`);
  if (typeof stamp.segment_id !== "string" || !ID_PATTERN.test(stamp.segment_id)) {
    throw new SafeCalloutError(`wordTimestamps[${index}].segment_id must cite a segment`);
  }
  if (typeof stamp.word !== "string" || stamp.word.length < 1 || stamp.word.length > 80) {
    throw new SafeCalloutError(`wordTimestamps[${index}].word must be 1-80 characters`);
  }
  if (!Number.isInteger(stamp.start_ms) || stamp.start_ms < 0) {
    throw new SafeCalloutError(`wordTimestamps[${index}].start_ms must be an integer >= 0`);
  }
  if (!Number.isInteger(stamp.end_ms) || stamp.end_ms <= stamp.start_ms) {
    throw new SafeCalloutError(`wordTimestamps[${index}].end_ms must be greater than start_ms`);
  }
  return stamp;
}

function readTheme(theme: unknown): ThemeInk {
  if (!theme || typeof theme !== "object") throw new SafeCalloutError("useCaseBible() returned no CaseBible theme");
  const record = theme as Record<string, unknown>;
  return {
    paperBgHex: requireHex(record.paperBgHex, "paperBgHex"),
    inkHex: requireHex(record.inkHex, "inkHex"),
    slateHex: requireHex(record.slateHex, "slateHex"),
    evidenceCrimsonHex: requireHex(record.evidenceCrimsonHex, "evidenceCrimsonHex"),
  };
}

function readMotion(sample: unknown): { timeMs: number | null; segmentKind: string } {
  if (!sample || typeof sample !== "object") return { timeMs: null, segmentKind: "NONE" };
  const record = sample as { timeMs?: unknown; segmentKind?: unknown };
  const timeMs = typeof record.timeMs === "number" && Number.isFinite(record.timeMs) ? record.timeMs : null;
  const segmentKind = typeof record.segmentKind === "string" ? record.segmentKind : "NONE";
  return { timeMs, segmentKind };
}

function readMeasurement(value: unknown): ZoneMeasurement {
  if (!value || typeof value !== "object") throw new SafeCalloutError("measureSafeZone returned no frame");
  const record = value as Record<string, unknown>;
  const endScreenCard = record.endScreenCard == null ? null : readRect(record.endScreenCard, "endScreenCard");
  return {
    content: readRect(record.content, "content"),
    exclusion: readRect(record.exclusion, "exclusion"),
    captionBar: readRect(record.captionBar, "captionBar"),
    endScreenCard,
  };
}

function readRect(value: unknown, label: string): Rect {
  if (!value || typeof value !== "object") throw new SafeCalloutError(`safe zone ${label} is missing`);
  const record = value as Record<string, unknown>;
  const rect = {
    x: requirePx(record.x, label),
    y: requirePx(record.y, label),
    width: requirePx(record.width, label),
    height: requirePx(record.height, label),
  };
  assertRect(rect, label);
  return rect;
}

function assertRect(rect: Rect, label: string): void {
  if (rect.width <= 0 || rect.height <= 0) throw new SafeCalloutError(`${label} must have a positive area`);
}

function requirePx(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new SafeCalloutError(`safe zone ${label} must be a finite px number`);
  }
  return snap(value);
}

function requireHex(value: unknown, label: string): string {
  if (typeof value !== "string" || !/^#[0-9A-Fa-f]{6}$/.test(value)) {
    throw new SafeCalloutError(`CaseBible ${label} must be a #RRGGBB color`);
  }
  return value;
}

function snap(value: number): number {
  return Math.round(value * 1000) / 1000;
}
