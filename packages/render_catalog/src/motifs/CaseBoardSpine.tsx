/**
 * Motif #10 — CaseBoardSpine.
 *
 * A 2-row corkboard inside Task 101's `<SafeZoneLayout>`. Up to 16 clue
 * polaroids, one `pin_thud` per pin, a crimson spine drawn pin to pin, and a
 * 5-second camera zoom-out that settles on that full board. Task 110 schedules
 * the cue (60 ms cooldown, 48 kHz mix). Task 114 certifies the stick rig; this
 * board does not draw it. Neither module is copied onto this branch.
 *
 * The SQL registry lists `CaseBoardSpine` after `SplitScreenComparison`. This
 * task still owns it as motif 10. `MOTIF_REGISTRY_V1` stays the four MVP motifs.
 *
 * SVG turbulence filters are banned. Strokes are plain paths. Crimson
 * `#C92A2A` is the evidence string on this Remotion board, not a Flow keyframe.
 */

// @ts-expect-error TS2307 — Task 101's ../safe_zone.js lands in parallel and is not on this branch.
import { SafeZoneLayout } from "../safe_zone.js";
// @ts-expect-error TS2307 — Task 110's ../sfx/SfxRegistry.js lands in parallel and is not on this branch.
import { dispatchMicroSfx } from "../sfx/SfxRegistry.js";

export const MOTIF_COMPONENT = "CaseBoardSpine";
export const MOTIF_NUMBER = 10;
export const MOTIF_OWNER = "render_catalog";

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const EXCLUSION_WIDTH_RATIO = 0.22;
export const EXCLUSION_HEIGHT_RATIO = 0.14;
/** Matches Task 101's label clamp ceiling so a 3-line caption cannot cover a card. */
export const LABEL_SLOT_PX = 144.9;
export const BOARD_INSET = 16;
export const CARD_GAP_X = 16;
export const CARD_GAP_Y = 20;
export const ROW_COUNT = 2;
export const MAX_CLUES = 16;
export const MIN_CLUES = 1;
export const MAX_LABEL_WORDS = 12;
export const PIN_RADIUS = 7;
export const PIN_INSET = PIN_RADIUS + 4;
export const PIN_DROP_PX = 18;
export const PIN_DROP_FRAMES = 8;
export const PIN_STAGGER_FRAMES = 3;
export const STRING_DRAW_FRAMES = 12;
export const STRING_STROKE = 4;
export const CAPTION_H = 48;
export const CAPTION_PAD = 8;
export const RESET_SECONDS = 5;
export const RESET_FRAMES = RESET_SECONDS * FRAME_FPS;
export const RESET_MS = RESET_SECONDS * 1000;
export const ZOOM_START = 1.65;

export const WINDOW_START_MS = 210_000;
export const WINDOW_END_MS = 270_000;
export const WINDOW_NOMINAL_MS = 240_000;
export const WINDOW_PERIOD_MS = 240_000;
export const WINDOW_FLEX_MS = 30_000;

export const EVIDENCE_CRIMSON = "#C92A2A";
export const CORK_FILL = "#3A2A22";
export const POLAROID_FILL = "#F4F1EA";
export const POLAROID_STROKE = "#1C1917";
export const PHOTO_FILL = "#242220";
export const CAPTION_FILL = "#1C1917";
export const PIN_FILL = "#C4A574";

export const PIN_THUD_CUE = "pin_thud";

export const REMOTION_CLOCK = { fps: FRAME_FPS, width: FRAME_WIDTH, height: FRAME_HEIGHT } as const;

const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const BOUNDARY_KINDS = ["scene", "sentence", "call"] as const;

export type BoundaryKind = (typeof BOUNDARY_KINDS)[number];

export type CaseBoardErrorCode =
  | "BOUNDED_16"
  | "CLUE"
  | "LABEL"
  | "FRAME"
  | "SCENE"
  | "ACT"
  | "WINDOW"
  | "BOUNDARY"
  | "UNCLIPPED"
  | "SFX";

export class CaseBoardSpineError extends Error {
  readonly code: CaseBoardErrorCode;

