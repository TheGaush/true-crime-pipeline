import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import {
  ARROW_DRAW_FRAMES,
  ARROW_HEAD,
  CAMERA_SHUTTER_CUE,
  CAMERA_SHUTTER_DBTP,
  CAMERA_SHUTTER_DURATION_SAMPLES,
  CAMERA_SHUTTER_GAIN_UNITS,
  COOLDOWN_SAMPLES,
  END_SCREEN_MASK_H,
  EVIDENCE_CRIMSON,
  EVIDENCE_MATCH_CARD_ID,
  EVIDENCE_MATCH_CARD_OWNER,
  EVIDENCE_MOTIF_NUMBER,
  EXHIBIT_OBJECT_FIT,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  FROZEN_CATALOG_SLOT_12,
  GUTTER_W,
  INK,
  MAT,
  MAX_LABEL_WORDS,
  MIX_SAMPLE_RATE_HZ,
  PAPER_BG,
  SAFE_MARGIN_X,
  SAFE_MARGIN_Y,
  SAFE_PADDING_BOTTOM,
  SAFE_PADDING_TOP,
  SAMPLES_PER_FRAME,
  SHUTTER_FRAME_LEFT,
  SHUTTER_FRAME_RIGHT,
  SLATE,
  TRUE_PEAK_CEILING_DBTP,
  TRUE_PEAK_CEILING_UNITS,
  EvidenceMatchCard,
  EvidenceMatchCardError,
  arrowProgress,
  containFit,
  layoutEvidenceMatchCard,
  mixOffsetMs,
  rectInside,
  rectsOverlap,
  walkMatch,
  type EvidenceMatchCardProps,
  type ForensicExhibit,
  type MatchNode,
} from "../../src/motifs/EvidenceMatchCard.tsx";

const models = readFileSync(new URL("../../../shared-contracts-ts/src/models.ts", import.meta.url), "utf8");
const sql = readFileSync(new URL("../../../../schema/pipeline.sql", import.meta.url), "utf8");

const WIDE: ForensicExhibit = {
  exhibit_id: "exhibit_porch",
  fact_id: "case_golden_01_20min_fact_clue",
  label: "Porch light at the front steps",
  intrinsic_width: 1920,
  intrinsic_height: 1080,
  src: "exhibit/porch-light-wide",
};

const TALL: ForensicExhibit = {
  exhibit_id: "exhibit_clock",
  fact_id: "case_golden_01_20min_fact_affidavit",
  label: "Dispatch clock at 2:14 a.m.",
  intrinsic_width: 1080,
  intrinsic_height: 1920,
  src: "exhibit/dispatch-clock-tall",
};

function props(frame: number, extra: Partial<EvidenceMatchCardProps> = {}): EvidenceMatchCardProps {
  return {
    left: WIDE,
    right: TALL,
    frame,
    sceneId: "ep_golden_01_20min",
    ...extra,
  };
}

function node(root: MatchNode, key: string, value: string): MatchNode {
  const found = walkMatch(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function catalogNames(source: string): string[] {
  const mvp = namedList(source, "MVP_MOTIFS");
  const catalog = namedList(source, "CATALOG_MOTIFS");
  return [...mvp, ...catalog];
}

function namedList(source: string, name: string): string[] {
  const match = source.match(new RegExp(`export const ${name} = \\[([\\s\\S]*?)\\] as const`));
  if (!match?.[1]) throw new Error(`missing ${name}`);
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1] ?? "");
}

