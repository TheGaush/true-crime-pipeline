import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import {
  BADGE_BG_HEX,
  CHAR_WIDTH_PX,
  CITATION_HEIGHT_PX,
  DEFAULT_COLUMN_WIDTH_PX,
  FILING_CAPTION,
  FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  HIGHLIGHTER_GLIDE,
  HIGHLIGHTER_GLIDE_COOLDOWN_MS,
  HIGHLIGHTER_GLIDE_DURATION_MS,
  HIGHLIGHTER_HEX,
  INK_HEX,
  LINE_HEIGHT_PX,
  MARK_HEIGHT_PX,
  MOTIF_COMPONENT,
  PAPER_HEX,
  REDACTION_HEX,
  RedactedDocError,
  RedactedDocReveal,
  SAFE_HEIGHT_PX,
  SAFE_PADDING_BOTTOM_PX,
  SAFE_PADDING_TOP_PX,
  captionBarRect,
  exclusionRect,
  lineSweepWidthPx,
  timelineMs,
  wordProgress,
  type DocChild,
  type DocElement,
  type FrameRect,
  type RedactedDocRevealProps,
  type WordStamp,
} from "../../src/motifs/RedactedDocReveal.tsx";

const SOURCE = readFileSync(new URL("../../src/motifs/RedactedDocReveal.tsx", import.meta.url), "utf8");

const PACK_IDS = ["ep_golden_01_20min", "ep_golden_02_2strike_fallback", "ep_golden_03_2k_grid_heavy"] as const;

type Pack = {
  temporal_fact_ledger: Array<{ fact_id: string; citation_locator: string }>;
  scene_plans: Array<{
    scene_id: string;
    motif_component: string;
    approved_narration_text: string;
    cited_fact_ids_json: string[];
    timing_start_ms: number;
    visual_concept: string;
  }>;
  scenes: Array<{ scene_id: string; motif_component: string; start_ms: number; end_ms: number }>;
  voice_track_manifest: {
    segments: Array<{
      start_ms: number;
      end_ms: number;
      segment_kind: string;
      word_timestamps: WordStamp[];
    }>;
  };
};

const PACKS = PACK_IDS.map((id) => ({
  id,
  pack: JSON.parse(
    readFileSync(new URL(`../../../../fixtures/golden_manifests/${id}/pack.json`, import.meta.url), "utf8"),
  ) as Pack,
}));

const MULTI_QUOTE = "alpha bravo charlie delta echo foxtrot";
const MULTI_STAMPS: WordStamp[] = [
  { word: "alpha", start_ms: 1000, end_ms: 1200 },
  { word: "bravo", start_ms: 1200, end_ms: 1600 },
  { word: "charlie", start_ms: 1600, end_ms: 2000 },
  { word: "delta", start_ms: 2000, end_ms: 2400 },
  { word: "echo", start_ms: 2400, end_ms: 2800 },
  { word: "foxtrot", start_ms: 2800, end_ms: 3200 },
];

function reveal(patch: Partial<RedactedDocRevealProps> = {}) {
  const props: RedactedDocRevealProps = {
    citation: "2021 MT 142 at paragraph 18",
    quote: MULTI_QUOTE,
    wordTimestamps: MULTI_STAMPS,
    sceneStartMs: 0,
    frame: 0,
    sceneId: "scene_redacted_doc",
    columnWidthPx: 252,
    ...patch,
  };
  return RedactedDocReveal(props);
}

function walk(node: DocChild, into: DocElement[] = []): DocElement[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walk(child, into);
  return into;
}

function texts(node: DocChild, into: string[] = []): string[] {
  if (typeof node === "string") {
    into.push(node);
    return into;
  }
  const children = node.props.children;
  if (typeof children === "string") into.push(children);
  else if (Array.isArray(children)) {
    for (const child of children) texts(child, into);
  } else if (children !== undefined) {
    texts(children, into);
  }
  return into;
}

