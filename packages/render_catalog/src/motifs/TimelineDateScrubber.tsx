/**
 * Motif #9 — TimelineDateScrubber.
 *
 * Non-linear forensic date ruler: tight clusters keep a minimum notch pitch,
 * and any jump longer than four minutes is a fixed `// TIME GAP` divider
 * instead of a proportional stretch. The focal event opens a zoom card.
 * Each notch the playhead crosses emits one `tick_sfx` cue.
 *
 * Task 123 names this Motif #9. The frozen SQL motif_registry and
 * CATALOG_MOTIFS still list the corkboard in that catalog slot. This file
 * does not amend those contracts, and it does not import Task 110 or Task 114.
 * Cue rows use the same 48 kHz clock, 60 ms cooldown, 30 ms tick, and
 * -14 dBTP nominal as that dispatcher so a later merge can pass `tickSfxTriggers`
 * through without copying it.
 *
 * `<SafeZoneLayout>` is a function, not JSX. The package tsconfig has no jsx
 * flag (Task 001), and Task 101's safe_zone.tsx is not on this branch.
 * Illustrative2KPanZoom stays in packages/crime_scene_2k.
 */

export const TIMELINE_DATE_SCRUBBER_ID = "TimelineDateScrubber" as const;
export const TIMELINE_DATE_SCRUBBER_OWNER = "render_catalog" as const;
export const MOTIF_NUMBER = 9 as const;
export const TIME_GAP_LABEL = "// TIME GAP" as const;
export const TICK_SFX = "tick_sfx" as const;

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FPS = 30;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const EXCLUSION_WIDTH = "22%";
export const EXCLUSION_HEIGHT = "14%";
export const RULE_07_MAX_WORDS = 12;
export const LABEL_CHAR_PX = 14;
export const LABEL_MIN_WIDTH = 36;
export const LABEL_HEIGHT = 32;
export const LABEL_GAP = 12;

/** Gaps at or under four minutes stay a cluster. Longer jumps are not to scale. */
export const CLUSTER_MAX_MS = 4 * 60 * 1000;

export const MIX_SAMPLE_RATE_HZ = 48_000;
export const COOLDOWN_MS = 60;
export const TICK_DURATION_MS = 30;
export const TICK_PEAK_DBTP = -14;
export const GAIN_UNIT_SCALE = 1_000_000_000;
export const TRUE_PEAK_CEILING_DBTP = -1;

export const FOCAL_ZOOM_MAX = 1.5;
export const FOCAL_ZOOM_SIGMA_FRAMES = 10;
export const FOCAL_CARD_W = 460;
export const FOCAL_CARD_H = 150;
export const DEFAULT_DURATION_FRAMES = 240;
export const MAX_DURATION_FRAMES = 216_000;

const CONTENT_TOP = SAFE_PADDING_TOP;
const FOCAL_TOP = CONTENT_TOP + 20;
const LABEL_Y = CONTENT_TOP + 280;
const NOTCH_Y = LABEL_Y + LABEL_HEIGHT + 8;
const NOTCH_W = 2;
const NOTCH_H = 20;
const RULER_Y = NOTCH_Y + 8;
const RULER_H = 4;
const GAP_LABEL_Y = RULER_Y + 16;

const INK = "#141414";
const PAPER = "#F4F1EA";
const SLATE = "#4C5A67";
const AMBER = "#C4A574";
const GAP_INK = "#6B6256";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
const ISO_DT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})$/;
const FACT_ID = /^[A-Za-z0-9_-]{1,128}$/;
const SAMPLES_PER_FRAME = MIX_SAMPLE_RATE_HZ / FPS;
const SAMPLES_PER_MS = MIX_SAMPLE_RATE_HZ / 1_000;
const COOLDOWN_SAMPLES = COOLDOWN_MS * SAMPLES_PER_MS;
const TICK_DURATION_SAMPLES = TICK_DURATION_MS * SAMPLES_PER_MS;

const OWNED_BY_CRIME_SCENE_2K = "Illustrative2KPanZoom";

export const TICK_GAIN_UNITS = Math.floor(10 ** (TICK_PEAK_DBTP / 20) * GAIN_UNIT_SCALE + 1e-6);

export type CssValue = string | number;

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type ScrubNode = {
  readonly type: "div";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: Readonly<Record<string, CssValue>>;
    readonly children?: ScrubChild | readonly ScrubChild[];
  };
};

export type ScrubChild = ScrubNode | string;

export type ForensicDateEvent = {
  readonly fact_id: string;
  readonly datetime_iso: string;
  readonly event_summary: string;
};

