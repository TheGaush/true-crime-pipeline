/**
 * MVP motif #3 — RedactedDocReveal.
 *
 * Aged court-filing sheet at 1920×1080 @ 30 fps: black redaction bars, a
 * citation badge, and a yellow highlighter that sweeps one `<mark>` rect per
 * wrapped line in reading order. The sweep clock is `word_timestamps[]`.
 * Each new line schedules a `highlighter_glide` cue (280 ms, 60 ms cooldown).
 *
 * The sheet sits in the catalog safe zone (top 108 px, bottom 194 px) with
 * overflow hidden, so a wrapped quote cannot enter the caption bar or the
 * bottom-right 22% × 14% exclusion. Task 101's `<SafeZoneLayout>` and Task
 * 110's dispatcher are not on this branch and are not copied here.
 *
 * Remotion paints the sheet flat. No paper grain, vignette, or SVG turbulence.
 */

export const MOTIF_COMPONENT = "RedactedDocReveal";
export const FPS = 30;
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const SAFE_PADDING_TOP_PX = 108;
export const SAFE_PADDING_BOTTOM_PX = 194;
export const SAFE_HEIGHT_PX = FRAME_HEIGHT - SAFE_PADDING_TOP_PX - SAFE_PADDING_BOTTOM_PX;
export const EXCLUSION_WIDTH_RATIO = 0.22;
export const EXCLUSION_HEIGHT_RATIO = 0.14;

export const CHAR_WIDTH_PX = 18;
export const DEFAULT_COLUMN_WIDTH_PX = 640;
export const LINE_HEIGHT_PX = 48;
export const MARK_HEIGHT_PX = 40;

export const HIGHLIGHTER_HEX = "#F3E37A";
export const REDACTION_HEX = "#000000";
export const PAPER_HEX = "#E4D2AE";
export const INK_HEX = "#1C1915";
export const RULE_HEX = "#8A7353";
export const BADGE_BG_HEX = "#2A241C";
export const BADGE_INK_HEX = "#F4EFE6";

export const HIGHLIGHTER_GLIDE = "highlighter_glide";
export const HIGHLIGHTER_GLIDE_DURATION_MS = 280;
export const HIGHLIGHTER_GLIDE_COOLDOWN_MS = 60;

export const SHEET_INSET_X = 72;
export const SHEET_INSET_Y = 28;
export const SHEET_PAD_PX = 32;
export const CAPTION_HEIGHT_PX = 44;
export const CAPTION_GAP_PX = 16;
export const BAR_HEIGHT_PX = 28;
export const BAR_GAP_PX = 12;
export const QUOTE_GAP_PX = 16;
export const CITATION_HEIGHT_PX = 64;
export const MAX_AFFIDAVIT_BARS = 4;
export const MAX_QUOTE_TOKENS = 80;
export const MAX_SCENE_START_MS = 7_200_000;
export const MAX_FRAME = 216_000;
export const FILING_CAPTION = "COURT FILING";

const REACT_ELEMENT = Symbol.for("react.element");
const SCENE_ID = /^[A-Za-z0-9_-]+$/;

export class RedactedDocError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RedactedDocError";
  }
}

export type DocStyle = Readonly<Record<string, string | number>>;

export type DocChild = DocElement | string;

export type DocElement = {
  readonly $$typeof: symbol;
  readonly type: "div" | "mark" | "span";
  readonly key: string | null;
  readonly ref: null;
  readonly props: {
    readonly style: DocStyle;
    readonly children?: DocChild | readonly DocChild[];
  } & Readonly<Record<string, unknown>>;
};

export type WordStamp = {
  readonly word: string;
  readonly start_ms: number;
  readonly end_ms: number;
};

export type QuoteRedaction = {
  readonly startWord: number;
  readonly endWord: number;
};

export type RedactedDocRevealProps = {
  readonly citation: string;
  readonly quote: string;
  readonly wordTimestamps: readonly WordStamp[];
  readonly sceneStartMs: number;
  readonly frame: number;
  readonly sceneId: string;
  readonly isEndScreen?: boolean;
  readonly affidavitBarCount?: number;
  readonly quoteRedactions?: readonly QuoteRedaction[];
  readonly columnWidthPx?: number;
};