function slot(root: DocElement, name: string): DocElement {
  const found = walk(root).find((node) => node.props["data-slot"] === name);
  if (!found) throw new Error(`missing slot ${name}`);
  return found;
}

function overlaps(left: FrameRect, right: FrameRect): boolean {
  return (
    left.x < right.x + right.width &&
    left.x + left.width > right.x &&
    left.y < right.y + right.height &&
    left.y + left.height > right.y
  );
}

function contains(outer: FrameRect, inner: FrameRect): boolean {
  return (
    inner.x >= outer.x - 1e-6 &&
    inner.y >= outer.y - 1e-6 &&
    inner.x + inner.width <= outer.x + outer.width + 1e-6 &&
    inner.y + inner.height <= outer.y + outer.height + 1e-6
  );
}

function absoluteBoxes(root: DocElement): Array<{ node: DocElement; rect: FrameRect }> {
  const boxes: Array<{ node: DocElement; rect: FrameRect }> = [];
  const visit = (node: DocElement, originX: number, originY: number): void => {
    const left = Number(node.props.style.left ?? 0);
    const top = Number(node.props.style.top ?? 0);
    const width = Number(node.props.style.width);
    const height = Number(node.props.style.height);
    const positioned = node.props.style.position === "absolute" || node.props.style.position === "relative";
    const rect = {
      x: positioned ? originX + left : originX,
      y: positioned ? originY + top : originY,
      width,
      height,
    };
    boxes.push({ node, rect });
    const children = node.props.children;
    if (children === undefined) return;
    const list = Array.isArray(children) ? children : [children];
    for (const child of list) {
      if (typeof child === "string") continue;
      visit(child, rect.x, rect.y);
    }
  };
  visit(root, 0, 0);
  return boxes;
}

test("provider keys stay unset under the offline setup", () => {
  expect(process.env.GEMINI_API_KEY).toBeUndefined();
  expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
  expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
});