export type TimelineDateScrubberProps = {
  readonly events: readonly ForensicDateEvent[];
  readonly focalFactId?: string;
  readonly frame?: number;
  readonly durationFrames?: number;
  readonly sceneId?: string;
  readonly isEndScreen?: boolean;
};

export type PlacedNotch = {
  readonly fact_id: string;
  readonly datetime_iso: string;
  readonly ms: number;
  readonly summary: string;
  readonly label: string;
  readonly inCluster: boolean;
  readonly x: number;
  readonly frame: number;
  readonly mark: Rect;
  readonly labelBox: Rect;
};

export type PlacedGap = {
  readonly kind: "cluster" | "time-gap";
  readonly label: typeof TIME_GAP_LABEL | null;
  readonly fromFactId: string;
  readonly toFactId: string;
  readonly deltaMs: number;
  readonly x: number;
  readonly widthPx: number;
  readonly box: Rect | null;
};

export type FocalCard = {
  readonly fact_id: string;
  readonly datetime_iso: string;
  readonly summary: string;
  readonly scale: number;
  readonly arrivalFrame: number;
  readonly box: Rect;
};

export type TickSfxCue = {
  readonly cue_id: string;
  readonly cue: typeof TICK_SFX;
  readonly scene_id: string;
  readonly fact_id: string;
  readonly start_sample: number;
  readonly sample_rate_hz: typeof MIX_SAMPLE_RATE_HZ;
  readonly start_frame: number;
  readonly offset_ms: number;
  readonly duration_samples: number;
  readonly cooldown_ms: typeof COOLDOWN_MS;
  readonly gain_units: number;
  readonly gain_unit_scale: typeof GAIN_UNIT_SCALE;
  readonly peak_dbtp: number;
  readonly burst: false;
  readonly tapered: false;
};

export type SuppressedTick = {
  readonly cue: typeof TICK_SFX;
  readonly fact_id: string;
  readonly scene_id: string;
  readonly start_sample: number;
  readonly start_frame: number;
  readonly reason: "cooldown";
};

export type TickSfxTrigger = {
  readonly cue: typeof TICK_SFX;
  readonly sceneId: string;
  readonly frame: number;
};

export type TimelineDateScrubberLayout = {
  readonly motif: typeof TIMELINE_DATE_SCRUBBER_ID;
  readonly motifNumber: typeof MOTIF_NUMBER;
  readonly owner: typeof TIMELINE_DATE_SCRUBBER_OWNER;
  readonly sceneId: string;
  readonly frame: number;
  readonly durationFrames: number;
  readonly isEndScreen: boolean;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly captionBar: Rect;
  readonly endScreenMask: Rect | null;
  readonly notches: readonly PlacedNotch[];
  readonly gaps: readonly PlacedGap[];
  readonly focal: FocalCard;
  readonly playhead: Rect;
  readonly playheadX: number;
  readonly ruler: Rect;
  readonly trackLeft: number;
  readonly trackRight: number;
  readonly linearXs: readonly number[];
  readonly cues: readonly TickSfxCue[];
  readonly suppressed: readonly SuppressedTick[];
};

export type TimelineDateScrubberNode = ScrubNode & {
  readonly layout: TimelineDateScrubberLayout;
};

type RegistryRow = {
  readonly motif_component: string;
  readonly owner_package: string;
  readonly is_mvp_4: boolean | number;
};

type WallClock = {
  readonly ms: number;
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly hour: number;
  readonly minute: number;
  readonly second: number;
  readonly raw: string;
  readonly fact_id: string;
  readonly summary: string;
};

type Slot = {
  readonly min: number;
  readonly flex: boolean;
  readonly weight: number;
  readonly kind: "cluster" | "time-gap";
};

export class TimelineDateScrubberError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimelineDateScrubberError";
  }
}

export function contentRect(): Rect {
  return {
    x: 0,
    y: SAFE_PADDING_TOP,
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT - SAFE_PADDING_TOP - SAFE_PADDING_BOTTOM,
  };
}

export function exclusionRect(): Rect {
  const width = FRAME_WIDTH * 0.22;
  const height = FRAME_HEIGHT * 0.14;
  return {
    x: FRAME_WIDTH - width,
    y: FRAME_HEIGHT - height,
    width,
    height,
  };
}