export type FrameRect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type LaidWord = {
  readonly index: number;
  readonly word: string;
  readonly line: number;
  readonly xPx: number;
  readonly widthPx: number;
  readonly start_ms: number;
  readonly end_ms: number;
  readonly redacted: boolean;
  readonly frame: FrameRect;
};

export type LaidLine = {
  readonly index: number;
  readonly words: readonly LaidWord[];
  readonly textWidthPx: number;
  readonly frame: FrameRect;
};

export type SweepPhase = "pending" | "partial" | "full";

export type MarkRect = {
  readonly line: number;
  readonly widthPx: number;
  readonly sweep: SweepPhase;
  readonly frame: FrameRect;
};

export type RedactionRect = {
  readonly kind: "affidavit" | "quote";
  readonly line: number | null;
  readonly frame: FrameRect;
};

export type GlideCue = {
  readonly cue: typeof HIGHLIGHTER_GLIDE;
  readonly cue_id: string;
  readonly scene_id: string;
  readonly offset_ms: number;
  readonly line: number;
  readonly duration_ms: typeof HIGHLIGHTER_GLIDE_DURATION_MS;
  readonly cooldown_ms: typeof HIGHLIGHTER_GLIDE_COOLDOWN_MS;
};

export type SolvedRedactedDoc = {
  readonly nowMs: number;
  readonly citation: string;
  readonly sceneId: string;
  readonly isEndScreen: boolean;
  readonly columnWidthPx: number;
  readonly safe: FrameRect;
  readonly sheet: FrameRect;
  readonly caption: FrameRect;
  readonly citationFrame: FrameRect;
  readonly lines: readonly LaidLine[];
  readonly marks: readonly MarkRect[];
  readonly redactions: readonly RedactionRect[];
  readonly cues: readonly GlideCue[];
  readonly suppressed: readonly GlideCue[];
};

export type RedactedDocRevealNode = DocElement & {
  readonly solved: SolvedRedactedDoc;
};

export function safeZoneRect(): FrameRect {
  return { x: 0, y: SAFE_PADDING_TOP_PX, width: FRAME_WIDTH, height: SAFE_HEIGHT_PX };
}

export function exclusionRect(): FrameRect {
  const width = FRAME_WIDTH * EXCLUSION_WIDTH_RATIO;
  const height = FRAME_HEIGHT * EXCLUSION_HEIGHT_RATIO;
  return { x: FRAME_WIDTH - width, y: FRAME_HEIGHT - height, width, height };
}

export function captionBarRect(): FrameRect {
  return { x: 0, y: FRAME_HEIGHT - SAFE_PADDING_BOTTOM_PX, width: FRAME_WIDTH, height: SAFE_PADDING_BOTTOM_PX };
}

export function timelineMs(sceneStartMs: number, frame: number): number {
  return sceneStartMs + Math.floor((frame * 1000) / FPS);
}

/** 0 before the word, 1 at `end_ms`, linear between. */
export function wordProgress(startMs: number, endMs: number, nowMs: number): number {
  if (nowMs <= startMs) return 0;
  if (nowMs >= endMs) return 1;
  return (nowMs - startMs) / (endMs - startMs);
}

export function lineTextWidthPx(words: readonly { widthPx: number }[]): number {
  if (words.length === 0) return 0;
  let width = 0;
  for (let index = 0; index < words.length; index += 1) {
    const word = words[index];
    if (!word) continue;
    width += word.widthPx;
    if (index < words.length - 1) width += CHAR_WIDTH_PX;
  }
  return width;
}

/**
 * Highlighter distance from the left of a line.
 * A finished word includes the gap before the next word. Later words stay
 * dark until earlier words on this line have finished, so the rect sweeps
 * left to right instead of lighting tokens out of order.
 */