test("a wrapped quote sweeps one mark per line, in order", () => {
  expect(wordProgress(100, 300, 100)).toBe(0);
  expect(wordProgress(100, 300, 200)).toBe(0.5);
  expect(wordProgress(100, 300, 300)).toBe(1);
  expect(wordProgress(100, 300, 50)).toBe(0);
  expect(FPS).toBe(30);
  expect(timelineMs(980_000, 78)).toBe(982_600);

  const hand = [
    { widthPx: 18, start_ms: 0, end_ms: 100 },
    { widthPx: 36, start_ms: 100, end_ms: 300 },
  ];
  expect(lineSweepWidthPx(hand, 200)).toBe(18 + CHAR_WIDTH_PX + 18);
  expect(lineSweepWidthPx(hand, 100)).toBe(18 + CHAR_WIDTH_PX);
  expect(lineSweepWidthPx(hand, 0)).toBe(0);

  const mid = reveal({ frame: 66 });
  expect(timelineMs(0, 66)).toBe(2200);
  expect(mid.solved.nowMs).toBe(2200);
  expect(mid.solved.lines.map((line) => line.words.map((word) => word.word))).toEqual([
    ["alpha", "bravo"],
    ["charlie", "delta"],
    ["echo", "foxtrot"],
  ]);

  const widths = [5, 5, 7, 5, 4, 7].map((chars) => chars * CHAR_WIDTH_PX);
  mid.solved.lines.flatMap((line) => line.words).forEach((word, index) => {
    expect(word.widthPx).toBe(widths[index]);
  });

  expect(mid.solved.marks.map((mark) => mark.sweep)).toEqual(["full", "partial", "pending"]);
  expect(mid.solved.marks[0]?.widthPx).toBe(90 + CHAR_WIDTH_PX + 90);
  expect(mid.solved.marks[1]?.widthPx).toBe(126 + CHAR_WIDTH_PX + 45);
  expect(mid.solved.marks[2]?.widthPx).toBe(0);
  expect(mid.solved.marks[1]?.widthPx).toBeLessThan(mid.solved.lines[1]?.textWidthPx ?? 0);
  expect(mid.solved.marks[0]?.widthPx).toBe(mid.solved.lines[0]?.textWidthPx);

  const marks = walk(mid).filter((node) => node.type === "mark");
  expect(marks).toHaveLength(3);
  marks.forEach((mark, index) => {
    expect(mark.props["data-slot"]).toBe("mark");
    expect(mark.props["data-line"]).toBe(String(index));
    expect(mark.props["data-sweep"]).toBe(mid.solved.marks[index]?.sweep);
    expect(mark.props.style.backgroundColor).toBe(HIGHLIGHTER_HEX);
    expect(mark.props.style.height).toBe(MARK_HEIGHT_PX);
  });
  expect(marks.map((mark) => mark.props["data-sweep"])).toEqual(["full", "partial", "pending"]);

  const early = reveal({ frame: 0 });
  expect(early.solved.nowMs).toBe(0);
  expect(early.solved.marks.every((mark) => mark.sweep === "pending" && mark.widthPx === 0)).toBe(true);

  const done = reveal({ frame: 96 });
  expect(done.solved.nowMs).toBe(3200);
  expect(done.solved.marks.every((mark) => mark.sweep === "full")).toBe(true);
  done.solved.marks.forEach((mark, index) => {
    expect(mark.widthPx).toBe(done.solved.lines[index]?.textWidthPx);
  });

  const boundary = RedactedDocReveal({
    citation: "2021 MT 142 at paragraph 18",
    quote: "a b",
    wordTimestamps: [
      { word: "a", start_ms: 0, end_ms: 100 },
      { word: "b", start_ms: 100, end_ms: 200 },
    ],
    sceneStartMs: 0,
    frame: 3,
    sceneId: "scene_boundary",
    columnWidthPx: CHAR_WIDTH_PX,
  });
  expect(boundary.solved.nowMs).toBe(100);
  expect(boundary.solved.lines).toHaveLength(2);
  expect(boundary.solved.marks.map((mark) => mark.sweep)).toEqual(["full", "pending"]);
  expect(boundary.solved.marks[1]?.widthPx).toBe(0);
});

test("black redaction bars cover wrapped words and hide their text", () => {
  const rendered = reveal({
    frame: 66,
    quoteRedactions: [
      { startWord: 1, endWord: 3 },
    ],
  });
  const body = texts(rendered).join("\n");
  expect(body).toContain("alpha");
  expect(body).toContain("delta");
  expect(body).toContain("echo");
  expect(body).toContain("foxtrot");
  expect(body).not.toContain("bravo");
  expect(body).not.toContain("charlie");

  const quoteBars = rendered.solved.redactions.filter((bar) => bar.kind === "quote");
  expect(quoteBars).toHaveLength(2);
  const line0 = rendered.solved.lines[0];
  const line1 = rendered.solved.lines[1];
  if (!line0 || !line1) throw new Error("expected two quote lines");
  expect(quoteBars[0]).toMatchObject({
    line: 0,
    frame: { x: line0.frame.x + 90 + CHAR_WIDTH_PX, y: line0.frame.y, width: 90, height: LINE_HEIGHT_PX },
  });
  expect(quoteBars[1]).toMatchObject({
    line: 1,
    frame: { x: line1.frame.x, y: line1.frame.y, width: 126, height: LINE_HEIGHT_PX },
  });

  const nodes = walk(rendered);
  for (const lineIndex of [0, 1]) {
    const lineNode = nodes.find((node) => node.props["data-slot"] === "line" && node.props["data-line"] === String(lineIndex));
    if (!lineNode) throw new Error(`missing line ${lineIndex}`);
    const children = lineNode.props.children;
    const list = Array.isArray(children) ? children : [];
    const markAt = list.findIndex((child) => typeof child !== "string" && child.type === "mark");
    const barAt = list.findIndex(
      (child) => typeof child !== "string" && child.props["data-kind"] === "quote",
    );
    expect(markAt).toBeGreaterThanOrEqual(0);
    expect(barAt).toBeGreaterThan(markAt);
  }

  const bars = nodes.filter((node) => node.props["data-kind"] === "quote");
  expect(bars).toHaveLength(2);
  for (const bar of bars) expect(bar.props.style.backgroundColor).toBe(REDACTION_HEX);

  const affidavit = rendered.solved.redactions.filter((bar) => bar.kind === "affidavit");
  expect(affidavit).toHaveLength(2);
  const affidavitNodes = nodes.filter((node) => node.props["data-kind"] === "affidavit");
  expect(affidavitNodes).toHaveLength(2);
  for (const bar of affidavitNodes) {
    expect(bar.props.style.backgroundColor).toBe("#000000");
    expect(texts(bar)).toEqual([]);
  }
  expect(REDACTION_HEX).toBe("#000000");
});

