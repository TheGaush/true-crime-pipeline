import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import { CATALOG_MOTIFS, MOTIF_REGISTRY_V1 } from "../../../shared-contracts-ts/src/models.ts";
import {
  BEZEL_BG,
  BUBBLE_INBOUND_BG,
  BUBBLE_MAX_W,
  BUBBLE_OUTBOUND_BG,
  COOLDOWN_SAMPLES,
  FRAME_FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  HIGHLIGHT_BORDER,
  IDLE_BORDER,
  MIX_SAMPLE_RATE_HZ,
  PAPER_BG,
  SAFE_PADDING_BOTTOM,
  SAFE_PADDING_TOP,
  SAMPLES_PER_FRAME,
  SCREEN_BG,
  SCROLL_EASE_FRAMES,
  SMS_MOTIF_NUMBER,
  SMS_PHONE_THREAD_ID,
  SMS_PHONE_THREAD_OWNER,
  STATUS_LABEL,
  TAP_STRIDE_FRAMES,
  THREAD_PAD,
  TYPING_TAP_CUE,
  TYPING_TAP_DURATION_SAMPLES,
  TYPING_TAP_GAIN_UNITS,
  SmsPhoneThread,
  SmsPhoneThreadError,
  layoutSmsPhoneThread,
  rectInside,
  rectsOverlap,
  walkSms,
  type PlacedBubble,
  type SmsMessage,
  type SmsNode,
  type SmsPhoneThreadProps,
} from "../../src/motifs/SmsPhoneThread.tsx";

const pack = JSON.parse(
  readFileSync(new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url), "utf8"),
) as {
  temporal_fact_ledger: { fact_id: string; datetime_iso: string; event_summary: string }[];
};

const facts = [...pack.temporal_fact_ledger].sort((left, right) => {
  const delta = Date.parse(left.datetime_iso) - Date.parse(right.datetime_iso);
  if (delta !== 0) return delta;
  return left.fact_id < right.fact_id ? -1 : 1;
});

const GOLDEN: SmsMessage[] = facts.map((fact, index) => ({
  message_id: `sms_golden_${index + 1}`,
  fact_id: fact.fact_id,
  party: index % 2 === 0 ? "inbound" : "outbound",
  body: fact.event_summary,
  appear_frame: 30 * (index + 1),
  typing_frames: 12,
}));

const HIGHLIGHT_ID = "sms_golden_2";

const TWELVE: SmsMessage[] = Array.from({ length: 12 }, (_, index) => {
  const fact = facts[index % facts.length];
  if (!fact) throw new Error("golden pack has no facts");
  return {
    message_id: `sms_${String(index + 1).padStart(2, "0")}`,
    fact_id: fact.fact_id,
    party: index % 2 === 0 ? "inbound" : "outbound",
    body: `Line ${String(index + 1).padStart(2, "0")}`,
    appear_frame: (index + 1) * 18,
    typing_frames: 9,
  };
});

function goldenProps(frame: number, extra: Partial<SmsPhoneThreadProps> = {}): SmsPhoneThreadProps {
  return {
    messages: GOLDEN,
    frame,
    sceneId: "ep_golden_01_20min",
    highlightMessageId: HIGHLIGHT_ID,
    ...extra,
  };
}