test("EvidenceMatchCard is motif 12 and leaves the frozen registry alone", () => {
  expect(EVIDENCE_MOTIF_NUMBER).toBe(12);
  expect(EVIDENCE_MATCH_CARD_ID).toBe("EvidenceMatchCard");
  expect(EVIDENCE_MATCH_CARD_OWNER).toBe("render_catalog");
  expect(FROZEN_CATALOG_SLOT_12).toBe("ChapterSlateTransition");
  expect(SAFE_MARGIN_X).toBe(96);
  expect(SAFE_MARGIN_Y).toBe(54);

  const catalog = catalogNames(models);
  expect(catalog[11]).toBe("ChapterSlateTransition");
  expect(catalog).not.toContain(EVIDENCE_MATCH_CARD_ID);
  expect(catalog.slice(0, 4)).toEqual([
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
  ]);
  expect(sql).toContain("('ChapterSlateTransition', 'render_catalog', 0)");
  expect(sql).not.toContain("EvidenceMatchCard");

  const source = readFileSync(new URL("../../src/motifs/EvidenceMatchCard.tsx", import.meta.url), "utf8");
  expect(source).toContain('EXHIBIT_OBJECT_FIT = "contain"');
  expect(source).toContain("objectFit: EXHIBIT_OBJECT_FIT");
  expect(source).toContain(EVIDENCE_CRIMSON);
  expect(source).toContain(CAMERA_SHUTTER_CUE);
  expect(source).not.toMatch(/feTurbulence|feDisplacementMap/);
  expect(source).not.toMatch(/from ["'][^"']*(SfxRegistry|safe_zone|StickFigure)/);
  expect(source).not.toMatch(/\bfetch\s*\(/);
});

test("mismatched aspects share one dossier box and contain instead of stretching", () => {
  const layout = layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES));
  expect(layout.left.frameBox.width).toBe(layout.right.frameBox.width);
  expect(layout.left.frameBox.height).toBe(layout.right.frameBox.height);
  expect(layout.left.frameBox.y).toBe(layout.right.frameBox.y);
  expect(layout.left.frameBox.x - layout.content.x).toBe(
    layout.content.x + layout.content.width - (layout.right.frameBox.x + layout.right.frameBox.width),
  );
  expect(layout.left.well.width).toBe(layout.right.well.width);
  expect(layout.left.well.height).toBe(layout.right.well.height);
  expect(layout.content.x).toBe(SAFE_MARGIN_X);
  expect(layout.content.y).toBe(SAFE_PADDING_TOP);
  expect(layout.gutter.width).toBeGreaterThanOrEqual(GUTTER_W);

  const wide = layout.left;
  const tall = layout.right;
  expect(wide.fitted.height).toBeLessThan(wide.well.height);
  expect(wide.fitted.width).toBe(wide.well.width);
  expect(tall.fitted.width).toBeLessThan(tall.well.width);
  expect(tall.fitted.height).toBe(tall.well.height);
  expect(Math.abs(wide.fitted.width / wide.fitted.height - 16 / 9)).toBeLessThan(0.01);
  expect(Math.abs(tall.fitted.width / tall.fitted.height - 9 / 16)).toBeLessThan(0.01);
  expect(wide.fittedLocal.offsetX).toBe(0);
  expect(wide.fittedLocal.offsetY).toBe(Math.floor((wide.well.height - wide.fitted.height) / 2));
  expect(tall.fittedLocal.offsetY).toBe(0);
  expect(tall.fittedLocal.offsetX).toBe(Math.floor((tall.well.width - tall.fitted.width) / 2));
  expect(rectInside(wide.fitted, wide.well)).toBe(true);
  expect(rectInside(tall.fitted, tall.well)).toBe(true);
  expect(wide.objectFit).toBe(EXHIBIT_OBJECT_FIT);
  expect(tall.objectFit).toBe(EXHIBIT_OBJECT_FIT);
  expect(containFit(wide.well.width, wide.well.height, 1920, 1080)).toEqual(wide.fittedLocal);
  expect(containFit(tall.well.width, tall.well.height, 1080, 1920)).toEqual(tall.fittedLocal);

  const swapped = layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES, { left: TALL, right: WIDE }));
  expect(swapped.left.frameBox).toEqual(layout.left.frameBox);
  expect(swapped.right.frameBox).toEqual(layout.right.frameBox);
  expect(swapped.left.fittedLocal).toEqual(layout.right.fittedLocal);
  expect(swapped.right.fittedLocal).toEqual(layout.left.fittedLocal);

  const extreme = layoutEvidenceMatchCard(
    props(0, {
      left: { ...WIDE, intrinsic_width: 3, intrinsic_height: 1, src: "exhibit/panorama" },
      right: { ...TALL, intrinsic_width: 1, intrinsic_height: 4, src: "exhibit/strip" },
    }),
  );
  expect(extreme.left.frameBox).toEqual(layout.left.frameBox);
  expect(extreme.right.frameBox).toEqual(layout.right.frameBox);
  expect(rectInside(extreme.left.fitted, extreme.left.well)).toBe(true);
  expect(rectInside(extreme.right.fitted, extreme.right.well)).toBe(true);
  expect(extreme.left.fitted.width).toBe(extreme.left.well.width);
  expect(extreme.left.fitted.height).toBeLessThan(extreme.left.well.height);
  expect(extreme.right.fitted.height).toBe(extreme.right.well.height);
  expect(extreme.right.fitted.width).toBeLessThan(extreme.right.well.width);

  const strip = layoutEvidenceMatchCard(
    props(0, {
      left: { ...WIDE, intrinsic_width: 10_000, intrinsic_height: 1 },
      right: { ...TALL, intrinsic_width: 1, intrinsic_height: 10_000 },
    }),
  );
  expect(strip.left.frameBox.width).toBe(strip.right.frameBox.width);
  expect(strip.left.fitted.height).toBeGreaterThanOrEqual(1);
  expect(strip.right.fitted.width).toBeGreaterThanOrEqual(1);
  expect(rectInside(strip.left.fitted, strip.left.well)).toBe(true);
  expect(rectInside(strip.right.fitted, strip.right.well)).toBe(true);

  for (const rect of [wide.frameBox, tall.frameBox, wide.fitted, tall.fitted, wide.caption, tall.caption]) {
    expect(rect.x).toBeGreaterThanOrEqual(SAFE_MARGIN_X);
    expect(rect.y).toBeGreaterThanOrEqual(SAFE_MARGIN_Y);
    expect(rect.x + rect.width).toBeLessThanOrEqual(FRAME_WIDTH - SAFE_MARGIN_X);
    expect(rect.y + rect.height).toBeLessThanOrEqual(FRAME_HEIGHT - SAFE_MARGIN_Y);
  }
  expect(rectsOverlap(layout.left.frameBox, layout.captionBar)).toBe(false);
  expect(rectsOverlap(layout.right.frameBox, layout.exclusion)).toBe(false);
  expect(layout.left.fact_id).toBe(WIDE.fact_id);
  expect(layout.right.fact_id).toBe(TALL.fact_id);
  expect(layout.left.display).toBe(WIDE.label);
  expect(layout.right.wordCount).toBeLessThanOrEqual(MAX_LABEL_WORDS);
});