  constructor(code: CaseBoardErrorCode, message: string) {
    super(message);
    this.name = "CaseBoardSpineError";
    this.code = code;
  }
}

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type BoardChild = BoardNode | string;

export type BoardNode = {
  readonly type: string;
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style?: Readonly<Record<string, string | number>>;
    readonly transform?: string;
    readonly d?: string;
    readonly fill?: string;
    readonly stroke?: string;
    readonly strokeWidth?: number;
    readonly strokeDasharray?: string;
    readonly strokeDashoffset?: string;
    readonly cx?: number;
    readonly cy?: number;
    readonly r?: number;
    readonly x?: number;
    readonly y?: number;
    readonly width?: number;
    readonly height?: number;
    readonly children?: BoardChild | readonly BoardChild[];
  };
};

export type CaseClueInput = {
  readonly clueId: string;
  readonly factId: string;
  readonly label: string;
};

export type TimelineSpan = {
  readonly startMs: number;
  readonly endMs: number;
  readonly kind: BoundaryKind;
  readonly id?: string;
};

export type CaseBoardWindow = {
  readonly index: number;
  readonly startMs: number;
  readonly endMs: number;
  readonly nominalMs: number;
};

export type CaseBoardSpineInput = {
  readonly clues: readonly CaseClueInput[];
  readonly frame: number;
  readonly sceneId: string;
  readonly act?: 1 | 2 | 3;
  readonly isEndScreen?: boolean;
  readonly label?: string;
};

export type NormalizedClue = {
  readonly clueId: string;
  readonly factId: string;
  readonly label: string;
  readonly wordCount: number;
  readonly truncated: boolean;
};

export type SolvedCard = {
  readonly clueId: string;
  readonly factId: string;
  readonly label: string;
  readonly wordCount: number;
  readonly truncated: boolean;
  readonly row: number;
  readonly column: number;
  readonly rect: Rect;
  readonly caption: Rect;
  readonly pin: { readonly x: number; readonly y: number };
};

export type SolvedPin = {
  readonly clueId: string;
  readonly x: number;
  readonly restY: number;
  readonly y: number;
  readonly landFrame: number;
  readonly landed: boolean;
  readonly circle: Rect;
};

export type SolvedString = {
  readonly fromId: string;
  readonly toId: string;
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
  readonly draw: number;
  readonly length: number;
  readonly bounds: Rect;
};

export type PinThudTrigger = {
  readonly cue: typeof PIN_THUD_CUE;
  readonly sceneId: string;
  readonly frame: number;
};

export type PinThudCue = {
  readonly cue_id: string;
  readonly cue: string;
  readonly scene_id: string;
  readonly start_frame: number;
};

export type SolvedCaseBoard = {
  readonly motif: typeof MOTIF_COMPONENT;
  readonly act: 1 | 2 | 3 | null;
  readonly frame: number;
  readonly sceneId: string;
  readonly isEndScreen: boolean;
  readonly label?: string;
  readonly columns: number;
  readonly rows: typeof ROW_COUNT;
  readonly zoom: number;
  readonly cameraTransform: string;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly board: Rect;
  readonly cards: readonly SolvedCard[];
  readonly pins: readonly SolvedPin[];
  readonly strings: readonly SolvedString[];
  readonly triggers: readonly PinThudTrigger[];
  readonly cues: readonly PinThudCue[];
};

type DispatchShape = {
  readonly cues?: readonly {
    readonly cue_id?: string;
    readonly cue?: string;
    readonly scene_id?: string;
    readonly start_frame?: number;
  }[];
};

export function safeContentRect(): Rect {
  return {
    x: 0,
    y: SAFE_PADDING_TOP,
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT - SAFE_PADDING_TOP - SAFE_PADDING_BOTTOM,
  };
}

export function exclusionRect(): Rect {
  const width = FRAME_WIDTH * EXCLUSION_WIDTH_RATIO;
  const height = FRAME_HEIGHT * EXCLUSION_HEIGHT_RATIO;
  return {
    x: FRAME_WIDTH - width,
    y: FRAME_HEIGHT - height,
    width,
    height,
  };
}