export function lineSweepWidthPx(
  words: readonly { widthPx: number; start_ms: number; end_ms: number }[],
  nowMs: number,
): number {
  let cursor = 0;
  let width = 0;
  for (let index = 0; index < words.length; index += 1) {
    const word = words[index];
    if (!word) continue;
    const progress = wordProgress(word.start_ms, word.end_ms, nowMs);
    if (progress <= 0) break;
    if (progress >= 1) {
      cursor += word.widthPx;
      if (index < words.length - 1) cursor += CHAR_WIDTH_PX;
      width = cursor;
      continue;
    }
    width = cursor + progress * word.widthPx;
    break;
  }
  return width;
}

export function tokenizeQuote(quote: string): string[] {
  if (typeof quote !== "string" || quote.trim().length === 0) {
    throw new RedactedDocError("quote must be a non-empty string");
  }
  if (quote !== quote.trim() || /\s{2,}/.test(quote) || /[\r\n\t]/.test(quote)) {
    throw new RedactedDocError("quote must be single-spaced tokens without a leading or trailing space");
  }
  const tokens = quote.split(" ");
  if (tokens.length > MAX_QUOTE_TOKENS) {
    throw new RedactedDocError(`quote must contain at most ${MAX_QUOTE_TOKENS} words`);
  }
  for (const token of tokens) {
    if (token.length === 0 || token.length > 80) {
      throw new RedactedDocError("each quote word must be 1 to 80 characters");
    }
  }
  return tokens;
}

export function wrapQuoteTokens(tokens: readonly string[], columnWidthPx: number): string[][] {
  const maxChars = Math.floor(columnWidthPx / CHAR_WIDTH_PX);
  if (maxChars < 1) throw new RedactedDocError("columnWidthPx cannot hold a character");
  const lines: string[][] = [];
  let current: string[] = [];
  let chars = 0;
  for (const token of tokens) {
    if (token.length > maxChars) {
      throw new RedactedDocError(`word ${JSON.stringify(token)} is wider than the quote column`);
    }
    const next = chars === 0 ? token.length : chars + 1 + token.length;
    if (current.length > 0 && next > maxChars) {
      lines.push(current);
      current = [token];
      chars = token.length;
    } else {
      current.push(token);
      chars = next;
    }
  }
  if (current.length > 0) lines.push(current);
  if (lines.length === 0) throw new RedactedDocError("quote produced no lines");
  return lines;
}

export function RedactedDocReveal(props: RedactedDocRevealProps): RedactedDocRevealNode {
  const solved = solveRedactedDoc(props);
  const root = renderSolved(solved);
  return { ...root, solved };
}