export function captionBarRect(): Rect {
  return {
    x: 0,
    y: FRAME_HEIGHT - SAFE_PADDING_BOTTOM,
    width: FRAME_WIDTH,
    height: SAFE_PADDING_BOTTOM,
  };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

export function rectInside(inner: Rect, outer: Rect): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

export function wordCount(text: string): number {
  return text
    .trim()
    .split(/\s+/)
    .filter((word) => word.length > 0).length;
}

export function clampWords(text: string, max = RULE_07_MAX_WORDS): string {
  const words = text
    .trim()
    .split(/\s+/)
    .filter((word) => word.length > 0);
  return words.slice(0, max).join(" ");
}

export function textWidth(text: string): number {
  return Math.max(LABEL_MIN_WIDTH, text.length * LABEL_CHAR_PX);
}

export function focalZoomScale(distanceFrames: number): number {
  const distance = Math.abs(distanceFrames);
  const weight = Math.exp(-(distance * distance) / (2 * FOCAL_ZOOM_SIGMA_FRAMES * FOCAL_ZOOM_SIGMA_FRAMES));
  return 1 + (FOCAL_ZOOM_MAX - 1) * weight;
}

export function linearNotchXs(times: readonly number[], left: number, right: number): number[] {
  const count = times.length;
  if (count === 0) return [];
  const start = Math.round(left);
  const end = Math.round(right);
  if (count === 1) return [Math.round((start + end) / 2)];
  const first = times[0] ?? 0;
  const last = times[count - 1] ?? first;
  const span = last - first;
  if (span <= 0) return times.map(() => start);
  return times.map((time) => Math.round(start + ((end - start) * (time - first)) / span));
}

export function assertDateScrubberOwnership(row: RegistryRow): void {
  if (row.motif_component === OWNED_BY_CRIME_SCENE_2K) {
    throw new TimelineDateScrubberError(
      "Illustrative2KPanZoom is owned by crime_scene_2k and is not implemented in Remotion",
    );
  }
  if (row.motif_component !== TIMELINE_DATE_SCRUBBER_ID || row.owner_package !== TIMELINE_DATE_SCRUBBER_OWNER) {
    throw new TimelineDateScrubberError("TimelineDateScrubber is motif #9 owned by render_catalog");
  }
  const mvp = row.is_mvp_4 === true || row.is_mvp_4 === 1;
  if (mvp) throw new TimelineDateScrubberError("TimelineDateScrubber is motif #9, not an MVP-4 motif");
}

export function walkScrub(node: ScrubChild, into: ScrubNode[] = []): ScrubNode[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walkScrub(child, into);
  return into;
}

export function exportTickSfxCues(cues: readonly TickSfxCue[]): string {
  const rows = cues.map((cue) => ({
    cue_id: cue.cue_id,
    cue: cue.cue,
    scene_id: cue.scene_id,
    fact_id: cue.fact_id,
    start_sample: cue.start_sample,
    sample_rate_hz: cue.sample_rate_hz,
    start_frame: cue.start_frame,
    offset_ms: cue.offset_ms,
    duration_samples: cue.duration_samples,
    cooldown_ms: cue.cooldown_ms,
    gain_units: cue.gain_units,
    gain_unit_scale: cue.gain_unit_scale,
    peak_dbtp: cue.peak_dbtp,
    burst: cue.burst,
    tapered: cue.tapered,
  }));
  return `${JSON.stringify(rows, null, 2)}\n`;
}

export function tickSfxTriggers(cues: readonly TickSfxCue[]): TickSfxTrigger[] {
  return cues.map((cue) => ({
    cue: TICK_SFX,
    sceneId: cue.scene_id,
    frame: cue.start_frame,
  }));
}

export function layoutTimelineDateScrubber(props: TimelineDateScrubberProps): TimelineDateScrubberLayout {
  const events = parseEvents(props.events);
  const sceneId = resolveSceneId(props.sceneId);
  const durationFrames = resolveDuration(props.durationFrames);
  const frame = resolveFrame(props.frame, durationFrames);
  const isEndScreen = props.isEndScreen === true;
  const deltas = events.slice(1).map((event, index) => event.ms - (events[index]?.ms ?? event.ms));
  const inCluster = events.map((_, index) => {
    const prev = index > 0 ? (deltas[index - 1] ?? Infinity) : Infinity;
    const next = index < deltas.length ? (deltas[index] ?? Infinity) : Infinity;
    return prev <= CLUSTER_MAX_MS || next <= CLUSTER_MAX_MS;
  });
  const labels = events.map((event, index) => clockLabel(event, inCluster[index] === true));
  const slots = deltas.map((delta, index) => {
    const left = labels[index] ?? "";
    const right = labels[index + 1] ?? "";
    const cluster = delta <= CLUSTER_MAX_MS;
    return {
      min: pairMin(left, right, !cluster),
      flex: !cluster,
      weight: Math.max(0, delta),
      kind: cluster ? ("cluster" as const) : ("time-gap" as const),
    };
  });
  const firstLabel = labels[0] ?? "";
  const lastLabel = labels[labels.length - 1] ?? firstLabel;
  const trackLeft = textWidth(firstLabel) / 2;
  const trackRight = FRAME_WIDTH - textWidth(lastLabel) / 2;
  const xs = placeNotchXs(slots, trackLeft, trackRight);
  const linearXs = linearNotchXs(
    events.map((event) => event.ms),
    trackLeft,
    trackRight,
  );
  const notches = events.map((event, index) => {
    const x = xs[index];
    const label = labels[index];
    if (x === undefined || label === undefined) fail("notch layout missed an event");
    const labelBox = centerBox(x, LABEL_Y, label);
    const mark: Rect = { x: x - NOTCH_W / 2, y: NOTCH_Y, width: NOTCH_W, height: NOTCH_H };
    return {
      fact_id: event.fact_id,
      datetime_iso: event.raw,
      ms: event.ms,
      summary: event.summary,
      label,
      inCluster: inCluster[index] === true,
      x,
      frame: notchFrame(x, xs[0] ?? x, xs[xs.length - 1] ?? x, durationFrames),
      mark,
      labelBox,
    };
  });
  const gaps = slots.map((slot, index) => {
    const left = notches[index];
    const right = notches[index + 1];
    const delta = deltas[index];
    if (!left || !right || delta === undefined) fail("time-gap layout missed a pair");
    const widthPx = right.x - left.x;
    const x = left.x + widthPx / 2;
    const box = slot.kind === "time-gap" ? centerBox(x, GAP_LABEL_Y, TIME_GAP_LABEL) : null;
    return {
      kind: slot.kind,
      label: slot.kind === "time-gap" ? TIME_GAP_LABEL : null,
      fromFactId: left.fact_id,
      toFactId: right.fact_id,
      deltaMs: delta,
      x,
      widthPx,
      box,
    };
  });
  const playheadX = playheadAt(xs, frame, durationFrames);
  const focalIndex = resolveFocalIndex(notches, props.focalFactId, playheadX);
  const focalNotch = notches[focalIndex];
  if (!focalNotch) fail("focal card missed its notch");
  const scale = focalZoomScale(frame - focalNotch.frame);
  const focal = placeFocal(focalNotch, scale);
  const firstX = notches[0]?.x ?? trackLeft;
  const lastX = notches[notches.length - 1]?.x ?? trackRight;
  const ruler: Rect = {
    x: firstX,
    y: RULER_Y,
    width: Math.max(1, lastX - firstX),
    height: RULER_H,
  };
  const playhead: Rect = {
    x: playheadX - 1,
    y: NOTCH_Y,
    width: 2,
    height: RULER_Y + RULER_H - NOTCH_Y,
  };
  const mask = isEndScreen ? endScreenMask() : null;
  const { cues, suppressed } = emitTicks(notches, sceneId);
  const layout: TimelineDateScrubberLayout = {
    motif: TIMELINE_DATE_SCRUBBER_ID,
    motifNumber: MOTIF_NUMBER,
    owner: TIMELINE_DATE_SCRUBBER_OWNER,
    sceneId,
    frame,
    durationFrames,
    isEndScreen,
    content: contentRect(),
    exclusion: exclusionRect(),
    captionBar: captionBarRect(),
    endScreenMask: mask,
    notches,
    gaps,
    focal,
    playhead,
    playheadX,
    ruler,
    trackLeft: Math.round(trackLeft),
    trackRight: Math.round(trackRight),
    linearXs,
    cues,
    suppressed,
  };
  assertInvariant(layout);
  return layout;
}

export function TimelineDateScrubber(props: TimelineDateScrubberProps): TimelineDateScrubberNode {
  const layout = layoutTimelineDateScrubber(props);
  const tree = renderTree(layout);
  return { ...tree, layout };
}

function fail(message: string): never {
  throw new TimelineDateScrubberError(message);
}

function parseEvents(value: readonly ForensicDateEvent[]): WallClock[] {
  if (!Array.isArray(value) || value.length === 0) fail("events must be a non-empty forensic date list");
  const parsed = value.map((row, index) => parseEvent(row, index));
  const seen = new Set<string>();
  for (const event of parsed) {
    if (seen.has(event.fact_id)) fail(`duplicate fact_id: ${event.fact_id}`);
    seen.add(event.fact_id);
  }
  return [...parsed].sort((a, b) => a.ms - b.ms || a.fact_id.localeCompare(b.fact_id));
}

function parseEvent(value: unknown, index: number): WallClock {
  if (value === null || typeof value !== "object") fail(`events[${index}] must be a fact_ledger row`);
  const row = value as Record<string, unknown>;
  const factId = row.fact_id;
  const datetime = row.datetime_iso;
  const summary = row.event_summary;
  if (typeof factId !== "string" || !FACT_ID.test(factId)) {
    fail(`fact_id must reference fact_ledger: ${String(factId)}`);
  }
  if (typeof datetime !== "string") fail(`datetime_iso must be ISO-8601 at events[${index}]`);
  if (typeof summary !== "string" || summary.trim().length === 0) fail(`event_summary is required for ${factId}`);
  const wall = parseIso(datetime);
  return { ...wall, fact_id: factId, summary: clampWords(summary) };
}

function parseIso(value: string): Omit<WallClock, "fact_id" | "summary"> {
  const match = ISO_DT.exec(value);
  if (!match) fail(`datetime_iso must be ISO-8601: ${value}`);
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  if (month < 1 || month > 12 || hour > 23 || minute > 59 || second > 59) {
    fail(`datetime_iso must be ISO-8601: ${value}`);
  }
  const probe = new Date(Date.UTC(year, month - 1, day));
  if (probe.getUTCFullYear() !== year || probe.getUTCMonth() !== month - 1 || probe.getUTCDate() !== day) {
    fail(`datetime_iso must be ISO-8601: ${value}`);
  }
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) fail(`datetime_iso must be ISO-8601: ${value}`);
  return { ms, year, month, day, hour, minute, second, raw: value };
}