export function columnCount(clueCount: number): number {
  if (!Number.isInteger(clueCount) || clueCount < MIN_CLUES || clueCount > MAX_CLUES) {
    throw new CaseBoardSpineError(
      "BOUNDED_16",
      `Bounded 16-Clue Corkboard Invariant: CaseBoardSpine renders ${MIN_CLUES}–${MAX_CLUES} clues, received ${clueCount}`,
    );
  }
  return Math.ceil(clueCount / ROW_COUNT);
}

export function pinLandFrame(index: number): number {
  if (!Number.isInteger(index) || index < 0 || index >= MAX_CLUES) {
    throw new CaseBoardSpineError("FRAME", "pin index is outside the 16-clue board");
  }
  return PIN_DROP_FRAMES + index * PIN_STAGGER_FRAMES;
}

export function easeOutCubic(t: number): number {
  const clamped = t < 0 ? 0 : t > 1 ? 1 : t;
  const inverse = 1 - clamped;
  return 1 - inverse * inverse * inverse;
}

export function resetProgress(frame: number): number {
  if (!Number.isInteger(frame) || frame < 0 || frame >= RESET_FRAMES) {
    throw new CaseBoardSpineError("FRAME", `frame must be an integer in 0..${RESET_FRAMES - 1}`);
  }
  return frame / (RESET_FRAMES - 1);
}

export function cameraZoom(frame: number): number {
  return ZOOM_START + (1 - ZOOM_START) * easeOutCubic(resetProgress(frame));
}

export function pinDropOffset(frame: number, index: number): number {
  const start = index * PIN_STAGGER_FRAMES;
  const land = pinLandFrame(index);
  if (frame >= land) return 0;
  if (frame <= start) return -PIN_DROP_PX;
  const t = (frame - start) / PIN_DROP_FRAMES;
  return -PIN_DROP_PX * (1 - easeOutCubic(t));
}

export function stringDrawProgress(frame: number, stringIndex: number): number {
  const start = pinLandFrame(stringIndex + 1);
  const end = start + STRING_DRAW_FRAMES;
  if (frame <= start) return 0;
  if (frame >= end) return 1;
  return (frame - start) / (end - start);
}

export function caseBoardWindow(index: number): CaseBoardWindow {
  if (!Number.isInteger(index) || index < 1) {
    throw new CaseBoardSpineError("WINDOW", "CaseBoardSpine window index starts at 1");
  }
  const nominalMs = WINDOW_NOMINAL_MS + (index - 1) * WINDOW_PERIOD_MS;
  return {
    index,
    startMs: nominalMs - WINDOW_FLEX_MS,
    endMs: nominalMs + WINDOW_FLEX_MS,
    nominalMs,
  };
}

export function resetShot(resetMs: number): { startMs: number; endMs: number; frames: number } {
  if (!Number.isInteger(resetMs) || resetMs < 0) {
    throw new CaseBoardSpineError("BOUNDARY", "reset start must be an integer millisecond >= 0");
  }
  return { startMs: resetMs, endMs: resetMs + RESET_MS, frames: RESET_FRAMES };
}

function fail(code: CaseBoardErrorCode, message: string): never {
  throw new CaseBoardSpineError(code, message);
}

function containsRect(outer: Rect, inner: Rect): boolean {
  const eps = 1e-6;
  return (
    inner.x >= outer.x - eps &&
    inner.y >= outer.y - eps &&
    inner.x + inner.width <= outer.x + outer.width + eps &&
    inner.y + inner.height <= outer.y + outer.height + eps
  );
}

function intersects(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

function circleRect(x: number, y: number, radius: number): Rect {
  return { x: x - radius, y: y - radius, width: radius * 2, height: radius * 2 };
}

function strokeBounds(x1: number, y1: number, x2: number, y2: number, stroke: number): Rect {
  const pad = stroke / 2;
  const x = Math.min(x1, x2) - pad;
  const y = Math.min(y1, y2) - pad;
  return {
    x,
    y,
    width: Math.abs(x2 - x1) + stroke,
    height: Math.abs(y2 - y1) + stroke,
  };
}

function clampLabel(label: string): { text: string; wordCount: number; truncated: boolean } {
  if (typeof label !== "string") fail("LABEL", "clue label must be a string");
  const words = label.trim().split(/\s+/).filter((word) => word.length > 0);
  if (words.length === 0) fail("LABEL", "clue label needs at least one word");
  if (words.length > MAX_LABEL_WORDS) {
    return { text: words.slice(0, MAX_LABEL_WORDS).join(" "), wordCount: MAX_LABEL_WORDS, truncated: true };
  }
  return { text: words.join(" "), wordCount: words.length, truncated: false };
}

function readId(value: string, code: CaseBoardErrorCode, name: string): string {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) {
    fail(code, `${name} must match ${ID_PATTERN.source}`);
  }
  return value;
}