export function solveRedactedDoc(props: RedactedDocRevealProps): SolvedRedactedDoc {
  const citation = requireCitation(props.citation);
  const sceneId = requireSceneId(props.sceneId);
  const sceneStartMs = requireSceneStart(props.sceneStartMs);
  const frame = requireFrame(props.frame);
  const isEndScreen = requireEndScreen(props.isEndScreen);
  const barCount = props.affidavitBarCount === undefined ? 2 : requireBarCount(props.affidavitBarCount);
  const tokens = tokenizeQuote(props.quote);
  const stamps = requireStamps(props.wordTimestamps, tokens);
  const redactionIndexes = requireRedactions(props.quoteRedactions, tokens.length);
  const columnWidthPx = props.columnWidthPx === undefined ? DEFAULT_COLUMN_WIDTH_PX : requireColumn(props.columnWidthPx);
  const wrapped = wrapQuoteTokens(tokens, columnWidthPx);
  const nowMs = timelineMs(sceneStartMs, frame);

  const safe = safeZoneRect();
  const sheet: FrameRect = {
    x: SHEET_INSET_X,
    y: safe.y + SHEET_INSET_Y,
    width: FRAME_WIDTH - SHEET_INSET_X * 2,
    height: safe.height - SHEET_INSET_Y * 2,
  };
  const innerX = sheet.x + SHEET_PAD_PX;
  const innerY = sheet.y + SHEET_PAD_PX;
  const innerW = sheet.width - SHEET_PAD_PX * 2;
  const innerBottom = sheet.y + sheet.height - SHEET_PAD_PX;
  if (columnWidthPx > innerW) {
    throw new RedactedDocError("columnWidthPx leaves the filing sheet");
  }

  const caption: FrameRect = { x: innerX, y: innerY, width: innerW, height: CAPTION_HEIGHT_PX };
  let cursorY = innerY + CAPTION_HEIGHT_PX + CAPTION_GAP_PX;
  const redactions: RedactionRect[] = [];
  for (let index = 0; index < barCount; index += 1) {
    const frameRect: FrameRect = { x: innerX, y: cursorY, width: columnWidthPx, height: BAR_HEIGHT_PX };
    redactions.push({ kind: "affidavit", line: null, frame: frameRect });
    cursorY += BAR_HEIGHT_PX + BAR_GAP_PX;
  }
  if (barCount > 0) cursorY += QUOTE_GAP_PX - BAR_GAP_PX;

  const citationFrame: FrameRect = {
    x: innerX,
    y: innerBottom - CITATION_HEIGHT_PX,
    width: innerW,
    height: CITATION_HEIGHT_PX,
  };
  const quoteTop = cursorY;
  const quoteBottom = citationFrame.y - QUOTE_GAP_PX;
  const available = quoteBottom - quoteTop;
  if (wrapped.length * LINE_HEIGHT_PX > available) {
    throw new RedactedDocError("wrapped quote leaves the safe zone");
  }
  if (citation.length * CHAR_WIDTH_PX > innerW - 28) {
    throw new RedactedDocError("citation does not fit the badge");
  }

  const redacted = new Set(redactionIndexes);
  const lines: LaidLine[] = [];
  let wordIndex = 0;
  for (let lineIndex = 0; lineIndex < wrapped.length; lineIndex += 1) {
    const lineTokens = wrapped[lineIndex];
    if (!lineTokens) continue;
    const lineY = quoteTop + lineIndex * LINE_HEIGHT_PX;
    const words: LaidWord[] = [];
    let xPx = 0;
    for (let local = 0; local < lineTokens.length; local += 1) {
      const token = lineTokens[local];
      const stamp = stamps[wordIndex];
      if (!token || !stamp) throw new RedactedDocError("quote line lost a word");
      const widthPx = token.length * CHAR_WIDTH_PX;
      const word: LaidWord = {
        index: wordIndex,
        word: token,
        line: lineIndex,
        xPx,
        widthPx,
        start_ms: stamp.start_ms,
        end_ms: stamp.end_ms,
        redacted: redacted.has(wordIndex),
        frame: { x: innerX + xPx, y: lineY, width: widthPx, height: LINE_HEIGHT_PX },
      };
      words.push(word);
      xPx += widthPx;
      if (local < lineTokens.length - 1) xPx += CHAR_WIDTH_PX;
      wordIndex += 1;
    }
    lines.push({
      index: lineIndex,
      words,
      textWidthPx: lineTextWidthPx(words),
      frame: { x: innerX, y: lineY, width: columnWidthPx, height: LINE_HEIGHT_PX },
    });
  }
  if (wordIndex !== tokens.length) throw new RedactedDocError("quote line lost a word");

  const marks: MarkRect[] = [];
  let previousFull = true;
  for (const line of lines) {
    const last = line.words[line.words.length - 1];
    if (!last) throw new RedactedDocError("quote line is empty");
    const swept = previousFull ? lineSweepWidthPx(line.words, nowMs) : 0;
    const full = previousFull && nowMs >= last.end_ms;
    const widthPx = full ? line.textWidthPx : swept;
    const sweep: SweepPhase = full ? "full" : widthPx <= 0 ? "pending" : "partial";
    const markInset = (LINE_HEIGHT_PX - MARK_HEIGHT_PX) / 2;
    marks.push({
      line: line.index,
      widthPx,
      sweep,
      frame: {
        x: line.frame.x,
        y: line.frame.y + markInset,
        width: widthPx,
        height: MARK_HEIGHT_PX,
      },
    });
    if (!full) previousFull = false;
  }

  for (const line of lines) {
    let run: LaidWord[] = [];
    const flush = (): void => {
      const first = run[0];
      const last = run[run.length - 1];
      if (!first || !last) {
        run = [];
        return;
      }
      redactions.push({
        kind: "quote",
        line: line.index,
        frame: {
          x: first.frame.x,
          y: line.frame.y,
          width: last.frame.x + last.frame.width - first.frame.x,
          height: LINE_HEIGHT_PX,
        },
      });
      run = [];
    };
    for (const word of line.words) {
      if (!word.redacted) {
        flush();
        continue;
      }
      run.push(word);
    }
    flush();
  }

  const { cues, suppressed } = glideCues(lines, sceneId);
  const solved: SolvedRedactedDoc = {
    nowMs,
    citation,
    sceneId,
    isEndScreen,
    columnWidthPx,
    safe,
    sheet,
    caption,
    citationFrame,
    lines,
    marks,
    redactions,
    cues,
    suppressed,
  };
  assertContained(solved);
  return solved;
}