test("crimson comparison arrows draw on inside the gutter", () => {
  const start = layoutEvidenceMatchCard(props(0));
  expect(start.arrows.progress).toBe(0);
  expect(start.arrows.revealed).toBe(0);
  expect(start.arrows.left.box.width).toBe(0);
  expect(start.arrows.right.box.width).toBe(0);
  expect(start.arrows.left.color).toBe(EVIDENCE_CRIMSON);
  expect(rectsOverlap(start.arrows.left.box, start.left.frameBox)).toBe(false);

  const mid = layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES / 2));
  expect(arrowProgress(ARROW_DRAW_FRAMES / 2)).toBe(0.5);
  expect(mid.arrows.revealed).toBe(Math.round(mid.arrows.full * 0.5));
  expect(mid.arrows.left.box.width).toBe(mid.arrows.right.box.width);
  expect(mid.arrows.left.box.width).toBeGreaterThan(0);
  expect(mid.arrows.left.box.width).toBeLessThan(mid.arrows.full);

  const done = layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES));
  expect(done.arrows.progress).toBe(1);
  expect(done.arrows.revealed).toBe(done.arrows.full);
  expect(done.arrows.revealed).toBeGreaterThanOrEqual(ARROW_HEAD);
  const leftInset = done.arrows.left.box.x - done.gutter.x;
  const rightInset = done.gutter.x + done.gutter.width - (done.arrows.right.box.x + done.arrows.right.box.width);
  expect(leftInset).toBe(rightInset);
  expect(rectsOverlap(done.arrows.left.box, done.left.frameBox)).toBe(false);
  expect(rectsOverlap(done.arrows.right.box, done.right.frameBox)).toBe(false);
  expect(rectInside(done.arrows.left.box, done.gutter)).toBe(true);
  expect(rectInside(done.arrows.right.box, done.gutter)).toBe(true);

  let previous = -1;
  for (let frame = 0; frame <= ARROW_DRAW_FRAMES; frame += 1) {
    const revealed = layoutEvidenceMatchCard(props(frame)).arrows.revealed;
    expect(revealed).toBeGreaterThanOrEqual(previous);
    previous = revealed;
  }
  expect(layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES + 12)).arrows.revealed).toBe(done.arrows.full);

  const tree = EvidenceMatchCard(props(ARROW_DRAW_FRAMES));
  const arrows = walkMatch(tree).filter((item) => item.dataset.slot === "comparison-arrow");
  expect(arrows.map((item) => item.dataset.direction)).toEqual(["left", "right"]);
  expect(arrows.every((item) => item.dataset.revealed === String(done.arrows.revealed))).toBe(true);
  const painted = walkMatch(tree).filter((item) => item.dataset.slot === "arrow-shaft" || item.dataset.slot === "arrow-head");
  expect(painted.length).toBeGreaterThan(0);
  for (const item of painted) {
    const style = JSON.stringify(item.props.style);
    expect(style).toContain(EVIDENCE_CRIMSON);
  }
  const crimsonNodes = walkMatch(tree).filter((item) => JSON.stringify(item.props.style).includes(EVIDENCE_CRIMSON));
  expect(crimsonNodes.every((item) => item.dataset.slot === "arrow-shaft" || item.dataset.slot === "arrow-head")).toBe(true);
  expect(JSON.stringify(tree)).not.toMatch(/feTurbulence|feDisplacementMap/);
});