function resolveSceneId(sceneId: string | undefined): string {
  const resolved = sceneId ?? "timeline_date_scrubber";
  if (resolved.length === 0 || resolved.length > 200) {
    fail("sceneId must be a non-empty string of at most 200 characters");
  }
  return resolved;
}

function resolveDuration(durationFrames: number | undefined): number {
  const resolved = durationFrames ?? DEFAULT_DURATION_FRAMES;
  if (!Number.isInteger(resolved) || resolved < 1 || resolved > MAX_DURATION_FRAMES) {
    fail(`durationFrames must be an integer from 1 to ${MAX_DURATION_FRAMES}`);
  }
  return resolved;
}

function resolveFrame(frame: number | undefined, durationFrames: number): number {
  const resolved = frame ?? 0;
  if (!Number.isInteger(resolved) || resolved < 0 || resolved > durationFrames - 1) {
    fail(`frame must be an integer from 0 to ${durationFrames - 1}`);
  }
  return resolved;
}

function clockLabel(wall: Omit<WallClock, "fact_id" | "summary">, inCluster: boolean): string {
  const hh = String(wall.hour).padStart(2, "0");
  const mm = String(wall.minute).padStart(2, "0");
  if (inCluster) return `${hh}:${mm}`;
  const month = MONTHS[wall.month - 1] ?? "Jan";
  return `${month} ${wall.day} ${wall.year}`;
}