function node(root: SmsNode, key: string, value: string): SmsNode {
  const found = walkSms(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function fullyVisible(bubble: PlacedBubble): boolean {
  return bubble.visible !== null && !bubble.clipped;
}

test("SmsPhoneThread is motif 6 and does not amend the frozen registry", () => {
  expect(SMS_MOTIF_NUMBER).toBe(6);
  expect(SMS_PHONE_THREAD_ID).toBe("SmsPhoneThread");
  expect(SMS_PHONE_THREAD_OWNER).toBe("render_catalog");
  expect(CATALOG_MOTIFS[5]).toBe("AnimatedMapRoute");
  expect(CATALOG_MOTIFS).not.toContain(SMS_PHONE_THREAD_ID);
  expect(MOTIF_REGISTRY_V1.map((entry) => entry.motif_component)).toEqual([
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
  ]);

  const source = readFileSync(new URL("../../src/motifs/SmsPhoneThread.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/function SafeZoneLayout/);
  expect(source).not.toMatch(/feTurbulence|feDisplacementMap|Illustrative2KPanZoom|#C92A2A/);
  expect(source).not.toMatch(/from ["'][^"']*sfx\/SfxRegistry/);
  expect(source).not.toMatch(/from ["'][^"']*safe_zone/);

  const sql = readFileSync(new URL("../../../../schema/pipeline.sql", import.meta.url), "utf8");
  expect(sql).toContain("('AnimatedMapRoute',       'render_catalog', 0)");
  expect(sql).not.toContain("SmsPhoneThread");
});

test("golden ledger thread syncs typing, highlight, and typing_tap inside the bezel", () => {
  expect(facts.map((fact) => fact.fact_id)).toEqual([
    "case_golden_01_20min_fact_affidavit",
    "case_golden_01_20min_fact_clue",
    "case_golden_01_20min_fact_news",
    "case_golden_01_20min_fact_ruling",
  ]);

  const during = layoutSmsPhoneThread(goldenProps(54));
  expect(during.typing?.message_id).toBe(HIGHLIGHT_ID);
  expect(during.typing?.window_start).toBe(48);
  expect(during.typing?.window_end).toBe(60);
  expect(during.bubbles.map((bubble) => bubble.message_id)).toEqual(["sms_golden_1"]);
  expect(during.bubbles.every((bubble) => bubble.highlight)).toBe(false);
  const clueTaps = during.cues.filter((cue) => cue.message_id === HIGHLIGHT_ID);
  expect(clueTaps.map((cue) => cue.start_frame)).toEqual([48, 51, 54, 57]);
  expect(during.cuesStarted.filter((cue) => cue.message_id === HIGHLIGHT_ID).map((cue) => cue.start_frame)).toEqual([
    48, 51, 54,
  ]);

  const shown = layoutSmsPhoneThread(goldenProps(60));
  expect(shown.typing).toBeNull();
  expect(shown.overflows).toBe(false);
  expect(shown.scrollOffset).toBe(0);
  expect(shown.bubbles.map((bubble) => bubble.fact_id)).toEqual(facts.slice(0, 2).map((fact) => fact.fact_id));
  const highlighted = shown.bubbles.find((bubble) => bubble.message_id === HIGHLIGHT_ID);
  if (!highlighted) throw new Error("missing highlighted bubble");
  expect(highlighted.highlight).toBe(true);
  expect(highlighted.body).toBe("The affidavit describes a porch light at the front steps.");
  expect(highlighted.display.replaceAll("\n", " ")).toBe(highlighted.body);
  expect(fullyVisible(highlighted)).toBe(true);
  expect(shown.bubbles.filter((bubble) => bubble.highlight).map((bubble) => bubble.message_id)).toEqual([HIGHLIGHT_ID]);

  const settled = layoutSmsPhoneThread(goldenProps(120 + SCROLL_EASE_FRAMES));
  expect(settled.bubbles).toHaveLength(4);
  expect(settled.overflows).toBe(false);
  for (const [index, bubble] of settled.bubbles.entries()) {
    const fact = facts[index];
    if (!fact) throw new Error("missing fact");
    expect(bubble.fact_id).toBe(fact.fact_id);
    expect(bubble.body).toBe(fact.event_summary);
    expect(bubble.display.replaceAll("\n", " ")).toBe(fact.event_summary);
    expect(bubble.truncated).toBe(false);
    expect(bubble.party).toBe(index % 2 === 0 ? "inbound" : "outbound");
    expect(fullyVisible(bubble)).toBe(true);
    expect(rectInside(bubble.visible ?? bubble.page, settled.screen)).toBe(true);
    expect(rectInside(bubble.page, settled.phone)).toBe(true);
    if (bubble.party === "inbound") expect(bubble.box.x).toBe(THREAD_PAD);
    else expect(bubble.box.x + bubble.box.width).toBe(settled.screen.width - THREAD_PAD);
  }
  expect(rectsOverlap(settled.phone, settled.captionBar)).toBe(false);
  expect(rectsOverlap(settled.phone, settled.exclusion)).toBe(false);
  expect(rectInside(settled.phone, settled.content)).toBe(true);

  for (let index = 1; index < settled.cues.length; index += 1) {
    const previous = settled.cues[index - 1];
    const cue = settled.cues[index];
    if (!previous || !cue) throw new Error("missing cue");
    expect(cue.start_sample - previous.start_sample).toBeGreaterThanOrEqual(COOLDOWN_SAMPLES);
  }
  expect(settled.cues.length).toBe(16);
  expect(settled.suppressed).toEqual([]);
  for (const cue of settled.cues) {
    expect(cue.cue).toBe(TYPING_TAP_CUE);
    expect(cue.scene_id).toBe("ep_golden_01_20min");
    expect(cue.sample_rate_hz).toBe(MIX_SAMPLE_RATE_HZ);
    expect(cue.start_sample).toBe(cue.start_frame * SAMPLES_PER_FRAME);
    expect(cue.offset_ms).toBe(cue.start_sample / (MIX_SAMPLE_RATE_HZ / 1_000));
    expect(cue.duration_samples).toBe(TYPING_TAP_DURATION_SAMPLES);
    expect(cue.duration_samples).toBeLessThan(COOLDOWN_SAMPLES);
    expect(cue.cooldown_ms).toBe(60);
    expect(cue.tapered).toBe(false);
    expect(cue.burst).toBe(false);
    expect(cue.gain_units).toBe(TYPING_TAP_GAIN_UNITS);
    expect(cue.gain_units).toBeLessThanOrEqual(TYPING_TAP_GAIN_UNITS);
    expect(cue.start_frame % TAP_STRIDE_FRAMES).toBe(0);
  }
  expect(FRAME_FPS).toBe(30);
  expect(SAMPLES_PER_FRAME).toBe(1600);

  const early = layoutSmsPhoneThread(goldenProps(0));
  expect(early.cues.map((cue) => cue.cue_id)).toEqual(settled.cues.map((cue) => cue.cue_id));
  expect(early.cuesStarted).toEqual([]);

  const tree = SmsPhoneThread(goldenProps(60));
  expect(tree.dataset["safe-zone"]).toBe("css-contained");
  expect(tree.dataset.motif).toBe(SMS_PHONE_THREAD_ID);
  expect(tree.dataset["motif-number"]).toBe("6");
  expect(tree.dataset.owner).toBe(SMS_PHONE_THREAD_OWNER);
  expect(tree.dataset["end-screen"]).toBe("false");
  expect(tree.props.style.paddingTop).toBe(SAFE_PADDING_TOP);
  expect(tree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM);
  expect(tree.props.style.width).toBe(FRAME_WIDTH);
  expect(tree.props.style.height).toBe(FRAME_HEIGHT);
  expect(tree.props.style.overflow).toBe("hidden");
  expect(tree.props.style.background).toBe(PAPER_BG);

  const bezel = node(tree, "slot", "bezel");
  const screen = node(tree, "slot", "screen");
  const thread = node(tree, "slot", "thread");
  expect(bezel.props.style.background).toBe(BEZEL_BG);
  expect(bezel.props.style.overflow).toBe("hidden");
  expect(bezel.props.style.background).not.toBe(PAPER_BG);
  expect(screen.props.style.background).toBe(SCREEN_BG);
  expect(screen.props.style.overflow).toBe("hidden");
  expect(screen.dataset.scroll).toBe("0");
  expect(thread.props.style.top).toBe(0);
  expect(node(tree, "slot", "status").props.children).toBe(STATUS_LABEL);
  expect(node(tree, "exclusion", "bottom-right").props.style).toMatchObject({ width: "22%", height: "14%" });

  const bubbles = walkSms(tree).filter((item) => item.dataset.slot === "bubble");
  expect(bubbles).toHaveLength(2);
  const clueNode = bubbles.find((item) => item.dataset["message-id"] === HIGHLIGHT_ID);
  if (!clueNode) throw new Error("missing clue bubble");
  expect(clueNode.dataset.highlight).toBe("true");
  expect(clueNode.dataset["fact-id"]).toBe("case_golden_01_20min_fact_clue");
  expect(clueNode.props.style.background).toBe(BUBBLE_OUTBOUND_BG);
  expect(clueNode.props.style.border).toBe(`2px solid ${HIGHLIGHT_BORDER}`);
  expect(clueNode.props.style.overflow).toBe("hidden");
  expect(bubbles[0]?.props.style.background).toBe(BUBBLE_INBOUND_BG);
  expect(bubbles[0]?.props.style.border).toBe(`2px solid ${IDLE_BORDER}`);
  expect(walkSms(tree).some((item) => item.dataset.slot === "typing")).toBe(false);

  const duringTree = SmsPhoneThread(goldenProps(54));
  expect(node(duringTree, "slot", "typing").dataset["message-id"]).toBe(HIGHLIGHT_ID);
  expect(node(duringTree, "slot", "typing").dataset.cue).toBe(TYPING_TAP_CUE);
  const tapNodes = walkSms(duringTree).filter((item) => item.dataset.slot === "typing-tap");
  expect(tapNodes.map((item) => item.dataset["start-frame"])).toEqual(during.cues.map((cue) => String(cue.start_frame)));
  expect(tapNodes.every((item) => item.dataset.cue === TYPING_TAP_CUE)).toBe(true);
  expect(JSON.stringify(tree)).not.toMatch(/feTurbulence|feDisplacementMap|#C92A2A/);
});

test("ten or more messages auto-scroll inside the clipped bezel", () => {
  const lastAppear = 12 * 18;
  const props = {
    messages: TWELVE,
    frame: lastAppear + SCROLL_EASE_FRAMES,
    sceneId: "ep_golden_01_20min",
  } satisfies SmsPhoneThreadProps;
  const settled = layoutSmsPhoneThread(props);
  expect(TWELVE.length).toBeGreaterThanOrEqual(10);
  expect(settled.bubbles).toHaveLength(12);
  expect(settled.overflows).toBe(true);
  expect(settled.scrollTarget).toBeGreaterThan(0);
  expect(settled.scrollOffset).toBe(settled.scrollTarget);
  expect(settled.bubbles[0]?.visible).toBeNull();
  expect(settled.bubbles[0]?.clipped).toBe(true);
  const newest = settled.bubbles[11];
  if (!newest?.visible) throw new Error("newest bubble was clipped away");
  expect(newest.clipped).toBe(false);
  expect(rectInside(newest.visible, settled.screen)).toBe(true);
  expect(rectInside(newest.page, settled.phone)).toBe(true);
  for (const bubble of settled.bubbles) {
    if (bubble.visible) expect(rectInside(bubble.visible, settled.screen)).toBe(true);
    expect(bubble.box.width).toBeLessThanOrEqual(BUBBLE_MAX_W);
  }
  expect(settled.bubbles.filter((bubble) => bubble.party === "outbound").length).toBe(6);

  let overflowFrame = -1;
  let previousScroll = 0;
  let largestStep = 0;
  for (let frame = 0; frame <= lastAppear + SCROLL_EASE_FRAMES; frame += 1) {
    const layout = layoutSmsPhoneThread({ ...props, frame });
    expect(layout.scrollOffset).toBeGreaterThanOrEqual(previousScroll);
    largestStep = Math.max(largestStep, layout.scrollOffset - previousScroll);
    previousScroll = layout.scrollOffset;
    if (overflowFrame < 0 && layout.scrollTarget > 0) overflowFrame = frame;
  }
  expect(overflowFrame).toBeGreaterThan(0);
  expect(largestStep).toBeLessThan(32);

  const crossing = layoutSmsPhoneThread({ ...props, frame: overflowFrame });
  const tail = crossing.typing ?? crossing.bubbles[crossing.bubbles.length - 1];
  if (!tail) throw new Error("missing the row that crossed the bezel");
  expect(crossing.scrollOffset).toBeLessThan(crossing.scrollTarget);
  expect(tail.clipped).toBe(true);
  if (tail.visible) expect(rectInside(tail.visible, crossing.screen)).toBe(true);

  const caughtUp = layoutSmsPhoneThread({ ...props, frame: overflowFrame + SCROLL_EASE_FRAMES });
  expect(caughtUp.scrollOffset).toBe(caughtUp.scrollTarget);
  const caughtTail = caughtUp.typing ?? caughtUp.bubbles[caughtUp.bubbles.length - 1];
  if (!caughtTail) throw new Error("missing the eased row");
  expect(caughtTail.clipped).toBe(false);

  const tree = SmsPhoneThread(props);
  const screen = node(tree, "slot", "screen");
  const thread = node(tree, "slot", "thread");
  const bezel = node(tree, "slot", "bezel");
  expect(screen.props.style.overflow).toBe("hidden");
  expect(bezel.props.style.overflow).toBe("hidden");
  expect(screen.dataset.scroll).toBe(String(settled.scrollOffset));
  expect(thread.props.style.top).toBe(-settled.scrollOffset);
  const firstBubble = walkSms(thread).find((item) => item.dataset.slot === "bubble");
  if (!firstBubble) throw new Error("missing a scrolled bubble");
  expect(firstBubble.props.style.top).toBe(settled.bubbles[0]?.box.y);
  const paintedTop = settled.screen.y + Number(firstBubble.props.style.top) + Number(thread.props.style.top);
  expect(paintedTop).toBe(settled.bubbles[0]?.page.y);
  expect(paintedTop + Number(firstBubble.props.style.height)).toBeLessThanOrEqual(settled.screen.y);
});

test("end-screen mask keeps the phone above the card", () => {
  const layout = layoutSmsPhoneThread(goldenProps(120, { isEndScreen: true }));
  expect(layout.isEndScreen).toBe(true);
  expect(layout.endScreenMask).not.toBeNull();
  if (!layout.endScreenMask) throw new Error("missing end-screen mask");
  expect(rectsOverlap(layout.phone, layout.endScreenMask)).toBe(false);
  expect(layout.bubbles.every((bubble) => fullyVisible(bubble))).toBe(true);
  const tree = SmsPhoneThread(goldenProps(120, { isEndScreen: true }));
  expect(tree.dataset["end-screen"]).toBe("true");
  expect(node(tree, "mask", "end-screen-card").props.style.overflow).toBe("hidden");
});

test("a long evidence line stays inside the bubble", () => {
  const body = Array.from({ length: 40 }, () => "alpha").join(" ");
  const layout = layoutSmsPhoneThread({
    messages: [
      {
        message_id: "sms_long",
        fact_id: "case_golden_01_20min_fact_affidavit",
        party: "inbound",
        body,
        appear_frame: 12,
        typing_frames: 0,
      },
    ],
    frame: 12,
    sceneId: "ep_golden_01_20min",
  });
  const bubble = layout.bubbles[0];
  if (!bubble) throw new Error("missing long bubble");
  expect(bubble.truncated).toBe(true);
  expect(bubble.display.endsWith("…")).toBe(true);
  expect(bubble.display.length).toBeLessThan(body.length);
  expect(bubble.box.width).toBeLessThanOrEqual(BUBBLE_MAX_W);
  expect(fullyVisible(bubble)).toBe(true);
  const tree = SmsPhoneThread({
    messages: [
      {
        message_id: "sms_long",
        fact_id: "case_golden_01_20min_fact_affidavit",
        party: "inbound",
        body,
        appear_frame: 12,
        typing_frames: 0,
      },
    ],
    frame: 12,
  });
  const bubbleNode = node(tree, "slot", "bubble");
  expect(bubbleNode.dataset.body).toBe(body);
  expect(bubbleNode.props.children).toBe(bubble.display);
  expect(bubbleNode.props.style.overflow).toBe("hidden");
});

test("cooldown drops a tap inside 60 ms and a dense run tapers", () => {
  const tight = layoutSmsPhoneThread({
    messages: [
      {
        message_id: "sms_a",
        fact_id: "case_golden_01_20min_fact_affidavit",
        party: "inbound",
        body: "One",
        appear_frame: 10,
        typing_frames: 1,
      },
      {
        message_id: "sms_b",
        fact_id: "case_golden_01_20min_fact_clue",
        party: "outbound",
        body: "Two",
        appear_frame: 11,
        typing_frames: 1,
      },
    ],
    frame: 11,
  });
  expect(tight.cues.map((cue) => cue.message_id)).toEqual(["sms_a"]);
  expect(tight.suppressed).toEqual([
    {
      cue: TYPING_TAP_CUE,
      message_id: "sms_b",
      start_frame: 10,
      start_sample: 10 * SAMPLES_PER_FRAME,
      reason: "cooldown",
    },
  ]);

  const dense = layoutSmsPhoneThread({
    messages: Array.from({ length: 15 }, (_, index) => ({
      message_id: `sms_dense_${index + 1}`,
      fact_id: "case_golden_01_20min_fact_affidavit",
      party: index % 2 === 0 ? ("inbound" as const) : ("outbound" as const),
      body: "Tap",
      appear_frame: 4 + index * 2,
      typing_frames: 2,
    })),
    frame: 4 + 14 * 2,
  });
  expect(dense.suppressed).toEqual([]);
  expect(dense.cues).toHaveLength(15);
  expect(dense.cues.every((cue) => cue.burst)).toBe(true);
  expect(dense.cues[0]?.tapered).toBe(false);
  expect(dense.cues[0]?.gain_units).toBe(TYPING_TAP_GAIN_UNITS);
  expect(dense.cues[1]?.tapered).toBe(true);
  expect(dense.cues[1]?.gain_units).toBeLessThan(TYPING_TAP_GAIN_UNITS);
  expect(dense.cues.every((cue) => cue.gain_units <= TYPING_TAP_GAIN_UNITS)).toBe(true);
});

test("rejects an empty thread, a bad id, and an overlapping typing window", () => {
  const row = {
    message_id: "sms_a",
    fact_id: "case_golden_01_20min_fact_affidavit",
    party: "inbound" as const,
    body: "Hello",
    appear_frame: 12,
    typing_frames: 6,
  };
  expect(() => layoutSmsPhoneThread({ messages: [], frame: 0 })).toThrow(/non-empty/);
  expect(() => layoutSmsPhoneThread({ messages: [{ ...row, body: "   " }], frame: 0 })).toThrow(/body/);
  expect(() => layoutSmsPhoneThread({ messages: [{ ...row, fact_id: "bad id" }], frame: 0 })).toThrow(/fact_id/);
  expect(() => layoutSmsPhoneThread({ messages: [{ ...row, party: "narrator" as "inbound" }], frame: 0 })).toThrow(
    /party/,
  );
  expect(() =>
    layoutSmsPhoneThread({
      messages: [row, { ...row, message_id: "sms_a", appear_frame: 24 }],
      frame: 0,
    }),
  ).toThrow(/duplicate message_id/);
  expect(() =>
    layoutSmsPhoneThread({
      messages: [row, { ...row, message_id: "sms_b", appear_frame: 10 }],
      frame: 0,
    }),
  ).toThrow(/appear_frame/);
  expect(() =>
    layoutSmsPhoneThread({
      messages: [
        { ...row, appear_frame: 10, typing_frames: 0 },
        { ...row, message_id: "sms_b", appear_frame: 14, typing_frames: 8 },
      ],
      frame: 0,
    }),
  ).toThrow(/typing window/);
  expect(() => layoutSmsPhoneThread({ messages: [row], frame: 0, highlightMessageId: "sms_missing" })).toThrow(
    /highlight/,
  );
  expect(() => layoutSmsPhoneThread({ messages: [row], frame: -1 })).toThrow(SmsPhoneThreadError);
  expect(() => layoutSmsPhoneThread({ messages: [{ ...row, typing_frames: 30 }], frame: 0 })).toThrow(/typing_frames/);
});