test("the citation badge and the filing sheet stay inside the safe zone", () => {
  expect(FRAME_WIDTH).toBe(1920);
  expect(FRAME_HEIGHT).toBe(1080);
  expect(SAFE_PADDING_TOP_PX).toBe(108);
  expect(SAFE_PADDING_BOTTOM_PX).toBe(194);
  expect(SAFE_HEIGHT_PX).toBe(778);
  expect(MOTIF_COMPONENT).toBe("RedactedDocReveal");
  expect(DEFAULT_COLUMN_WIDTH_PX).toBe(640);

  const rendered = reveal({ frame: 66, isEndScreen: true });
  expect(rendered.$$typeof).toBe(Symbol.for("react.element"));
  expect(rendered.type).toBe("div");
  expect(rendered.props["data-motif"]).toBe("RedactedDocReveal");
  expect(rendered.props["data-safe-zone"]).toBe("css-contained");
  expect(rendered.props["data-end-screen"]).toBe("true");
  expect(rendered.props["data-paper-grain"]).toBe("0");
  expect(rendered.props["data-vignette"]).toBe("0");
  expect(rendered.props["data-apply-grade"]).toBe("true");
  expect(rendered.props["data-fps"]).toBe("30");
  expect(rendered.props.style).toMatchObject({
    width: 1920,
    height: 1080,
    overflow: "hidden",
    filter: "none",
    backgroundImage: "none",
    backgroundColor: PAPER_HEX,
  });

  const safe = slot(rendered, "safe");
  expect(safe.props.style).toMatchObject({
    left: 0,
    top: SAFE_PADDING_TOP_PX,
    width: FRAME_WIDTH,
    height: SAFE_HEIGHT_PX,
    overflow: "hidden",
  });
  const sheet = slot(rendered, "sheet");
  expect(sheet.props["data-sheet"]).toBe("aged-court-filing");
  expect(sheet.props.style.backgroundColor).toBe(PAPER_HEX);
  expect(sheet.props.style.filter).toBe("none");
  expect(texts(slot(rendered, "caption"))).toEqual([FILING_CAPTION]);
  expect(texts(slot(rendered, "citation"))).toEqual(["2021 MT 142 at paragraph 18"]);
  expect(slot(rendered, "citation").props.style).toMatchObject({
    backgroundColor: BADGE_BG_HEX,
    color: "#F4EFE6",
    fontWeight: 700,
    overflow: "hidden",
    height: CITATION_HEIGHT_PX,
  });

  const safeRect = rendered.solved.safe;
  expect(safeRect).toEqual({ x: 0, y: 108, width: 1920, height: 778 });
  const exclusion = exclusionRect();
  const captionBar = captionBarRect();
  expect(exclusion.x).toBeCloseTo(FRAME_WIDTH * 0.78, 6);
  expect(exclusion.y).toBeCloseTo(FRAME_HEIGHT * 0.86, 6);
  expect(exclusion.width).toBeCloseTo(FRAME_WIDTH * 0.22, 6);
  expect(exclusion.height).toBeCloseTo(FRAME_HEIGHT * 0.14, 6);
  expect(captionBar).toEqual({ x: 0, y: 886, width: 1920, height: 194 });
  expect(overlaps(rendered.solved.sheet, exclusion)).toBe(false);
  expect(overlaps(rendered.solved.sheet, captionBar)).toBe(false);
  expect(overlaps(rendered.solved.citationFrame, exclusion)).toBe(false);

  const boxes = absoluteBoxes(rendered);
  const painted = boxes.filter((box) => box.node.props["data-slot"] !== undefined);
  expect(painted.length).toBeGreaterThan(8);
  for (const box of painted) {
    expect(contains(safeRect, box.rect)).toBe(true);
    expect(overlaps(box.rect, exclusion)).toBe(false);
    expect(overlaps(box.rect, captionBar)).toBe(false);
    expect(box.node.props.style.filter).toBe("none");
    expect(box.node.props.style.backgroundImage).toBe("none");
  }

  const domMarks = boxes.filter((box) => box.node.type === "mark");
  expect(domMarks).toHaveLength(3);
  domMarks.forEach((box, index) => {
    const mark = rendered.solved.marks[index];
    expect(mark).toBeDefined();
    expect(box.rect.x).toBeCloseTo(mark?.frame.x ?? -1, 4);
    expect(box.rect.y).toBeCloseTo(mark?.frame.y ?? -1, 4);
    expect(box.rect.width).toBeCloseTo(mark?.frame.width ?? -1, 4);
    expect(box.rect.height).toBe(MARK_HEIGHT_PX);
  });

  const citationBox = boxes.find((box) => box.node.props["data-slot"] === "citation");
  if (!citationBox) throw new Error("missing citation box");
  expect(citationBox.rect).toEqual(rendered.solved.citationFrame);
  for (const mark of domMarks) {
    expect(mark.rect.y + mark.rect.height).toBeLessThanOrEqual(citationBox.rect.y);
  }

  expect(SOURCE.includes("#C92A2A")).toBe(false);
  expect(SOURCE.includes("feTurbulence")).toBe(false);
  expect(SOURCE.includes("feDisplacementMap")).toBe(false);
  expect(SOURCE.includes("Math.random")).toBe(false);
  expect(SOURCE.includes("from \"../")).toBe(false);
  expect(JSON.stringify(rendered.props).includes("#C92A2A")).toBe(false);
  expect(INK_HEX).not.toBe("#C92A2A");
  expect(HIGHLIGHTER_HEX).not.toBe("#C92A2A");

  const again = reveal({ frame: 66, isEndScreen: true });
  expect(again.props).toEqual(rendered.props);
  expect(again.solved.marks).toEqual(rendered.solved.marks);
  expect(again.solved.cues).toEqual(rendered.solved.cues);
});