function pairMin(left: string, right: string, withDivider: boolean): number {
  const span = textWidth(left) / 2 + LABEL_GAP + textWidth(right) / 2;
  if (!withDivider) return Math.ceil(span);
  return Math.ceil(span + textWidth(TIME_GAP_LABEL) + LABEL_GAP);
}

function placeNotchXs(slots: readonly Slot[], left: number, right: number): number[] {
  const start = Math.round(left);
  const end = Math.round(right);
  if (slots.length === 0) return [Math.round((start + end) / 2)];
  if (end <= start) fail("Non-overlapping notch invariant: ruler has no width");
  const minSum = slots.reduce((sum, slot) => sum + slot.min, 0);
  const width = end - start;
  if (minSum > width) fail("Non-overlapping notch invariant: ruler cannot separate every notch");
  const extra = width - minSum;
  const shares = slotShares(slots, extra);
  const xs: number[] = [start];
  let cursor = start;
  for (let index = 0; index < slots.length; index += 1) {
    const slot = slots[index];
    const share = shares[index] ?? 0;
    if (!slot) fail("Non-overlapping notch invariant");
    cursor += slot.min + share;
    xs.push(Math.round(cursor));
  }
  for (let index = 1; index < xs.length; index += 1) {
    const min = slots[index - 1]?.min ?? 0;
    const previous = xs[index - 1] ?? start;
    const current = xs[index] ?? previous;
    if (current < previous + min) xs[index] = previous + min;
  }
  const last = xs[xs.length - 1] ?? end;
  if (last > end) {
    xs[xs.length - 1] = end;
    for (let index = xs.length - 2; index >= 0; index -= 1) {
      const min = slots[index]?.min ?? 0;
      const next = xs[index + 1] ?? end;
      const current = xs[index] ?? start;
      if (current > next - min) xs[index] = next - min;
    }
  }
  if ((xs[0] ?? start) < start || (xs[xs.length - 1] ?? end) > end) {
    fail("Non-overlapping notch invariant: ruler cannot separate every notch");
  }
  for (let index = 1; index < xs.length; index += 1) {
    const min = slots[index - 1]?.min ?? 0;
    const previous = xs[index - 1] ?? start;
    const current = xs[index] ?? previous;
    if (current - previous < min) fail("Non-overlapping notch invariant");
  }
  return xs;
}