test("camera_shutter cues land on the 48 kHz clock with a 60 ms cooldown", () => {
  const early = layoutEvidenceMatchCard(props(0));
  expect(early.cues.map((cue) => cue.side)).toEqual(["left", "right"]);
  expect(early.cuesStarted.map((cue) => cue.side)).toEqual(["left"]);
  expect(early.suppressed).toEqual([]);
  expect(early.cues[0]?.start_frame).toBe(SHUTTER_FRAME_LEFT);
  expect(early.cues[1]?.start_frame).toBe(SHUTTER_FRAME_RIGHT);
  expect(SHUTTER_FRAME_RIGHT - SHUTTER_FRAME_LEFT).toBe(2);

  const settled = layoutEvidenceMatchCard(props(SHUTTER_FRAME_RIGHT));
  expect(settled.cuesStarted).toHaveLength(2);
  expect(settled.cues.map((cue) => cue.cue_id)).toEqual(early.cues.map((cue) => cue.cue_id));
  let overlap = 0;
  for (const cue of settled.cues) {
    expect(cue.cue).toBe(CAMERA_SHUTTER_CUE);
    expect(cue.scene_id).toBe("ep_golden_01_20min");
    expect(cue.sample_rate_hz).toBe(MIX_SAMPLE_RATE_HZ);
    expect(cue.start_sample).toBe(cue.start_frame * SAMPLES_PER_FRAME);
    expect(cue.duration_samples).toBe(CAMERA_SHUTTER_DURATION_SAMPLES);
    expect(cue.duration_samples).toBe(90 * 48);
    expect(cue.cooldown_ms).toBe(60);
    expect(cue.gain_units).toBe(CAMERA_SHUTTER_GAIN_UNITS);
    expect(cue.gain_unit_scale).toBe(1_000_000_000);
    expect(cue.peak_dbtp).toBe(CAMERA_SHUTTER_DBTP);
    expect(cue.peak_dbtp).toBeLessThanOrEqual(TRUE_PEAK_CEILING_DBTP);
    expect(cue.tapered).toBe(false);
    expect(cue.burst).toBe(false);
    expect(cue.gain_units).toBeLessThanOrEqual(TRUE_PEAK_CEILING_UNITS);
  }
  const first = settled.cues[0];
  const second = settled.cues[1];
  if (!first || !second) throw new Error("missing shutter cue");
  expect(first.offset_ms).toBe(0);
  expect(first.offset_ms).toBe(mixOffsetMs(0));
  expect(second.start_sample).toBe(3200);
  expect(second.offset_ms).toBe(66.666667);
  expect(second.offset_ms).toBe(mixOffsetMs(3200));
  expect(second.start_sample - first.start_sample).toBeGreaterThanOrEqual(COOLDOWN_SAMPLES);
  expect(second.start_sample).toBeLessThan(first.start_sample + first.duration_samples);
  overlap = first.gain_units + second.gain_units;
  expect(overlap).toBeLessThanOrEqual(TRUE_PEAK_CEILING_UNITS);
  expect(SAMPLES_PER_FRAME).toBe(1600);

  const tree = EvidenceMatchCard(props(SHUTTER_FRAME_RIGHT));
  const shutters = walkMatch(tree).filter((item) => item.dataset.slot === "camera-shutter");
  expect(shutters.map((item) => item.dataset["start-sample"])).toEqual(settled.cues.map((cue) => String(cue.start_sample)));
  expect(shutters.every((item) => item.dataset.cue === CAMERA_SHUTTER_CUE)).toBe(true);

  const tight = layoutEvidenceMatchCard(props(2, { shutterFrameLeft: 0, shutterFrameRight: 1 }));
  expect(tight.cues.map((cue) => cue.side)).toEqual(["left"]);
  expect(tight.suppressed).toEqual([
    {
      cue: CAMERA_SHUTTER_CUE,
      exhibit_id: TALL.exhibit_id,
      side: "right",
      start_frame: 1,
      start_sample: SAMPLES_PER_FRAME,
      reason: "cooldown",
    },
  ]);
});

