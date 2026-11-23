import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import {
  CLUSTER_MAX_MS,
  COOLDOWN_MS,
  EXCLUSION_HEIGHT,
  EXCLUSION_WIDTH,
  FOCAL_ZOOM_MAX,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  GAIN_UNIT_SCALE,
  MIX_SAMPLE_RATE_HZ,
  MOTIF_NUMBER,
  RULE_07_MAX_WORDS,
  SAFE_PADDING_BOTTOM,
  SAFE_PADDING_TOP,
  TICK_DURATION_MS,
  TICK_GAIN_UNITS,
  TICK_PEAK_DBTP,
  TICK_SFX,
  TIME_GAP_LABEL,
  TIMELINE_DATE_SCRUBBER_ID,
  TIMELINE_DATE_SCRUBBER_OWNER,
  TimelineDateScrubber,
  TimelineDateScrubberError,
  assertDateScrubberOwnership,
  captionBarRect,
  clampWords,
  contentRect,
  exclusionRect,
  exportTickSfxCues,
  layoutTimelineDateScrubber,
  linearNotchXs,
  rectInside,
  rectsOverlap,
  tickSfxTriggers,
  walkScrub,
  wordCount,
  type ForensicDateEvent,
  type Rect,
  type ScrubNode,
  type TimelineDateScrubberLayout,
} from "../../src/motifs/TimelineDateScrubber.tsx";

const pack = JSON.parse(
  readFileSync(new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url), "utf8"),
) as {
  temporal_fact_ledger: ForensicDateEvent[];
};

const CLUSTER: ForensicDateEvent[] = [
  {
    fact_id: "cluster_c",
    datetime_iso: "2019-04-03T02:18:00-06:00",
    event_summary: "Porch light noted at the steps",
  },
  {
    fact_id: "cluster_a",
    datetime_iso: "2019-04-03T02:14:00-06:00",
    event_summary: "Dispatch logged the first call",
  },
  {
    fact_id: "cluster_b",
    datetime_iso: "2019-04-03T02:16:00-06:00",
    event_summary: "Second unit arrived on the lane",
  },
  {
    fact_id: "years_later",
    datetime_iso: "2021-06-18T15:04:00-06:00",
    event_summary: "The state court affirmed the conviction",
  },
];