function readClues(clues: readonly CaseClueInput[]): NormalizedClue[] {
  if (!Array.isArray(clues) || clues.length < MIN_CLUES || clues.length > MAX_CLUES) {
    fail(
      "BOUNDED_16",
      `Bounded 16-Clue Corkboard Invariant: CaseBoardSpine renders ${MIN_CLUES}–${MAX_CLUES} clues, received ${Array.isArray(clues) ? clues.length : "none"}`,
    );
  }
  const seen = new Set<string>();
  return clues.map((clue) => {
    if (clue === null || typeof clue !== "object") fail("CLUE", "each clue must be an object");
    const clueId = readId(clue.clueId, "CLUE", "clueId");
    if (seen.has(clueId)) fail("CLUE", `duplicate clueId ${clueId}`);
    seen.add(clueId);
    const factId = readId(clue.factId, "CLUE", "factId");
    const label = clampLabel(clue.label);
    return {
      clueId,
      factId,
      label: label.text,
      wordCount: label.wordCount,
      truncated: label.truncated,
    };
  });
}

function readAct(act: unknown): 1 | 2 | 3 | null {
  if (act === undefined) return null;
  if (act !== 1 && act !== 2 && act !== 3) fail("ACT", "act must be 1, 2, or 3");
  return act;
}

function boardRect(reserveBottom: boolean): Rect {
  const reserve = reserveBottom ? LABEL_SLOT_PX : 0;
  const x = BOARD_INSET;
  const y = SAFE_PADDING_TOP + BOARD_INSET;
  const bottom = FRAME_HEIGHT - SAFE_PADDING_BOTTOM - reserve - BOARD_INSET;
  const height = bottom - y;
  if (height <= 0) fail("UNCLIPPED", "safe-zone board height collapsed");
  return { x, y, width: FRAME_WIDTH - BOARD_INSET * 2, height };
}

function layoutCards(clues: readonly NormalizedClue[], board: Rect): SolvedCard[] {
  const columns = columnCount(clues.length);
  const cardWidth = (board.width - CARD_GAP_X * (columns - 1)) / columns;
  const cardHeight = (board.height - CARD_GAP_Y * (ROW_COUNT - 1)) / ROW_COUNT;
  if (cardWidth <= CAPTION_PAD * 2 || cardHeight <= CAPTION_H + PIN_INSET + CAPTION_PAD) {
    fail("UNCLIPPED", "polaroid cells collapsed inside the safe zone");
  }
  return clues.map((clue, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const rect = {
      x: board.x + column * (cardWidth + CARD_GAP_X),
      y: board.y + row * (cardHeight + CARD_GAP_Y),
      width: cardWidth,
      height: cardHeight,
    };
    const caption = {
      x: rect.x + CAPTION_PAD,
      y: rect.y + rect.height - CAPTION_PAD - CAPTION_H,
      width: rect.width - CAPTION_PAD * 2,
      height: CAPTION_H,
    };
    return {
      clueId: clue.clueId,
      factId: clue.factId,
      label: clue.label,
      wordCount: clue.wordCount,
      truncated: clue.truncated,
      row,
      column,
      rect,
      caption,
      pin: { x: rect.x + rect.width / 2, y: rect.y + PIN_INSET },
    };
  });
}

function interior(span: TimelineSpan, timeMs: number): boolean {
  return span.startMs < timeMs && timeMs < span.endMs;
}

