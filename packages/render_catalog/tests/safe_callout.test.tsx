/**
 * Task 111. React markup plus bounding boxes for kinetic safe-zone callouts.
 * Task 101, 102, and 108 modules are imported by SafeCallout. When those files
 * are absent, this file installs doubles and deletes them before exit.
 * It does not overwrite a real module and it does not leave the doubles in git.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterAll, describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(here, "../src");
const MARK = "TC-TASK-111-TEST-STUB";

const safePath = path.join(srcDir, "safe_zone.tsx");
const themePath = path.join(srcDir, "theme/CaseBibleContext.tsx");
const voicePath = path.join(srcDir, "rig/useVoiceSyncMotion.ts");

const BIBLE = {
  contract_version: "v4",
  episode_id: "ep_golden_01_20min",
  locked_at: 500,
  style_dna_json: {
    evidence_crimson_hex: "#B42318",
    paper_bg_hex: "#F7F4EC",
    ink_hex: "#161616",
    slate_hex: "#2C455C",
    flow_keyframe_safe_palette: ["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"],
  },
  characters_json: [{ character_id: "detective_01", prop: "notepad", color_hex: "#2C455C" }],
};

const SAFE_STUB = `/** ${MARK} — stand-in for Task 101 SafeZoneLayout. Removed when the test exits. */
const WIDTH = 1920;
const HEIGHT = 1080;
const PAD_TOP = 108;
const PAD_BOTTOM = 194;

function snap(value) {
  return Math.round(value * 1000) / 1000;
}

function geometry(isEndScreen) {
  const content = { x: 0, y: PAD_TOP, width: WIDTH, height: HEIGHT - PAD_TOP - PAD_BOTTOM };
  const exclusionWidth = snap(WIDTH * 0.22);
  const exclusionHeight = snap(HEIGHT * 0.14);
  const exclusion = {
    x: snap(WIDTH - exclusionWidth),
    y: snap(HEIGHT - exclusionHeight),
    width: exclusionWidth,
    height: exclusionHeight,
  };
  const captionBar = { x: 0, y: HEIGHT - PAD_BOTTOM, width: WIDTH, height: PAD_BOTTOM };
  const cardHeight = 144.9;
  const endScreenCard = isEndScreen
    ? {
        x: 0,
        y: snap(HEIGHT - PAD_BOTTOM - cardHeight),
        width: snap(WIDTH - exclusionWidth),
        height: cardHeight,
      }
    : null;
  return { content, exclusion, captionBar, endScreenCard };
}

function element(dataset, style, children) {
  const props = { style };
  if (children && children.length === 1) props.children = children[0];
  else if (children && children.length > 1) props.children = children;
  return { type: "div", dataset, props };
}

export function SafeZoneLayout(props) {
  const end = props.isEndScreen === true;
  const layers = [
    element(
      { slot: "content" },
      {
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      },
      props.children === undefined ? [] : [props.children],
    ),
    element(
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: "22%",
        height: "14%",
        overflow: "hidden",
        pointerEvents: "none",
      },
    ),
  ];
  if (end) {
    layers.push(
      element(
        { mask: "end-screen-card" },
        {
          position: "absolute",
          left: 0,
          right: "22%",
          bottom: PAD_BOTTOM,
          overflow: "hidden",
          maxHeight: "144.9px",
        },
      ),
    );
  }
  return element(
    { "safe-zone": "css-contained", "end-screen": end ? "true" : "false" },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      width: WIDTH,
      height: HEIGHT,
      paddingTop: PAD_TOP,
      paddingBottom: PAD_BOTTOM,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
    },
    layers,
  );
}