function glideCues(lines: readonly LaidLine[], sceneId: string): { cues: GlideCue[]; suppressed: GlideCue[] } {
  const cues: GlideCue[] = [];
  const suppressed: GlideCue[] = [];
  let lastEmitted: number | null = null;
  for (const line of lines) {
    const first = line.words[0];
    if (!first) continue;
    const cue: GlideCue = {
      cue: HIGHLIGHTER_GLIDE,
      cue_id: `${sceneId}:${HIGHLIGHTER_GLIDE}:${first.start_ms}:line${line.index}`,
      scene_id: sceneId,
      offset_ms: first.start_ms,
      line: line.index,
      duration_ms: HIGHLIGHTER_GLIDE_DURATION_MS,
      cooldown_ms: HIGHLIGHTER_GLIDE_COOLDOWN_MS,
    };
    if (lastEmitted !== null && cue.offset_ms - lastEmitted < HIGHLIGHTER_GLIDE_COOLDOWN_MS) {
      suppressed.push(cue);
      continue;
    }
    cues.push(cue);
    lastEmitted = cue.offset_ms;
  }
  return { cues, suppressed };
}

function assertContained(solved: SolvedRedactedDoc): void {
  const exclusion = exclusionRect();
  const captionBar = captionBarRect();
  const boxes = [
    solved.sheet,
    solved.caption,
    solved.citationFrame,
    ...solved.lines.map((line) => line.frame),
    ...solved.marks.map((mark) => mark.frame),
    ...solved.redactions.map((bar) => bar.frame),
    ...solved.lines.flatMap((line) => line.words.map((word) => word.frame)),
  ];
  for (const box of boxes) {
    if (!rectContains(solved.safe, box)) {
      throw new RedactedDocError("mark or bar leaves the safe zone");
    }
    if (rectOverlaps(box, exclusion) || rectOverlaps(box, captionBar)) {
      throw new RedactedDocError("mark or bar enters a YouTube exclusion");
    }
  }
  if (rectOverlaps(solved.sheet, exclusion) || rectOverlaps(solved.sheet, captionBar)) {
    throw new RedactedDocError("filing sheet enters a YouTube exclusion");
  }
  for (const mark of solved.marks) {
    if (rectOverlaps(mark.frame, solved.citationFrame)) {
      throw new RedactedDocError("highlighter overlaps the citation badge");
    }
  }
}

function rectContains(outer: FrameRect, inner: FrameRect): boolean {
  return (
    inner.width >= 0 &&
    inner.height >= 0 &&
    inner.x >= outer.x - 1e-6 &&
    inner.y >= outer.y - 1e-6 &&
    inner.x + inner.width <= outer.x + outer.width + 1e-6 &&
    inner.y + inner.height <= outer.y + outer.height + 1e-6
  );
}

function rectOverlaps(left: FrameRect, right: FrameRect): boolean {
  return (
    left.x < right.x + right.width &&
    left.x + left.width > right.x &&
    left.y < right.y + right.height &&
    left.y + left.height > right.y
  );
}