function readSpans(spans: readonly TimelineSpan[]): TimelineSpan[] {
  if (!Array.isArray(spans)) fail("BOUNDARY", "timeline spans must be an array");
  return spans.map((span) => {
    if (span === null || typeof span !== "object") fail("BOUNDARY", "each span must be an object");
    if (!Number.isInteger(span.startMs) || !Number.isInteger(span.endMs) || span.endMs <= span.startMs) {
      fail("BOUNDARY", "span startMs and endMs must be integers with endMs > startMs");
    }
    if (!BOUNDARY_KINDS.includes(span.kind)) fail("BOUNDARY", "span kind must be scene, sentence, or call");
    if (span.id !== undefined) readId(span.id, "BOUNDARY", "span id");
    return span;
  });
}

function legalBoundary(spans: readonly TimelineSpan[], timeMs: number, window: CaseBoardWindow): boolean {
  if (timeMs < window.startMs || timeMs > window.endMs) return false;
  if (!spans.some((span) => span.endMs === timeMs)) return false;
  return !spans.some((span) => interior(span, timeMs));
}

/**
 * Place the 5-second reset on a completed scene, sentence, or call end inside
 * the 210–270s window (and each later 240s ± 30s window). A nominal 4:00 that
 * falls inside a 911 call snaps to that call's end instead of chopping it.
 */
export function snapCaseBoardReset(spans: readonly TimelineSpan[], windowIndex = 1): number {
  const window = caseBoardWindow(windowIndex);
  const read = readSpans(spans);
  const covering = read.filter((span) => interior(span, window.nominalMs));
  if (covering.length > 0) {
    const outerEnd = covering.reduce((latest, span) => Math.max(latest, span.endMs), covering[0]?.endMs ?? window.nominalMs);
    if (!legalBoundary(read, outerEnd, window)) {
      fail(
        "BOUNDARY",
        `nominal ${window.nominalMs}ms is inside a span that does not finish inside ${window.startMs}–${window.endMs}ms`,
      );
    }
    return outerEnd;
  }
  const ends: number[] = [];
  for (const span of read) {
    if (legalBoundary(read, span.endMs, window) && !ends.includes(span.endMs)) ends.push(span.endMs);
  }
  if (ends.length === 0) {
    fail("BOUNDARY", `no completed boundary inside ${window.startMs}–${window.endMs}ms`);
  }
  ends.sort((left, right) => {
    const distance = Math.abs(left - window.nominalMs) - Math.abs(right - window.nominalMs);
    if (distance !== 0) return distance;
    return right - left;
  });
  const chosen = ends[0];
  if (chosen === undefined) fail("BOUNDARY", "completed boundary list was empty");
  return chosen;
}

function assertUnclipped(content: Rect, exclusion: Rect, cards: readonly SolvedCard[], pins: readonly SolvedPin[], strings: readonly SolvedString[], board: Rect): void {
  if (!containsRect(content, board)) fail("UNCLIPPED", "corkboard leaves the safe zone");
  if (intersects(board, exclusion)) fail("UNCLIPPED", "corkboard enters the bottom-right exclusion");
  for (const card of cards) {
    if (!containsRect(content, card.rect) || !containsRect(card.rect, card.caption)) {
      fail("UNCLIPPED", `${card.clueId} polaroid leaves the safe zone`);
    }
    if (intersects(card.rect, exclusion)) fail("UNCLIPPED", `${card.clueId} polaroid enters the exclusion`);
    const pinHead = circleRect(card.pin.x, card.pin.y, PIN_RADIUS);
    if (!containsRect(content, pinHead)) fail("UNCLIPPED", `${card.clueId} pin leaves the safe zone`);
  }
  for (const pin of pins) {
    if (!containsRect(content, pin.circle)) fail("UNCLIPPED", `${pin.clueId} pin drop leaves the safe zone`);
  }
  for (const thread of strings) {
    if (!containsRect(content, thread.bounds) || intersects(thread.bounds, exclusion)) {
      fail("UNCLIPPED", `string ${thread.fromId}->${thread.toId} leaves the safe zone`);
    }
  }
  for (let i = 0; i < cards.length; i += 1) {
    const left = cards[i];
    if (!left) continue;
    for (let j = i + 1; j < cards.length; j += 1) {
      const right = cards[j];
      if (right && intersects(left.rect, right.rect)) {
        fail("UNCLIPPED", `${left.clueId} overlaps ${right.clueId}`);
      }
    }
  }
}

