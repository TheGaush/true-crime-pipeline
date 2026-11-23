/**
 * Motif 7 — MapRouteTrace.
 *
 * Procedural blueprint of a multi-stop route: SVG grid, polyline, drive-time
 * HUD, and a marker that eases along `waypoints[]`. The package tsconfig has
 * no `jsx` flag (Task 001), so `<SafeZoneLayout>` is a function in this file.
 * Task 101's `safe_zone.tsx`, Task 111's `SafeCallout.tsx`, and Task 114's rig
 * suite are other branches. They are not copied here.
 *
 * The frozen SQL catalog's seventh Remotion name is `CellTowerTriangulation`.
 * The procedural map row stays `AnimatedMapRoute`. `MOTIF_REGISTRY_V1` stays
 * the four MVP motifs. This file does not amend that contract. Task 121 owns
 * this component as motif 7.
 *
 * Coordinates are caller-supplied schematic numbers in `[0, 1]`. Nothing in
 * this module fetches or embeds a map tile.
 */

export const MAP_ROUTE_TRACE_ID = "MapRouteTrace" as const;
export const MAP_ROUTE_TRACE_OWNER = "render_catalog" as const;
export const MAP_MOTIF_NUMBER = 7 as const;
export const FROZEN_CATALOG_SLOT_7 = "CellTowerTriangulation" as const;
export const FROZEN_MAP_ROUTE_NAME = "AnimatedMapRoute" as const;

export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FRAME_FPS = 30;
export const SAFE_PADDING_TOP = 108;
export const SAFE_PADDING_BOTTOM = 194;
export const END_SCREEN_MASK_H = 48;
export const EXCLUSION_WIDTH = "22%";
export const EXCLUSION_HEIGHT = "14%";

export const BOARD_INSET_X = 48;
export const BOARD_INSET_Y = 28;
export const HUD_W = 440;
export const HUD_H = 96;
export const HUD_MARGIN = 20;
export const PLOT_GAP = 16;
export const PLOT_INSET_X = 24;
export const PLOT_INSET_BOTTOM = 24;
export const GRID_COLS = 12;
export const GRID_ROWS = 8;
export const MARKER_R = 9;
export const PIN_R = 4;
export const PULSE_R_MIN = 9;
export const PULSE_R_MAX = 14;
export const PULSE_PERIOD = 30;
export const COINCIDENT_NORM = 1e-6;
export const CALLOUT_H = 36;
export const CALLOUT_MAX_W = 280;
export const CALLOUT_PAD_X = 14;
export const CALLOUT_CHAR_PX = 11;
export const CALLOUT_GAP = 12;
export const DECONFLICT_STEP = 64;
export const MAX_WORDS = 12;
export const HOLD_BASE_SEC = 1;
export const HOLD_PER_WORD_SEC = 0.3;
export const MAX_WAYPOINTS = 32;
export const MAX_DRIVE_SEC = 24 * 60 * 60;
export const DEFAULT_ROUTE_LABEL = "ROUTE TRACE";
export const SCHEMATIC_LABEL = "SCHEMATIC · NO TILES";

export const BLUEPRINT_BG = "#0E2438";
export const BOARD_BG = "#0B1E30";
export const GRID_STROKE = "#1C4E6E";
export const GHOST_STROKE = "#2F6F8F";
export const TRACE_STROKE = "#E7C27A";
export const PIN_FILL = "#8FB8CC";
export const MARKER_FILL = "#F7F1E4";
export const INK = "#E7F2F8";
export const HUD_BG = "#123044";
export const CALLOUT_BG = "#16384E";
export const CALLOUT_BORDER = "#7EC8E3";

const ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const HTTP_PATTERN = /https?:\/\//i;
const TILE_HOST_PATTERN = /openstreetmap|mapbox|googleapis|arcgis|carto\.com|maptiler|leaflet|tiles\.|tile\.openstreetmap/i;
const BANNED_ATTR = /^(href|src|xlinkhref|xlink:href)$/i;
const ALLOWED_TYPES = new Set(["div", "svg", "polyline", "line", "circle"]);

export type CssValue = string | number;

