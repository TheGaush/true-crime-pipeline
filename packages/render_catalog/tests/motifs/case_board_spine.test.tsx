/**
 * Task 124 CaseBoardSpine tests.
 *
 * Tasks 101 and 110 own SafeZoneLayout and dispatchMicroSfx. Those files are
 * not on this branch. The suite rewrites the two imports and supplies stand-ins
 * so the corkboard runs offline without copying either module.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { beforeEach, describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const ts = require("typescript") as typeof import("typescript");

interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface SolvedCard {
  clueId: string;
  factId: string;
  label: string;
  wordCount: number;
  truncated: boolean;
  row: number;
  column: number;
  rect: Rect;
  caption: Rect;
  pin: { x: number; y: number };
}

interface SolvedPin {
  clueId: string;
  x: number;
  restY: number;
  y: number;
  landFrame: number;
  landed: boolean;
  circle: Rect;
}

interface SolvedString {
  fromId: string;
  toId: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  draw: number;
  bounds: Rect;
}

interface PinTrigger {
  cue: string;
  sceneId: string;
  frame: number;
}

interface SolvedBoard {
  motif: string;
  act: 1 | 2 | 3 | null;
  frame: number;
  sceneId: string;
  isEndScreen: boolean;
  label?: string;
  columns: number;
  rows: number;
  zoom: number;
  cameraTransform: string;
  content: Rect;
  board: Rect;
  cards: SolvedCard[];
  pins: SolvedPin[];
  strings: SolvedString[];
  triggers: PinTrigger[];
  cues: { cue: string; scene_id: string; start_frame: number }[];
}

interface BoardNode {
  type: string;
  dataset: Record<string, string>;
  props: {
    transform?: string;
    stroke?: string;
    d?: string;
    children?: BoardNode | string | readonly (BoardNode | string)[];
    [key: string]: unknown;
  };
}

interface ZoneProps {
  isEndScreen: boolean;
  label?: string;
  children?: BoardNode;
}

interface SfxCall {
  triggers: PinTrigger[];
  options: { clock?: { fps: number; width: number; height: number } };
}

interface BoardModule {
  MOTIF_COMPONENT: string;
  MOTIF_NUMBER: number;
  MOTIF_OWNER: string;
  FRAME_WIDTH: number;
  FRAME_HEIGHT: number;
  FRAME_FPS: number;
  SAFE_PADDING_TOP: number;
  SAFE_PADDING_BOTTOM: number;
  LABEL_SLOT_PX: number;
  BOARD_INSET: number;
  CARD_GAP_X: number;
  CARD_GAP_Y: number;
  ROW_COUNT: number;
  MAX_CLUES: number;
  MAX_LABEL_WORDS: number;
  PIN_DROP_PX: number;
  PIN_STAGGER_FRAMES: number;
  RESET_FRAMES: number;
  RESET_MS: number;
  RESET_SECONDS: number;
  ZOOM_START: number;
  WINDOW_START_MS: number;
  WINDOW_END_MS: number;
  WINDOW_NOMINAL_MS: number;
  EVIDENCE_CRIMSON: string;
  PIN_THUD_CUE: string;
  CaseBoardSpineError: new (code: string, message: string) => Error & { code: string };
  columnCount: (count: number) => number;
  pinLandFrame: (index: number) => number;
  cameraZoom: (frame: number) => number;
  caseBoardWindow: (index: number) => { index: number; startMs: number; endMs: number; nominalMs: number };
  resetShot: (resetMs: number) => { startMs: number; endMs: number; frames: number };
  snapCaseBoardReset: (spans: readonly { startMs: number; endMs: number; kind: string; id?: string }[], windowIndex?: number) => number;
  solveCaseBoardSpine: (input: Record<string, unknown>) => SolvedBoard;
  CaseBoardSpine: (input: Record<string, unknown>) => BoardNode;
}

const SOURCE_URL = new URL("../../src/motifs/CaseBoardSpine.tsx", import.meta.url);
const SOURCE = readFileSync(SOURCE_URL, "utf8");
const SAFE_ZONE_IMPORT = 'import { SafeZoneLayout } from "../safe_zone.js";';
const SFX_IMPORT = 'import { dispatchMicroSfx } from "../sfx/SfxRegistry.js";';

const zoneCalls: ZoneProps[] = [];
const sfxCalls: SfxCall[] = [];

function SafeZoneLayout(props: ZoneProps): BoardNode {
  zoneCalls.push(props);
  const node: BoardNode = {
    type: "SafeZoneLayout",
    dataset: { "safe-zone": "stub" },
    props: {},
  };
  if (props.children !== undefined) node.props.children = props.children;
  return node;
}

function dispatchMicroSfx(triggers: PinTrigger[], options: SfxCall["options"]): { cues: unknown[]; suppressed: [] } {
  sfxCalls.push({ triggers, options });
  return {
    cues: triggers.map((trigger) => ({
      cue_id: `${trigger.sceneId}:${trigger.cue}:${trigger.frame}`,
      cue: trigger.cue,
      scene_id: trigger.sceneId,
      start_frame: trigger.frame,
    })),
    suppressed: [],
  };
}

function loadBoard(): BoardModule {
  if (!SOURCE.includes(SAFE_ZONE_IMPORT) || !SOURCE.includes(SFX_IMPORT)) {
    throw new Error("CaseBoardSpine must import SafeZoneLayout and dispatchMicroSfx");
  }
  const rewritten = SOURCE.replace(SAFE_ZONE_IMPORT, "").replace(SFX_IMPORT, "");
  const printed = ts.transpileModule(rewritten, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: "CaseBoardSpine.tsx",
  }).outputText;
  const exports: Record<string, unknown> = {};
  const runner = new Function(
    "SafeZoneLayout",
    "dispatchMicroSfx",
    "exports",
    printed,
  ) as (zone: typeof SafeZoneLayout, sfx: typeof dispatchMicroSfx, exports: Record<string, unknown>) => void;
  runner(SafeZoneLayout, dispatchMicroSfx, exports);
  return exports as unknown as BoardModule;
}

const board = loadBoard();

const PACK_URL = new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url);

function contains(outer: Rect, inner: Rect): boolean {
  const eps = 1e-6;
  return (
    inner.x >= outer.x - eps &&
    inner.y >= outer.y - eps &&
    inner.x + inner.width <= outer.x + outer.width + eps &&
    inner.y + inner.height <= outer.y + outer.height + eps
  );
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

function clues(count: number, label?: string): { clueId: string; factId: string; label: string }[] {
  return Array.from({ length: count }, (_, index) => {
    const n = String(index + 1).padStart(2, "0");
    return {
      clueId: `clue_${n}`,
      factId: `fact_${n}`,
      label: label ?? `Clue ${index + 1}`,
    };
  });
}

function input(count: number, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    clues: clues(count),
    frame: board.RESET_FRAMES - 1,
    sceneId: "scene_board",
    act: 3,
    ...overrides,
  };
}

function errorCode(run: () => void): string {
  try {
    run();
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (!code) throw error;
    return code;
  }
  throw new Error("expected CaseBoardSpine to throw");
}

function childList(node: BoardNode): BoardNode[] {
  const children = node.props.children;
  if (children === undefined || typeof children === "string") return [];
  const list = Array.isArray(children) ? children : [children];
  return list.filter((child): child is BoardNode => typeof child !== "string");
}

function walk(node: BoardNode, into: BoardNode[] = []): BoardNode[] {
  into.push(node);
  for (const child of childList(node)) walk(child, into);
  return into;
}

const TWELVE = "one two three four five six seven eight nine ten eleven twelve";
const THIRTEEN = `${TWELVE} thirteen`;

beforeEach(() => {
  zoneCalls.length = 0;
  sfxCalls.length = 0;
});

describe("CaseBoardSpine", () => {
  it("keeps the safe-zone and micro-SFX modules as imports", () => {
    expect(process.env.GEMINI_API_KEY).toBeUndefined();
    expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
    expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
    expect(SOURCE.includes("feTurbulence")).toBe(false);
    expect(SOURCE.includes("feDisplacementMap")).toBe(false);
    expect(SOURCE.includes("Math.random")).toBe(false);
    expect(SOURCE.includes("function SafeZoneLayout")).toBe(false);
    expect(SOURCE.includes("COOLDOWN_SAMPLES")).toBe(false);
    expect(SOURCE.includes(SAFE_ZONE_IMPORT)).toBe(true);
    expect(SOURCE.includes(SFX_IMPORT)).toBe(true);
    expect(board.MOTIF_COMPONENT).toBe("CaseBoardSpine");
    expect(board.MOTIF_NUMBER).toBe(10);
    expect(board.MOTIF_OWNER).toBe("render_catalog");
    expect(board.MAX_CLUES).toBe(16);
    expect(board.ROW_COUNT).toBe(2);
    expect(board.RESET_SECONDS).toBe(5);
    expect(board.RESET_FRAMES).toBe(150);
    expect(board.RESET_MS).toBe(5000);
    expect(board.FRAME_FPS).toBe(30);
    expect(board.PIN_THUD_CUE).toBe("pin_thud");
    expect(board.EVIDENCE_CRIMSON).toBe("#C92A2A");
    expect(board.WINDOW_START_MS).toBe(210_000);
    expect(board.WINDOW_NOMINAL_MS).toBe(240_000);
    expect(board.WINDOW_END_MS).toBe(270_000);
  });

  it("lays out 3, 8, and 16 clues on two unclipped rows", () => {
    const content = {
      x: 0,
      y: board.SAFE_PADDING_TOP,
      width: board.FRAME_WIDTH,
      height: board.FRAME_HEIGHT - board.SAFE_PADDING_TOP - board.SAFE_PADDING_BOTTOM,
    };
    const exclusion = {
      x: board.FRAME_WIDTH * 0.78,
      y: board.FRAME_HEIGHT * 0.86,
      width: board.FRAME_WIDTH * 0.22,
      height: board.FRAME_HEIGHT * 0.14,
    };
    for (const count of [3, 8, 16]) {
      const solved = board.solveCaseBoardSpine(input(count));
      expect(solved.columns).toBe(board.columnCount(count));
      expect(solved.rows).toBe(2);
      expect(solved.cards).toHaveLength(count);
      expect(solved.strings).toHaveLength(count - 1);
      expect(solved.pins).toHaveLength(count);
      expect(new Set(solved.cards.map((card) => card.row))).toEqual(new Set([0, 1]));
      expect(contains(content, solved.board)).toBe(true);
      expect(overlaps(solved.board, exclusion)).toBe(false);
      for (const card of solved.cards) {
        expect(contains(content, card.rect)).toBe(true);
        expect(contains(card.rect, card.caption)).toBe(true);
        expect(overlaps(card.rect, exclusion)).toBe(false);
        expect(card.column).toBeGreaterThanOrEqual(0);
        expect(card.column).toBeLessThan(solved.columns);
      }
      for (let i = 0; i < solved.cards.length; i += 1) {
        const card = solved.cards[i];
        if (!card) continue;
        for (let j = i + 1; j < solved.cards.length; j += 1) {
          const other = solved.cards[j];
          if (other) expect(overlaps(card.rect, other.rect)).toBe(false);
        }
      }
      for (const thread of solved.strings) {
        expect(contains(content, thread.bounds)).toBe(true);
        expect(overlaps(thread.bounds, exclusion)).toBe(false);
        expect(thread.draw).toBe(1);
      }
      for (const pin of solved.pins) {
        expect(pin.landed).toBe(true);
        expect(contains(content, pin.circle)).toBe(true);
      }
      const row0 = solved.cards.filter((card) => card.row === 0);
      for (let i = 1; i < row0.length; i += 1) {
        const previous = row0[i - 1];
        const current = row0[i];
        if (!previous || !current) continue;
        expect(current.rect.x - (previous.rect.x + previous.rect.width)).toBe(board.CARD_GAP_X);
      }
    }
  });

  it("keeps the final Act 3 board of 16 polaroids on an exact 8-by-2 grid", () => {
    const solved = board.solveCaseBoardSpine(input(16, { act: 3, frame: 149 }));
    expect(solved.act).toBe(3);
    expect(solved.columns).toBe(8);
    const boardBox = {
      x: board.BOARD_INSET,
      y: board.SAFE_PADDING_TOP + board.BOARD_INSET,
      width: board.FRAME_WIDTH - board.BOARD_INSET * 2,
      height: board.FRAME_HEIGHT - board.SAFE_PADDING_TOP - board.SAFE_PADDING_BOTTOM - board.BOARD_INSET * 2,
    };
    expect(solved.board).toEqual(boardBox);
    const cardWidth = (boardBox.width - board.CARD_GAP_X * 7) / 8;
    const cardHeight = (boardBox.height - board.CARD_GAP_Y) / 2;
    expect(cardWidth).toBe(222);
    expect(cardHeight).toBe(363);
    expect(solved.cards[0]?.rect).toEqual({ x: 16, y: 124, width: 222, height: 363 });
    expect(solved.cards[7]?.column).toBe(7);
    expect(solved.cards[7]?.row).toBe(0);
    expect(solved.cards[7]?.rect.x).toBe(1682);
    expect(solved.cards[8]?.row).toBe(1);
    expect(solved.cards[8]?.column).toBe(0);
    expect(solved.cards[8]?.rect.y).toBe(507);
    const last = solved.cards[15];
    expect(last?.rect.x).toBe(1682);
    expect(last && last.rect.x + last.rect.width).toBe(1904);
    expect(solved.strings[7]?.fromId).toBe("clue_08");
    expect(solved.strings[7]?.toId).toBe("clue_09");
    expect(solved.zoom).toBe(1);
    expect(solved.cameraTransform).toContain("scale(1)");
  });

  it("drops every pin with a pin_thud and finishes the 5-second zoom-out", () => {
    const opened = board.solveCaseBoardSpine(input(16, { frame: 0, sceneId: "scene_act3" }));
    expect(opened.zoom).toBe(board.ZOOM_START);
    expect(opened.zoom).toBeGreaterThan(1);
    expect(opened.pins[0]?.landed).toBe(false);
    expect(opened.pins[0]?.y).toBe((opened.pins[0]?.restY ?? 0) - board.PIN_DROP_PX);
    expect(opened.strings[0]?.draw).toBe(0);
    expect(opened.pins.every((pin) => pin.circle.y >= board.SAFE_PADDING_TOP)).toBe(true);

    const settled = board.solveCaseBoardSpine(input(16, { frame: 149, sceneId: "scene_act3" }));
    expect(settled.zoom).toBe(1);
    expect(board.cameraZoom(0)).toBe(board.ZOOM_START);
    expect(board.cameraZoom(149)).toBe(1);
    expect(settled.pins.every((pin) => pin.landed && pin.y === pin.restY)).toBe(true);
    expect(settled.strings.every((thread) => thread.draw === 1)).toBe(true);
    expect(settled.triggers.map((trigger) => trigger.frame)).toEqual(
      settled.pins.map((_, index) => board.pinLandFrame(index)),
    );
    for (let index = 1; index < settled.triggers.length; index += 1) {
      const previous = settled.triggers[index - 1];
      const current = settled.triggers[index];
      expect(current && previous && current.frame - previous.frame).toBe(board.PIN_STAGGER_FRAMES);
      expect(board.PIN_STAGGER_FRAMES * (1000 / board.FRAME_FPS)).toBeGreaterThan(60);
    }
    expect(settled.triggers[0]?.frame).toBe(8);
    expect(settled.triggers[15]?.frame).toBe(53);
    expect(settled.triggers.every((trigger) => trigger.cue === "pin_thud" && trigger.sceneId === "scene_act3")).toBe(true);
    expect(settled.cues).toHaveLength(16);
    expect(sfxCalls.at(-1)?.options.clock).toEqual({ fps: 30, width: 1920, height: 1080 });
  });

  it("renders the settled board inside SafeZoneLayout with crimson string draw-on", () => {
    const tree = board.CaseBoardSpine(input(8, { label: "Act 3 board", isEndScreen: false }));
    expect(tree.type).toBe("SafeZoneLayout");
    expect(zoneCalls).toHaveLength(1);
    expect(zoneCalls[0]?.isEndScreen).toBe(false);
    expect(zoneCalls[0]?.label).toBe("Act 3 board");
    const root = zoneCalls[0]?.children;
    expect(root).toBeDefined();
    const nodes = walk(root as BoardNode);
    const motif = nodes.find((node) => node.dataset.motif === "CaseBoardSpine");
    expect(motif?.dataset["clue-count"]).toBe("8");
    expect(motif?.dataset.columns).toBe("4");
    expect(motif?.dataset.rows).toBe("2");
    expect(motif?.dataset.act).toBe("3");
    expect(motif?.dataset["apply-grade"]).toBe("true");
    expect(motif?.dataset["needs-grade"]).toBe("true");
    expect(motif?.dataset.owner).toBe("render_catalog");
    expect(motif?.dataset["motif-number"]).toBe("10");
    expect(motif?.dataset.zoom).toBe("1");
    expect(motif?.dataset["pin-thud-count"]).toBe("8");
    const strings = nodes.filter((node) => node.dataset.crimson === "#C92A2A");
    expect(strings).toHaveLength(7);
    expect(strings.every((node) => node.props.stroke === "#C92A2A" && node.dataset.draw === "1")).toBe(true);
    expect(JSON.stringify(nodes).includes("feTurbulence")).toBe(false);
    expect(JSON.stringify(nodes).includes("feDisplacementMap")).toBe(false);
    const endScreen = board.CaseBoardSpine(input(16, { isEndScreen: true, act: 3 }));
    expect(endScreen.type).toBe("SafeZoneLayout");
    expect(zoneCalls.at(-1)?.isEndScreen).toBe(true);
    const reserved = board.solveCaseBoardSpine(input(16, { isEndScreen: true }));
    const limit = board.FRAME_HEIGHT - board.SAFE_PADDING_BOTTOM - board.LABEL_SLOT_PX;
    for (const card of reserved.cards) {
      expect(card.rect.y + card.rect.height).toBeLessThanOrEqual(limit + 1e-6);
    }
  });

  it("clamps captions at 12 words without moving the 16-card grid", () => {
    const short = board.solveCaseBoardSpine(input(16));
    const full = board.solveCaseBoardSpine(input(16, { clues: clues(16, TWELVE) }));
    const long = board.solveCaseBoardSpine(input(1, { clues: clues(1, THIRTEEN), act: 1 }));
    expect(full.cards.every((card) => card.wordCount === 12 && card.truncated === false)).toBe(true);
    expect(full.cards.map((card) => card.rect)).toEqual(short.cards.map((card) => card.rect));
    expect(long.cards[0]?.truncated).toBe(true);
    expect(long.cards[0]?.label).toBe(TWELVE);
    expect(long.cards[0]?.wordCount).toBe(board.MAX_LABEL_WORDS);
    expect(JSON.stringify(short)).toBe(JSON.stringify(board.solveCaseBoardSpine(input(16))));
  });

  it("refuses a 17th clue and an empty board", () => {
    expect(errorCode(() => board.solveCaseBoardSpine(input(17)))).toBe("BOUNDED_16");
    expect(errorCode(() => board.solveCaseBoardSpine(input(0)))).toBe("BOUNDED_16");
    expect(errorCode(() => board.columnCount(17))).toBe("BOUNDED_16");
    expect(errorCode(() => board.CaseBoardSpine(input(16, { frame: 150 })))).toBe("FRAME");
    expect(sfxCalls).toHaveLength(0);
    const duplicate = clues(3);
    const first = duplicate[0];
    const second = duplicate[1];
    if (!first || !second) throw new Error("fixture missing");
    duplicate[1] = { ...second, clueId: first.clueId };
    expect(errorCode(() => board.solveCaseBoardSpine(input(3, { clues: duplicate })))).toBe("CLUE");
  });

  it("snaps the reset to a completed boundary inside 210–270s", () => {
    const call = { startMs: 230_000, endMs: 255_000, kind: "call", id: "call_911" };
    const sentence = { startMs: 230_000, endMs: 245_000, kind: "sentence", id: "sent_911" };
    expect(board.snapCaseBoardReset([call, sentence])).toBe(255_000);
    const shot = board.resetShot(255_000);
    expect(shot).toEqual({ startMs: 255_000, endMs: 260_000, frames: 150 });
    expect(shot.endMs).toBeLessThanOrEqual(board.WINDOW_END_MS);
    expect(board.snapCaseBoardReset([{ startMs: 210_000, endMs: 240_000, kind: "scene" }])).toBe(240_000);
    expect(board.snapCaseBoardReset([
      { startMs: 200_000, endMs: 220_000, kind: "scene" },
      { startMs: 250_000, endMs: 260_000, kind: "scene" },
    ])).toBe(260_000);
    expect(board.snapCaseBoardReset([
      { startMs: 200_000, endMs: 230_000, kind: "scene" },
      { startMs: 250_000, endMs: 265_000, kind: "sentence" },
    ])).toBe(230_000);
    expect(errorCode(() => board.snapCaseBoardReset([
      { startMs: 230_000, endMs: 280_000, kind: "call" },
    ]))).toBe("BOUNDARY");
    expect(board.caseBoardWindow(1)).toEqual({
      index: 1,
      startMs: 210_000,
      endMs: 270_000,
      nominalMs: 240_000,
    });
    expect(board.snapCaseBoardReset(
      [{ startMs: 470_000, endMs: 495_000, kind: "call" }],
      2,
    )).toBe(495_000);
  });

  it("is registered to render_catalog and is outside the MVP four", () => {
    const pack = JSON.parse(readFileSync(PACK_URL, "utf8")) as {
      motif_registry_v1: { motif_component: string; owner_package: string; is_mvp_4: number }[];
    };
    const entry = pack.motif_registry_v1.find((row) => row.motif_component === "CaseBoardSpine");
    expect(entry).toEqual({ motif_component: "CaseBoardSpine", owner_package: "render_catalog", is_mvp_4: 0 });
    const mvp = pack.motif_registry_v1.filter((row) => row.is_mvp_4 === 1).map((row) => row.motif_component);
    expect(mvp).not.toContain("CaseBoardSpine");
  });
});