test("each wrapped line schedules highlighter_glide, with a 60 ms cooldown", () => {
  expect(HIGHLIGHTER_GLIDE).toBe("highlighter_glide");
  expect(HIGHLIGHTER_GLIDE_DURATION_MS).toBe(280);
  expect(HIGHLIGHTER_GLIDE_COOLDOWN_MS).toBe(60);

  const rendered = reveal({ frame: 66 });
  expect(rendered.props["data-highlighter-glide"]).toBe("highlighter_glide");
  expect(rendered.solved.cues.map((cue) => cue.offset_ms)).toEqual([1000, 1600, 2400]);
  expect(rendered.solved.suppressed).toEqual([]);
  for (const cue of rendered.solved.cues) {
    expect(cue.cue).toBe("highlighter_glide");
    expect(cue.scene_id).toBe("scene_redacted_doc");
    expect(cue.duration_ms).toBe(280);
    expect(cue.cooldown_ms).toBe(60);
    expect(cue.cue_id).toBe(`scene_redacted_doc:highlighter_glide:${cue.offset_ms}:line${cue.line}`);
  }
  expect(rendered.solved.cues[1]?.offset_ms).toBe(rendered.solved.lines[1]?.words[0]?.start_ms);

  const tight = RedactedDocReveal({
    citation: "2021 MT 142 at paragraph 18",
    quote: "alpha bravo",
    wordTimestamps: [
      { word: "alpha", start_ms: 1000, end_ms: 1030 },
      { word: "bravo", start_ms: 1040, end_ms: 1100 },
    ],
    sceneStartMs: 0,
    frame: 0,
    sceneId: "scene_cooldown",
    columnWidthPx: 90,
  });
  expect(tight.solved.lines).toHaveLength(2);
  expect(tight.solved.cues).toHaveLength(1);
  expect(tight.solved.cues[0]).toMatchObject({ line: 0, offset_ms: 1000, cue: "highlighter_glide" });
  expect(tight.solved.suppressed).toHaveLength(1);
  expect(tight.solved.suppressed[0]).toMatchObject({ line: 1, offset_ms: 1040 });
  expect(tight.props["data-glide-cues"]).toBe("1");
});