function readCues(value: unknown, sceneId: string): PinThudCue[] {
  const dispatched = value as DispatchShape;
  if (!dispatched || !Array.isArray(dispatched.cues)) {
    fail("SFX", "dispatchMicroSfx did not return cues");
  }
  return dispatched.cues.map((cue) => {
    const start = cue.start_frame;
    if (!Number.isInteger(start) || typeof cue.cue !== "string" || typeof cue.scene_id !== "string") {
      fail("SFX", "dispatchMicroSfx returned a cue without cue, scene_id, and start_frame");
    }
    return {
      cue_id: typeof cue.cue_id === "string" ? cue.cue_id : `${sceneId}:${cue.cue}:${start}`,
      cue: cue.cue,
      scene_id: cue.scene_id,
      start_frame: start,
    };
  });
}

export function solveCaseBoardSpine(input: CaseBoardSpineInput): SolvedCaseBoard {
  if (input === null || typeof input !== "object") fail("SCENE", "CaseBoardSpine input must be an object");
  const sceneId = readId(input.sceneId, "SCENE", "sceneId");
  const frame = input.frame;
  resetProgress(frame);
  const clues = readClues(input.clues);
  const act = readAct(input.act);
  const isEndScreen = input.isEndScreen === true;
  const label = input.label;
  if (label !== undefined && typeof label !== "string") fail("LABEL", "board label must be a string");
  const content = safeContentRect();
  const exclusion = exclusionRect();
  const board = boardRect(isEndScreen || label !== undefined);
  const cards = layoutCards(clues, board);
  const zoom = cameraZoom(frame);
  const originX = content.x + content.width / 2;
  const originY = content.y + content.height / 2;
  const pins: SolvedPin[] = cards.map((card, index) => {
    const landFrame = pinLandFrame(index);
    const y = card.pin.y + pinDropOffset(frame, index);
    return {
      clueId: card.clueId,
      x: card.pin.x,
      restY: card.pin.y,
      y,
      landFrame,
      landed: frame >= landFrame,
      circle: circleRect(card.pin.x, y, PIN_RADIUS),
    };
  });
  const strings: SolvedString[] = [];
  for (let index = 0; index < cards.length - 1; index += 1) {
    const from = cards[index];
    const to = cards[index + 1];
    if (!from || !to) continue;
    const draw = stringDrawProgress(frame, index);
    const length = Math.hypot(to.pin.x - from.pin.x, to.pin.y - from.pin.y);
    strings.push({
      fromId: from.clueId,
      toId: to.clueId,
      x1: from.pin.x,
      y1: from.pin.y,
      x2: to.pin.x,
      y2: to.pin.y,
      draw,
      length,
      bounds: strokeBounds(from.pin.x, from.pin.y, to.pin.x, to.pin.y, STRING_STROKE),
    });
  }
  assertUnclipped(content, exclusion, cards, pins, strings, board);
  const triggers: PinThudTrigger[] = [];
  for (let index = 0; index < cards.length; index += 1) {
    triggers.push({ cue: PIN_THUD_CUE, sceneId, frame: pinLandFrame(index) });
  }
  const cues = readCues(dispatchMicroSfx(triggers, { clock: REMOTION_CLOCK }), sceneId);
  const solved: SolvedCaseBoard = {
    motif: MOTIF_COMPONENT,
    act,
    frame,
    sceneId,
    isEndScreen,
    columns: columnCount(cards.length),
    rows: ROW_COUNT,
    zoom,
    cameraTransform: `translate(${originX} ${originY}) scale(${formatPx(zoom)}) translate(${-originX} ${-originY})`,
    content,
    exclusion,
    board,
    cards,
    pins,
    strings,
    triggers,
    cues,
  };
  if (label !== undefined) return { ...solved, label };
  return solved;
}

function formatPx(value: number): string {
  const rounded = Object.is(value, -0) ? 0 : Math.round(value * 1000) / 1000;
  return Object.is(rounded, -0) ? "0" : String(rounded);
}

function element(type: string, dataset: Record<string, string>, props: BoardNode["props"]): BoardNode {
  return { type, dataset, props };
}