function slotShares(slots: readonly Slot[], extra: number): number[] {
  const flexCount = slots.filter((slot) => slot.flex).length;
  if (flexCount > 0) {
    const each = extra / flexCount;
    return slots.map((slot) => (slot.flex ? each : 0));
  }
  const total = slots.reduce((sum, slot) => sum + slot.weight, 0);
  if (total <= 0) {
    const each = slots.length === 0 ? 0 : extra / slots.length;
    return slots.map(() => each);
  }
  return slots.map((slot) => (extra * slot.weight) / total);
}

function centerBox(center: number, y: number, text: string): Rect {
  const width = textWidth(text);
  let x = Math.round(center - width / 2);
  if (x < 0) x = 0;
  const maxX = FRAME_WIDTH - width;
  if (x > maxX) x = maxX;
  return { x, y, width, height: LABEL_HEIGHT };
}

function notchFrame(x: number, first: number, last: number, durationFrames: number): number {
  if (durationFrames <= 1 || last === first) return 0;
  const t = (x - first) / (last - first);
  return Math.round(t * (durationFrames - 1));
}

function playheadAt(xs: readonly number[], frame: number, durationFrames: number): number {
  const first = xs[0] ?? 0;
  const last = xs[xs.length - 1] ?? first;
  if (durationFrames <= 1 || last === first) return Math.round(first);
  const t = frame / (durationFrames - 1);
  return Math.round(first + (last - first) * t);
}

function resolveFocalIndex(notches: readonly PlacedNotch[], focalFactId: string | undefined, playheadX: number): number {
  if (focalFactId !== undefined) {
    const index = notches.findIndex((notch) => notch.fact_id === focalFactId);
    if (index < 0) fail(`focalFactId is not on this ruler: ${focalFactId}`);
    return index;
  }
  let best = 0;
  let bestDist = Infinity;
  for (let index = 0; index < notches.length; index += 1) {
    const notch = notches[index];
    if (!notch) continue;
    const dist = Math.abs(notch.x - playheadX);
    if (dist < bestDist) {
      bestDist = dist;
      best = index;
    }
  }
  return best;
}

function placeFocal(notch: PlacedNotch, scale: number): FocalCard {
  const width = Math.round(FOCAL_CARD_W * scale);
  const height = Math.round(FOCAL_CARD_H * scale);
  let x = Math.round(notch.x - width / 2);
  if (x < 0) x = 0;
  const maxX = FRAME_WIDTH - width;
  if (x > maxX) x = maxX;
  const y = FOCAL_TOP;
  return {
    fact_id: notch.fact_id,
    datetime_iso: notch.datetime_iso,
    summary: notch.summary,
    scale,
    arrivalFrame: notch.frame,
    box: { x, y, width, height },
  };
}

function endScreenMask(): Rect {
  const exclusion = exclusionRect();
  const height = 48;
  const y = captionBarRect().y - height;
  return { x: 0, y, width: exclusion.x, height };
}

function emitTicks(
  notches: readonly PlacedNotch[],
  sceneId: string,
): { cues: TickSfxCue[]; suppressed: SuppressedTick[] } {
  const ordered = [...notches].sort((a, b) => a.frame - b.frame || a.x - b.x || a.fact_id.localeCompare(b.fact_id));
  const cues: TickSfxCue[] = [];
  const suppressed: SuppressedTick[] = [];
  let lastSample: number | null = null;
  for (const notch of ordered) {
    const startSample = notch.frame * SAMPLES_PER_FRAME;
    if (lastSample !== null && startSample - lastSample < COOLDOWN_SAMPLES) {
      suppressed.push({
        cue: TICK_SFX,
        fact_id: notch.fact_id,
        scene_id: sceneId,
        start_sample: startSample,
        start_frame: notch.frame,
        reason: "cooldown",
      });
      continue;
    }
    cues.push(toCue(notch, sceneId, startSample));
    lastSample = startSample;
  }
  return { cues, suppressed };
}