export function measureSafeZone(props) {
  const end = props.isEndScreen === true;
  const geo = geometry(end);
  return {
    element: SafeZoneLayout({ isEndScreen: end }),
    frame: { x: 0, y: 0, width: WIDTH, height: HEIGHT },
    content: geo.content,
    exclusion: geo.exclusion,
    label: null,
    endScreenCard: geo.endScreenCard,
    captionBar: geo.captionBar,
  };
}
`;

const THEME_STUB = `/** ${MARK} — stand-in for Task 102 useCaseBible(). Removed when the test exits. */
export function useCaseBible() {
  return {
    paperBgHex: "#F7F4EC",
    inkHex: "#161616",
    slateHex: "#2C455C",
    evidenceCrimsonHex: "#B42318",
    flowKeyframeSafePalette: ["#1B1B1D", "#E9E2D2", "#3A4F66", "#C4A574"],
  };
}
`;

const VOICE_STUB = `/** ${MARK} — stand-in for Task 108 sampleVoiceSyncMotion(). Removed when the test exits. */
export const VOICE_SYNC_FPS = 30;

export function voiceSyncFrameStartMs(frameIndex) {
  return Math.floor((frameIndex * 1000) / 30);
}

export function sampleVoiceSyncMotion(manifest, frame) {
  if (typeof frame !== "number" || !Number.isFinite(frame)) {
    return { frameIndex: null, timeMs: null, segmentKind: "NONE", amplitude: 0, nodPitchDeg: 0, gestureBounceDeg: 0 };
  }
  const frameIndex = Math.round(frame);
  const timeMs = voiceSyncFrameStartMs(frameIndex);
  let segment = null;
  for (const item of manifest?.segments ?? []) {
    if (item.start_ms <= timeMs && timeMs < item.end_ms) segment = item;
  }
  const kind = segment?.segment_kind;
  const known = kind === "NARRATION" || kind === "TWIST_PAD" || kind === "FOIA_AUDIO_SLOT";
  return {
    frameIndex,
    timeMs,
    segmentKind: known ? kind : "NONE",
    amplitude: kind === "NARRATION" ? 0.5 : 0,
    nodPitchDeg: kind === "NARRATION" ? 2.25 : 0,
    gestureBounceDeg: kind === "NARRATION" ? 3 : 0,
  };
}
`;

const created = [];

function canReplace(file) {
  if (!fs.existsSync(file)) return true;
  return fs.readFileSync(file, "utf8").includes(MARK);
}

function writeStub(file, source) {
  if (!canReplace(file)) return;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, source);
  created.push(file);
}

writeStub(safePath, SAFE_STUB);
writeStub(themePath, THEME_STUB);
writeStub(voicePath, VOICE_STUB);

function removeStubs() {
  for (const file of created) {
    if (fs.existsSync(file) && fs.readFileSync(file, "utf8").includes(MARK)) fs.rmSync(file);
  }
  for (const dir of [path.dirname(themePath), path.dirname(voicePath)]) {
    if (fs.existsSync(dir) && fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
  }
}

process.on("exit", removeStubs);

const calloutMod = await import("../src/typography/SafeCallout.tsx");
const zone = await import("../src/safe_zone.tsx");
const voice = await import("../src/rig/useVoiceSyncMotion.ts");
const theme = await import("../src/theme/CaseBibleContext.tsx");

afterAll(removeStubs);

const {
  CALLOUT_FONT_PX,
  CALLOUT_LINE_HEIGHT,
  MAX_CALLOUT_WORDS,
  SafeCallout,
  SafeCalloutError,
  Y_SLOT_STEP_PX,
  clampCalloutWords,
  deconflictYSlots,
  layoutKineticCallouts,
  measureCalloutText,
  minCalloutHoldMs,
  rectInside,
  rectsOverlap,
  usableCalloutBounds,
} = calloutMod;

function snap(value) {
  return Math.round(value * 1000) / 1000;
}

function render(props) {
  const node = createElement(SafeCallout, props);
  const provider = theme.CaseBibleProvider;
  if (typeof provider === "function") {
    return renderToStaticMarkup(createElement(provider, { bible: BIBLE }, node));
  }
  return renderToStaticMarkup(node);
}

function frameStarting(predicate) {
  for (let frame = 0; frame < 4000; frame += 1) {
    if (predicate(voice.voiceSyncFrameStartMs(frame))) return frame;
  }
  throw new Error("no 30 fps frame matched");
}

function attr(tag, name) {
  const match = new RegExp(`\\bdata-${name}="([^"]*)"`).exec(tag);
  return match ? match[1] : null;
}