const FOUR_MINUTES: ForensicDateEvent[] = [
  { fact_id: "m0", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Start of the four minute cluster" },
  { fact_id: "m1", datetime_iso: "2019-04-03T02:15:00Z", event_summary: "One minute inside the cluster" },
  { fact_id: "m2", datetime_iso: "2019-04-03T02:16:00Z", event_summary: "Two minutes inside the cluster" },
  { fact_id: "m3", datetime_iso: "2019-04-03T02:17:00Z", event_summary: "Three minutes inside the cluster" },
  { fact_id: "m4", datetime_iso: "2019-04-03T02:18:00Z", event_summary: "Exactly four minutes from the start" },
];

const LONG_SUMMARY = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike";

function node(root: ScrubNode, key: string, value: string): ScrubNode {
  const found = walkScrub(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function overlapsAny(boxes: readonly Rect[]): boolean {
  return boxes.some((box, index) => boxes.slice(index + 1).some((other) => rectsOverlap(box, other)));
}

function linearLabelBoxes(layout: TimelineDateScrubberLayout): Rect[] {
  return layout.linearXs.map((x, index) => {
    const notch = layout.notches[index];
    if (!notch) throw new Error("missing notch");
    return {
      x: Math.round(x - notch.labelBox.width / 2),
      y: notch.labelBox.y,
      width: notch.labelBox.width,
      height: notch.labelBox.height,
    };
  });
}

test("TimelineDateScrubber is task motif #9 and does not rewrite the frozen registry", () => {
  expect(MOTIF_NUMBER).toBe(9);
  expect(TIMELINE_DATE_SCRUBBER_ID).toBe("TimelineDateScrubber");
  expect(TIMELINE_DATE_SCRUBBER_OWNER).toBe("render_catalog");
  expect(TIME_GAP_LABEL).toBe("// TIME GAP");
  expect(TICK_SFX).toBe("tick_sfx");
  expect(CLUSTER_MAX_MS).toBe(4 * 60 * 1000);

  const models = readFileSync(new URL("../../../shared-contracts-ts/src/models.ts", import.meta.url), "utf8");
  expect(models).toContain('"CaseBoardSpine"');
  expect(models).not.toContain("TimelineDateScrubber");
  const sql = readFileSync(new URL("../../../../schema/pipeline.sql", import.meta.url), "utf8");
  expect(sql).toContain("('CaseBoardSpine',         'render_catalog', 0)");
  expect(sql).not.toContain("TimelineDateScrubber");
  expect(sql).toContain("('Illustrative2KPanZoom',  'crime_scene_2k', 0)");

  assertDateScrubberOwnership({
    motif_component: TIMELINE_DATE_SCRUBBER_ID,
    owner_package: TIMELINE_DATE_SCRUBBER_OWNER,
    is_mvp_4: 0,
  });
  expect(() =>
    assertDateScrubberOwnership({
      motif_component: "Illustrative2KPanZoom",
      owner_package: "crime_scene_2k",
      is_mvp_4: 0,
    }),
  ).toThrow(/crime_scene_2k/);
  expect(() =>
    assertDateScrubberOwnership({
      motif_component: TIMELINE_DATE_SCRUBBER_ID,
      owner_package: TIMELINE_DATE_SCRUBBER_OWNER,
      is_mvp_4: 1,
    }),
  ).toThrow(/not an MVP-4/);

  const source = readFileSync(new URL("../../src/motifs/TimelineDateScrubber.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/function SafeZoneLayout/);
  expect(source).not.toMatch(/function CaseBoardSpine|function Illustrative2KPanZoom|<Illustrative2KPanZoom/);
  expect(source).not.toMatch(/feTurbulence|feDisplacementMap|#C92A2A/);
  expect(source).not.toMatch(/from ["'].*SfxRegistry/);
});

test("golden multi-year ledger compresses jumps into // TIME GAP dividers", () => {
  const events = pack.temporal_fact_ledger.map((fact) => ({
    fact_id: fact.fact_id,
    datetime_iso: fact.datetime_iso,
    event_summary: fact.event_summary,
  }));
  const layout = layoutTimelineDateScrubber({ events, durationFrames: 240, sceneId: "scene_golden_dates" });
  const tree = TimelineDateScrubber({ events, durationFrames: 240, sceneId: "scene_golden_dates" });

  expect(layout.notches.map((notch) => notch.fact_id)).toEqual([
    "case_golden_01_20min_fact_affidavit",
    "case_golden_01_20min_fact_clue",
    "case_golden_01_20min_fact_news",
    "case_golden_01_20min_fact_ruling",
  ]);
  expect(layout.gaps).toHaveLength(3);
  expect(layout.gaps.every((gap) => gap.kind === "time-gap" && gap.label === TIME_GAP_LABEL)).toBe(true);
  expect(layout.gaps[0]?.deltaMs).toBe(6 * 60 * 1000);
  const yearOverSix = (layout.gaps[2]?.widthPx ?? 0) / (layout.gaps[0]?.widthPx ?? 1);
  const yearOverSixMs = (layout.gaps[2]?.deltaMs ?? 0) / (layout.gaps[0]?.deltaMs ?? 1);
  expect(yearOverSixMs).toBeGreaterThan(1000);
  expect(yearOverSix).toBeLessThan(yearOverSixMs / 100);

  const labels = layout.notches.map((notch) => notch.labelBox);
  expect(overlapsAny(labels)).toBe(false);
  for (const box of [...labels, ...layout.gaps.flatMap((gap) => (gap.box ? [gap.box] : [])), layout.focal.box]) {
    expect(rectInside(box, contentRect())).toBe(true);
    expect(rectsOverlap(box, captionBarRect())).toBe(false);
    expect(rectsOverlap(box, exclusionRect())).toBe(false);
  }
  expect(layout.focal.datetime_iso).toContain("02:14:00-06:00");
  expect(layout.cues).toHaveLength(layout.notches.length);
  expect(layout.suppressed).toHaveLength(0);
  expect(layout.cues.every((cue) => cue.cue === "tick_sfx" && cue.scene_id === "scene_golden_dates")).toBe(true);
  for (let index = 1; index < layout.cues.length; index += 1) {
    const prev = layout.cues[index - 1];
    const next = layout.cues[index];
    if (!prev || !next) throw new Error("missing cue");
    expect(next.start_sample - prev.start_sample).toBeGreaterThanOrEqual((COOLDOWN_MS * MIX_SAMPLE_RATE_HZ) / 1000);
  }

  expect(tree.dataset["safe-zone"]).toBe("css-contained");
  expect(tree.dataset.motif).toBe("TimelineDateScrubber");
  expect(tree.dataset["motif-number"]).toBe("9");
  expect(tree.dataset.owner).toBe("render_catalog");
  expect(tree.dataset["end-screen"]).toBe("false");
  expect(tree.props.style.paddingTop).toBe(SAFE_PADDING_TOP);
  expect(tree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM);
  expect(tree.props.style.width).toBe(FRAME_WIDTH);
  expect(tree.props.style.height).toBe(FRAME_HEIGHT);
  expect(tree.props.style.overflow).toBe("hidden");
  const exclusion = node(tree, "exclusion", "bottom-right");
  expect(exclusion.props.style.width).toBe(EXCLUSION_WIDTH);
  expect(exclusion.props.style.height).toBe(EXCLUSION_HEIGHT);
  const gaps = walkScrub(tree).filter((item) => item.dataset.slot === "time-gap");
  expect(gaps).toHaveLength(3);
  expect(JSON.stringify(tree)).toContain(TIME_GAP_LABEL);
  expect(JSON.stringify(tree)).toContain('"tick_sfx"');
  expect(JSON.stringify(tree)).not.toMatch(/feTurbulence|feDisplacementMap|#C92A2A|Illustrative2KPanZoom/);
  expect(node(tree, "slot", "focal-card").dataset.zoom).toBe(layout.focal.scale.toFixed(3));
});

test("a four-minute cluster stays readable when a multi-year jump would collapse a linear ruler", () => {
  const layout = layoutTimelineDateScrubber({ events: CLUSTER, durationFrames: 240, focalFactId: "years_later" });
  expect(layout.notches.map((notch) => notch.fact_id)).toEqual([
    "cluster_a",
    "cluster_b",
    "cluster_c",
    "years_later",
  ]);
  expect(layout.notches.map((notch) => notch.label)).toEqual(["02:14", "02:16", "02:18", "Jun 18 2021"]);
  expect(layout.notches.slice(0, 3).every((notch) => notch.inCluster)).toBe(true);
  expect(layout.notches[3]?.inCluster).toBe(false);
  expect(layout.gaps.map((gap) => gap.kind)).toEqual(["cluster", "cluster", "time-gap"]);
  expect(layout.gaps[0]?.label).toBeNull();
  expect(layout.gaps[2]?.label).toBe(TIME_GAP_LABEL);
  expect(layout.gaps[0]?.deltaMs).toBe(2 * 60 * 1000);
  expect(layout.gaps[1]?.deltaMs).toBe(2 * 60 * 1000);
  const clusterPx = layout.gaps[0]?.widthPx ?? 0;
  const yearPx = layout.gaps[2]?.widthPx ?? 0;
  expect(clusterPx).toBeGreaterThan(0);
  expect(clusterPx).toBeLessThan(160);
  expect(yearPx).toBeGreaterThan(400);
  expect(yearPx / clusterPx).toBeLessThan((layout.gaps[2]?.deltaMs ?? 1) / (layout.gaps[0]?.deltaMs ?? 1) / 100);

  expect(overlapsAny(layout.notches.map((notch) => notch.labelBox))).toBe(false);
  expect(overlapsAny(layout.notches.map((notch) => notch.mark))).toBe(false);
  for (const notch of layout.notches) expect(rectInside(notch.labelBox, layout.content)).toBe(true);

  const linear = linearLabelBoxes(layout);
  expect(linearNotchXs(
    layout.notches.map((notch) => notch.ms),
    layout.trackLeft,
    layout.trackRight,
  )).toEqual(layout.linearXs);
  expect(overlapsAny(linear)).toBe(true);

  const atArrival = layoutTimelineDateScrubber({
    events: CLUSTER,
    durationFrames: 240,
    focalFactId: "years_later",
    frame: layout.focal.arrivalFrame,
  });
  expect(atArrival.focal.fact_id).toBe("years_later");
  expect(atArrival.focal.scale).toBe(FOCAL_ZOOM_MAX);
  expect(atArrival.focal.arrivalFrame).toBe(239);
  expect(layout.focal.scale).toBeLessThan(1.05);
  expect(rectInside(atArrival.focal.box, contentRect())).toBe(true);
  expect(rectsOverlap(atArrival.focal.box, atArrival.notches[0]?.labelBox ?? contentRect())).toBe(false);
  const tree = TimelineDateScrubber({
    events: CLUSTER,
    durationFrames: 240,
    focalFactId: "years_later",
    frame: layout.focal.arrivalFrame,
  });
  expect(node(tree, "slot", "focal-card").dataset.zoom).toBe("1.500");
  expect(node(tree, "slot", "focal-card").dataset["fact-id"]).toBe("years_later");

  const again = layoutTimelineDateScrubber({ events: CLUSTER, durationFrames: 240, focalFactId: "years_later" });
  expect(JSON.stringify(again)).toBe(JSON.stringify(layout));
});

test("an exact four-minute span is a cluster, and one extra second is a time gap", () => {
  const cluster = layoutTimelineDateScrubber({ events: FOUR_MINUTES, durationFrames: 180 });
  expect(cluster.gaps.every((gap) => gap.kind === "cluster" && gap.label === null)).toBe(true);
  expect(cluster.notches.every((notch) => notch.inCluster && notch.label.startsWith("02:"))).toBe(true);
  expect(overlapsAny(cluster.notches.map((notch) => notch.labelBox))).toBe(false);
  expect(cluster.notches[4]?.ms).toBe((cluster.notches[0]?.ms ?? 0) + CLUSTER_MAX_MS);
  const steps = cluster.notches.slice(1).map((notch, index) => notch.x - (cluster.notches[index]?.x ?? notch.x));
  expect(Math.min(...steps)).toBeGreaterThanOrEqual(cluster.notches[0]?.labelBox.width ?? 0);

  const boundary = layoutTimelineDateScrubber({
    events: [
      { fact_id: "start", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Cluster start" },
      { fact_id: "end", datetime_iso: "2019-04-03T02:18:00Z", event_summary: "Four minutes later" },
    ],
  });
  expect(boundary.gaps[0]?.kind).toBe("cluster");
  expect(boundary.gaps[0]?.deltaMs).toBe(CLUSTER_MAX_MS);

  const over = layoutTimelineDateScrubber({
    events: [
      { fact_id: "start", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Cluster start" },
      { fact_id: "end", datetime_iso: "2019-04-03T02:18:01Z", event_summary: "Just past four minutes" },
    ],
  });
  expect(over.gaps[0]?.kind).toBe("time-gap");
  expect(over.gaps[0]?.label).toBe("// TIME GAP");
  expect(over.gaps[0]?.deltaMs).toBe(CLUSTER_MAX_MS + 1000);
  expect(walkScrub(TimelineDateScrubber({
    events: [
      { fact_id: "start", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Cluster start" },
      { fact_id: "end", datetime_iso: "2019-04-03T02:18:01Z", event_summary: "Just past four minutes" },
    ],
  })).some((item) => item.dataset.slot === "time-gap")).toBe(true);
});

test("tick_sfx cues keep the 60 ms cooldown and the nominal -14 dBTP tick", () => {
  const layout = layoutTimelineDateScrubber({
    events: FOUR_MINUTES.slice(0, 3),
    durationFrames: 3,
    sceneId: "scene_dense_ticks",
  });
  expect(layout.suppressed.length).toBeGreaterThan(0);
  expect(layout.suppressed.every((hit) => hit.reason === "cooldown" && hit.cue === "tick_sfx")).toBe(true);
  expect(layout.cues.length).toBeGreaterThan(0);
  for (let index = 1; index < layout.cues.length; index += 1) {
    const prev = layout.cues[index - 1];
    const next = layout.cues[index];
    if (!prev || !next) throw new Error("missing cue");
    expect(next.start_frame - prev.start_frame).toBeGreaterThanOrEqual(2);
  }
  const cue = layout.cues[0];
  if (!cue) throw new Error("missing tick");
  expect(cue.sample_rate_hz).toBe(48_000);
  expect(cue.duration_samples).toBe(TICK_DURATION_MS * 48);
  expect(cue.cooldown_ms).toBe(60);
  expect(cue.peak_dbtp).toBe(TICK_PEAK_DBTP);
  expect(cue.gain_unit_scale).toBe(GAIN_UNIT_SCALE);
  expect(cue.gain_units).toBe(Math.floor(10 ** (-14 / 20) * GAIN_UNIT_SCALE + 1e-6));
  expect(TICK_GAIN_UNITS).toBe(cue.gain_units);
  expect(cue.burst).toBe(false);
  expect(cue.tapered).toBe(false);
  expect(cue.start_sample).toBe(cue.start_frame * (MIX_SAMPLE_RATE_HZ / 30));
  const exported = exportTickSfxCues(layout.cues);
  expect(exported.endsWith("\n")).toBe(true);
  const parsed = JSON.parse(exported) as { cue: string; fact_id: string }[];
  expect(parsed.map((row) => row.cue)).toEqual(layout.cues.map(() => "tick_sfx"));
  expect(tickSfxTriggers(layout.cues)).toEqual(
    layout.cues.map((row) => ({ cue: "tick_sfx", sceneId: "scene_dense_ticks", frame: row.start_frame })),
  );

  const content = node(TimelineDateScrubber({ events: FOUR_MINUTES.slice(0, 3), durationFrames: 3 }), "slot", "content");
  for (const item of walkScrub(content)) {
    const { left, top, width, height } = item.props.style;
    if (typeof left !== "number" || typeof top !== "number" || typeof width !== "number" || typeof height !== "number") {
      continue;
    }
    expect(left).toBeGreaterThanOrEqual(0);
    expect(top).toBeGreaterThanOrEqual(0);
    expect(left + width).toBeLessThanOrEqual(contentRect().width);
    expect(top + height).toBeLessThanOrEqual(contentRect().height);
  }
});

test("identical timestamps separate, long summaries clamp to 12 words, and the end screen stays clear", () => {
  const layout = layoutTimelineDateScrubber({
    events: [
      { fact_id: "fact_b", datetime_iso: "2019-04-03T02:14:00Z", event_summary: LONG_SUMMARY },
      { fact_id: "fact_a", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Earlier docket line" },
    ],
    isEndScreen: true,
    focalFactId: "fact_b",
  });
  expect(layout.notches.map((notch) => notch.fact_id)).toEqual(["fact_a", "fact_b"]);
  expect(layout.notches[0]?.x).toBeLessThan(layout.notches[1]?.x ?? 0);
  expect(rectsOverlap(layout.notches[0]?.labelBox ?? contentRect(), layout.notches[1]?.labelBox ?? contentRect())).toBe(
    false,
  );
  expect(layout.gaps[0]?.kind).toBe("cluster");
  expect(wordCount(layout.focal.summary)).toBe(RULE_07_MAX_WORDS);
  expect(layout.focal.summary).toBe(clampWords(LONG_SUMMARY));
  expect(layout.focal.summary.endsWith("mike")).toBe(false);
  expect(layout.endScreenMask).not.toBeNull();
  if (!layout.endScreenMask) throw new Error("expected an end-screen mask");
  for (const notch of layout.notches) expect(rectsOverlap(notch.labelBox, layout.endScreenMask)).toBe(false);
  const tree = TimelineDateScrubber({
    events: [
      { fact_id: "fact_b", datetime_iso: "2019-04-03T02:14:00Z", event_summary: LONG_SUMMARY },
      { fact_id: "fact_a", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Earlier docket line" },
    ],
    isEndScreen: true,
    focalFactId: "fact_b",
  });
  expect(tree.dataset["end-screen"]).toBe("true");
  expect(node(tree, "mask", "end-screen-card").props.style.overflow).toBe("hidden");
  expect(JSON.stringify(tree)).not.toContain(" mike");
});

test("rejects a blank ledger, a broken instant, and a ruler that cannot separate its notches", () => {
  expect(() => layoutTimelineDateScrubber({ events: [] })).toThrow(/forensic date list/);
  expect(() =>
    layoutTimelineDateScrubber({
      events: [{ fact_id: "fact_a", datetime_iso: "2019-02-31T00:00:00Z", event_summary: "Impossible day" }],
    }),
  ).toThrow(/ISO-8601/);
  expect(() =>
    layoutTimelineDateScrubber({
      events: [{ fact_id: "fact a", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "Bad id" }],
    }),
  ).toThrow(/fact_ledger/);
  expect(() =>
    layoutTimelineDateScrubber({
      events: [
        { fact_id: "fact_a", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "One" },
        { fact_id: "fact_a", datetime_iso: "2019-04-03T03:14:00Z", event_summary: "Two" },
      ],
    }),
  ).toThrow(/duplicate fact_id/);
  expect(() =>
    layoutTimelineDateScrubber({
      events: [{ fact_id: "fact_a", datetime_iso: "2019-04-03T02:14:00Z", event_summary: "   " }],
    }),
  ).toThrow(/event_summary/);
  expect(() =>
    layoutTimelineDateScrubber({
      events: FOUR_MINUTES,
      focalFactId: "missing",
    }),
  ).toThrow(/focalFactId/);
  expect(() => layoutTimelineDateScrubber({ events: FOUR_MINUTES, frame: 240, durationFrames: 240 })).toThrow(/frame/);
  expect(() => layoutTimelineDateScrubber({ events: FOUR_MINUTES, sceneId: "" })).toThrow(/sceneId/);

  const crowded = Array.from({ length: 40 }, (_, index) => ({
    fact_id: `crowd_${index}`,
    datetime_iso: new Date(Date.UTC(2019, 3, 3, 2, 14, index)).toISOString().replace(".000Z", "Z"),
    event_summary: `Notch ${index}`,
  }));
  expect(() => layoutTimelineDateScrubber({ events: crowded })).toThrow(/Non-overlapping notch invariant/);
});