function requireCitation(citation: unknown): string {
  if (typeof citation !== "string" || citation.trim().length === 0 || citation !== citation.trim()) {
    throw new RedactedDocError("citation must be a non-empty trimmed string");
  }
  if (citation.length > 300 || /[\r\n\t]/.test(citation)) {
    throw new RedactedDocError("citation must be one line of at most 300 characters");
  }
  return citation;
}

function requireSceneId(sceneId: unknown): string {
  if (typeof sceneId !== "string" || !SCENE_ID.test(sceneId) || sceneId.length > 128) {
    throw new RedactedDocError("sceneId must match ^[A-Za-z0-9_-]+$ and be at most 128 characters");
  }
  return sceneId;
}

function requireSceneStart(sceneStartMs: unknown): number {
  if (typeof sceneStartMs !== "number" || !Number.isInteger(sceneStartMs) || sceneStartMs < 0 || sceneStartMs > MAX_SCENE_START_MS) {
    throw new RedactedDocError(`sceneStartMs must be an integer from 0 to ${MAX_SCENE_START_MS}`);
  }
  return sceneStartMs;
}

function requireFrame(frame: unknown): number {
  if (typeof frame !== "number" || !Number.isInteger(frame) || frame < 0 || frame > MAX_FRAME) {
    throw new RedactedDocError(`frame must be an integer from 0 to ${MAX_FRAME}`);
  }
  return frame;
}

function requireEndScreen(isEndScreen: unknown): boolean {
  if (isEndScreen === undefined) return false;
  if (isEndScreen === true || isEndScreen === false) return isEndScreen;
  throw new RedactedDocError("isEndScreen must be true or false");
}

function requireBarCount(count: unknown): number {
  if (typeof count !== "number" || !Number.isInteger(count) || count < 0 || count > MAX_AFFIDAVIT_BARS) {
    throw new RedactedDocError(`affidavitBarCount must be an integer from 0 to ${MAX_AFFIDAVIT_BARS}`);
  }
  return count;
}

function requireColumn(columnWidthPx: unknown): number {
  if (typeof columnWidthPx !== "number" || !Number.isInteger(columnWidthPx) || columnWidthPx < CHAR_WIDTH_PX) {
    throw new RedactedDocError(`columnWidthPx must be an integer >= ${CHAR_WIDTH_PX}`);
  }
  return columnWidthPx;
}

function requireStamps(stamps: readonly WordStamp[], tokens: readonly string[]): WordStamp[] {
  if (!Array.isArray(stamps)) throw new RedactedDocError("wordTimestamps must be an array");
  if (stamps.length !== tokens.length) {
    throw new RedactedDocError("wordTimestamps must align one-to-one with the quote");
  }
  const aligned: WordStamp[] = [];
  for (let index = 0; index < stamps.length; index += 1) {
    const stamp = stamps[index];
    const token = tokens[index];
    if (!stamp || typeof stamp !== "object" || token === undefined) {
      throw new RedactedDocError("wordTimestamps must align one-to-one with the quote");
    }
    if (stamp.word !== token) {
      throw new RedactedDocError(`wordTimestamps[${index}].word must equal the quote token`);
    }
    if (!Number.isInteger(stamp.start_ms) || !Number.isInteger(stamp.end_ms) || stamp.start_ms < 0 || stamp.end_ms > MAX_SCENE_START_MS) {
      throw new RedactedDocError("word timestamp milliseconds must be integers inside the timeline");
    }
    if (stamp.end_ms <= stamp.start_ms) {
      throw new RedactedDocError("word timestamp end_ms must be greater than start_ms");
    }
    const previous = aligned[index - 1];
    if (previous && stamp.start_ms < previous.end_ms) {
      throw new RedactedDocError("word timestamps must not overlap");
    }
    aligned.push({ word: stamp.word, start_ms: stamp.start_ms, end_ms: stamp.end_ms });
  }
  return aligned;
}