test("the safe-zone frame pads 96px horizontally and keeps the end screen clear", () => {
  const tree = EvidenceMatchCard(props(ARROW_DRAW_FRAMES));
  expect(tree.dataset["safe-zone"]).toBe("css-contained");
  expect(tree.dataset.motif).toBe(EVIDENCE_MATCH_CARD_ID);
  expect(tree.dataset["motif-number"]).toBe("12");
  expect(tree.dataset["frozen-catalog-slot"]).toBe(FROZEN_CATALOG_SLOT_12);
  expect(tree.dataset["margin-x"]).toBe("96");
  expect(tree.dataset["margin-y"]).toBe("54");
  expect(tree.dataset["texture-overlay"]).toBe("off");
  expect(tree.dataset["apply-grade"]).toBe("true");
  expect(tree.props.style.width).toBe(FRAME_WIDTH);
  expect(tree.props.style.height).toBe(FRAME_HEIGHT);
  expect(tree.props.style.paddingTop).toBe(SAFE_PADDING_TOP);
  expect(tree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM);
  expect(tree.props.style.paddingLeft).toBe(SAFE_MARGIN_X);
  expect(tree.props.style.paddingRight).toBe(SAFE_MARGIN_X);
  expect(tree.props.style.overflow).toBe("hidden");
  expect(tree.props.style.background).toBe(PAPER_BG);
  expect(node(tree, "exclusion", "bottom-right").props.style).toMatchObject({ width: "22%", height: "14%" });

  const images = walkMatch(tree).filter((item) => item.dataset.slot === "exhibit-image");
  expect(images).toHaveLength(2);
  expect(images[0]?.props.style.objectFit).toBe("contain");
  expect(images[1]?.props.style.objectFit).toBe("contain");
  expect(images[0]?.props.style.background).toBe(SLATE);
  expect(images[0]?.props.style.width).toBe(layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES)).left.fitted.width);
  expect(images[1]?.props.style.height).toBe(layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES)).right.fitted.height);
  const wells = walkMatch(tree).filter((item) => item.dataset.slot === "exhibit-well");
  expect(wells[0]?.props.style.background).toBe(MAT);
  expect(wells[0]?.props.style.overflow).toBe("hidden");
  expect(node(tree, "slot", "dossier").props.style.border).toBe(`2px solid ${INK}`);
  expect(node(tree, "slot", "caption").props.children).toBe(WIDE.label);

  const endLayout = layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES, { isEndScreen: true }));
  expect(endLayout.endScreenMask).not.toBeNull();
  if (!endLayout.endScreenMask) throw new Error("missing end-screen mask");
  expect(endLayout.left.frameBox.height).toBeLessThan(layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES)).left.frameBox.height);
  expect(endLayout.left.frameBox.height).toBe(endLayout.right.frameBox.height);
  expect(endLayout.left.frameBox.width).toBe(endLayout.right.frameBox.width);
  expect(rectsOverlap(endLayout.left.frameBox, endLayout.endScreenMask)).toBe(false);
  expect(rectsOverlap(endLayout.right.frameBox, endLayout.endScreenMask)).toBe(false);
  expect(endLayout.left.frameBox.y + endLayout.left.frameBox.height).toBeLessThanOrEqual(endLayout.endScreenMask.y);
  expect(endLayout.endScreenMask.height).toBe(END_SCREEN_MASK_H);

  const endTree = EvidenceMatchCard(props(ARROW_DRAW_FRAMES, { isEndScreen: true }));
  expect(endTree.dataset["end-screen"]).toBe("true");
  expect(endTree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM + END_SCREEN_MASK_H);
  expect(node(endTree, "mask", "end-screen-card").props.style.overflow).toBe("hidden");
});

