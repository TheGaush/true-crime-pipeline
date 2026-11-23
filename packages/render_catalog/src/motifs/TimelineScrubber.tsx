/**
 * Extended 2D motif #5 — TimelineScrubber.
 *
 * Chronological date and hour scrub bars, with milestone pins linked to
 * `fact_ledger(fact_id)`. `<SafeZoneLayout>` is a function, not JSX: the
 * package tsconfig has no `jsx` flag (Task 001). Task 101's shared
 * `safe_zone.tsx` is not on this branch, so this motif draws the same
 * 108px / 194px padding and 22% by 14% exclusion box itself.
 *
 * Illustrative2KPanZoom is not a Remotion component. `packages/crime_scene_2k`
 * owns that motif.
 */

export const TIMELINE_SCRUBBER_ID = "TimelineScrubber" as const;
export const TIMELINE_SCRUBBER_OWNER = "render_catalog" as const;

/** SQL `motif_registry` / golden `motif_registry_v1` name for this component. */
export const MOTIF_REGISTRY_V1_NAME = "MOTIF_REGISTRY_V1" as const;

const OWNED_BY_CRIME_SCENE_2K = "Illustrative2KPanZoom";

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const EXCLUSION_WIDTH = "22%";
export const EXCLUSION_HEIGHT = "14%";
export const RULE_07_MAX_WORDS = 12;
export const LABEL_CHAR_PX = 14;
export const LABEL_MIN_WIDTH = 36;
export const LABEL_HEIGHT = 32;
export const LABEL_GAP = 8;

const DATE_TICK_Y = 140;
const DATE_TRACK_Y = 196;
const DATE_TRACK_H = 4;
const PIN_MARK = 12;
const PIN_LABEL_Y = 216;
const HOUR_TRACK_Y = 392;
const HOUR_TRACK_H = 4;
const HOUR_LABEL_Y = 412;

const INK = "#141414";
const PAPER = "#F4F1EA";
const SLATE = "#4C5A67";
const AMBER = "#C4A574";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] as const;
const ISO_DT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})$/;
const FACT_ID = /^[A-Za-z0-9_-]{1,128}$/;
const DAY_MS = 86_400_000;

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

export type FactMilestone = {
  readonly fact_id: string;
  readonly datetime_iso: string;
  readonly event_summary: string;
};

export type TimelineScrubberProps = {
  readonly milestones: readonly FactMilestone[];
  readonly scrubAt?: string;
  readonly isEndScreen?: boolean;
};

export type PlacedLabel = {
  readonly text: string;
  readonly box: Rect;
};

export type PlacedPin = {
  readonly fact_id: string;
  readonly datetime_iso: string;
  readonly ms: number;
  readonly summary: string;
  readonly x: number;
  readonly mark: Rect;
  readonly label: PlacedLabel;
};

export type PlacedTick = {
  readonly kind: "date" | "hour";
  readonly text: string;
  readonly x: number;
  readonly mark: Rect;
  readonly label: PlacedLabel;
};

export type TimelineScrubberLayout = {
  readonly motif: typeof TIMELINE_SCRUBBER_ID;
  readonly owner: typeof TIMELINE_SCRUBBER_OWNER;
  readonly isEndScreen: boolean;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly captionBar: Rect;
  readonly endScreenMask: Rect | null;
  readonly pins: readonly PlacedPin[];
  readonly dateTicks: readonly PlacedTick[];
  readonly hourTicks: readonly PlacedTick[];
  readonly dateTrack: Rect;
  readonly hourTrack: Rect;
  readonly playhead: Rect;
  readonly hourPlayhead: Rect;
  readonly playheadX: number;
  readonly hourPlayheadX: number;
  readonly scrubAt: string;
  readonly trackLeft: number;
  readonly trackRight: number;
  readonly minStep: number;
};

export class TimelineScrubberError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimelineScrubberError";
  }
}

type WallClock = {
  readonly ms: number;
  readonly year: number;
  readonly month: number;
  readonly day: number;
  readonly hour: number;
  readonly minute: number;
  readonly second: number;
  readonly raw: string;
};

type ParsedMilestone = WallClock & {
  readonly fact_id: string;
  readonly summary: string;
};