export type Rect = {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type MapPoint = {
  readonly x: number;
  readonly y: number;
};

export type MapChild = MapNode | string;

export type MapNode = {
  readonly type: "div" | "svg" | "polyline" | "line" | "circle";
  readonly dataset: Readonly<Record<string, string>>;
  readonly props: {
    readonly style: Readonly<Record<string, CssValue>>;
    readonly attrs: Readonly<Record<string, string | number>>;
    readonly children?: MapChild | readonly MapChild[];
  };
};

export type MapWaypoint = {
  readonly waypoint_id: string;
  readonly fact_id: string;
  readonly label: string;
  readonly timestamp_label: string;
  readonly x: number;
  readonly y: number;
  readonly arrive_frame: number;
  readonly leg_drive_sec: number;
};

export type MapRouteTraceProps = {
  readonly waypoints: readonly MapWaypoint[];
  readonly frame: number;
  readonly sceneId?: string;
  readonly routeLabel?: string;
  readonly isEndScreen?: boolean;
};

export type PlacedWaypoint = {
  readonly waypoint_id: string;
  readonly fact_id: string;
  readonly label: string;
  readonly timestamp_label: string;
  readonly arrive_frame: number;
  readonly leg_drive_sec: number;
  readonly norm: MapPoint;
  readonly page: MapPoint;
};

export type PlacedCallout = {
  readonly waypoint_id: string;
  readonly fact_id: string;
  readonly leg: number;
  readonly text: string;
  readonly words: number;
  readonly truncated: boolean;
  readonly hold_frames: number;
  readonly box: Rect;
  readonly shifted: boolean;
};

export type MapRouteTraceLayout = {
  readonly motif: typeof MAP_ROUTE_TRACE_ID;
  readonly owner: typeof MAP_ROUTE_TRACE_OWNER;
  readonly motifNumber: typeof MAP_MOTIF_NUMBER;
  readonly frame: number;
  readonly sceneId: string;
  readonly routeLabel: string;
  readonly isEndScreen: boolean;
  readonly content: Rect;
  readonly exclusion: Rect;
  readonly captionBar: Rect;
  readonly endScreenMask: Rect | null;
  readonly board: Rect;
  readonly plot: Rect;
  readonly hud: Rect;
  readonly waypoints: readonly PlacedWaypoint[];
  readonly trace: readonly MapPoint[];
  readonly marker: MapPoint & { readonly r: number; readonly pulsing: boolean; readonly leg: number };
  readonly elapsedDriveSec: number;
  readonly totalDriveSec: number;
  readonly elapsedLabel: string;
  readonly totalLabel: string;
  readonly callouts: readonly PlacedCallout[];
  readonly gridLines: number;
  readonly tileCount: 0;
  readonly coincident: boolean;
};

type NormalizedWaypoint = {
  readonly waypoint_id: string;
  readonly fact_id: string;
  readonly label: string;
  readonly timestamp_label: string;
  readonly x: number;
  readonly y: number;
  readonly arrive_frame: number;
  readonly leg_drive_sec: number;
};

type Prepared = {
  readonly waypoints: readonly NormalizedWaypoint[];
  readonly sceneId: string;
  readonly routeLabel: string;
  readonly isEndScreen: boolean;
  readonly frame: number;
};

type LegState = {
  readonly fromIndex: number;
  readonly toIndex: number;
  readonly t: number;
  readonly moving: boolean;
  readonly pulsing: boolean;
  readonly coincident: boolean;
};

type CalloutDraft = {
  readonly waypoint: PlacedWaypoint;
  readonly leg: number;
  readonly text: string;
  readonly words: number;
  readonly truncated: boolean;
  readonly preferred: Rect;
};

export class MapRouteTraceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MapRouteTraceError";
  }
}

export function countWords(value: string): number {
  const words = value.trim().split(/\s+/).filter((word) => word.length > 0);
  return words.length;
}

export function holdFrames(wordCount: number): number {
  if (!Number.isInteger(wordCount) || wordCount < 1 || wordCount > MAX_WORDS) {
    fail(`callout word count must be 1–${MAX_WORDS}`);
  }
  return Math.ceil((HOLD_BASE_SEC + HOLD_PER_WORD_SEC * wordCount) * FRAME_FPS);
}