function calloutDivs(html) {
  return [...html.matchAll(/<div\b[^>]*\bdata-callout-id="[^"]+"[^>]*>[\s\S]*?<\/div>/g)].map((match) => match[0]);
}

function calloutById(html, id) {
  return calloutDivs(html).find((tag) => attr(tag, "callout-id") === id) ?? null;
}

function boxOf(tag) {
  return {
    x: Number(attr(tag, "x")),
    y: Number(attr(tag, "y")),
    width: Number(attr(tag, "width")),
    height: Number(attr(tag, "height")),
  };
}

function activeWords(tag) {
  return [...tag.matchAll(/data-word="([^"]*)"[^>]*\bdata-active="true"/g)].map((match) => match[1]);
}

function contentBounds(html) {
  const slot = html.match(/<div\b[^>]*data-component="SafeCallout"[^>]*>/);
  if (!slot) throw new Error("missing SafeCallout slot");
  const tag = slot[0];
  return {
    x: Number(attr(tag, "content-x")),
    y: Number(attr(tag, "content-y")),
    width: Number(attr(tag, "content-width")),
    height: Number(attr(tag, "content-height")),
  };
}

const narration = {
  segment_id: "seg_narr",
  segment_kind: "NARRATION",
  start_ms: 0,
  end_ms: 8000,
};

function stamps(words, start = 0, step = 200) {
  return words.map((word, index) => ({
    segment_id: narration.segment_id,
    word,
    start_ms: start + index * step,
    end_ms: start + index * step + 100,
  }));
}

function manifest(segments, wordTimestamps = []) {
  return { segments, word_timestamps: wordTimestamps, amplitude_envelope: [0.2, 0.8] };
}

const wide = { x: 0, y: 108, width: 1920, height: 778 };

describe("callout text and Y slots", () => {
  it("clamps a runtime string to 12 words", () => {
    const clamped = clampCalloutWords("one two three four five six seven eight nine ten eleven twelve thirteen");
    expect(clamped.words).toHaveLength(MAX_CALLOUT_WORDS);
    expect(clamped.clamped).toBe(true);
    expect(clamped.text.endsWith("twelve")).toBe(true);
    expect(clampCalloutWords("  County   courthouse ")).toEqual({
      text: "County courthouse",
      words: ["County", "courthouse"],
      clamped: false,
    });
    expect(minCalloutHoldMs(1)).toBe(1300);
    expect(minCalloutHoldMs(2)).toBe(1600);
    expect(minCalloutHoldMs(12)).toBe(4600);
  });

  it("separates overlapping slots by 64px steps", () => {
    const bounds = { x: 0, y: 0, width: 400, height: 800 };
    const placed = deconflictYSlots(
      [
        { id: "b", preferredY: 200, width: 120, height: 40 },
        { id: "a", preferredY: 200, width: 120, height: 40 },
      ],
      bounds,
    );
    expect(placed.find((slot) => slot.id === "a")?.y).toBe(200);
    expect(placed.find((slot) => slot.id === "b")?.y).toBe(200 + Y_SLOT_STEP_PX);
    const tall = deconflictYSlots(
      [
        { id: "a", preferredY: 200, width: 120, height: 100 },
        { id: "b", preferredY: 200, width: 120, height: 100 },
      ],
      bounds,
    );
    expect(tall.find((slot) => slot.id === "b")?.y).toBe(200 + Y_SLOT_STEP_PX * 2);
    for (const slot of [...placed, ...tall]) expect(rectInside(slot, bounds)).toBe(true);
    expect(rectsOverlap(placed[0], placed[1])).toBe(false);
    expect(rectsOverlap({ x: 0, y: 0, width: 10, height: 10 }, { x: 10, y: 0, width: 5, height: 5 })).toBe(false);
  });

  it("keeps a crowded slot inside the safe zone instead of overlapping", () => {
    const bounds = { x: 0, y: 0, width: 200, height: 90 };
    const placed = deconflictYSlots(
      [
        { id: "a", preferredY: 0, width: 80, height: 40 },
        { id: "b", preferredY: 0, width: 80, height: 40 },
      ],
      bounds,
    );
    expect(placed.map((slot) => slot.y).sort((left, right) => left - right)).toEqual([0, 50]);
    expect(rectsOverlap(placed[0], placed[1])).toBe(false);
    for (const slot of placed) expect(rectInside(slot, bounds)).toBe(true);
    expect(() =>
      deconflictYSlots(
        [
          { id: "a", preferredY: 0, width: 80, height: 40 },
          { id: "b", preferredY: 0, width: 80, height: 40 },
          { id: "c", preferredY: 0, width: 80, height: 40 },
        ],
        { x: 0, y: 0, width: 200, height: 70 },
      ),
    ).toThrow(SafeCalloutError);
  });
});

describe("kinetic timing", () => {
  const words = stamps(["Hello", "there"]);

  it("holds a fact callout for 1.0 + 0.3 * words seconds and highlights the spoken word", () => {
    const shown = layoutKineticCallouts({
      callouts: [{ id: "loc_hello", kind: "location", text: "Hello there", factId: "fact_hello", preferredY: 200 }],
      wordTimestamps: words,
      segments: [narration],
      timeMs: 50,
      segmentKind: "NARRATION",
      bounds: wide,
      obstacles: [],
    });
    expect(shown.placed).toHaveLength(2);
    const card = shown.placed.find((item) => item.id === "loc_hello");
    expect(card?.startMs).toBe(0);
    expect(card?.endMs).toBe(1600);
    expect(card?.activeIndex).toBe(0);
    const subtitle = shown.placed.find((item) => item.kind === "subtitle");
    expect(subtitle?.endMs).toBe(300);
    expect(subtitle?.activeIndex).toBe(0);

    const held = layoutKineticCallouts({
      callouts: [{ id: "loc_hello", kind: "location", text: "Hello there", factId: "fact_hello", preferredY: 200 }],
      wordTimestamps: words,
      segments: [narration],
      timeMs: 1500,
      segmentKind: "NARRATION",
      bounds: wide,
      obstacles: [],
    });
    expect(held.placed.some((item) => item.id === "loc_hello")).toBe(true);
    expect(held.placed.find((item) => item.id === "loc_hello")?.activeIndex).toBe(-1);
    expect(held.placed.some((item) => item.kind === "subtitle")).toBe(false);

    const gone = layoutKineticCallouts({
      callouts: [{ id: "loc_hello", kind: "location", text: "Hello there", factId: "fact_hello" }],
      wordTimestamps: words,
      segments: [narration],
      timeMs: 1600,
      segmentKind: "NARRATION",
      bounds: wide,
      obstacles: [],
    });
    expect(gone.placed.some((item) => item.id === "loc_hello")).toBe(false);
  });

  it("does not highlight during a silence pad even if the callout is still on screen", () => {
    const silent = layoutKineticCallouts({
      callouts: [{ id: "loc_hello", kind: "location", text: "Hello there", factId: "fact_hello", preferredY: 200 }],
      wordTimestamps: words,
      segments: [narration],
      timeMs: 50,
      segmentKind: "TWIST_PAD",
      bounds: wide,
      obstacles: [],
    });
    expect(silent.kinetic).toBe(false);
    expect(silent.placed.map((item) => item.kind)).toEqual(["location"]);
    expect(silent.placed[0]?.activeIndex).toBe(-1);

    const foia = layoutKineticCallouts({
      callouts: [{ id: "loc_hello", kind: "location", text: "Hello there", factId: "fact_hello" }],
      wordTimestamps: words,
      segments: [narration],
      timeMs: 50,
      segmentKind: "FOIA_AUDIO_SLOT",
      bounds: wide,
      obstacles: [],
    });
    expect(foia.placed.every((item) => item.activeIndex === -1)).toBe(true);
    expect(foia.placed.some((item) => item.kind === "subtitle")).toBe(false);
  });

  it("rejects a fact callout with no fact id or no matching WordTimestamp", () => {
    expect(() =>
      layoutKineticCallouts({
        callouts: [{ id: "loc_hello", kind: "location", text: "Hello there" }],
        wordTimestamps: words,
        segments: [narration],
        timeMs: 0,
        segmentKind: "NARRATION",
        bounds: wide,
        obstacles: [],
      }),
    ).toThrow(/fact_ledger/);
    expect(() =>
      layoutKineticCallouts({
        callouts: [{ id: "loc_hello", kind: "location", text: "Hello missing", factId: "fact_hello" }],
        wordTimestamps: words,
        segments: [narration],
        timeMs: 0,
        segmentKind: "NARRATION",
        bounds: wide,
        obstacles: [],
      }),
    ).toThrow(/missing/);
  });
});

describe("SafeCallout frame", () => {
  const goldenWords = [
    ["A", 40080, 40232],
    ["short", 40282, 40482],
    ["monochrome", 40532, 40792],
    ["bridge", 40842, 41054],
    ["crosses", 41104, 41328],
    ["the", 41378, 41554],
    ["courthouse", 41604, 41864],
    ["steps", 41914, 42114],
    ["in", 42164, 42328],
    ["charcoal", 42378, 42614],
    ["and", 42664, 42840],
    ["slate.", 42890, 43102],
  ].map(([word, start, end]) => ({
    segment_id: "ep_golden_01_20min_vs002",
    word,
    start_ms: start,
    end_ms: end,
  }));

  const goldenManifest = manifest(
    [
      {
        segment_id: "ep_golden_01_20min_vs001",
        segment_kind: "FOIA_AUDIO_SLOT",
        start_ms: 0,
        end_ms: 40000,
      },
      {
        segment_id: "ep_golden_01_20min_vs002",
        segment_kind: "NARRATION",
        start_ms: 40000,
        end_ms: 48000,
      },
    ],
    goldenWords,
  );

  const location = {
    id: "loc_steps",
    kind: "location",
    text: "courthouse steps",
    factId: "fact_courthouse",
    preferredY: 180,
  };

  function paint(frame, extra = {}) {
    return render({
      callouts: [location],
      wordTimestamps: goldenWords,
      manifest: goldenManifest,
      frame,
      ...extra,
    });
  }

  it("highlights the global WordTimestamp inside the safe-zone frame", () => {
    const frame = frameStarting((start) => start >= 40532 && start < 40792);
    const html = paint(frame);
    expect(voice.sampleVoiceSyncMotion(goldenManifest, frame).segmentKind).toBe("NARRATION");
    expect(html).toContain('data-safe-zone="css-contained"');
    expect(html).toContain('data-end-screen="false"');
    expect(html).toContain("padding-top:108px");
    expect(html).toContain("padding-bottom:194px");
    expect(html).toContain("width:1920px");
    expect(html).toContain("height:1080px");
    expect(html).toContain("overflow:hidden");
    expect(html).toContain('data-kinetic="on"');
    const zoneFrame = zone.measureSafeZone({ isEndScreen: false });
    const bounds = contentBounds(html);
    expect(bounds).toEqual({
      x: snap(zoneFrame.content.x),
      y: snap(zoneFrame.content.y),
      width: snap(zoneFrame.content.width),
      height: snap(zoneFrame.content.height),
    });
    const subtitle = calloutDivs(html).find((tag) => attr(tag, "callout-kind") === "subtitle");
    expect(subtitle).toBeTruthy();
    expect(attr(subtitle, "word-count")).toBe("12");
    expect(attr(subtitle, "clamped")).toBe("false");
    expect(attr(subtitle, "hold-start-ms")).toBe("40080");
    expect(attr(subtitle, "hold-end-ms")).toBe("43102");
    expect(activeWords(subtitle)).toEqual(["monochrome"]);
    expect(calloutById(html, "loc_steps")).toBeNull();
    expect(html).not.toContain("feTurbulence");
    expect(html).not.toContain("feDisplacementMap");
    expect(html).toContain("#F7F4EC");
    expect(html).toContain("#161616");
    expect(html).toContain("#B42318");
    expect(html).not.toContain("#C4A574");
    expect(html).not.toContain("#C92A2A");
  });

  it("places the fact callout and the subtitle on separate rows with no exclusion overlap", () => {
    const frame = frameStarting((start) => start >= 41914 && start < 42114);
    const html = paint(frame);
    const tags = calloutDivs(html);
    expect(tags).toHaveLength(2);
    const locationTag = calloutById(html, "loc_steps");
    const subtitle = tags.find((tag) => attr(tag, "callout-kind") === "subtitle");
    expect(attr(locationTag, "fact-id")).toBe("fact_courthouse");
    expect(locationTag).toContain('data-citation="fact_courthouse"');
    expect(locationTag).toContain("#2C455C");
    expect(attr(locationTag, "y")).toBe("180");
    expect(activeWords(locationTag)).toEqual(["steps"]);
    expect(activeWords(subtitle)).toEqual(["steps"]);
    const boxes = tags.map(boxOf);
    expect(rectsOverlap(boxes[0], boxes[1])).toBe(false);
    const measured = zone.measureSafeZone({ isEndScreen: false });
    const bounds = contentBounds(html);
    for (const box of boxes) {
      expect(rectInside(box, bounds)).toBe(true);
      expect(rectsOverlap(box, measured.exclusion)).toBe(false);
      expect(rectsOverlap(box, measured.captionBar)).toBe(false);
      expect(box.y).toBeGreaterThanOrEqual(measured.content.y);
      expect(box.y + box.height).toBeLessThanOrEqual(measured.content.y + measured.content.height + 0.001);
    }
  });

  it("drops the kinetic line during FOIA and during the gap between words", () => {
    const foia = paint(0);
    expect(voice.sampleVoiceSyncMotion(goldenManifest, 0).segmentKind).toBe("FOIA_AUDIO_SLOT");
    expect(foia).toContain('data-kinetic="off"');
    expect(calloutDivs(foia)).toHaveLength(0);
    expect(foia).not.toContain('data-active="true"');

    const gap = frameStarting((start) => start >= 40482 && start < 40532);
    const html = paint(gap);
    expect(html).toContain('data-kinetic="on"');
    const subtitle = calloutDivs(html).find((tag) => attr(tag, "callout-kind") === "subtitle");
    expect(subtitle).toBeTruthy();
    expect(activeWords(subtitle)).toEqual([]);
  });

  it("separates two callouts that ask for the same Y and clamps the 13th word", () => {
    const words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen"];
    const timed = stamps(words);
    const text = words.join(" ");
    const frame = 0;
    const html = render({
      callouts: [
        { id: "loc_a", kind: "location", text, factId: "fact_a", preferredY: 200 },
        { id: "loc_b", kind: "timestamp", text, factId: "fact_b", preferredY: 200 },
      ],
      manifest: manifest([narration], timed),
      frame,
    });
    const first = calloutById(html, "loc_a");
    const second = calloutById(html, "loc_b");
    expect(attr(first, "clamped")).toBe("true");
    expect(attr(first, "word-count")).toBe("12");
    expect(first).not.toContain('data-word="thirteen"');
    expect(attr(first, "hold-end-ms")).toBe(String(minCalloutHoldMs(12)));
    expect(Number(attr(second, "y")) - Number(attr(first, "y"))).toBe(Y_SLOT_STEP_PX);
    expect(rectsOverlap(boxOf(first), boxOf(second))).toBe(false);
    const line = snap(CALLOUT_FONT_PX * CALLOUT_LINE_HEIGHT);
    expect(measureCalloutText(words.slice(0, 12).join(" "), 1920).lineCount).toBeGreaterThan(0);
    expect(boxOf(first).height).toBeGreaterThanOrEqual(line);
  });

  it("moves an end-screen callout above the end card", () => {
    const html = render({
      callouts: [{ id: "act_end", kind: "action", text: "Hello there", factId: "fact_end", preferredY: 900 }],
      manifest: manifest([narration], stamps(["Hello", "there"])),
      frame: 0,
      isEndScreen: true,
    });
    expect(html).toContain('data-end-screen="true"');
    const measured = zone.measureSafeZone({ isEndScreen: true });
    const bounds = contentBounds(html);
    expect(measured.endScreenCard).toBeTruthy();
    expect(bounds.height).toBe(snap(snap(measured.endScreenCard.y) - snap(measured.content.y)));
    expect(bounds.height).toBeLessThan(measured.content.height);
    const box = boxOf(calloutById(html, "act_end"));
    expect(rectInside(box, bounds)).toBe(true);
    expect(rectsOverlap(box, measured.endScreenCard)).toBe(false);
    expect(box.y + box.height).toBeLessThanOrEqual(measured.endScreenCard.y + 0.001);
    expect(rectsOverlap(box, measured.exclusion)).toBe(false);
    expect(rectsOverlap(box, measured.captionBar)).toBe(false);
  });

  it("escapes callout text and stays flat on a twist pad", () => {
    const segments = [
      { segment_id: "seg_narr", segment_kind: "NARRATION", start_ms: 0, end_ms: 500 },
      { segment_id: "seg_twist", segment_kind: "TWIST_PAD", start_ms: 500, end_ms: 1200 },
    ];
    const timed = [
      { segment_id: "seg_narr", word: "<b>", start_ms: 0, end_ms: 100 },
      { segment_id: "seg_narr", word: "there", start_ms: 100, end_ms: 200 },
    ];
    const spoken = render({
      callouts: [{ id: "loc_mark", kind: "location", text: "<b> there", factId: "fact_mark", preferredY: 220 }],
      manifest: manifest(segments, timed),
      frame: 0,
    });
    expect(spoken).toContain("&lt;b&gt;");
    expect(spoken).not.toContain("<b>");
    expect(activeWords(calloutById(spoken, "loc_mark"))).toEqual(["&lt;b&gt;"]);

    const twistFrame = frameStarting((start) => start >= 500 && start < 1200);
    const twist = render({
      callouts: [{ id: "loc_mark", kind: "location", text: "<b> there", factId: "fact_mark", preferredY: 220 }],
      manifest: manifest(segments, timed),
      frame: twistFrame,
    });
    expect(voice.sampleVoiceSyncMotion(manifest(segments, timed), twistFrame).segmentKind).toBe("TWIST_PAD");
    expect(twist).toContain('data-kinetic="off"');
    expect(twist).not.toContain('data-active="true"');
    expect(calloutDivs(twist).some((tag) => attr(tag, "callout-kind") === "subtitle")).toBe(false);
    expect(attr(calloutById(twist, "loc_mark"), "hold-end-ms")).toBe("1600");
  });

  it("reads the CaseBible palette and the safe-zone module instead of a hardcoded plate", () => {
    const source = fs.readFileSync(path.join(srcDir, "typography/SafeCallout.tsx"), "utf8");
    expect(source).toContain("useCaseBible");
    expect(source).toContain("SafeZoneLayout");
    expect(source).toContain("measureSafeZone");
    expect(source).toContain("sampleVoiceSyncMotion");
    expect(source).not.toMatch(/#[0-9A-Fa-f]{3,8}/);
    expect(source).not.toMatch(/feTurbulence|feDisplacementMap/);
    expect(usableCalloutBounds({ x: 0, y: 108, width: 1920, height: 778 }, { x: 0, y: 741.1, width: 100, height: 10 }).height).toBe(
      snap(741.1 - 108),
    );
  });

  it("blocks outbound network under the zero-spend guard", async () => {
    expect(process.env.GEMINI_API_KEY).toBeUndefined();
    expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
    expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
    await expect(fetch("https://example.com/callout")).rejects.toThrow(/ZERO_SPEND_GUARD/);
  });
});