type RegistryRow = {
  readonly motif_component: string;
  readonly owner_package: string;
  readonly is_mvp_4: boolean | number;
};

type PinFormat = "day-year" | "month-day" | "month-year" | "year";

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
  const words = text.trim().split(/\s+/).filter((word) => word.length > 0);
  return words.length;
}

export function clampWords(text: string, max = RULE_07_MAX_WORDS): string {
  const words = text.trim().split(/\s+/).filter((word) => word.length > 0);
  return words.slice(0, max).join(" ");
}

export function textWidth(text: string): number {
  return Math.max(LABEL_MIN_WIDTH, text.length * LABEL_CHAR_PX);
}

export function assertExtendedMotifOwnership(row: RegistryRow): void {
  if (row.motif_component === OWNED_BY_CRIME_SCENE_2K) {
    throw new TimelineScrubberError(
      "Illustrative2KPanZoom is owned by crime_scene_2k and is not implemented in Remotion",
    );
  }
  if (row.motif_component !== TIMELINE_SCRUBBER_ID || row.owner_package !== TIMELINE_SCRUBBER_OWNER) {
    throw new TimelineScrubberError("TimelineScrubber is extended motif #5 owned by render_catalog");
  }
  const mvp = row.is_mvp_4 === true || row.is_mvp_4 === 1;
  if (mvp) {
    throw new TimelineScrubberError("TimelineScrubber is extended motif #5, not an MVP-4 motif");
  }
}

/**
 * Map sorted instants onto `[left, right]`.
 * `minStep <= 0` is pure linear time. A positive `minStep` reserves that many
 * pixels between neighbors and gives leftover width to the real time gaps,
 * so a 2018 cluster does not stack on top of itself before a 2023 jump.
 * `times` must be non-decreasing.
 */