function toCue(notch: PlacedNotch, sceneId: string, startSample: number): TickSfxCue {
  return {
    cue_id: `${sceneId}:${TICK_SFX}:${notch.fact_id}:${startSample}`,
    cue: TICK_SFX,
    scene_id: sceneId,
    fact_id: notch.fact_id,
    start_sample: startSample,
    sample_rate_hz: MIX_SAMPLE_RATE_HZ,
    start_frame: notch.frame,
    offset_ms: offsetMsFromSample(startSample),
    duration_samples: TICK_DURATION_SAMPLES,
    cooldown_ms: COOLDOWN_MS,
    gain_units: TICK_GAIN_UNITS,
    gain_unit_scale: GAIN_UNIT_SCALE,
    peak_dbtp: TICK_PEAK_DBTP,
    burst: false,
    tapered: false,
  };
}

function offsetMsFromSample(sample: number): number {
  const rate = BigInt(MIX_SAMPLE_RATE_HZ);
  const scaled = BigInt(sample) * 1_000_000_000n;
  const rounded = (scaled + rate / 2n) / rate;
  return Number(rounded) / 1_000_000;
}

function anyOverlap(boxes: readonly Rect[]): boolean {
  for (let i = 0; i < boxes.length; i += 1) {
    const box = boxes[i];
    if (!box) continue;
    for (let j = i + 1; j < boxes.length; j += 1) {
      const other = boxes[j];
      if (other && rectsOverlap(box, other)) return true;
    }
  }
  return false;
}

function assertInvariant(layout: TimelineDateScrubberLayout): void {
  const content = layout.content;
  const notchBoxes = layout.notches.flatMap((notch) => [notch.labelBox, notch.mark]);
  const gapBoxes = layout.gaps.flatMap((gap) => (gap.box ? [gap.box] : []));
  const boxes = [...notchBoxes, ...gapBoxes, layout.focal.box, layout.playhead, layout.ruler];
  if (anyOverlap(layout.notches.map((notch) => notch.labelBox))) {
    fail("Non-overlapping notch invariant");
  }
  if (anyOverlap(layout.notches.map((notch) => notch.mark))) fail("Non-overlapping notch invariant");
  if (gapBoxes.some((box) => notchBoxes.some((notch) => rectsOverlap(box, notch)))) {
    fail("Non-overlapping notch invariant");
  }
  if (notchBoxes.some((box) => rectsOverlap(box, layout.focal.box))) {
    fail("focal card covers a notch");
  }
  for (const box of boxes) {
    if (!rectInside(box, content)) fail("date ruler leaves the safe zone");
    if (rectsOverlap(box, layout.exclusion) || rectsOverlap(box, layout.captionBar)) {
      fail("date ruler intersects a YouTube exclusion zone");
    }
    if (layout.endScreenMask && rectsOverlap(box, layout.endScreenMask)) {
      fail("end-screen mask covers the date ruler");
    }
  }
  for (const notch of layout.notches) {
    if (wordCount(notch.label) > RULE_07_MAX_WORDS) fail(`notch ${notch.fact_id} exceeds ${RULE_07_MAX_WORDS} words`);
    if (wordCount(notch.summary) > RULE_07_MAX_WORDS) fail(`summary ${notch.fact_id} exceeds ${RULE_07_MAX_WORDS} words`);
  }
  for (const gap of layout.gaps) {
    if (gap.kind === "time-gap" && gap.label !== TIME_GAP_LABEL) fail("time gap divider must read // TIME GAP");
    if (gap.kind === "cluster" && gap.label !== null) fail("a four-minute cluster is not a time gap");
  }
  if (layout.focal.scale < 1 || layout.focal.scale > FOCAL_ZOOM_MAX + 1e-9) {
    fail("focal card zoom is outside 1..1.5");
  }
  for (const cue of layout.cues) {
    if (cue.cue !== TICK_SFX) fail("date ruler cues must be tick_sfx");
    if (cue.peak_dbtp > TRUE_PEAK_CEILING_DBTP) fail("tick_sfx peak exceeds -1.0 dBTP");
    if (cue.gain_units <= 0 || cue.gain_units !== TICK_GAIN_UNITS) fail("tick_sfx gain left the nominal tick");
  }
  for (let index = 1; index < layout.cues.length; index += 1) {
    const prev = layout.cues[index - 1];
    const next = layout.cues[index];
    if (!prev || !next) continue;
    if (next.start_sample - prev.start_sample < COOLDOWN_SAMPLES) fail("tick_sfx cues broke the 60 ms cooldown");
  }
}

function element(
  dataset: Readonly<Record<string, string>>,
  style: Readonly<Record<string, CssValue>>,
  children?: readonly ScrubChild[],
): ScrubNode {
  if (children !== undefined && children.length > 0) {
    const only = children.length === 1 ? children[0] : children;
    if (only !== undefined) return { type: "div", dataset, props: { style, children: only } };
  }
  return { type: "div", dataset, props: { style } };
}

