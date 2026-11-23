import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import { CATALOG_MOTIFS, MOTIF_REGISTRY_V1 } from "../../../shared-contracts-ts/src/models.ts";
import {
  BLUEPRINT_BG,
  CALLOUT_BORDER,
  DECONFLICT_STEP,
  FRAME_FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  FROZEN_CATALOG_SLOT_7,
  FROZEN_MAP_ROUTE_NAME,
  GRID_COLS,
  GRID_ROWS,
  MAP_MOTIF_NUMBER,
  MAP_ROUTE_TRACE_ID,
  MAP_ROUTE_TRACE_OWNER,
  MAX_WORDS,
  SAFE_PADDING_BOTTOM,
  SAFE_PADDING_TOP,
  SCHEMATIC_LABEL,
  TRACE_STROKE,
  MapRouteTrace,
  MapRouteTraceError,
  countWords,
  easeInOutCubic,
  formatDrive,
  holdFrames,
  layoutMapRouteTrace,
  pulseRadius,
  rectInside,
  rectsOverlap,
  walkMap,
  type MapNode,
  type MapPoint,
  type MapRouteTraceProps,
  type MapWaypoint,
} from "../../src/motifs/MapRouteTrace.tsx";

const pack = JSON.parse(
  readFileSync(new URL("../../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url), "utf8"),
) as {
  motif_registry_v1: { motif_component: string }[];
};

const NJ_ROUTE_9: MapWaypoint[] = [
  {
    waypoint_id: "nj9_bay",
    fact_id: "fact_nj9_bay_lot",
    label: "Bay lot",
    timestamp_label: "22:10",
    x: 0.16,
    y: 0.78,
    arrive_frame: 0,
    leg_drive_sec: 0,
  },
  {
    waypoint_id: "nj9_mile",
    fact_id: "fact_nj9_mile_12",
    label: "Mile 12 pull-off",
    timestamp_label: "22:18",
    x: 0.4,
    y: 0.5,
    arrive_frame: 120,
    leg_drive_sec: 480,
  },
  {
    waypoint_id: "nj9_diner",
    fact_id: "fact_nj9_diner",
    label: "Shore diner",
    timestamp_label: "22:31",
    x: 0.66,
    y: 0.36,
    arrive_frame: 270,
    leg_drive_sec: 780,
  },
  {
    waypoint_id: "nj9_end",
    fact_id: "fact_nj9_claimed_end",
    label: "Claimed end",
    timestamp_label: "22:44",
    x: 0.84,
    y: 0.2,
    arrive_frame: 420,
    leg_drive_sec: 780,
  },
];

function routeProps(frame: number, extra: Partial<MapRouteTraceProps> = {}): MapRouteTraceProps {
  return {
    waypoints: NJ_ROUTE_9,
    frame,
    sceneId: "nj_route_9_alibi",
    routeLabel: "NJ ROUTE 9",
    ...extra,
  };
}

function node(root: MapNode, key: string, value: string): MapNode {
  const found = walkMap(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function parsePoints(value: string | number | undefined): MapPoint[] {
  if (typeof value !== "string" || value.length === 0) return [];
  return value.split(" ").map((pair) => {
    const [x, y] = pair.split(",");
    return { x: Number(x), y: Number(y) };
  });
}

function distance(a: MapPoint, b: MapPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

test("MapRouteTrace is motif 7 and does not amend the frozen registry", () => {
  expect(MAP_MOTIF_NUMBER).toBe(7);
  expect(MAP_ROUTE_TRACE_ID).toBe("MapRouteTrace");
  expect(MAP_ROUTE_TRACE_OWNER).toBe("render_catalog");
  expect(FROZEN_CATALOG_SLOT_7).toBe("CellTowerTriangulation");
  expect(FROZEN_MAP_ROUTE_NAME).toBe("AnimatedMapRoute");
  expect(CATALOG_MOTIFS[6]).toBe("CellTowerTriangulation");
  expect(CATALOG_MOTIFS[5]).toBe("AnimatedMapRoute");
  expect(CATALOG_MOTIFS).not.toContain(MAP_ROUTE_TRACE_ID);
  expect(MOTIF_REGISTRY_V1.map((entry) => entry.motif_component)).toEqual([
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
  ]);
  expect(pack.motif_registry_v1.map((entry) => entry.motif_component)).toContain("AnimatedMapRoute");
  expect(pack.motif_registry_v1.map((entry) => entry.motif_component)).not.toContain("MapRouteTrace");

  const source = readFileSync(new URL("../../src/motifs/MapRouteTrace.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/function SafeZoneLayout/);
  expect(source).toMatch(/openstreetmap/);
  expect(source).not.toMatch(/feTurbulence|feDisplacementMap|Illustrative2KPanZoom|#C92A2A/);
  expect(source).not.toMatch(/<image[\s/>]/);
  expect(source).not.toMatch(/xlink:href\s*=/);
  expect(source).not.toMatch(/https?:\/\/[a-z0-9.-]+/i);
  expect(source).not.toMatch(/Math\.random|Date\.now|fetch\(/);
  expect(source).not.toMatch(/from ["'][^"']*safe_zone/);
  expect(source).not.toMatch(/from ["'][^"']*SafeCallout/);
  expect(source).not.toMatch(/from ["'][^"']*rig_consistency/);

  const sql = readFileSync(new URL("../../../../schema/pipeline.sql", import.meta.url), "utf8");
  expect(sql).toContain("('AnimatedMapRoute',       'render_catalog', 0)");
  expect(sql).toContain("('CellTowerTriangulation', 'render_catalog', 0)");
  expect(sql).not.toContain("MapRouteTrace");
});

test("NJ Route 9 multi-stop alibi traces the polyline, HUD, and per-leg timestamps", () => {
  expect(easeInOutCubic(0)).toBe(0);
  expect(easeInOutCubic(0.5)).toBe(0.5);
  expect(easeInOutCubic(1)).toBe(1);
  expect(formatDrive(0)).toBe("00:00");
  expect(formatDrive(240)).toBe("04:00");
  expect(formatDrive(480)).toBe("08:00");
  expect(formatDrive(1260)).toBe("21:00");
  expect(formatDrive(2040)).toBe("34:00");

  const start = layoutMapRouteTrace(routeProps(0));
  expect(start.routeLabel).toBe("NJ ROUTE 9");
  expect(start.tileCount).toBe(0);
  expect(start.marker).toMatchObject({ x: start.waypoints[0]?.page.x, y: start.waypoints[0]?.page.y, pulsing: false });
  expect(start.elapsedDriveSec).toBe(0);
  expect(start.elapsedLabel).toBe("00:00");
  expect(start.totalDriveSec).toBe(2040);
  expect(start.totalLabel).toBe("34:00");
  expect(start.callouts.map((callout) => callout.waypoint_id)).toEqual(["nj9_bay", "nj9_mile"]);
  expect(start.trace).toEqual([start.waypoints[0]?.page]);

  const mid = layoutMapRouteTrace(routeProps(60));
  const origin = mid.waypoints[0];
  const mile = mid.waypoints[1];
  if (!origin || !mile) throw new Error("missing the first leg");
  expect(mid.marker.pulsing).toBe(false);
  expect(mid.marker.leg).toBe(1);
  expect(mid.marker.x).toBe(Math.round(origin.page.x + (mile.page.x - origin.page.x) * 0.5));
  expect(mid.marker.y).toBe(Math.round(origin.page.y + (mile.page.y - origin.page.y) * 0.5));
  expect(mid.elapsedDriveSec).toBe(240);
  expect(mid.elapsedLabel).toBe("04:00");
  expect(mid.trace).toHaveLength(2);
  expect(mid.trace[1]).toEqual({ x: mid.marker.x, y: mid.marker.y });
  expect(mid.callouts.map((callout) => callout.fact_id)).toEqual(["fact_nj9_bay_lot", "fact_nj9_mile_12"]);
  const mileCallout = mid.callouts[1];
  if (!mileCallout) throw new Error("missing the mile 12 callout");
  expect(mileCallout.text).toBe("22:18 · Mile 12 pull-off");
  expect(mileCallout.words).toBe(countWords(mileCallout.text));
  expect(mileCallout.words).toBeLessThanOrEqual(MAX_WORDS);
  expect(mileCallout.truncated).toBe(false);
  expect(mileCallout.hold_frames).toBe(holdFrames(mileCallout.words));
  expect(mileCallout.hold_frames).toBeGreaterThanOrEqual(Math.ceil((1 + 0.3 * mileCallout.words) * FRAME_FPS));
  expect(layoutMapRouteTrace(routeProps(mileCallout.hold_frames - 1)).callouts.some((callout) => callout.fact_id === "fact_nj9_mile_12")).toBe(true);

  const atMile = layoutMapRouteTrace(routeProps(120));
  expect(atMile.marker).toMatchObject({ x: atMile.waypoints[1]?.page.x, y: atMile.waypoints[1]?.page.y });
  expect(atMile.elapsedDriveSec).toBe(480);
  expect(atMile.elapsedLabel).toBe("08:00");
  expect(atMile.callouts.map((callout) => callout.waypoint_id)).toEqual(["nj9_bay", "nj9_mile", "nj9_diner"]);

  const done = layoutMapRouteTrace(routeProps(420));
  expect(done.waypoints).toHaveLength(4);
  expect(done.marker).toMatchObject({ x: done.waypoints[3]?.page.x, y: done.waypoints[3]?.page.y, pulsing: true, leg: 3 });
  expect(done.marker.r).toBe(pulseRadius(420));
  expect(done.elapsedDriveSec).toBe(done.totalDriveSec);
  expect(done.elapsedLabel).toBe("34:00");
  expect(done.callouts.map((callout) => callout.text)).toEqual([
    "22:10 · Bay lot",
    "22:18 · Mile 12 pull-off",
    "22:31 · Shore diner",
    "22:44 · Claimed end",
  ]);
  expect(done.callouts.map((callout) => callout.fact_id)).toEqual(NJ_ROUTE_9.map((waypoint) => waypoint.fact_id));
  expect(done.callouts.every((callout) => callout.words <= MAX_WORDS && callout.truncated === false)).toBe(true);
  for (let left = 0; left < done.callouts.length; left += 1) {
    for (let right = left + 1; right < done.callouts.length; right += 1) {
      const a = done.callouts[left];
      const b = done.callouts[right];
      if (!a || !b) throw new Error("missing callout");
      expect(rectsOverlap(a.box, b.box)).toBe(false);
      expect(rectInside(a.box, done.board)).toBe(true);
    }
  }
  expect(rectInside(done.board, done.content)).toBe(true);
  expect(rectsOverlap(done.board, done.captionBar)).toBe(false);
  expect(rectsOverlap(done.board, done.exclusion)).toBe(false);
  expect(done.trace.at(-1)).toEqual({ x: done.marker.x, y: done.marker.y });
  expect(done.gridLines).toBe(GRID_COLS + 1 + (GRID_ROWS + 1));

  let previous = 0;
  for (let frame = 0; frame <= 120; frame += 1) {
    const layout = layoutMapRouteTrace(routeProps(frame));
    const traveled = distance(origin.page, layout.marker);
    expect(traveled).toBeGreaterThanOrEqual(previous);
    previous = traveled;
    expect(Number.isFinite(layout.marker.x)).toBe(true);
    expect(Number.isFinite(layout.marker.y)).toBe(true);
  }
  const openingStep = distance(layoutMapRouteTrace(routeProps(0)).marker, layoutMapRouteTrace(routeProps(1)).marker);
  const middleStep = distance(layoutMapRouteTrace(routeProps(59)).marker, layoutMapRouteTrace(routeProps(60)).marker);
  expect(middleStep).toBeGreaterThan(openingStep);

  const tree = MapRouteTrace(routeProps(60));
  expect(tree.dataset["safe-zone"]).toBe("css-contained");
  expect(tree.dataset.motif).toBe(MAP_ROUTE_TRACE_ID);
  expect(tree.dataset["motif-number"]).toBe("7");
  expect(tree.dataset.owner).toBe(MAP_ROUTE_TRACE_OWNER);
  expect(tree.dataset.procedural).toBe("svg");
  expect(tree.dataset.tiles).toBe("0");
  expect(tree.dataset["end-screen"]).toBe("false");
  expect(tree.props.style.paddingTop).toBe(SAFE_PADDING_TOP);
  expect(tree.props.style.paddingBottom).toBe(SAFE_PADDING_BOTTOM);
  expect(tree.props.style.width).toBe(FRAME_WIDTH);
  expect(tree.props.style.height).toBe(FRAME_HEIGHT);
  expect(tree.props.style.overflow).toBe("hidden");
  expect(tree.props.style.background).toBe(BLUEPRINT_BG);
  expect(node(tree, "exclusion", "bottom-right").props.style).toMatchObject({ width: "22%", height: "14%" });

  const svg = node(tree, "slot", "blueprint");
  expect(svg.type).toBe("svg");
  expect(svg.dataset.tiles).toBe("0");
  expect(svg.dataset.procedural).toBe("svg");
  const geometry = walkMap(svg);
  expect(geometry.every((item) => item.type === "svg" || item.type === "line" || item.type === "polyline" || item.type === "circle")).toBe(true);
  expect(geometry.some((item) => (item.type as string) === "image")).toBe(false);
  expect(geometry.filter((item) => item.dataset.slot === "grid")).toHaveLength(mid.gridLines);
  const vertical = geometry.filter((item) => item.dataset.slot === "grid" && item.dataset.axis === "x");
  expect(vertical[0]?.props.attrs.x1).toBe(0);
  expect(vertical.at(-1)?.props.attrs.x1).toBe(mid.plot.width);
  const ghost = node(tree, "slot", "route");
  expect(ghost.type).toBe("polyline");
  expect(parsePoints(ghost.props.attrs.points)).toEqual(
    mid.waypoints.map((waypoint) => ({ x: waypoint.page.x - mid.plot.x, y: waypoint.page.y - mid.plot.y })),
  );
  const trace = node(tree, "slot", "trace");
  expect(trace.props.attrs.stroke).toBe(TRACE_STROKE);
  expect(parsePoints(trace.props.attrs.points)).toHaveLength(2);
  const marker = node(tree, "slot", "marker");
  expect(marker.type).toBe("circle");
  expect(marker.props.attrs.cx).toBe(mid.marker.x - mid.plot.x);
  expect(marker.props.attrs.cy).toBe(mid.marker.y - mid.plot.y);
  expect(marker.dataset.pulsing).toBe("false");
  const hud = node(tree, "slot", "drive-hud");
  expect(hud.props.children).toBe(`NJ ROUTE 9\n${SCHEMATIC_LABEL}\nELAPSED 04:00\nCLAIMED 34:00`);
  expect(hud.dataset["elapsed-sec"]).toBe("240");
  expect(hud.dataset["total-sec"]).toBe("2040");
  expect(hud.dataset.tiles).toBe("0");
  const callouts = walkMap(tree).filter((item) => item.dataset.slot === "callout");
  expect(callouts.map((item) => item.dataset["fact-id"])).toEqual(["fact_nj9_bay_lot", "fact_nj9_mile_12"]);
  expect(callouts[1]?.props.children).toBe("22:18 · Mile 12 pull-off");
  expect(callouts[1]?.props.style.border).toBe(`1px solid ${CALLOUT_BORDER}`);
  expect(callouts[1]?.props.style.overflow).toBe("hidden");
  const rendered = JSON.stringify(tree);
  expect(rendered).not.toMatch(/openstreetmap|mapbox|googleapis|arcgis|maptiler|leaflet|carto\.com|https?:\/\//i);
  expect(rendered).not.toMatch(/feTurbulence|feDisplacementMap|#C92A2A|"type":"image"/);
  expect(JSON.stringify(MapRouteTrace(routeProps(60)))).toBe(rendered);
});

test("overlapping timestamp callouts separate by 64px and a long line clamps to 12 words", () => {
  const crowded = layoutMapRouteTrace({
    waypoints: [
      {
        waypoint_id: "nj9_a",
        fact_id: "fact_nj9_bay_lot",
        label: "Bay lot",
        timestamp_label: "22:10",
        x: 0.3,
        y: 0.55,
        arrive_frame: 0,
        leg_drive_sec: 0,
      },
      {
        waypoint_id: "nj9_b",
        fact_id: "fact_nj9_mile_12",
        label: "Mile post",
        timestamp_label: "22:18",
        x: 0.34,
        y: 0.55,
        arrive_frame: 90,
        leg_drive_sec: 120,
      },
    ],
    frame: 90,
    sceneId: "nj_route_9_alibi",
    routeLabel: "NJ ROUTE 9",
  });
  expect(crowded.callouts).toHaveLength(2);
  const [first, second] = crowded.callouts;
  if (!first || !second) throw new Error("missing crowded callouts");
  expect(rectsOverlap(first.box, second.box)).toBe(false);
  expect(first.shifted).toBe(false);
  expect(second.shifted).toBe(true);
  expect(Math.abs(second.box.y - first.box.y) % DECONFLICT_STEP).toBe(0);
  expect(Math.abs(second.box.y - first.box.y)).toBeGreaterThanOrEqual(DECONFLICT_STEP);
  expect(rectInside(first.box, crowded.board)).toBe(true);
  expect(rectInside(second.box, crowded.board)).toBe(true);

  const words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india", "juliet", "kilo"];
  const clamped = layoutMapRouteTrace({
    waypoints: [
      {
        waypoint_id: "nj9_bay",
        fact_id: "fact_nj9_bay_lot",
        label: "Bay lot",
        timestamp_label: "22:10",
        x: 0.2,
        y: 0.4,
        arrive_frame: 0,
        leg_drive_sec: 0,
      },
      {
        waypoint_id: "nj9_note",
        fact_id: "fact_nj9_mile_12",
        label: words.join(" "),
        timestamp_label: "22:18",
        x: 0.7,
        y: 0.3,
        arrive_frame: 60,
        leg_drive_sec: 60,
      },
    ],
    frame: 60,
    routeLabel: "NJ ROUTE 9",
  });
  const note = clamped.callouts.find((callout) => callout.waypoint_id === "nj9_note");
  if (!note) throw new Error("missing clamped callout");
  expect(note.truncated).toBe(true);
  expect(note.words).toBe(MAX_WORDS);
  expect(countWords(note.text)).toBe(MAX_WORDS);
  expect(note.text.includes("kilo")).toBe(false);
  expect(note.text.startsWith("22:18 · alpha")).toBe(true);
});

test("a coincident stop pulses in place instead of dividing by zero", () => {
  const props = {
    waypoints: [
      {
        waypoint_id: "nj9_same_a",
        fact_id: "fact_nj9_bay_lot",
        label: "Same pin",
        timestamp_label: "22:10",
        x: 0.4,
        y: 0.4,
        arrive_frame: 0,
        leg_drive_sec: 0,
      },
      {
        waypoint_id: "nj9_same_b",
        fact_id: "fact_nj9_mile_12",
        label: "Same pin",
        timestamp_label: "22:12",
        x: 0.4,
        y: 0.4 + 5e-8,
        arrive_frame: 30,
        leg_drive_sec: 90,
      },
    ],
    frame: 15,
    sceneId: "nj_route_9_alibi",
    routeLabel: "NJ ROUTE 9",
  } satisfies MapRouteTraceProps;
  const mid = layoutMapRouteTrace(props);
  const opened = layoutMapRouteTrace({ ...props, frame: 0 });
  expect(mid.coincident).toBe(true);
  expect(mid.marker.pulsing).toBe(true);
  expect(mid.marker.x).toBe(opened.marker.x);
  expect(mid.marker.y).toBe(opened.marker.y);
  expect(mid.marker.r).not.toBe(opened.marker.r);
  expect(mid.marker.r).toBe(pulseRadius(15));
  expect(mid.elapsedDriveSec).toBe(45);
  expect(Number.isFinite(mid.marker.x)).toBe(true);
  const tree = MapRouteTrace(props);
  expect(node(tree, "slot", "marker").dataset.coincident).toBe("true");
  expect(node(tree, "slot", "marker").dataset.pulsing).toBe("true");
});

test("the end-screen mask keeps the blueprint above the card", () => {
  const layout = layoutMapRouteTrace(routeProps(420, { isEndScreen: true }));
  expect(layout.isEndScreen).toBe(true);
  expect(layout.endScreenMask).not.toBeNull();
  if (!layout.endScreenMask) throw new Error("missing end-screen mask");
  expect(rectsOverlap(layout.board, layout.endScreenMask)).toBe(false);
  expect(layout.callouts.every((callout) => rectInside(callout.box, layout.board))).toBe(true);
  const tree = MapRouteTrace(routeProps(420, { isEndScreen: true }));
  expect(tree.dataset["end-screen"]).toBe("true");
  expect(node(tree, "mask", "end-screen-card").props.style.overflow).toBe("hidden");
});

test("rejects a broken route, a tile URL, and more stops than the schematic can hold", () => {
  const bay: MapWaypoint = {
    waypoint_id: "nj9_bay",
    fact_id: "fact_nj9_bay_lot",
    label: "Bay lot",
    timestamp_label: "22:10",
    x: 0.2,
    y: 0.4,
    arrive_frame: 0,
    leg_drive_sec: 0,
  };
  const mile: MapWaypoint = {
    waypoint_id: "nj9_mile",
    fact_id: "fact_nj9_mile_12",
    label: "Mile 12 pull-off",
    timestamp_label: "22:18",
    x: 0.6,
    y: 0.3,
    arrive_frame: 60,
    leg_drive_sec: 120,
  };
  expect(() => layoutMapRouteTrace({ waypoints: [], frame: 0 })).toThrow(/at least two stops/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay], frame: 0 })).toThrow(/at least two stops/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, { ...mile, waypoint_id: "nj9_bay" }], frame: 0 })).toThrow(
    /duplicate waypoint_id/,
  );
  expect(() => layoutMapRouteTrace({ waypoints: [bay, { ...mile, arrive_frame: 0 }], frame: 0 })).toThrow(/arrive_frame/);
  expect(() => layoutMapRouteTrace({ waypoints: [{ ...bay, arrive_frame: 4 }, mile], frame: 0 })).toThrow(/frame 0/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, { ...mile, x: 1.2 }], frame: 0 })).toThrow(/0\.\.1/);
  expect(() => layoutMapRouteTrace({ waypoints: [{ ...bay, leg_drive_sec: 5 }, mile], frame: 0 })).toThrow(/inbound drive/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, { ...mile, leg_drive_sec: 0 }], frame: 0 })).toThrow(/leg_drive_sec/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, { ...mile, fact_id: "bad id" }], frame: 0 })).toThrow(/fact_id/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, { ...mile, label: "   " }], frame: 0 })).toThrow(/label/);
  expect(() =>
    layoutMapRouteTrace({
      waypoints: [bay, { ...mile, label: "see https://tile.openstreetmap.org/1/2/3.png" }],
      frame: 0,
    }),
  ).toThrow(/map tile/);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, mile], frame: -1 })).toThrow(MapRouteTraceError);
  expect(() => layoutMapRouteTrace({ waypoints: [bay, mile], frame: 0, routeLabel: "https://mapbox.com/x" })).toThrow(
    /map tile/,
  );
  const tooMany = Array.from({ length: 33 }, (_, index) => ({
    waypoint_id: `nj9_${index}`,
    fact_id: "fact_nj9_bay_lot",
    label: "Stop",
    timestamp_label: "22:10",
    x: index / 40,
    y: 0.4,
    arrive_frame: index * 10,
    leg_drive_sec: index === 0 ? 0 : 30,
  }));
  expect(() => layoutMapRouteTrace({ waypoints: tooMany, frame: 0 })).toThrow(/at most 32/);
});
