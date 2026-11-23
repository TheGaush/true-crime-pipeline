import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import { CATALOG_MOTIFS, MOTIF_REGISTRY_V1 } from "../../../shared-contracts-ts/src/models.ts";
import {
  FRAME_HEIGHT,
  FRAME_WIDTH,
  RULE_07_MAX_WORDS,
  SAFE_PADDING_BOTTOM,
  SAFE_PADDING_TOP,
  TIMELINE_SCRUBBER_ID,
  TIMELINE_SCRUBBER_OWNER,
  TimelineScrubber,
  TimelineScrubberError,
  assertExtendedMotifOwnership,
  captionBarRect,
  contentRect,
  exclusionRect,
  layoutPinXs,
  layoutTimelineScrubber,
  rectInside,
  rectsOverlap,
  walkScrub,
  wordCount,
  type FactMilestone,
  type Rect,
  type ScrubNode,
} from "../../src/motifs/TimelineScrubber.tsx";

const pack = JSON.parse(
  readFileSync(new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url), "utf8"),
) as {
  motif_registry_v1: { motif_component: string; owner_package: string; is_mvp_4: number }[];
  temporal_fact_ledger: FactMilestone[];
};

const DENSE_JUMP = JSON.parse(`[
  {"fact_id":"fact_2018_a","datetime_iso":"2018-01-02T08:00:00Z","event_summary":"First warrant served"},
  {"fact_id":"fact_2018_b","datetime_iso":"2018-01-02T09:30:00Z","event_summary":"Second witness interview"},
  {"fact_id":"fact_2018_c","datetime_iso":"2018-01-03T11:00:00Z","event_summary":"Lab logged the sample"},
  {"fact_id":"fact_2018_d","datetime_iso":"2018-01-04T16:00:00Z","event_summary":"Neighbor statement filed"},
  {"fact_id":"fact_2018_e","datetime_iso":"2018-01-05T10:00:00Z","event_summary":"Search inventory closed"},
  {"fact_id":"fact_2023","datetime_iso":"2023-11-14T13:00:00Z","event_summary":"Appeal hearing opened"}
]`) as FactMilestone[];

const LONG_SUMMARY = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike";