function SafeZoneLayout(props: { readonly isEndScreen: boolean; readonly children: readonly ScrubChild[] }): ScrubNode {
  return element(
    {
      "safe-zone": "css-contained",
      motif: TIMELINE_DATE_SCRUBBER_ID,
      "motif-number": String(MOTIF_NUMBER),
      owner: TIMELINE_DATE_SCRUBBER_OWNER,
      "end-screen": props.isEndScreen ? "true" : "false",
    },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gridTemplateRows: "minmax(0, 1fr)",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      paddingTop: SAFE_PADDING_TOP,
      paddingBottom: SAFE_PADDING_BOTTOM,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
      background: PAPER,
    },
    props.children,
  );
}

function renderTree(layout: TimelineDateScrubberLayout): ScrubNode {
  const origin = layout.content;
  const bars: ScrubChild[] = [
    element(
      { slot: "ruler" },
      {
        position: "absolute",
        left: layout.ruler.x - origin.x,
        top: layout.ruler.y - origin.y,
        width: layout.ruler.width,
        height: layout.ruler.height,
        background: SLATE,
        overflow: "hidden",
      },
    ),
    element(
      { slot: "playhead" },
      {
        position: "absolute",
        left: layout.playhead.x - origin.x,
        top: layout.playhead.y - origin.y,
        width: layout.playhead.width,
        height: layout.playhead.height,
        background: AMBER,
        overflow: "hidden",
      },
    ),
  ];
  for (const notch of layout.notches) {
    bars.push(
      element(
        { slot: "notch", "fact-id": notch.fact_id, label: notch.label },
        {
          position: "absolute",
          left: notch.mark.x - origin.x,
          top: notch.mark.y - origin.y,
          width: notch.mark.width,
          height: notch.mark.height,
          background: INK,
          overflow: "hidden",
        },
      ),
    );
    bars.push(
      element(
        { slot: "notch-label", "fact-id": notch.fact_id },
        {
          position: "absolute",
          left: notch.labelBox.x - origin.x,
          top: notch.labelBox.y - origin.y,
          width: notch.labelBox.width,
          height: notch.labelBox.height,
          overflow: "hidden",
          whiteSpace: "nowrap",
          color: INK,
          fontSize: 24,
          lineHeight: 1,
          maxHeight: LABEL_HEIGHT,
        },
        [notch.label],
      ),
    );
  }
  for (const gap of layout.gaps) {
    if (gap.kind !== "time-gap" || !gap.box) continue;
    bars.push(
      element(
        { slot: "time-gap", "from-fact-id": gap.fromFactId, "to-fact-id": gap.toFactId },
        {
          position: "absolute",
          left: gap.box.x - origin.x,
          top: gap.box.y - origin.y,
          width: gap.box.width,
          height: gap.box.height,
          overflow: "hidden",
          whiteSpace: "nowrap",
          color: GAP_INK,
          fontSize: 22,
          lineHeight: 1,
          maxHeight: LABEL_HEIGHT,
        },
        [TIME_GAP_LABEL],
      ),
    );
  }
  const focal = layout.focal;
  bars.push(
    element(
      {
        slot: "focal-card",
        "fact-id": focal.fact_id,
        zoom: focal.scale.toFixed(3),
      },
      {
        position: "absolute",
        left: focal.box.x - origin.x,
        top: focal.box.y - origin.y,
        width: focal.box.width,
        height: focal.box.height,
        overflow: "hidden",
        background: PAPER,
        color: INK,
        border: `2px solid ${INK}`,
        fontSize: 28,
        lineHeight: 1.2,
        maxHeight: focal.box.height,
      },
      [focal.datetime_iso, focal.summary],
    ),
  );
  bars.push(
    element(
      { slot: "tick-cues", cue: TICK_SFX },
      {
        position: "absolute",
        left: 0,
        top: 0,
        width: 0,
        height: 0,
        overflow: "hidden",
      },
      [exportTickSfxCues(layout.cues)],
    ),
  );
  const layers: ScrubChild[] = [
    element(
      { slot: "content" },
      {
        position: "relative",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      },
      bars,
    ),
    element(
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: EXCLUSION_WIDTH,
        height: EXCLUSION_HEIGHT,
        overflow: "hidden",
        pointerEvents: "none",
      },
    ),
  ];
  if (layout.endScreenMask) {
    layers.push(
      element(
        { mask: "end-screen-card" },
        {
          position: "absolute",
          left: layout.endScreenMask.x,
          top: layout.endScreenMask.y,
          width: layout.endScreenMask.width,
          height: layout.endScreenMask.height,
          overflow: "hidden",
          pointerEvents: "none",
        },
      ),
    );
  }
  return SafeZoneLayout({ isEndScreen: layout.isEndScreen, children: layers });
}