test("golden court-record scenes wrap the cited sentence and sweep it on the word clock", () => {
  expect(PACKS).toHaveLength(3);
  for (const { id, pack } of PACKS) {
    const plans = pack.scene_plans.filter((plan) => plan.motif_component === "RedactedDocReveal");
    expect(plans.length).toBeGreaterThan(0);
    for (const plan of plans) {
      const scene = pack.scenes.find((item) => item.scene_id === plan.scene_id);
      const factId = plan.cited_fact_ids_json[0];
      const fact = pack.temporal_fact_ledger.find((item) => item.fact_id === factId);
      const segment = pack.voice_track_manifest.segments.find((item) => item.start_ms === plan.timing_start_ms);
      expect(scene?.motif_component).toBe("RedactedDocReveal");
      expect(scene?.start_ms).toBe(plan.timing_start_ms);
      expect(fact?.citation_locator).toBe("2021 MT 142 at paragraph 18");
      expect(plan.visual_concept).toContain("2021 MT 142 at paragraph 18");
      expect(plan.approved_narration_text).toBe(
        "The affirmed opinion at paragraph 18 is read from the primary court record.",
      );
      expect(segment?.segment_kind).toBe("NARRATION");
      if (!fact || !segment || !scene) throw new Error(`missing golden records for ${id} ${plan.scene_id}`);

      const held = RedactedDocReveal({
        citation: fact.citation_locator,
        quote: plan.approved_narration_text,
        wordTimestamps: segment.word_timestamps,
        sceneStartMs: plan.timing_start_ms,
        frame: 0,
        sceneId: plan.scene_id,
        isEndScreen: scene.end_ms === 1_200_000,
      });
      expect(held.solved.nowMs).toBe(plan.timing_start_ms);
      expect(held.solved.lines.map((line) => line.words.map((word) => word.word).join(" "))).toEqual([
        "The affirmed opinion at paragraph",
        "18 is read from the primary court",
        "record.",
      ]);
      expect(held.solved.marks.every((mark) => mark.widthPx === 0 && mark.sweep === "pending")).toBe(true);
      expect(texts(held)).toContain("2021 MT 142 at paragraph 18");
      expect(texts(held)).toContain("COURT FILING");
      expect(held.solved.cues.map((cue) => cue.line)).toEqual([0, 1, 2]);
      expect(held.solved.cues.map((cue) => cue.offset_ms)).toEqual([
        segment.word_timestamps[0]?.start_ms,
        segment.word_timestamps[5]?.start_ms,
        segment.word_timestamps[12]?.start_ms,
      ]);
      expect(held.solved.suppressed).toEqual([]);
      expect(held.props["data-end-screen"]).toBe(scene.end_ms === 1_200_000 ? "true" : "false");

      const swept = RedactedDocReveal({
        citation: fact.citation_locator,
        quote: plan.approved_narration_text,
        wordTimestamps: segment.word_timestamps,
        sceneStartMs: plan.timing_start_ms,
        frame: 78,
        sceneId: plan.scene_id,
      });
      expect(swept.solved.nowMs).toBe(plan.timing_start_ms + 2600);
      expect(swept.solved.marks.map((mark) => mark.sweep)).toEqual(["full", "partial", "pending"]);
      const line = swept.solved.lines[1];
      if (!line) throw new Error("missing wrapped opinion line");
      const primary = line.words.find((word) => word.word === "primary");
      if (!primary) throw new Error("missing primary");
      const progress =
        (swept.solved.nowMs - primary.start_ms) / (primary.end_ms - primary.start_ms);
      expect(progress).toBeGreaterThan(0);
      expect(progress).toBeLessThan(1);
      let expected = 0;
      for (const word of line.words) {
        if (word.index > primary.index) break;
        if (word.index < primary.index) {
          expected += word.widthPx + CHAR_WIDTH_PX;
          continue;
        }
        expected += progress * word.widthPx;
      }
      expect(swept.solved.marks[1]?.widthPx).toBeCloseTo(expected, 6);
      expect(swept.solved.marks[2]?.widthPx).toBe(0);
      for (const mark of swept.solved.marks) {
        expect(contains(swept.solved.safe, mark.frame)).toBe(true);
        expect(overlaps(mark.frame, exclusionRect())).toBe(false);
        expect(overlaps(mark.frame, captionBarRect())).toBe(false);
      }
    }
  }
});