function renderBoard(solved: SolvedCaseBoard): BoardNode {
  const cards = solved.cards.map((card) =>
    element(
      "g",
      {
        clue: card.clueId,
        fact: card.factId,
        row: String(card.row),
        column: String(card.column),
        truncated: card.truncated ? "true" : "false",
        words: String(card.wordCount),
      },
      {
        children: [
          element("rect", { part: "polaroid" }, {
            x: card.rect.x,
            y: card.rect.y,
            width: card.rect.width,
            height: card.rect.height,
            fill: POLAROID_FILL,
            stroke: POLAROID_STROKE,
            strokeWidth: 2,
          }),
          element("rect", { part: "photo" }, {
            x: card.rect.x + CAPTION_PAD,
            y: card.rect.y + PIN_INSET + PIN_RADIUS,
            width: card.rect.width - CAPTION_PAD * 2,
            height: Math.max(0, card.caption.y - (card.rect.y + PIN_INSET + PIN_RADIUS) - 4),
            fill: PHOTO_FILL,
          }),
          element("text", { part: "caption" }, {
            x: card.caption.x,
            y: card.caption.y,
            width: card.caption.width,
            height: card.caption.height,
            fill: CAPTION_FILL,
            style: { overflow: "hidden" },
            children: card.label,
          }),
        ],
      },
    ),
  );
  const threads = solved.strings.map((thread) =>
    element("path", {
      string: `${thread.fromId}-${thread.toId}`,
      from: thread.fromId,
      to: thread.toId,
      draw: formatPx(thread.draw),
      crimson: EVIDENCE_CRIMSON,
    }, {
      d: `M ${formatPx(thread.x1)} ${formatPx(thread.y1)} L ${formatPx(thread.x2)} ${formatPx(thread.y2)}`,
      fill: "none",
      stroke: EVIDENCE_CRIMSON,
      strokeWidth: STRING_STROKE,
      strokeDasharray: `${formatPx(thread.length)} ${formatPx(thread.length)}`,
      strokeDashoffset: formatPx(thread.length * (1 - thread.draw)),
    }),
  );
  const pins = solved.pins.map((pin) =>
    element("circle", {
      pin: pin.clueId,
      landed: pin.landed ? "true" : "false",
      "land-frame": String(pin.landFrame),
    }, {
      cx: pin.x,
      cy: pin.y,
      r: PIN_RADIUS,
      fill: PIN_FILL,
    }),
  );
  const cueFrames = solved.cues.map((cue) => String(cue.start_frame)).join(",");
  return element(
    "g",
    {
      motif: MOTIF_COMPONENT,
      "motif-number": String(MOTIF_NUMBER),
      owner: MOTIF_OWNER,
      act: solved.act === null ? "" : String(solved.act),
      scene: solved.sceneId,
      "apply-grade": "true",
      "needs-grade": "true",
      "clue-count": String(solved.cards.length),
      columns: String(solved.columns),
      rows: String(solved.rows),
      zoom: formatPx(solved.zoom),
      "pin-thud-count": String(solved.cues.length),
      "pin-thud-frames": cueFrames,
      "bounded-clues": String(MAX_CLUES),
    },
    {
      children: [
        element("rect", { layer: "cork" }, {
          x: solved.board.x,
          y: solved.board.y,
          width: solved.board.width,
          height: solved.board.height,
          fill: CORK_FILL,
        }),
        element("g", { layer: "camera" }, {
          transform: solved.cameraTransform,
          children: [
            element("g", { layer: "cards" }, { children: cards }),
            element("g", { layer: "strings" }, { children: threads }),
            element("g", { layer: "pins" }, { children: pins }),
          ],
        }),
      ],
    },
  );
}

export function CaseBoardSpine(input: CaseBoardSpineInput): BoardNode {
  const solved = solveCaseBoardSpine(input);
  const content = renderBoard(solved);
  if (solved.label !== undefined) {
    return SafeZoneLayout({ isEndScreen: solved.isEndScreen, label: solved.label, children: content }) as BoardNode;
  }
  return SafeZoneLayout({ isEndScreen: solved.isEndScreen, children: content }) as BoardNode;
}