export function layoutPinXs(
  times: readonly number[],
  left: number,
  right: number,
  minStep: number,
): number[] {
  const count = times.length;
  if (count === 0) return [];
  const start = Math.round(left);
  const end = Math.round(right);
  if (count === 1) return [Math.round((start + end) / 2)];
  if (end <= start) throw new TimelineScrubberError("scrub track has no width");
  if (minStep <= 0) {
    const first = times[0] ?? 0;
    const last = times[count - 1] ?? first;
    const span = last - first;
    return times.map((time) => {
      if (span <= 0) return start;
      return Math.round(start + ((end - start) * (time - first)) / span);
    });
  }
  const step = Math.ceil(minStep);
  const width = end - start;
  if ((count - 1) * step > width) {
    return times.map((_, index) => Math.round(start + (index * width) / (count - 1)));
  }
  const gaps = times.slice(1).map((time, index) => Math.max(0, time - (times[index] ?? time)));
  const total = gaps.reduce((sum, gap) => sum + gap, 0);
  const leftover = width - (count - 1) * step;
  const xs: number[] = new Array(count);
  xs[0] = start;
  let cursor = start;
  for (let index = 0; index < gaps.length; index += 1) {
    const gap = gaps[index] ?? 0;
    const extra = total === 0 ? leftover / gaps.length : (leftover * gap) / total;
    cursor += step + extra;
    xs[index + 1] = Math.round(cursor);
  }
  for (let index = 1; index < count; index += 1) {
    const previous = xs[index - 1] ?? start;
    const current = xs[index] ?? previous;
    xs[index] = current < previous + step ? previous + step : current;
  }
  const last = xs[count - 1] ?? end;
  if (last > end) {
    xs[count - 1] = end;
    for (let index = count - 2; index >= 0; index -= 1) {
      const next = xs[index + 1] ?? end;
      const current = xs[index] ?? start;
      if (current > next - step) xs[index] = next - step;
    }
    const first = xs[0] ?? start;
    if (first < start) {
      return times.map((_, index) => Math.round(start + (index * width) / (count - 1)));
    }
  }
  return xs;
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

function fail(message: string): never {
  throw new TimelineScrubberError(message);
}

function parseIso(value: string): WallClock {
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

function parseMilestone(value: unknown, index: number): ParsedMilestone {
  if (value === null || typeof value !== "object") fail(`milestones[${index}] must be a fact_ledger row`);
  const row = value as Record<string, unknown>;
  const factId = row.fact_id;
  const datetime = row.datetime_iso;
  const summary = row.event_summary;
  if (typeof factId !== "string" || !FACT_ID.test(factId)) {
    fail(`fact_id must reference fact_ledger: ${String(factId)}`);
  }
  if (typeof datetime !== "string") fail(`datetime_iso must be ISO-8601 at milestones[${index}]`);
  if (typeof summary !== "string" || summary.trim().length === 0) {
    fail(`event_summary is required for ${factId}`);
  }
  const wall = parseIso(datetime);
  return { ...wall, fact_id: factId, summary: clampWords(summary) };
}

function centerBox(center: number, y: number, text: string): Rect {
  const width = textWidth(text);
  let x = Math.round(center - width / 2);
  if (x < 0) x = 0;
  const maxX = FRAME_WIDTH - width;
  if (x > maxX) x = maxX;
  return { x, y, width, height: LABEL_HEIGHT };
}

function monthName(month: number): string {
  return MONTHS[month - 1] ?? "Jan";
}

function pinText(wall: WallClock, format: PinFormat): string {
  const month = monthName(wall.month);
  if (format === "year") return String(wall.year);
  if (format === "month-year") return `${month} ${wall.year}`;
  if (format === "month-day") return `${month} ${wall.day}`;
  return `${month} ${wall.day}, ${wall.year}`;
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

function assertLabelRules(text: string, box: Rect, what: string): void {
  if (wordCount(text) > RULE_07_MAX_WORDS) fail(`${what} exceeds ${RULE_07_MAX_WORDS} words`);
  if (!rectInside(box, contentRect())) fail(`${what} leaves the safe zone`);
  if (rectsOverlap(box, exclusionRect()) || rectsOverlap(box, captionBarRect())) {
    fail(`${what} intersects a YouTube exclusion zone`);
  }
}

function fitPins(sorted: readonly ParsedMilestone[]): {
  readonly pins: PlacedPin[];
  readonly trackLeft: number;
  readonly trackRight: number;
  readonly minStep: number;
} {
  const formats: readonly PinFormat[] = ["day-year", "month-year", "month-day", "year"];
  const content = contentRect();
  for (const format of formats) {
    const texts = sorted.map((pin) => pinText(pin, format));
    const widest = Math.max(...texts.map((text) => textWidth(text)));
    const minStep = widest + LABEL_GAP;
    const left = widest / 2;
    const right = FRAME_WIDTH - widest / 2;
    const xs = layoutPinXs(
      sorted.map((pin) => pin.ms),
      left,
      right,
      minStep,
    );
    const labels = xs.map((x, index) => {
      const text = texts[index] ?? "";
      return { text, box: centerBox(x, PIN_LABEL_Y, text) };
    });
    const marks = xs.map((x) => ({
      x: x - PIN_MARK / 2,
      y: DATE_TRACK_Y - (PIN_MARK - DATE_TRACK_H) / 2,
      width: PIN_MARK,
      height: PIN_MARK,
    }));
    const labelBoxes = labels.map((label) => label.box);
    const inside =
      labelBoxes.every((box) => rectInside(box, content)) && marks.every((box) => rectInside(box, content));
    if (!inside || anyOverlap(labelBoxes)) continue;
    const pins = sorted.map((pin, index) => {
      const label = labels[index];
      const mark = marks[index];
      const x = xs[index];
      if (!label || !mark || x === undefined) fail("pin layout missed a milestone");
      return {
        fact_id: pin.fact_id,
        datetime_iso: pin.raw,
        ms: pin.ms,
        summary: pin.summary,
        x,
        mark,
        label,
      };
    });
    return { pins, trackLeft: Math.round(left), trackRight: Math.round(right), minStep };
  }
  fail("RULE_07: date labels overlap inside the safe zone");
}

function axisFromPins(pins: readonly PlacedPin[]): (ms: number) => number {
  return (ms: number) => {
    const first = pins[0];
    const last = pins[pins.length - 1];
    if (!first || !last) return 0;
    if (ms <= first.ms) return first.x;
    if (ms >= last.ms) return last.x;
    for (let index = 1; index < pins.length; index += 1) {
      const right = pins[index];
      const left = pins[index - 1];
      if (!right || !left || ms > right.ms) continue;
      const span = right.ms - left.ms;
      if (span <= 0) return right.x;
      const t = (ms - left.ms) / span;
      return left.x + t * (right.x - left.x);
    }
    return last.x;
  };
}

function yearCandidates(startYear: number, endYear: number): { ms: number; text: string }[] {
  const out: { ms: number; text: string }[] = [];
  for (let year = startYear; year <= endYear; year += 1) {
    out.push({ ms: Date.UTC(year, 0, 1), text: String(year) });
  }
  return out;
}

function monthCandidates(start: WallClock, end: WallClock): { ms: number; text: string }[] {
  const out: { ms: number; text: string }[] = [];
  let year = start.year;
  let month = start.month;
  while (year < end.year || (year === end.year && month <= end.month)) {
    out.push({ ms: Date.UTC(year, month - 1, 1), text: `${monthName(month)} ${year}` });
    month += 1;
    if (month === 13) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

function dayCandidates(start: WallClock, end: WallClock): { ms: number; text: string }[] {
  const out: { ms: number; text: string }[] = [];
  const cursor = new Date(Date.UTC(start.year, start.month - 1, start.day));
  const last = Date.UTC(end.year, end.month - 1, end.day);
  while (cursor.getTime() <= last) {
    const month = cursor.getUTCMonth() + 1;
    const day = cursor.getUTCDate();
    out.push({
      ms: cursor.getTime(),
      text: `${monthName(month)} ${day}`,
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

function chooseDateCandidates(start: WallClock, end: WallClock): { ms: number; text: string }[] {
  const span = end.ms - start.ms;
  if (span >= 366 * DAY_MS) return yearCandidates(start.year, end.year);
  if (span >= 32 * DAY_MS) return monthCandidates(start, end);
  return dayCandidates(start, end);
}

function placeDateTicks(pins: readonly PlacedPin[], start: WallClock, end: WallClock): PlacedTick[] {
  const axis = axisFromPins(pins);
  const placed: PlacedTick[] = [];
  for (const candidate of chooseDateCandidates(start, end)) {
    const x = Math.round(axis(candidate.ms));
    const label = { text: candidate.text, box: centerBox(x, DATE_TICK_Y, candidate.text) };
    const mark: Rect = { x: x - 1, y: DATE_TRACK_Y - 10, width: 2, height: 10 };
    if (!rectInside(label.box, contentRect()) || !rectInside(mark, contentRect())) continue;
    if (placed.some((tick) => rectsOverlap(tick.label.box, label.box))) continue;
    placed.push({ kind: "date", text: candidate.text, x, mark, label });
  }
  if (placed.length === 0) fail("date scrub bar has no readable tick");
  return placed;
}

function placeHourTicks(): { ticks: PlacedTick[]; playheadAt: (hour: number, minute: number, second: number) => number } {
  const sample = textWidth("00:00");
  const left = sample / 2;
  const right = FRAME_WIDTH - sample / 2;
  const span = right - left;
  for (const step of [1, 2, 3, 4, 6, 12]) {
    const hours: number[] = [];
    for (let hour = 0; hour < 24; hour += step) hours.push(hour);
    const ticks = hours.map((hour) => {
      const text = `${String(hour).padStart(2, "0")}:00`;
      const x = Math.round(left + (hour / 24) * span);
      return {
        kind: "hour" as const,
        text,
        x,
        mark: { x: x - 1, y: HOUR_TRACK_Y - 10, width: 2, height: 10 },
        label: { text, box: centerBox(x, HOUR_LABEL_Y, text) },
      };
    });
    const boxes = ticks.map((tick) => tick.label.box);
    const inside = ticks.every(
      (tick) => rectInside(tick.label.box, contentRect()) && rectInside(tick.mark, contentRect()),
    );
    if (inside && !anyOverlap(boxes)) {
      return {
        ticks,
        playheadAt(hour: number, minute: number, second: number) {
          const fraction = (hour + minute / 60 + second / 3600) / 24;
          return Math.round(left + fraction * span);
        },
      };
    }
  }
  fail("hour scrub bar labels overlap inside the safe zone");
}

function endScreenMask(): Rect {
  const exclusion = exclusionRect();
  const height = 48;
  const y = captionBarRect().y - height;
  return { x: 0, y, width: exclusion.x, height };
}

function assertSeparated(boxes: readonly Rect[], what: string): void {
  if (anyOverlap(boxes)) fail(`${what} overlap`);
}

export function layoutTimelineScrubber(props: TimelineScrubberProps): TimelineScrubberLayout {
  if (!Array.isArray(props.milestones) || props.milestones.length === 0) {
    fail("milestones must be a non-empty fact_ledger list");
  }
  const parsed = props.milestones.map((row, index) => parseMilestone(row, index));
  const seen = new Set<string>();
  for (const pin of parsed) {
    if (seen.has(pin.fact_id)) fail(`duplicate fact_id: ${pin.fact_id}`);
    seen.add(pin.fact_id);
  }
  const sorted = [...parsed].sort((a, b) => a.ms - b.ms || a.fact_id.localeCompare(b.fact_id));
  const fitted = fitPins(sorted);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (!first || !last) fail("milestones must be a non-empty fact_ledger list");
  const scrub = props.scrubAt === undefined ? first : parseIso(props.scrubAt);
  const dateTicks = placeDateTicks(fitted.pins, first, last);
  const hours = placeHourTicks();
  const playheadX = Math.round(axisFromPins(fitted.pins)(scrub.ms));
  const hourPlayheadX = hours.playheadAt(scrub.hour, scrub.minute, scrub.second);
  const isEndScreen = props.isEndScreen === true;
  const dateTrack: Rect = {
    x: fitted.pins[0]?.x ?? fitted.trackLeft,
    y: DATE_TRACK_Y,
    width: Math.max(1, (fitted.pins[fitted.pins.length - 1]?.x ?? fitted.trackRight) - (fitted.pins[0]?.x ?? fitted.trackLeft)),
    height: DATE_TRACK_H,
  };
  const hourTrack: Rect = {
    x: Math.round(textWidth("00:00") / 2),
    y: HOUR_TRACK_Y,
    width: FRAME_WIDTH - textWidth("00:00"),
    height: HOUR_TRACK_H,
  };
  const playhead: Rect = {
    x: playheadX - 1,
    y: DATE_TRACK_Y,
    width: 2,
    height: HOUR_TRACK_Y + HOUR_TRACK_H - DATE_TRACK_Y,
  };
  const hourPlayhead: Rect = {
    x: hourPlayheadX - 1,
    y: HOUR_TRACK_Y - 14,
    width: 2,
    height: 18,
  };
  const mask = isEndScreen ? endScreenMask() : null;
  const labelBoxes = [
    ...fitted.pins.map((pin) => pin.label.box),
    ...dateTicks.map((tick) => tick.label.box),
    ...hours.ticks.map((tick) => tick.label.box),
  ];
  assertSeparated(labelBoxes, "RULE_07: date labels");
  for (const pin of fitted.pins) {
    assertLabelRules(pin.label.text, pin.label.box, `pin ${pin.fact_id}`);
    assertLabelRules(pin.summary, pin.label.box, `summary ${pin.fact_id}`);
    if (!rectInside(pin.mark, contentRect())) fail(`pin ${pin.fact_id} leaves the safe zone`);
  }
  for (const tick of [...dateTicks, ...hours.ticks]) {
    assertLabelRules(tick.label.text, tick.label.box, `${tick.kind} tick ${tick.text}`);
    if (!rectInside(tick.mark, contentRect())) fail(`${tick.kind} tick leaves the safe zone`);
  }
  for (const box of [dateTrack, hourTrack, playhead, hourPlayhead]) {
    if (!rectInside(box, contentRect())) fail("scrub bar leaves the safe zone");
  }
  if (mask) {
    if (labelBoxes.some((box) => rectsOverlap(box, mask))) fail("end-screen mask covers a date label");
  }
  return {
    motif: TIMELINE_SCRUBBER_ID,
    owner: TIMELINE_SCRUBBER_OWNER,
    isEndScreen,
    content: contentRect(),
    exclusion: exclusionRect(),
    captionBar: captionBarRect(),
    endScreenMask: mask,
    pins: fitted.pins,
    dateTicks,
    hourTicks: hours.ticks,
    dateTrack,
    hourTrack,
    playhead,
    hourPlayhead,
    playheadX,
    hourPlayheadX,
    scrubAt: scrub.raw,
    trackLeft: fitted.trackLeft,
    trackRight: fitted.trackRight,
    minStep: fitted.minStep,
  };
}

function labelNode(slot: string, factId: string | undefined, label: PlacedLabel, color: string): ScrubNode {
  const dataset: Record<string, string> = { slot };
  if (factId !== undefined) dataset["fact-id"] = factId;
  return element(
    dataset,
    {
      position: "absolute",
      left: label.box.x - contentRect().x,
      top: label.box.y - contentRect().y,
      width: label.box.width,
      height: label.box.height,
      overflow: "hidden",
      whiteSpace: "nowrap",
      color,
      fontSize: 24,
      lineHeight: 1,
      maxHeight: LABEL_HEIGHT,
    },
    [label.text],
  );
}

function markNode(slot: string, factId: string | undefined, box: Rect, color: string): ScrubNode {
  const dataset: Record<string, string> = { slot };
  if (factId !== undefined) dataset["fact-id"] = factId;
  return element(dataset, {
    position: "absolute",
    left: box.x - contentRect().x,
    top: box.y - contentRect().y,
    width: box.width,
    height: box.height,
    background: color,
    overflow: "hidden",
  });
}

/**
 * CSS containment frame. Children that must stay out of the caption bar and
 * the bottom-right exclusion box are positioned against this element.
 */
function SafeZoneLayout(props: { readonly isEndScreen: boolean; readonly children: readonly ScrubChild[] }): ScrubNode {
  return element(
    {
      "safe-zone": "css-contained",
      motif: TIMELINE_SCRUBBER_ID,
      owner: TIMELINE_SCRUBBER_OWNER,
      registry: MOTIF_REGISTRY_V1_NAME,
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

export function TimelineScrubber(props: TimelineScrubberProps): ScrubNode {
  const layout = layoutTimelineScrubber(props);
  const origin = contentRect();
  const bars: ScrubChild[] = [
    element(
      { slot: "date-bar" },
      {
        position: "absolute",
        left: layout.dateTrack.x - origin.x,
        top: layout.dateTrack.y - origin.y,
        width: layout.dateTrack.width,
        height: layout.dateTrack.height,
        background: SLATE,
        overflow: "hidden",
      },
    ),
    element(
      { slot: "hour-bar" },
      {
        position: "absolute",
        left: layout.hourTrack.x - origin.x,
        top: layout.hourTrack.y - origin.y,
        width: layout.hourTrack.width,
        height: layout.hourTrack.height,
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
    element(
      { slot: "hour-playhead" },
      {
        position: "absolute",
        left: layout.hourPlayhead.x - origin.x,
        top: layout.hourPlayhead.y - origin.y,
        width: layout.hourPlayhead.width,
        height: layout.hourPlayhead.height,
        background: AMBER,
        overflow: "hidden",
      },
    ),
  ];
  for (const tick of layout.dateTicks) {
    bars.push(markNode("date-tick", undefined, tick.mark, INK));
    bars.push(labelNode("date-label", undefined, tick.label, INK));
  }
  for (const tick of layout.hourTicks) {
    bars.push(markNode("hour-tick", undefined, tick.mark, SLATE));
    bars.push(labelNode("hour-label", undefined, tick.label, INK));
  }
  for (const pin of layout.pins) {
    bars.push(
      element(
        { slot: "pin", "fact-id": pin.fact_id, summary: pin.summary },
        {
          position: "absolute",
          left: pin.mark.x - origin.x,
          top: pin.mark.y - origin.y,
          width: pin.mark.width,
          height: pin.mark.height,
          background: INK,
          overflow: "hidden",
        },
      ),
    );
    bars.push(labelNode("pin-label", pin.fact_id, pin.label, INK));
  }
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