test("rejects a quote that cannot stay inside the safe zone or on the word clock", () => {
  const tokens = Array.from({ length: 40 }, () => "abcdefgh");
  const stamps = tokens.map((word, index) => ({
    word,
    start_ms: index * 100,
    end_ms: index * 100 + 80,
  }));
  expect(() =>
    RedactedDocReveal({
      citation: "2021 MT 142 at paragraph 18",
      quote: tokens.join(" "),
      wordTimestamps: stamps,
      sceneStartMs: 0,
      frame: 0,
      sceneId: "scene_overflow",
    }),
  ).toThrow(/leaves the safe zone/);

  expect(() => reveal({ quote: "alpha beta", wordTimestamps: MULTI_STAMPS })).toThrow(/one-to-one/);
  expect(() =>
    reveal({
      wordTimestamps: MULTI_STAMPS.map((stamp, index) =>
        index === 1 ? { ...stamp, word: "BRAVO" } : stamp,
      ),
    }),
  ).toThrow(/quote token/);
  expect(() =>
    reveal({
      wordTimestamps: [
        { word: "alpha", start_ms: 1000, end_ms: 1500 },
        { word: "bravo", start_ms: 1400, end_ms: 1600 },
        ...MULTI_STAMPS.slice(2),
      ],
    }),
  ).toThrow(/must not overlap/);
  expect(() => reveal({ citation: "  2021 MT 142  " })).toThrow(/citation/);
  expect(() => reveal({ citation: `${"A".repeat(94)} locator` })).toThrow(/citation does not fit/);
  expect(() => reveal({ frame: 1.5 })).toThrow(/frame/);
  expect(() => reveal({ sceneStartMs: -1 })).toThrow(/sceneStartMs/);
  expect(() =>
    RedactedDocReveal({
      citation: "2021 MT 142 at paragraph 18",
      quote: "toolong",
      wordTimestamps: [{ word: "toolong", start_ms: 0, end_ms: 100 }],
      sceneStartMs: 0,
      frame: 0,
      sceneId: "scene_wide",
      columnWidthPx: CHAR_WIDTH_PX,
    }),
  ).toThrow(/wider than the quote column/);
  expect(() =>
    reveal({
      quoteRedactions: [
        { startWord: 2, endWord: 4 },
        { startWord: 1, endWord: 2 },
      ],
    }),
  ).toThrow(/must not overlap/);
  expect(() => reveal({ affidavitBarCount: 5 })).toThrow(/affidavitBarCount/);
  expect(() => reveal({ isEndScreen: "yes" as unknown as boolean })).toThrow(/isEndScreen/);
});