function node(root: ScrubNode, key: string, value: string): ScrubNode {
  const found = walkScrub(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function overlapsAny(boxes: readonly Rect[]): boolean {
  return boxes.some((box, index) => boxes.slice(index + 1).some((other) => rectsOverlap(box, other)));
}

function labelBoxes(layout: ReturnType<typeof layoutTimelineScrubber>): Rect[] {
  return [
    ...layout.pins.map((pin) => pin.label.box),
    ...layout.dateTicks.map((tick) => tick.label.box),
    ...layout.hourTicks.map((tick) => tick.label.box),
  ];
}

test("TimelineScrubber is extended motif #5 under the authoritative registry", () => {
  expect(CATALOG_MOTIFS[4]).toBe(TIMELINE_SCRUBBER_ID);
  expect(MOTIF_REGISTRY_V1.map((entry) => entry.motif_component)).toEqual([
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
  ]);
  expect(MOTIF_REGISTRY_V1.every((entry) => entry.owner_package === "render_catalog" && entry.is_mvp_4)).toBe(true);

  const row = pack.motif_registry_v1.find((entry) => entry.motif_component === TIMELINE_SCRUBBER_ID);
  expect(row).toEqual({ motif_component: TIMELINE_SCRUBBER_ID, owner_package: TIMELINE_SCRUBBER_OWNER, is_mvp_4: 0 });
  if (!row) throw new Error("missing TimelineScrubber registry row");
  assertExtendedMotifOwnership(row);

  const panZoom = pack.motif_registry_v1.find((entry) => entry.motif_component === "Illustrative2KPanZoom");
  expect(panZoom).toEqual({
    motif_component: "Illustrative2KPanZoom",
    owner_package: "crime_scene_2k",
    is_mvp_4: 0,
  });
  if (!panZoom) throw new Error("missing Illustrative2KPanZoom registry row");
  expect(() => assertExtendedMotifOwnership(panZoom)).toThrow(TimelineScrubberError);
  expect(() => assertExtendedMotifOwnership(panZoom)).toThrow(/crime_scene_2k/);

  const source = readFileSync(new URL("../../src/motifs/TimelineScrubber.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/function SafeZoneLayout/);
  expect(source).not.toMatch(/function Illustrative2KPanZoom|class Illustrative2KPanZoom|<Illustrative2KPanZoom/);
  const sql = readFileSync(new URL("../../../../schema/pipeline.sql", import.meta.url), "utf8");
  expect(sql).toContain("('TimelineScrubber',       'render_catalog', 0)");
  expect(sql).toContain("('Illustrative2KPanZoom',  'crime_scene_2k', 0)");
});

test("golden multi-day facts scrub inside the safe zone with fact_ledger pins", () => {
  const milestones = pack.temporal_fact_ledger.map((fact) => ({
    fact_id: fact.fact_id,
    datetime_iso: fact.datetime_iso,
    event_summary: fact.event_summary,
  }));
  const layout = layoutTimelineScrubber({ milestones });
  const tree = TimelineScrubber({ milestones });

  expect(layout.motif).toBe("TimelineScrubber");
  expect(layout.owner).toBe("render_catalog");
  expect(layout.pins.map((pin) => pin.fact_id)).toEqual([
    "case_golden_01_20min_fact_affidavit",
    "case_golden_01_20min_fact_clue",
    "case_golden_01_20min_fact_news",
    "case_golden_01_20min_fact_ruling",
  ]);
  expect(layout.dateTicks.map((tick) => tick.text)).toEqual(["2019", "2020", "2021"]);
  expect(layout.hourTicks.map((tick) => tick.text)).toContain("02:00");
  expect(layout.hourTicks.map((tick) => tick.text)).toContain("03:00");
  const hour02 = layout.hourTicks.find((tick) => tick.text === "02:00");
  const hour03 = layout.hourTicks.find((tick) => tick.text === "03:00");
  if (!hour02 || !hour03) throw new Error("expected hour ticks");
  expect(layout.hourPlayheadX).toBeGreaterThan(hour02.x);
  expect(layout.hourPlayheadX).toBeLessThan(hour03.x);

  const boxes = labelBoxes(layout);
  expect(overlapsAny(boxes)).toBe(false);
  for (const box of boxes) {
    expect(rectInside(box, contentRect())).toBe(true);
    expect(rectsOverlap(box, captionBarRect())).toBe(false);
    expect(rectsOverlap(box, exclusionRect())).toBe(false);
  }
  for (const pin of layout.pins) expect(wordCount(pin.label.text)).toBeLessThanOrEqual(RULE_07_MAX_WORDS);
  for (const tick of [...layout.dateTicks, ...layout.hourTicks]) {
    expect(wordCount(tick.text)).toBeLessThanOrEqual(RULE_07_MAX_WORDS);
  }

  const gaps = layout.pins.slice(1).map((pin, index) => pin.x - (layout.pins[index]?.x ?? pin.x));
  expect(Math.max(...gaps)).toBe(gaps[gaps.length - 1]);
  expect(gaps[0]).toBeGreaterThanOrEqual(layout.minStep - 1);

  const linearXs = layoutPinXs(
    layout.pins.map((pin) => pin.ms),
    layout.trackLeft,
    layout.trackRight,
    0,
  );
  const linearBoxes = linearXs.map((x, index) => {
    const label = layout.pins[index]?.label;
    if (!label) throw new Error("missing pin label");
    return {
      x: Math.round(x - label.box.width / 2),
      y: label.box.y,
      width: label.box.width,
      height: label.box.height,
    };
  });
  expect(overlapsAny(linearBoxes)).toBe(true);

  expect(tree.dataset["safe-zone"]).toBe("css-contained");
  expect(tree.dataset.motif).toBe("TimelineScrubber");
  expect(tree.dataset.registry).toBe("MOTIF_REGISTRY_V1");
  expect(tree.dataset["end-screen"]).toBe("false");
  expect(tree.props.style.paddingTop).toBe(SAFE_PADDING_TOP);
  expect(tree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM);
  expect(tree.props.style.width).toBe(FRAME_WIDTH);
  expect(tree.props.style.height).toBe(FRAME_HEIGHT);
  expect(tree.props.style.overflow).toBe("hidden");
  expect(tree.props.style.display).toBe("grid");

  const content = node(tree, "slot", "content");
  expect(content.props.style.display).toBe("flex");
  expect(content.props.style.overflow).toBe("hidden");
  const exclusion = node(tree, "exclusion", "bottom-right");
  expect(exclusion.props.style.width).toBe("22%");
  expect(exclusion.props.style.height).toBe("14%");
  expect(node(tree, "slot", "date-bar").props.style.overflow).toBe("hidden");
  expect(node(tree, "slot", "hour-bar").props.style.overflow).toBe("hidden");

  const pins = walkScrub(tree).filter((item) => item.dataset.slot === "pin");
  expect(pins.map((item) => item.dataset["fact-id"])).toEqual(layout.pins.map((pin) => pin.fact_id));
  for (const item of walkScrub(content)) {
    const { left, top, width, height } = item.props.style;
    if (typeof left !== "number" || typeof top !== "number" || typeof width !== "number" || typeof height !== "number") {
      continue;
    }
    expect(left).toBeGreaterThanOrEqual(0);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(left + width).toBeLessThanOrEqual(layout.content.width);
    expect(top + height).toBeLessThanOrEqual(layout.content.height);
  }
  expect(JSON.stringify(tree)).not.toMatch(/feTurbulence|feDisplacementMap|Illustrative2KPanZoom/);
  expect(walkScrub(tree).some((item) => "filter" in item.props.style)).toBe(false);

  const atRuling = layoutTimelineScrubber({
    milestones,
    scrubAt: "2021-06-18T00:00:00-06:00",
  });
  expect(atRuling.playheadX).toBe(atRuling.pins[atRuling.pins.length - 1]?.x);
  expect(atRuling.hourPlayheadX).toBe(atRuling.hourTicks[0]?.x);
});

test("2018 to 2023 jumps compress tick spacing so date labels do not overlap", () => {
  const layout = layoutTimelineScrubber({ milestones: DENSE_JUMP, scrubAt: "2018-01-02T08:00:00Z" });
  expect(layout.pins.map((pin) => pin.fact_id)).toEqual(DENSE_JUMP.map((fact) => fact.fact_id));
  expect(layout.dateTicks.map((tick) => tick.text)).toEqual(["2018", "2019", "2020", "2021", "2022", "2023"]);
  expect(layout.dateTicks.length).toBeLessThanOrEqual(12);
  expect(overlapsAny(labelBoxes(layout))).toBe(false);
  for (const box of labelBoxes(layout)) expect(rectInside(box, layout.content)).toBe(true);

  const gaps = layout.pins.slice(1).map((pin, index) => pin.x - (layout.pins[index]?.x ?? pin.x));
  expect(gaps[gaps.length - 1]).toBe(Math.max(...gaps));
  expect(gaps[0]).toBeGreaterThanOrEqual(layout.minStep - 1);
  expect(layout.pins[0]?.label.text).toContain("2018");
  expect(layout.pins[layout.pins.length - 1]?.label.text).toContain("2023");

  const linearXs = layoutPinXs(
    layout.pins.map((pin) => pin.ms),
    layout.trackLeft,
    layout.trackRight,
    0,
  );
  const linearBoxes = linearXs.map((x, index) => {
    const label = layout.pins[index]?.label;
    if (!label) throw new Error("missing pin label");
    return {
      x: Math.round(x - label.box.width / 2),
      y: label.box.y,
      width: label.box.width,
      height: label.box.height,
    };
  });
  expect(overlapsAny(linearBoxes)).toBe(true);

  const tree = TimelineScrubber({ milestones: DENSE_JUMP });
  expect(JSON.stringify(tree)).not.toMatch(/feTurbulence|feDisplacementMap/);
});

test("identical timestamps stay separated and long summaries clamp to 12 words", () => {
  const layout = layoutTimelineScrubber({
    milestones: [
      { fact_id: "fact_b", datetime_iso: "2018-06-01T12:00:00Z", event_summary: LONG_SUMMARY },
      { fact_id: "fact_a", datetime_iso: "2018-06-01T12:00:00Z", event_summary: "Earlier docket line" },
    ],
  });
  expect(layout.pins.map((pin) => pin.fact_id)).toEqual(["fact_a", "fact_b"]);
  expect(layout.pins[0]?.x).toBeLessThan(layout.pins[1]?.x ?? 0);
  expect(rectsOverlap(layout.pins[0]?.label.box ?? contentRect(), layout.pins[1]?.label.box ?? contentRect())).toBe(
    false,
  );
  expect(wordCount(layout.pins[1]?.summary ?? "")).toBe(RULE_07_MAX_WORDS);
  expect(layout.pins[1]?.summary).toBe("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima");
  const tree = TimelineScrubber({
    milestones: [
      { fact_id: "fact_b", datetime_iso: "2018-06-01T12:00:00Z", event_summary: LONG_SUMMARY },
      { fact_id: "fact_a", datetime_iso: "2018-06-01T12:00:00Z", event_summary: "Earlier docket line" },
    ],
    isEndScreen: true,
  });
  expect(tree.dataset["end-screen"]).toBe("true");
  expect(node(tree, "mask", "end-screen-card").props.style.overflow).toBe("hidden");
  const ending = layoutTimelineScrubber({
    milestones: [
      { fact_id: "fact_a", datetime_iso: "2018-06-01T12:00:00Z", event_summary: "Earlier docket line" },
      { fact_id: "fact_b", datetime_iso: "2018-06-01T12:00:00Z", event_summary: LONG_SUMMARY },
    ],
    isEndScreen: true,
  });
  expect(ending.endScreenMask).not.toBeNull();
  if (!ending.endScreenMask) throw new Error("expected an end-screen mask");
  for (const box of labelBoxes(ending)) expect(rectsOverlap(box, ending.endScreenMask)).toBe(false);
});

test("rejects a blank ledger, duplicate fact ids, and a datetime that is not ISO-8601", () => {
  expect(() => layoutTimelineScrubber({ milestones: [] })).toThrow(/fact_ledger/);
  expect(() =>
    layoutTimelineScrubber({
      milestones: [{ fact_id: "fact_a", datetime_iso: "2018-02-31T00:00:00Z", event_summary: "Impossible day" }],
    }),
  ).toThrow(/ISO-8601/);
  expect(() =>
    layoutTimelineScrubber({
      milestones: [
        { fact_id: "fact a", datetime_iso: "2018-01-02T00:00:00Z", event_summary: "Bad id" },
      ],
    }),
  ).toThrow(/fact_ledger/);
  expect(() =>
    layoutTimelineScrubber({
      milestones: [
        { fact_id: "fact_a", datetime_iso: "2018-01-02T00:00:00Z", event_summary: "One" },
        { fact_id: "fact_a", datetime_iso: "2018-01-03T00:00:00Z", event_summary: "Two" },
      ],
    }),
  ).toThrow(/duplicate fact_id/);
  expect(() =>
    layoutTimelineScrubber({
      milestones: [{ fact_id: "fact_a", datetime_iso: "2018-01-02T00:00:00Z", event_summary: "   " }],
    }),
  ).toThrow(/event_summary/);
});