function requireRedactions(ranges: readonly QuoteRedaction[] | undefined, tokenCount: number): number[] {
  if (ranges === undefined) return [];
  if (!Array.isArray(ranges)) throw new RedactedDocError("quoteRedactions must be an array");
  const indexes: number[] = [];
  let previousEnd = 0;
  for (let index = 0; index < ranges.length; index += 1) {
    const range = ranges[index];
    if (!range || !Number.isInteger(range.startWord) || !Number.isInteger(range.endWord)) {
      throw new RedactedDocError("quote redaction bounds must be integers");
    }
    if (range.startWord < 0 || range.endWord > tokenCount || range.endWord <= range.startWord) {
      throw new RedactedDocError("quote redaction must cover at least one in-range word");
    }
    if (index > 0 && range.startWord < previousEnd) {
      throw new RedactedDocError("quote redactions must be sorted and must not overlap");
    }
    previousEnd = range.endWord;
    for (let word = range.startWord; word < range.endWord; word += 1) indexes.push(word);
  }
  return indexes;
}

function renderSolved(solved: SolvedRedactedDoc): DocElement {
  const flat = flatPaint();
  const lineNodes = solved.lines.map((line) => {
    const mark = solved.marks.find((item) => item.line === line.index);
    if (!mark) throw new RedactedDocError("missing highlighter mark");
    const children: DocElement[] = [
      element(
        "mark",
        `mark-${line.index}`,
        {
          slot: "mark",
          line: String(line.index),
          sweep: mark.sweep,
          "sweep-width": mark.widthPx.toFixed(4),
        },
        place(mark.frame, line.frame, {
          ...flat,
          backgroundColor: HIGHLIGHTER_HEX,
          overflow: "hidden",
        }),
      ),
    ];
    for (const word of line.words) {
      if (word.redacted) continue;
      children.push(
        element(
          "span",
          `word-${word.index}`,
          { slot: "word", line: String(line.index), index: String(word.index) },
          place(word.frame, line.frame, {
            ...flat,
            color: INK_HEX,
            fontSize: 32,
            lineHeight: 1.2,
            whiteSpace: "nowrap",
            overflow: "hidden",
          }),
          [word.word],
        ),
      );
    }
    for (const bar of solved.redactions) {
      if (bar.kind !== "quote" || bar.line !== line.index) continue;
      children.push(
        element(
          "div",
          `redact-${line.index}-${bar.frame.x}`,
          { slot: "redaction", kind: "quote", line: String(line.index) },
          place(bar.frame, line.frame, {
            ...flat,
            backgroundColor: REDACTION_HEX,
          }),
        ),
      );
    }
    return element(
      "div",
      `line-${line.index}`,
      { slot: "line", line: String(line.index) },
      place(line.frame, quoteOrigin(solved), { ...flat, overflow: "hidden" }),
      children,
    );
  });

  const quoteFrame: FrameRect = {
    x: solved.lines[0]?.frame.x ?? solved.sheet.x + SHEET_PAD_PX,
    y: solved.lines[0]?.frame.y ?? solved.citationFrame.y,
    width: solved.columnWidthPx,
    height: solved.lines.length * LINE_HEIGHT_PX,
  };

  const affidavit = solved.redactions.filter((bar) => bar.kind === "affidavit");
  const affidavitNodes = affidavit.map((bar, index) =>
    element(
      "div",
      `affidavit-${index}`,
      { slot: "redaction", kind: "affidavit", index: String(index) },
      place(bar.frame, solved.sheet, { ...flat, backgroundColor: REDACTION_HEX }),
    ),
  );

  const sheetChildren: DocElement[] = [
    element(
      "div",
      "caption",
      { slot: "caption" },
      place(solved.caption, solved.sheet, {
        ...flat,
        color: INK_HEX,
        fontSize: 28,
        fontWeight: 700,
        letterSpacing: "0.08em",
        lineHeight: 1.15,
        whiteSpace: "nowrap",
        overflow: "hidden",
      }),
      [FILING_CAPTION],
    ),
    element(
      "div",
      "rule",
      { slot: "rule" },
      place(
        {
          x: solved.caption.x,
          y: solved.caption.y + solved.caption.height - 3,
          width: solved.columnWidthPx,
          height: 2,
        },
        solved.sheet,
        { ...flat, backgroundColor: RULE_HEX },
      ),
    ),
    ...affidavitNodes,
    element(
      "div",
      "quote",
      { slot: "quote", lines: String(solved.lines.length) },
      place(quoteFrame, solved.sheet, { ...flat, overflow: "hidden" }),
      lineNodes,
    ),
    element(
      "div",
      "citation",
      { slot: "citation", badge: "citation" },
      place(solved.citationFrame, solved.sheet, {
        ...flat,
        backgroundColor: BADGE_BG_HEX,
        color: BADGE_INK_HEX,
        fontSize: 28,
        fontWeight: 700,
        lineHeight: 1.15,
        whiteSpace: "nowrap",
        overflow: "hidden",
        paddingLeft: 20,
        boxSizing: "border-box",
        display: "flex",
        alignItems: "center",
      }),
      [solved.citation],
    ),
  ];

  const sheet = element(
    "div",
    "sheet",
    { slot: "sheet", sheet: "aged-court-filing" },
    place(solved.sheet, solved.safe, {
      ...flat,
      backgroundColor: PAPER_HEX,
      overflow: "hidden",
      boxSizing: "border-box",
    }),
    sheetChildren,
  );

  const safe = element(
    "div",
    "safe",
    { slot: "safe", "safe-zone": "css-contained" },
    place(solved.safe, { x: 0, y: 0, width: FRAME_WIDTH, height: FRAME_HEIGHT }, {
      ...flat,
      overflow: "hidden",
    }),
    [sheet],
  );

  return element(
    "div",
    "redacted-doc-reveal",
    {
      motif: MOTIF_COMPONENT,
      fps: String(FPS),
      "safe-zone": "css-contained",
      "end-screen": solved.isEndScreen ? "true" : "false",
      citation: solved.citation,
      "scene-id": solved.sceneId,
      "now-ms": String(solved.nowMs),
      lines: String(solved.lines.length),
      "paper-grain": "0",
      vignette: "0",
      "apply-grade": "true",
      "highlighter-glide": HIGHLIGHTER_GLIDE,
      "glide-cues": String(solved.cues.length),
    },
    {
      ...flat,
      position: "relative",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      overflow: "hidden",
      boxSizing: "border-box",
      backgroundColor: PAPER_HEX,
    },
    [safe],
  );
}