test("a long caption clamps to 12 words and bad exhibits are rejected", () => {
  const words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen"];
  const layout = layoutEvidenceMatchCard(
    props(0, {
      left: { ...WIDE, label: words.join(" ") },
    }),
  );
  expect(layout.left.clamped).toBe(true);
  expect(layout.left.wordCount).toBe(MAX_LABEL_WORDS);
  expect(layout.left.display).toBe(words.slice(0, MAX_LABEL_WORDS).join(" "));
  expect(layout.right.clamped).toBe(false);

  const tree = EvidenceMatchCard(props(0, { left: { ...WIDE, label: words.join(" ") } }));
  const caption = walkMatch(tree).find((item) => item.dataset.slot === "caption" && item.dataset.side === "left");
  if (!caption) throw new Error("missing caption");
  expect(caption.dataset.clamped).toBe("true");
  expect(caption.dataset["word-count"]).toBe("12");
  expect(caption.props.children).toBe(layout.left.display);
  expect(caption.props.style.overflow).toBe("hidden");

  expect(() => layoutEvidenceMatchCard(props(0, { left: { ...WIDE, label: "   " } }))).toThrow(/label/);
  expect(() => layoutEvidenceMatchCard(props(0, { left: { ...WIDE, fact_id: "bad id" } }))).toThrow(/fact_id/);
  expect(() => layoutEvidenceMatchCard(props(0, { left: { ...WIDE, src: "https://example.com/plate.png" } }))).toThrow(
    /offline asset id/,
  );
  expect(() => layoutEvidenceMatchCard(props(0, { left: { ...WIDE, intrinsic_width: 0 } }))).toThrow(/intrinsic_width/);
  expect(() => layoutEvidenceMatchCard(props(0, { right: { ...TALL, exhibit_id: WIDE.exhibit_id } }))).toThrow(
    /exhibit ids/,
  );
  expect(() => layoutEvidenceMatchCard(props(-1))).toThrow(EvidenceMatchCardError);
  expect(() => layoutEvidenceMatchCard(props(0, { shutterFrameRight: -1 }))).toThrow(/shutterFrameRight/);

  const calls: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (input) => {
    calls.push(String(input));
    throw new Error("fetch");
  };
  try {
    layoutEvidenceMatchCard(props(4));
    EvidenceMatchCard(props(4));
  } finally {
    globalThis.fetch = original;
  }
  expect(calls).toEqual([]);

  const again = layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES));
  expect(JSON.stringify(again)).toBe(JSON.stringify(layoutEvidenceMatchCard(props(ARROW_DRAW_FRAMES))));
});