export function formatDrive(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) fail("drive time must be a finite non-negative number");
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remain = whole % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(remain).padStart(2, "0");
  if (hours > 0) return `${hours}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}

export function easeInOutCubic(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  if (t < 0.5) return 4 * t * t * t;
  return 1 - ((-2 * t + 2) ** 3) / 2;
}

export function pulseRadius(frame: number): number {
  const phase = frame % PULSE_PERIOD;
  const tri = phase <= 15 ? phase / 15 : (PULSE_PERIOD - phase) / 15;
  return Math.round((PULSE_R_MIN + (PULSE_R_MAX - PULSE_R_MIN) * tri) * 10) / 10;
}

export function contentRect(): Rect {
  return {
    x: 0,
    y: SAFE_PADDING_TOP,
    width: FRAME_WIDTH,
    height: FRAME_HEIGHT - SAFE_PADDING_TOP - SAFE_PADDING_BOTTOM,
  };
}

export function exclusionRect(): Rect {
  const width = FRAME_WIDTH * 0.22;
  const height = FRAME_HEIGHT * 0.14;
  return {
    x: FRAME_WIDTH - width,
    y: FRAME_HEIGHT - height,
    width,
    height,
  };
}

export function captionBarRect(): Rect {
  return {
    x: 0,
    y: FRAME_HEIGHT - SAFE_PADDING_BOTTOM,
    width: FRAME_WIDTH,
    height: SAFE_PADDING_BOTTOM,
  };
}

export function endScreenMaskRect(): Rect {
  const exclusion = exclusionRect();
  const caption = captionBarRect();
  return {
    x: 0,
    y: caption.y - END_SCREEN_MASK_H,
    width: exclusion.x,
    height: END_SCREEN_MASK_H,
  };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

export function rectInside(inner: Rect, outer: Rect): boolean {
  return (
    inner.x >= outer.x &&
    inner.y >= outer.y &&
    inner.x + inner.width <= outer.x + outer.width &&
    inner.y + inner.height <= outer.y + outer.height
  );
}

export function walkMap(node: MapChild, into: MapNode[] = []): MapNode[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined) return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) walkMap(child, into);
  return into;
}

export function layoutMapRouteTrace(props: MapRouteTraceProps): MapRouteTraceLayout {
  const prepared = prepare(props);
  const chrome = placeChrome(prepared.isEndScreen);
  const placed = prepared.waypoints.map((waypoint) => placeWaypoint(chrome.plot, waypoint));
  const leg = legState(prepared.waypoints, prepared.frame);
  const markerPoint = markerAt(placed, leg);
  const trace = tracePoints(placed, leg, markerPoint);
  const elapsedDriveSec = elapsedDrive(prepared.waypoints, leg);
  const totalDriveSec = prepared.waypoints.reduce((sum, waypoint) => sum + waypoint.leg_drive_sec, 0);
  const callouts = placeCallouts(visibleCallouts(placed, prepared.frame, leg), chrome.board, [chrome.hud]);
  const layout: MapRouteTraceLayout = {
    motif: MAP_ROUTE_TRACE_ID,
    owner: MAP_ROUTE_TRACE_OWNER,
    motifNumber: MAP_MOTIF_NUMBER,
    frame: prepared.frame,
    sceneId: prepared.sceneId,
    routeLabel: prepared.routeLabel,
    isEndScreen: prepared.isEndScreen,
    content: chrome.content,
    exclusion: exclusionRect(),
    captionBar: captionBarRect(),
    endScreenMask: prepared.isEndScreen ? endScreenMaskRect() : null,
    board: chrome.board,
    plot: chrome.plot,
    hud: chrome.hud,
    waypoints: placed,
    trace,
    marker: {
      x: markerPoint.x,
      y: markerPoint.y,
      r: leg.pulsing ? pulseRadius(prepared.frame) : MARKER_R,
      pulsing: leg.pulsing,
      leg: leg.toIndex,
    },
    elapsedDriveSec,
    totalDriveSec,
    elapsedLabel: formatDrive(elapsedDriveSec),
    totalLabel: formatDrive(totalDriveSec),
    callouts,
    gridLines: GRID_COLS + 1 + (GRID_ROWS + 1),
    tileCount: 0,
    coincident: leg.coincident,
  };
  assertContained(layout);
  return layout;
}

export function MapRouteTrace(props: MapRouteTraceProps): MapNode {
  const layout = layoutMapRouteTrace(props);
  const origin = layout.board;
  const svgChildren: MapChild[] = [];
  for (let col = 0; col <= GRID_COLS; col += 1) {
    const x = Math.round((col * layout.plot.width) / GRID_COLS);
    svgChildren.push(
      shape(
        "line",
        { slot: "grid", axis: "x", index: String(col) },
        { x1: x, y1: 0, x2: x, y2: layout.plot.height, stroke: GRID_STROKE, "stroke-width": 1 },
      ),
    );
  }
  for (let row = 0; row <= GRID_ROWS; row += 1) {
    const y = Math.round((row * layout.plot.height) / GRID_ROWS);
    svgChildren.push(
      shape(
        "line",
        { slot: "grid", axis: "y", index: String(row) },
        { x1: 0, y1: y, x2: layout.plot.width, y2: y, stroke: GRID_STROKE, "stroke-width": 1 },
      ),
    );
  }
  svgChildren.push(
    shape(
      "polyline",
      { slot: "route", points: String(layout.waypoints.length) },
      {
        points: pointString(layout.waypoints.map((waypoint) => localPoint(layout.plot, waypoint.page))),
        fill: "none",
        stroke: GHOST_STROKE,
        "stroke-width": 4,
        "stroke-dasharray": "10 8",
      },
    ),
  );
  if (layout.trace.length >= 2) {
    svgChildren.push(
      shape(
        "polyline",
        { slot: "trace", points: String(layout.trace.length) },
        {
          points: pointString(layout.trace.map((point) => localPoint(layout.plot, point))),
          fill: "none",
          stroke: TRACE_STROKE,
          "stroke-width": 6,
        },
      ),
    );
  }
  for (const waypoint of layout.waypoints) {
    const local = localPoint(layout.plot, waypoint.page);
    svgChildren.push(
      shape(
        "circle",
        { slot: "pin", "waypoint-id": waypoint.waypoint_id, "fact-id": waypoint.fact_id },
        { cx: local.x, cy: local.y, r: PIN_R, fill: PIN_FILL },
      ),
    );
  }
  const markerLocal = localPoint(layout.plot, layout.marker);
  svgChildren.push(
    shape(
      "circle",
      {
        slot: "marker",
        pulsing: layout.marker.pulsing ? "true" : "false",
        leg: String(layout.marker.leg),
        coincident: layout.coincident ? "true" : "false",
      },
      { cx: markerLocal.x, cy: markerLocal.y, r: layout.marker.r, fill: MARKER_FILL },
    ),
  );
  const calloutNodes = layout.callouts.map((callout) =>
    element(
      "div",
      {
        slot: "callout",
        "waypoint-id": callout.waypoint_id,
        "fact-id": callout.fact_id,
        leg: String(callout.leg),
        timestamp: callout.text,
        words: String(callout.words),
        truncated: callout.truncated ? "true" : "false",
        shifted: callout.shifted ? "true" : "false",
        "hold-frames": String(callout.hold_frames),
      },
      {
        position: "absolute",
        left: callout.box.x - origin.x,
        top: callout.box.y - origin.y,
        width: callout.box.width,
        height: callout.box.height,
        boxSizing: "border-box",
        overflow: "hidden",
        padding: `0 ${CALLOUT_PAD_X}px`,
        background: CALLOUT_BG,
        color: INK,
        border: `1px solid ${CALLOUT_BORDER}`,
        fontSize: 18,
        lineHeight: `${CALLOUT_H}px`,
        whiteSpace: "nowrap",
      },
      {},
      [callout.text],
    ),
  );
  const boardChildren: MapChild[] = [
    element(
      "svg",
      {
        slot: "blueprint",
        procedural: "svg",
        tiles: "0",
        route: layout.routeLabel,
      },
      {
        position: "absolute",
        left: layout.plot.x - origin.x,
        top: layout.plot.y - origin.y,
        width: layout.plot.width,
        height: layout.plot.height,
        overflow: "hidden",
      },
      {
        viewBox: `0 0 ${layout.plot.width} ${layout.plot.height}`,
        width: layout.plot.width,
        height: layout.plot.height,
      },
      svgChildren,
    ),
    element(
      "div",
      {
        slot: "drive-hud",
        route: layout.routeLabel,
        "elapsed-sec": String(Math.round(layout.elapsedDriveSec)),
        "total-sec": String(Math.round(layout.totalDriveSec)),
        leg: String(layout.marker.leg),
        tiles: "0",
      },
      {
        position: "absolute",
        left: layout.hud.x - origin.x,
        top: layout.hud.y - origin.y,
        width: layout.hud.width,
        height: layout.hud.height,
        boxSizing: "border-box",
        overflow: "hidden",
        padding: "10px 14px",
        background: HUD_BG,
        color: INK,
        fontSize: 20,
        lineHeight: "24px",
        whiteSpace: "pre",
      },
      {},
      [`${layout.routeLabel}\n${SCHEMATIC_LABEL}\nELAPSED ${layout.elapsedLabel}\nCLAIMED ${layout.totalLabel}`],
    ),
    ...calloutNodes,
  ];
  const layers: MapChild[] = [
    element(
      "div",
      { slot: "content" },
      {
        position: "relative",
        display: "flex",
        flexDirection: "column",
        minWidth: 0,
        minHeight: 0,
        overflow: "hidden",
        width: "100%",
        height: "100%",
      },
      {},
      [
        element(
          "div",
          {
            slot: "board",
            motif: MAP_ROUTE_TRACE_ID,
            "motif-number": String(MAP_MOTIF_NUMBER),
            procedural: "svg",
            tiles: "0",
          },
          {
            position: "absolute",
            left: layout.board.x - layout.content.x,
            top: layout.board.y - layout.content.y,
            width: layout.board.width,
            height: layout.board.height,
            boxSizing: "border-box",
            overflow: "hidden",
            background: BOARD_BG,
            border: `1px solid ${GRID_STROKE}`,
          },
          {},
          boardChildren,
        ),
      ],
    ),
    element(
      "div",
      { exclusion: "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: EXCLUSION_WIDTH,
        height: EXCLUSION_HEIGHT,
        overflow: "hidden",
        pointerEvents: "none",
      },
      {},
    ),
  ];
  if (layout.endScreenMask) {
    layers.push(
      element(
        "div",
        { mask: "end-screen-card" },
        {
          position: "absolute",
          left: layout.endScreenMask.x,
          top: layout.endScreenMask.y,
          width: layout.endScreenMask.width,
          height: layout.endScreenMask.height,
          overflow: "hidden",
          pointerEvents: "none",
        },
        {},
      ),
    );
  }
  return SafeZoneLayout({ isEndScreen: layout.isEndScreen, children: layers });
}

function SafeZoneLayout(props: { readonly isEndScreen: boolean; readonly children: readonly MapChild[] }): MapNode {
  return element(
    "div",
    {
      "safe-zone": "css-contained",
      motif: MAP_ROUTE_TRACE_ID,
      owner: MAP_ROUTE_TRACE_OWNER,
      "motif-number": String(MAP_MOTIF_NUMBER),
      "end-screen": props.isEndScreen ? "true" : "false",
      procedural: "svg",
      tiles: "0",
    },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gridTemplateRows: "minmax(0, 1fr)",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      paddingTop: SAFE_PADDING_TOP,
      paddingBottom: SAFE_PADDING_BOTTOM,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
      background: BLUEPRINT_BG,
    },
    {},
    props.children,
  );
}

function prepare(props: MapRouteTraceProps): Prepared {
  if (props === null || typeof props !== "object") fail("map route props must be an object");
  if (!Number.isInteger(props.frame) || props.frame < 0) fail("frame must be a non-negative integer");
  if (!Array.isArray(props.waypoints) || props.waypoints.length < 2) fail("waypoints must contain at least two stops");
  if (props.waypoints.length > MAX_WAYPOINTS) fail(`waypoints must contain at most ${MAX_WAYPOINTS} stops`);
  const sceneId = props.sceneId === undefined ? "map_route_trace" : readId(props.sceneId, "scene_id");
  const routeLabel = props.routeLabel === undefined ? DEFAULT_ROUTE_LABEL : readRouteLabel(props.routeLabel);
  const isEndScreen = props.isEndScreen === undefined ? false : props.isEndScreen;
  if (typeof isEndScreen !== "boolean") fail("isEndScreen must be a boolean");
  const waypoints = props.waypoints.map((waypoint, index) => readWaypoint(waypoint, index));
  const seen = new Set<string>();
  for (const waypoint of waypoints) {
    if (seen.has(waypoint.waypoint_id)) fail(`duplicate waypoint_id: ${waypoint.waypoint_id}`);
    seen.add(waypoint.waypoint_id);
  }
  const first = waypoints[0];
  if (!first || first.leg_drive_sec !== 0) fail("the first stop has no inbound drive time");
  if (!first || first.arrive_frame !== 0) fail("the first stop arrives at frame 0");
  for (let index = 1; index < waypoints.length; index += 1) {
    const waypoint = waypoints[index];
    const previous = waypoints[index - 1];
    if (!waypoint || !previous) fail("waypoints must contain at least two stops");
    if (waypoint.arrive_frame <= previous.arrive_frame) fail("arrive_frame must increase");
    if (waypoint.leg_drive_sec <= 0) fail(`leg_drive_sec must be positive at ${waypoint.waypoint_id}`);
  }
  return { waypoints, sceneId, routeLabel, isEndScreen, frame: props.frame };
}

function readWaypoint(value: MapWaypoint, index: number): NormalizedWaypoint {
  if (value === null || typeof value !== "object") fail(`waypoints[${index}] must be an object`);
  const waypointId = readId(value.waypoint_id, "waypoint_id");
  const factId = readId(value.fact_id, "fact_id");
  if (typeof value.label !== "string" || value.label.trim().length === 0 || value.label.trim().length > 160) {
    fail(`label must be 1–160 characters at ${waypointId}`);
  }
  if (value.label.includes("\n")) fail(`label must be one line at ${waypointId}`);
  rejectRemote(value.label, "label");
  if (typeof value.timestamp_label !== "string" || value.timestamp_label.trim().length === 0 || value.timestamp_label.trim().length > 16) {
    fail(`timestamp_label must be 1–16 characters at ${waypointId}`);
  }
  if (value.timestamp_label.includes("\n") || countWords(value.timestamp_label) > 3) {
    fail(`timestamp_label must be a short clock label at ${waypointId}`);
  }
  rejectRemote(value.timestamp_label, "timestamp_label");
  if (!Number.isFinite(value.x) || value.x < 0 || value.x > 1 || !Number.isFinite(value.y) || value.y < 0 || value.y > 1) {
    fail(`waypoint coordinates must be inside 0..1 at ${waypointId}`);
  }
  if (!Number.isInteger(value.arrive_frame) || value.arrive_frame < 0) {
    fail(`arrive_frame must be a non-negative integer at ${waypointId}`);
  }
  if (!Number.isInteger(value.leg_drive_sec) || value.leg_drive_sec < 0 || value.leg_drive_sec > MAX_DRIVE_SEC) {
    fail(`leg_drive_sec must be a non-negative integer at ${waypointId}`);
  }
  return {
    waypoint_id: waypointId,
    fact_id: factId,
    label: value.label.trim(),
    timestamp_label: value.timestamp_label.trim(),
    x: value.x,
    y: value.y,
    arrive_frame: value.arrive_frame,
    leg_drive_sec: value.leg_drive_sec,
  };
}

function readRouteLabel(value: string): string {
  if (typeof value !== "string" || value.trim().length === 0 || value.trim().length > 32 || value.includes("\n")) {
    fail("routeLabel must be 1–32 characters");
  }
  rejectRemote(value, "routeLabel");
  return value.trim();
}

function readId(value: unknown, label: string): string {
  if (typeof value !== "string" || !ID_PATTERN.test(value)) fail(`${label} must match ${ID_PATTERN}`);
  return value;
}

function rejectRemote(value: string, label: string): void {
  if (HTTP_PATTERN.test(value) || TILE_HOST_PATTERN.test(value)) fail(`${label} cannot point at a map tile`);
}

function placeChrome(isEndScreen: boolean): { content: Rect; board: Rect; plot: Rect; hud: Rect } {
  const content = contentRect();
  const mask = isEndScreen ? endScreenMaskRect() : null;
  const usableBottom = mask ? mask.y : content.y + content.height;
  const usableHeight = usableBottom - content.y;
  const boardHeight = usableHeight - BOARD_INSET_Y * 2;
  const boardWidth = content.width - BOARD_INSET_X * 2;
  if (boardWidth < 640 || boardHeight < 360) fail("blueprint does not fit the safe zone");
  const board: Rect = {
    x: content.x + BOARD_INSET_X,
    y: content.y + BOARD_INSET_Y,
    width: boardWidth,
    height: boardHeight,
  };
  const hud: Rect = {
    x: board.x + HUD_MARGIN,
    y: board.y + HUD_MARGIN,
    width: HUD_W,
    height: HUD_H,
  };
  const plot: Rect = {
    x: board.x + PLOT_INSET_X,
    y: hud.y + hud.height + PLOT_GAP,
    width: board.width - PLOT_INSET_X * 2,
    height: board.y + board.height - PLOT_INSET_BOTTOM - (hud.y + hud.height + PLOT_GAP),
  };
  if (plot.width < 480 || plot.height < 180) fail("plot does not fit the blueprint");
  if (!rectInside(hud, board) || !rectInside(plot, board)) fail("hud or plot leaves the blueprint");
  return { content, board, plot, hud };
}

function placeWaypoint(plot: Rect, waypoint: NormalizedWaypoint): PlacedWaypoint {
  return {
    waypoint_id: waypoint.waypoint_id,
    fact_id: waypoint.fact_id,
    label: waypoint.label,
    timestamp_label: waypoint.timestamp_label,
    arrive_frame: waypoint.arrive_frame,
    leg_drive_sec: waypoint.leg_drive_sec,
    norm: { x: waypoint.x, y: waypoint.y },
    page: {
      x: Math.round(plot.x + waypoint.x * plot.width),
      y: Math.round(plot.y + waypoint.y * plot.height),
    },
  };
}

function legState(waypoints: readonly NormalizedWaypoint[], frame: number): LegState {
  const last = waypoints.length - 1;
  const finalStop = waypoints[last];
  const firstStop = waypoints[0];
  if (!finalStop || !firstStop) fail("waypoints must contain at least two stops");
  if (frame >= finalStop.arrive_frame) {
    return { fromIndex: last, toIndex: last, t: 1, moving: false, pulsing: true, coincident: false };
  }
  let toIndex = 1;
  while (toIndex < last && frame >= (waypoints[toIndex]?.arrive_frame ?? 0)) toIndex += 1;
  const fromIndex = toIndex - 1;
  const from = waypoints[fromIndex];
  const to = waypoints[toIndex];
  if (!from || !to) fail("arrive_frame must increase");
  const span = to.arrive_frame - from.arrive_frame;
  if (span <= 0) fail("arrive_frame must increase");
  const raw = (frame - from.arrive_frame) / span;
  const coincident = Math.hypot(to.x - from.x, to.y - from.y) < COINCIDENT_NORM;
  const moving = !coincident;
  return {
    fromIndex,
    toIndex,
    t: easeInOutCubic(raw),
    moving,
    pulsing: !moving,
    coincident,
  };
}

function markerAt(waypoints: readonly PlacedWaypoint[], leg: LegState): MapPoint {
  const from = waypoints[leg.fromIndex];
  const to = waypoints[leg.toIndex];
  if (!from || !to) fail("waypoints must contain at least two stops");
  if (leg.coincident || leg.fromIndex === leg.toIndex) return { x: from.page.x, y: from.page.y };
  return {
    x: Math.round(from.page.x + (to.page.x - from.page.x) * leg.t),
    y: Math.round(from.page.y + (to.page.y - from.page.y) * leg.t),
  };
}

function tracePoints(waypoints: readonly PlacedWaypoint[], leg: LegState, marker: MapPoint): MapPoint[] {
  const points: MapPoint[] = [];
  for (let index = 0; index <= leg.fromIndex; index += 1) {
    const waypoint = waypoints[index];
    if (!waypoint) fail("waypoints must contain at least two stops");
    pushUnique(points, waypoint.page);
  }
  if (leg.fromIndex !== leg.toIndex && !leg.coincident) pushUnique(points, marker);
  return points;
}

function elapsedDrive(waypoints: readonly NormalizedWaypoint[], leg: LegState): number {
  let seconds = 0;
  for (let index = 1; index <= leg.fromIndex; index += 1) {
    const waypoint = waypoints[index];
    if (!waypoint) fail("waypoints must contain at least two stops");
    seconds += waypoint.leg_drive_sec;
  }
  if (leg.fromIndex !== leg.toIndex) {
    const destination = waypoints[leg.toIndex];
    if (!destination) fail("waypoints must contain at least two stops");
    seconds += leg.t * destination.leg_drive_sec;
  }
  return seconds;
}

function visibleCallouts(
  waypoints: readonly PlacedWaypoint[],
  frame: number,
  leg: LegState,
): { waypoint: PlacedWaypoint; leg: number }[] {
  const indexes = new Set<number>();
  waypoints.forEach((waypoint, index) => {
    if (frame >= waypoint.arrive_frame) indexes.add(index);
  });
  if (leg.fromIndex !== leg.toIndex) indexes.add(leg.toIndex);
  return [...indexes].sort((left, right) => left - right).map((index) => {
    const waypoint = waypoints[index];
    if (!waypoint) fail("waypoints must contain at least two stops");
    return { waypoint, leg: index };
  });
}

function placeCallouts(
  items: readonly { waypoint: PlacedWaypoint; leg: number }[],
  board: Rect,
  obstacles: readonly Rect[],
): PlacedCallout[] {
  const drafts = items.map((item) => draftCallout(item.waypoint, item.leg, board));
  const placed: PlacedCallout[] = [];
  for (const draft of drafts) {
    let chosen: Rect | null = null;
    for (let guard = 0; guard <= 24; guard += 1) {
      const y = guard === 0 ? draft.preferred.y : draft.preferred.y + shiftAmount(guard);
      const box: Rect = { ...draft.preferred, y };
      if (!rectInside(box, board)) continue;
      if (obstacles.some((obstacle) => rectsOverlap(box, obstacle))) continue;
      if (placed.some((callout) => rectsOverlap(box, callout.box))) continue;
      chosen = box;
      break;
    }
    if (!chosen) fail(`callout does not fit the safe zone: ${draft.waypoint.waypoint_id}`);
    placed.push({
      waypoint_id: draft.waypoint.waypoint_id,
      fact_id: draft.waypoint.fact_id,
      leg: draft.leg,
      text: draft.text,
      words: draft.words,
      truncated: draft.truncated,
      hold_frames: holdFrames(draft.words),
      box: chosen,
      shifted: chosen.y !== draft.preferred.y,
    });
  }
  return placed;
}

function draftCallout(waypoint: PlacedWaypoint, leg: number, board: Rect): CalloutDraft {
  const built = calloutText(waypoint.timestamp_label, waypoint.label);
  const width = Math.min(CALLOUT_MAX_W, CALLOUT_PAD_X * 2 + built.text.length * CALLOUT_CHAR_PX);
  const gap = MARKER_R + CALLOUT_GAP;
  let x = waypoint.page.x + gap;
  if (x + width > board.x + board.width - 12) x = waypoint.page.x - gap - width;
  const minX = board.x + 12;
  const maxX = board.x + board.width - 12 - width;
  if (maxX < minX) fail(`callout does not fit the safe zone: ${waypoint.waypoint_id}`);
  x = Math.min(Math.max(x, minX), maxX);
  const y = waypoint.page.y - Math.floor(CALLOUT_H / 2);
  return {
    waypoint,
    leg,
    text: built.text,
    words: built.words,
    truncated: built.truncated,
    preferred: { x, y, width, height: CALLOUT_H },
  };
}

function calloutText(timestamp: string, label: string): { text: string; words: number; truncated: boolean } {
  const raw = `${timestamp} · ${label}`.trim().replace(/\s+/g, " ");
  const words = raw.split(" ").filter((word) => word.length > 0);
  if (words.length <= MAX_WORDS) return { text: words.join(" "), words: words.length, truncated: false };
  const kept = words.slice(0, MAX_WORDS);
  return { text: kept.join(" "), words: MAX_WORDS, truncated: true };
}

function shiftAmount(guard: number): number {
  const step = Math.ceil(guard / 2) * DECONFLICT_STEP;
  const sign = guard % 2 === 1 ? 1 : -1;
  return sign * step;
}

function assertContained(layout: MapRouteTraceLayout): void {
  if (layout.tileCount !== 0) fail("map tiles are not allowed");
  if (!rectInside(layout.board, layout.content)) fail("blueprint leaves the safe zone");
  if (!rectInside(layout.plot, layout.board) || !rectInside(layout.hud, layout.board)) fail("plot leaves the blueprint");
  if (rectsOverlap(layout.board, layout.captionBar)) fail("blueprint enters the caption bar");
  if (rectsOverlap(layout.board, layout.exclusion)) fail("blueprint enters the exclusion box");
  if (layout.endScreenMask && rectsOverlap(layout.board, layout.endScreenMask)) fail("blueprint enters the end-screen mask");
  if (layout.trace.length === 0) fail("trace is empty");
  const markerBox: Rect = { x: layout.marker.x, y: layout.marker.y, width: 0, height: 0 };
  if (!rectInside(markerBox, layout.plot)) fail("marker leaves the plot");
  for (let left = 0; left < layout.callouts.length; left += 1) {
    for (let right = left + 1; right < layout.callouts.length; right += 1) {
      const a = layout.callouts[left];
      const b = layout.callouts[right];
      if (!a || !b) fail("callout is missing");
      if (rectsOverlap(a.box, b.box)) fail("timestamp callouts overlap");
    }
  }
  for (const callout of layout.callouts) {
    if (!rectInside(callout.box, layout.board)) fail("timestamp callout leaves the safe zone");
    if (callout.words < 1 || callout.words > MAX_WORDS) fail("timestamp callout exceeds 12 words");
    if (callout.hold_frames < holdFrames(callout.words)) fail("timestamp callout hold is short");
    if (rectsOverlap(callout.box, layout.hud)) fail("timestamp callout covers the drive-time HUD");
  }
  const last = layout.trace[layout.trace.length - 1];
  if (!last || last.x !== layout.marker.x || last.y !== layout.marker.y) fail("trace does not meet the marker");
}

function localPoint(plot: Rect, page: MapPoint): MapPoint {
  return { x: page.x - plot.x, y: page.y - plot.y };
}

function pointString(points: readonly MapPoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

function pushUnique(points: MapPoint[], point: MapPoint): void {
  const last = points[points.length - 1];
  if (last && last.x === point.x && last.y === point.y) return;
  points.push(point);
}

function shape(
  type: "polyline" | "line" | "circle",
  dataset: Readonly<Record<string, string>>,
  attrs: Readonly<Record<string, string | number>>,
): MapNode {
  return element(type, dataset, {}, attrs);
}

function element(
  type: MapNode["type"],
  dataset: Readonly<Record<string, string>>,
  style: Readonly<Record<string, CssValue>>,
  attrs: Readonly<Record<string, string | number>>,
  children?: readonly MapChild[],
): MapNode {
  if (!ALLOWED_TYPES.has(type)) fail("only procedural svg geometry is allowed");
  for (const key of Object.keys(attrs)) {
    if (BANNED_ATTR.test(key)) fail("map tiles are not allowed");
  }
  for (const value of [...Object.values(dataset), ...Object.values(attrs)]) {
    if (typeof value === "string" && TILE_HOST_PATTERN.test(value)) fail("map tiles are not allowed");
  }
  if (children !== undefined && children.length > 0) {
    const only = children.length === 1 ? children[0] : children;
    if (only !== undefined) return { type, dataset, props: { style, attrs, children: only } };
  }
  return { type, dataset, props: { style, attrs } };
}

function fail(message: string): never {
  throw new MapRouteTraceError(message);
}