function quoteOrigin(solved: SolvedRedactedDoc): FrameRect {
  const first = solved.lines[0];
  if (!first) {
    return { x: solved.sheet.x + SHEET_PAD_PX, y: solved.citationFrame.y, width: solved.columnWidthPx, height: 0 };
  }
  return {
    x: first.frame.x,
    y: first.frame.y,
    width: solved.columnWidthPx,
    height: solved.lines.length * LINE_HEIGHT_PX,
  };
}

function flatPaint(): DocStyle {
  return { backgroundImage: "none", filter: "none" };
}

function place(rect: FrameRect, origin: FrameRect, style: DocStyle): DocStyle {
  return {
    position: "absolute",
    left: rect.x - origin.x,
    top: rect.y - origin.y,
    width: rect.width,
    height: rect.height,
    ...style,
  };
}

function element(
  type: DocElement["type"],
  key: string,
  dataset: Readonly<Record<string, string>>,
  style: DocStyle,
  children?: readonly DocChild[],
): DocElement {
  const props: Record<string, unknown> = { style };
  for (const [name, value] of Object.entries(dataset)) props[`data-${name}`] = value;
  if (children && children.length === 1) {
    const only = children[0];
    if (only !== undefined) props.children = only;
  } else if (children && children.length > 1) {
    props.children = children;
  }
  return {
    $$typeof: REACT_ELEMENT,
    type,
    key,
    ref: null,
    props: props as DocElement["props"],
  };
}
