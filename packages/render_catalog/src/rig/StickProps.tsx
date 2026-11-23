/**
 * Task 105 stick-figure silhouette props.
 *
 * Outlines are authored facing right. Left facing is one SVG
 * `translate(axis) scale(-1 1)` around `torsoAxisX`, so an asymmetric
 * badge or brim is mirrored with the body instead of having its points flipped.
 * `BoilPath` here is the crisp polyline: no SVG filter and no vertex jitter.
 * Task 103 owns the 6 fps jitter and should consume these point lists.
 * Seeds include `Math.floor(frame / 5)` so the 30 fps boil clock is explicit.
 */

export type StickPropErrorCode =
  | "INVALID_INPUT"
  | "INVALID_FACING"
  | "INVALID_FRAME"
  | "INVALID_SEED"
  | "INVALID_COLOR"
  | "INVALID_BONES"
  | "INVALID_SOCKET"
  | "INVALID_SAFE_ZONE"
  | "UNKNOWN_STICK_PROP"
  | "DUPLICATE_STICK_PROP"
  | "SOCKET_OUTSIDE_SAFE_ZONE"
  | "SILHOUETTE_UNREADABLE";

export class StickPropError extends Error {
  readonly code: StickPropErrorCode;

  constructor(code: StickPropErrorCode, message: string) {
    super(message);
    this.name = "StickPropError";
    this.code = code;
  }
}

export const STICK_PROP_LIBRARY = [
  "fedora",
  "hoodie",
  "badge",
  "glasses",
  "tie",
  "scarf",
  "briefcase",
  "flashlight",
  "phone",
  "document",
] as const;

export type StickPropId = (typeof STICK_PROP_LIBRARY)[number];

export const STICK_FACINGS = ["right", "left"] as const;

export type StickFacing = (typeof STICK_FACINGS)[number];

export const STICK_SOCKET_NAMES = [
  "crown",
  "headCenter",
  "brow",
  "neck",
  "chest",
  "shoulder",
  "hand",
  "hip",
  "knee",
  "foot",
] as const;

export type StickSocketName = (typeof STICK_SOCKET_NAMES)[number];

/** Prop id -> the idle socket it anchors to. Hand props share `hand` and are slotted forward. */
export const STICK_PROP_SOCKET = {
  fedora: "crown",
  hoodie: "neck",
  badge: "chest",
  glasses: "brow",
  tie: "neck",
  scarf: "neck",
  briefcase: "hand",
  flashlight: "hand",
  phone: "hand",
  document: "hand",
} as const satisfies Record<StickPropId, StickSocketName>;

export const STICK_PROP_INK = "#1B1B1D";
export const STICK_PROP_PAPER = "#E9E2D2";
export const EVIDENCE_CRIMSON_HEX = "#C92A2A";

/** YouTube exclusion band for a 1920x1080 frame: 108px top (10%), 194px bottom (18%). */
export const FRAME_SAFE_ZONE_1080 = {
  top: 108,
  right: 1920,
  bottom: 886,
  left: 0,
} as const satisfies StickSafeZone;

export interface StickSafeZone {
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly left: number;
}

export interface StickSocket {
  readonly x: number;
  readonly y: number;
}

export interface StickBoneLengths {
  readonly headRadius: number;
  readonly torsoLen: number;
  readonly upperArm: number;
  readonly forearm: number;
  readonly thigh: number;
  readonly shin: number;
}

export interface StickFigureSockets {
  readonly torsoAxisX: number;
  readonly headRadius: number;
  readonly crown: StickSocket;
  readonly headCenter: StickSocket;
  readonly brow: StickSocket;
  readonly neck: StickSocket;
  readonly chest: StickSocket;
  readonly shoulder: StickSocket;
  readonly hand: StickSocket;
  readonly hip: StickSocket;
  readonly knee: StickSocket;
  readonly foot: StickSocket;
}

/** Canonical idle ratios. Uniform scale keeps every bone locked to the head. */
export const DEFAULT_STICK_BONES: StickBoneLengths = {
  headRadius: 36,
  torsoLen: 110,
  upperArm: 64,
  forearm: 56,
  thigh: 78,
  shin: 72,
};

const BONE_KEYS = ["headRadius", "torsoLen", "upperArm", "forearm", "thigh", "shin"] as const;

/** Chin-to-neck gap is 0.15 head radii, so the head center sits 1.15 radii above the neck. */
const NECK_OFFSET_HUNDREDTHS = 115;
const SHOULDER_DROP_HUNDREDTHS = 20;
const BROW_FORWARD_HUNDREDTHS = 72;
const HAND_FORWARD_HUNDREDTHS = 45;
const CHEST_DROP_HUNDREDTHS = 45;
/** Separates held props so flashlight and briefcase silhouettes do not merge. */
const HAND_SLOT_HUNDREDTHS = 210;
const MIN_EXTENT_RADII = 0.45;
const HEAD_RADIUS_TOLERANCE = 0.05;

type Pt = readonly [number, number];
type Unit = readonly [number, number];

interface PartDef {
  readonly name: string;
  readonly role: "outer" | "detail";
  /** Hundredths of a head radius. +X is forward, +Y is down. */
  readonly units: readonly Unit[];
}

/**
 * Local silhouettes. Asymmetric on purpose: fedora brim and badge tab, glasses
 * temple, scarf tails, briefcase clasp, flashlight head, document dog-ear.
 */
const PROP_PARTS = {
  fedora: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [-70, 14],
        [-70, -2],
        [-48, -4],
        [-50, -62],
        [-8, -80],
        [46, -64],
        [52, -4],
        [162, 10],
        [162, 30],
        [-70, 28],
      ],
    },
    {
      name: "band",
      role: "detail",
      units: [
        [-42, -6],
        [44, -6],
        [44, 0],
        [-42, 0],
      ],
    },
  ],
  hoodie: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [-20, 145],
        [-35, 35],
        [-115, -120],
        [-85, -230],
        [10, -248],
        [95, -185],
        [70, -20],
        [40, 150],
      ],
    },
    {
      name: "pocket",
      role: "detail",
      units: [
        [-2, 72],
        [36, 72],
        [36, 88],
        [-2, 88],
      ],
    },
  ],
  badge: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [12, -64],
        [30, -64],
        [30, -48],
        [66, -46],
        [74, -16],
        [58, 32],
        [36, 58],
        [14, 32],
        [6, -16],
        [14, -46],
        [12, -48],
      ],
    },
    {
      name: "stripe",
      role: "detail",
      units: [
        [18, -4],
        [56, -2],
        [52, 12],
        [20, 10],
      ],
    },
  ],
  glasses: [
    {
      name: "lens",
      role: "outer",
      units: [
        [-2, -28],
        [46, -28],
        [52, -8],
        [46, 24],
        [-2, 24],
        [-8, 0],
      ],
    },
    {
      name: "lens-inner",
      role: "detail",
      units: [
        [6, -16],
        [38, -16],
        [38, 12],
        [6, 12],
      ],
    },
    {
      name: "temple",
      role: "outer",
      units: [
        [-2, -6],
        [-105, 2],
        [-105, 16],
        [-2, 10],
      ],
    },
  ],
  tie: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [-22, 0],
        [28, 2],
        [16, 30],
        [34, 110],
        [2, 148],
        [-22, 105],
        [-16, 30],
      ],
    },
  ],
  scarf: [
    {
      name: "band",
      role: "outer",
      units: [
        [-62, -22],
        [48, -28],
        [55, 18],
        [-50, 24],
      ],
    },
    {
      name: "tail-front",
      role: "outer",
      units: [
        [10, 12],
        [36, 18],
        [42, 115],
        [30, 162],
        [12, 148],
        [2, 162],
        [-6, 120],
        [2, 20],
      ],
    },
    {
      name: "tail-back",
      role: "outer",
      units: [
        [-48, 8],
        [-22, 2],
        [-16, 55],
        [-40, 78],
        [-58, 48],
      ],
    },
  ],
  briefcase: [
    {
      name: "case",
      role: "outer",
      units: [
        [-78, 16],
        [70, 16],
        [86, 40],
        [86, 58],
        [70, 58],
        [70, 105],
        [-78, 105],
      ],
    },
    {
      name: "handle",
      role: "outer",
      units: [
        [-26, 16],
        [-26, -30],
        [-14, -46],
        [22, -46],
        [36, -34],
        [36, 16],
        [22, 16],
        [22, -18],
        [-12, -18],
        [-12, 16],
      ],
    },
  ],
  flashlight: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [-55, -14],
        [62, -14],
        [62, -30],
        [115, -30],
        [115, 30],
        [62, 30],
        [62, 14],
        [-55, 14],
      ],
    },
    {
      name: "lens",
      role: "detail",
      units: [
        [92, -16],
        [106, -16],
        [106, 16],
        [92, 16],
      ],
    },
  ],
  phone: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [-40, -58],
        [-32, -70],
        [28, -70],
        [36, -58],
        [36, 62],
        [28, 74],
        [-32, 74],
        [-40, 62],
      ],
    },
    {
      name: "screen",
      role: "detail",
      units: [
        [-22, -46],
        [20, -46],
        [20, 46],
        [-22, 46],
      ],
    },
    {
      name: "camera",
      role: "detail",
      units: [
        [6, -60],
        [18, -60],
        [18, -50],
        [6, -50],
      ],
    },
  ],
  document: [
    {
      name: "silhouette",
      role: "outer",
      units: [
        [-55, -70],
        [22, -70],
        [48, -44],
        [48, 70],
        [-55, 70],
      ],
    },
    {
      name: "crease",
      role: "detail",
      units: [
        [12, -58],
        [24, -46],
        [18, -40],
        [8, -52],
      ],
    },
    {
      name: "line-1",
      role: "detail",
      units: [
        [-38, -22],
        [20, -22],
        [20, -10],
        [-38, -10],
      ],
    },
    {
      name: "line-2",
      role: "detail",
      units: [
        [-38, 6],
        [16, 6],
        [16, 18],
        [-38, 18],
      ],
    },
    {
      name: "line-3",
      role: "detail",
      units: [
        [-38, 32],
        [24, 32],
        [24, 44],
        [-38, 44],
      ],
    },
  ],
} as const satisfies Record<StickPropId, readonly PartDef[]>;

export interface SvgElement {
  readonly tag: "g" | "path";
  readonly attrs: Readonly<Record<string, string>>;
  readonly children: readonly SvgElement[];
}

export interface BoilPathInput {
  readonly points: readonly Pt[];
  readonly seed: string;
  readonly closed?: boolean;
  readonly fill: string;
  readonly stroke?: string;
  readonly strokeWidth?: number;
}

export interface StickPropsInput {
  readonly props: readonly StickPropId[];
  readonly sockets: StickFigureSockets;
  readonly facing?: StickFacing;
  readonly seed?: string | number;
  readonly frame?: number;
  readonly ink?: string;
  readonly paper?: string;
  readonly safeZone?: StickSafeZone;
}

export function isStickPropId(value: string): value is StickPropId {
  return (STICK_PROP_LIBRARY as readonly string[]).includes(value);
}

/** 6 fps boil clock at 30 fps. */
export function boilTick(frame: number): number {
  if (!Number.isFinite(frame) || frame < 0) {
    throw new StickPropError("INVALID_FRAME", "frame must be a finite number >= 0");
  }
  return Math.floor(frame / 5);
}

export function stickFigureSockets(bones: StickBoneLengths, origin: StickSocket = { x: 0, y: 0 }): StickFigureSockets {
  for (const key of BONE_KEYS) {
    const value = bones[key];
    if (!Number.isFinite(value) || value <= 0) {
      throw new StickPropError("INVALID_BONES", `${key} must be a finite number > 0`);
    }
  }
  if (!Number.isFinite(origin.x) || !Number.isFinite(origin.y)) {
    throw new StickPropError("INVALID_SOCKET", "socket origin must be finite");
  }
  const radius = bones.headRadius;
  const hip = { x: round2(origin.x), y: round2(origin.y) };
  const neck = { x: hip.x, y: round2(hip.y - bones.torsoLen) };
  const headCenter = { x: hip.x, y: addY(neck.y, radius, -NECK_OFFSET_HUNDREDTHS) };
  const crown = { x: hip.x, y: addY(headCenter.y, radius, -100) };
  const sockets: StickFigureSockets = {
    torsoAxisX: hip.x,
    headRadius: radius,
    crown,
    headCenter,
    brow: { x: addX(headCenter.x, radius, BROW_FORWARD_HUNDREDTHS), y: headCenter.y },
    neck,
    chest: { x: hip.x, y: round2(hip.y - (bones.torsoLen * CHEST_DROP_HUNDREDTHS) / 100) },
    shoulder: { x: hip.x, y: addY(neck.y, radius, SHOULDER_DROP_HUNDREDTHS) },
    hand: {
      x: addX(hip.x, radius, HAND_FORWARD_HUNDREDTHS),
      y: round2(addY(neck.y, radius, SHOULDER_DROP_HUNDREDTHS) + bones.upperArm + bones.forearm),
    },
    hip,
    knee: { x: hip.x, y: round2(hip.y + bones.thigh) },
    foot: { x: hip.x, y: round2(hip.y + bones.thigh + bones.shin) },
  };
  assertHeadRadius(sockets);
  return sockets;
}

export function translateStickSockets(sockets: StickFigureSockets, dx: number, dy: number): StickFigureSockets {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) {
    throw new StickPropError("INVALID_SOCKET", "translation must be finite");
  }
  const move = (point: StickSocket): StickSocket => ({ x: round2(point.x + dx), y: round2(point.y + dy) });
  return {
    torsoAxisX: round2(sockets.torsoAxisX + dx),
    headRadius: sockets.headRadius,
    crown: move(sockets.crown),
    headCenter: move(sockets.headCenter),
    brow: move(sockets.brow),
    neck: move(sockets.neck),
    chest: move(sockets.chest),
    shoulder: move(sockets.shoulder),
    hand: move(sockets.hand),
    hip: move(sockets.hip),
    knee: move(sockets.knee),
    foot: move(sockets.foot),
  };
}

export function BoilPath(input: BoilPathInput): SvgElement {
  const closed = input.closed ?? false;
  const seed = assertSeed(input.seed);
  const fill = assertColor(input.fill, "fill");
  const stroke = input.stroke === undefined || input.stroke === "none" ? "none" : assertColor(input.stroke, "stroke");
  if (stroke !== "none" && (input.strokeWidth === undefined || !Number.isFinite(input.strokeWidth) || input.strokeWidth < 2)) {
    throw new StickPropError("SILHOUETTE_UNREADABLE", "a stroked BoilPath needs strokeWidth >= 2");
  }
  const points = finalizePoints(input.points, closed);
  if (points.length < (closed ? 4 : 2)) {
    throw new StickPropError("SILHOUETTE_UNREADABLE", "BoilPath needs a longer point list");
  }
  const attrs: Record<string, string> = {
    "data-component": "BoilPath",
    "data-seed": seed,
    "data-closed": closed ? "true" : "false",
    d: pathD(points, closed),
    fill,
    stroke,
  };
  if (input.strokeWidth !== undefined) attrs["stroke-width"] = fmt(input.strokeWidth);
  return { tag: "path", attrs, children: [] };
}

export function serializeSvg(element: SvgElement): string {
  return serializeSvgAt(element, "");
}

function serializeSvgAt(element: SvgElement, indent: string): string {
  const attrs = Object.entries(element.attrs)
    .map(([key, value]) => `${key}="${escapeAttr(value)}"`)
    .join(" ");
  const open = attrs.length > 0 ? `<${element.tag} ${attrs}` : `<${element.tag}`;
  if (element.children.length === 0) return `${indent}${open}/>`;
  const inner = element.children.map((child) => serializeSvgAt(child, `${indent}  `)).join("\n");
  return `${indent}${open}>\n${inner}\n${indent}</${element.tag}>`;
}

export function StickProps(input: StickPropsInput): SvgElement {
  if (input === null || typeof input !== "object") {
    throw new StickPropError("INVALID_INPUT", "StickProps input must be an object");
  }
  if (!Array.isArray(input.props)) {
    throw new StickPropError("INVALID_INPUT", "props must be an array of stick prop ids");
  }
  const facing = assertFacing(input.facing);
  const frame = input.frame ?? 0;
  const tick = boilTick(frame);
  const seed = assertSeed(input.seed === undefined ? "stick-props" : input.seed);
  const ink = assertColor(input.ink ?? STICK_PROP_INK, "ink");
  const paper = assertColor(input.paper ?? STICK_PROP_PAPER, "paper");
  const sockets = assertSockets(input.sockets);
  const safeZone = input.safeZone === undefined ? null : assertSafeZone(input.safeZone);
  const seen = new Set<string>();
  let handSlot = 0;
  const props: SvgElement[] = [];
  for (const id of input.props) {
    if (!isStickPropId(id)) {
      throw new StickPropError(
        "UNKNOWN_STICK_PROP",
        `Unknown stick prop "${String(id)}". Expected one of: ${STICK_PROP_LIBRARY.join(", ")}`,
      );
    }
    if (seen.has(id)) {
      throw new StickPropError("DUPLICATE_STICK_PROP", `Duplicate stick prop "${id}" collapses the silhouette`);
    }
    seen.add(id);
    const socketName = STICK_PROP_SOCKET[id];
    const slot = socketName === "hand" ? handSlot : 0;
    if (socketName === "hand") handSlot += 1;
    props.push(renderProp(id, sockets, slot, seed, tick, ink, paper, safeZone));
  }
  const axis = sockets.torsoAxisX;
  const sign = facing === "left" ? "-1" : "1";
  return {
    tag: "g",
    attrs: {
      "data-component": "StickProps",
      "data-contract": "stick-prop-library-v1",
      "data-facing": facing,
      "data-torso-axis": fmt(axis),
      "data-boil-tick": String(tick),
    },
    children: [
      {
        tag: "g",
        attrs: {
          "data-component": "FacingMirror",
          transform: `translate(${fmt(axis)} 0) scale(${sign} 1) translate(${fmt(-axis)} 0)`,
        },
        children: props,
      },
    ],
  };
}

export function renderStickPropsSvg(input: StickPropsInput): string {
  return serializeSvg(StickProps(input));
}

function renderProp(
  id: StickPropId,
  sockets: StickFigureSockets,
  slot: number,
  seed: string,
  tick: number,
  ink: string,
  paper: string,
  safeZone: StickSafeZone | null,
): SvgElement {
  const socketName = STICK_PROP_SOCKET[id];
  const socket = sockets[socketName];
  const radius = sockets.headRadius;
  const anchor: Pt = [round2(socket.x + (slot * HAND_SLOT_HUNDREDTHS * radius) / 100), socket.y];
  const placed = PROP_PARTS[id].map((part) => ({
    name: part.name,
    role: part.role,
    points: place(socket, radius, slot, part.units),
  }));
  assertReadable(id, radius, placed);
  const fitted = safeZone === null ? placed.map((part) => ({ ...part, points: part.points.map(roundPt) })) : fitProp(id, anchor, sockets.torsoAxisX, placed, safeZone, radius);
  assertRoundedReadable(id, radius, fitted, safeZone);
  return {
    tag: "g",
    attrs: {
      "data-prop": id,
      "data-socket": socketName,
      "data-slot": String(slot),
      "data-anchor-x": fmt(anchor[0]),
      "data-anchor-y": fmt(anchor[1]),
    },
    children: fitted.map((part) =>
      BoilPath({
        points: part.points,
        seed: `${seed}:${tick}:${id}:${part.name}`,
        closed: true,
        fill: part.role === "outer" ? ink : paper,
      }),
    ),
  };
}

interface PlacedPart {
  readonly name: string;
  readonly role: "outer" | "detail";
  readonly points: readonly Pt[];
}

function fitProp(
  id: StickPropId,
  anchor: Pt,
  axis: number,
  parts: readonly PlacedPart[],
  safeZone: StickSafeZone,
  radius: number,
): PlacedPart[] {
  const points = parts.flatMap((part) => part.points);
  const mirroredAnchor = mirrorPoint(anchor, axis);
  if (outside(anchor, safeZone)) {
    throw new StickPropError("SOCKET_OUTSIDE_SAFE_ZONE", `${id} socket is outside the safe zone`);
  }
  if (outside(mirroredAnchor, safeZone)) {
    throw new StickPropError("SOCKET_OUTSIDE_SAFE_ZONE", `${id} mirrored socket is outside the safe zone`);
  }
  const factor = Math.min(
    containFactor(points, anchor, safeZone),
    containFactor(points.map((point) => mirrorPoint(point, axis)), mirroredAnchor, safeZone),
  );
  if (!(factor > 0)) {
    throw new StickPropError("SOCKET_OUTSIDE_SAFE_ZONE", `${id} socket is outside the safe zone`);
  }
  let current = factor;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const scaled = parts.map((part) => ({
      ...part,
      points: part.points.map((point) => roundPt(scaleAbout(anchor, point, current))),
    }));
    const flat = scaled.flatMap((part) => part.points);
    if (flat.every((point) => inside(point, safeZone)) && flat.every((point) => inside(mirrorPoint(point, axis), safeZone))) {
      assertRoundedReadable(id, radius, scaled, safeZone);
      return scaled;
    }
    current *= 0.997;
  }
  throw new StickPropError("SILHOUETTE_UNREADABLE", `${id} does not fit the safe zone without losing its silhouette`);
}

function assertReadable(id: StickPropId, radius: number, parts: readonly PlacedPart[]): void {
  const outers = parts.filter((part) => part.role === "outer");
  if (outers.length === 0) {
    throw new StickPropError("SILHOUETTE_UNREADABLE", `${id} has no outer silhouette`);
  }
  let area = 0;
  for (const outer of outers) {
    const outerArea = polygonArea(outer.points);
    if (!(outerArea > 0)) {
      throw new StickPropError("SILHOUETTE_UNREADABLE", `${id} ${outer.name} does not enclose area`);
    }
    area += outerArea;
  }
  if (area < 0.08 * radius * radius) {
    throw new StickPropError("SILHOUETTE_UNREADABLE", `${id} silhouette area is below the readability floor`);
  }
  assertExtent(id, radius, outers.flatMap((part) => part.points));
  for (const detail of parts) {
    if (detail.role !== "detail") continue;
    for (const point of detail.points) {
      if (!outers.some((outer) => pointInPolygon(point, outer.points))) {
        throw new StickPropError("SILHOUETTE_UNREADABLE", `${id} detail ${detail.name} leaves the ${id} silhouette`);
      }
    }
  }
}

function assertRoundedReadable(
  id: StickPropId,
  radius: number,
  parts: readonly PlacedPart[],
  safeZone: StickSafeZone | null,
): void {
  const points = parts.filter((part) => part.role === "outer").flatMap((part) => part.points);
  assertExtent(id, radius, points);
  if (safeZone === null) return;
  for (const point of parts.flatMap((part) => part.points)) {
    if (!inside(point, safeZone)) {
      throw new StickPropError("SILHOUETTE_UNREADABLE", `${id} draws outside the safe zone`);
    }
  }
}

function assertExtent(id: StickPropId, radius: number, points: readonly Pt[]): void {
  const box = bounds(points);
  const width = box.maxX - box.minX;
  const height = box.maxY - box.minY;
  const floor = MIN_EXTENT_RADII * radius - 0.05;
  if (width < floor || height < floor) {
    throw new StickPropError(
      "SILHOUETTE_UNREADABLE",
      `${id} silhouette is ${width.toFixed(2)} by ${height.toFixed(2)} px, below the ${floor.toFixed(2)} px readability floor`,
    );
  }
}

function place(anchor: StickSocket, radius: number, slot: number, units: readonly Unit[]): Pt[] {
  const shift = slot * HAND_SLOT_HUNDREDTHS;
  return units.map(([ux, uy]) => [anchor.x + ((ux + shift) * radius) / 100, anchor.y + (uy * radius) / 100] as const);
}

function assertSockets(sockets: StickFigureSockets): StickFigureSockets {
  if (sockets === null || typeof sockets !== "object") {
    throw new StickPropError("INVALID_SOCKET", "sockets must be a stick-figure socket set");
  }
  if (!Number.isFinite(sockets.torsoAxisX) || !Number.isFinite(sockets.headRadius) || sockets.headRadius <= 0) {
    throw new StickPropError("INVALID_SOCKET", "torsoAxisX and headRadius must be finite and headRadius > 0");
  }
  for (const name of STICK_SOCKET_NAMES) {
    const point = sockets[name];
    if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
      throw new StickPropError("INVALID_SOCKET", `${name} socket must be a finite point`);
    }
  }
  assertHeadRadius(sockets);
  return sockets;
}

function assertHeadRadius(sockets: StickFigureSockets): void {
  const distance = Math.hypot(sockets.crown.x - sockets.headCenter.x, sockets.crown.y - sockets.headCenter.y);
  if (Math.abs(distance - sockets.headRadius) > HEAD_RADIUS_TOLERANCE) {
    throw new StickPropError("INVALID_SOCKET", "headRadius must match the crown-to-head-center distance");
  }
}

function assertSafeZone(zone: StickSafeZone): StickSafeZone {
  const values = [zone.top, zone.right, zone.bottom, zone.left];
  if (values.some((value) => !Number.isFinite(value)) || !(zone.top < zone.bottom) || !(zone.left < zone.right)) {
    throw new StickPropError("INVALID_SAFE_ZONE", "safe zone edges must be finite with top < bottom and left < right");
  }
  return zone;
}

function assertFacing(value: StickFacing | undefined): StickFacing {
  const facing = value ?? "right";
  if (!(STICK_FACINGS as readonly string[]).includes(facing)) {
    throw new StickPropError("INVALID_FACING", "facing must be left or right");
  }
  return facing;
}

function assertSeed(value: string | number): string {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.length > 0 && value.length <= 200 && !/[\u0000-\u001F]/.test(value)) return value;
  throw new StickPropError("INVALID_SEED", "seed must be a finite number or a single-line string of 1-200 characters");
}

function assertColor(value: string, label: string): string {
  if (!/^#[0-9A-Fa-f]{6}$/.test(value)) {
    throw new StickPropError("INVALID_COLOR", `${label} must be a #RRGGBB hex color`);
  }
  const hex = value.toUpperCase();
  if (hex === EVIDENCE_CRIMSON_HEX) {
    throw new StickPropError("SILHOUETTE_UNREADABLE", `${label} must not be evidence crimson`);
  }
  return hex;
}

function addX(x: number, radius: number, hundredths: number): number {
  return round2(x + (radius * hundredths) / 100);
}

function addY(y: number, radius: number, hundredths: number): number {
  return round2(y + (radius * hundredths) / 100);
}

function round2(value: number): number {
  const rounded = Math.round((value + Number.EPSILON) * 100) / 100;
  return Object.is(rounded, -0) ? 0 : rounded;
}

function roundPt(point: Pt): Pt {
  return [round2(point[0]), round2(point[1])];
}

function fmt(value: number): string {
  return String(round2(value));
}

function finalizePoints(points: readonly Pt[], closed: boolean): Pt[] {
  if (points.length === 0 || points.some((point) => !Number.isFinite(point[0]) || !Number.isFinite(point[1]))) {
    throw new StickPropError("SILHOUETTE_UNREADABLE", "BoilPath points must be finite");
  }
  const rounded = points.map(roundPt);
  if (!closed) return rounded;
  const first = rounded[0];
  if (!first) throw new StickPropError("SILHOUETTE_UNREADABLE", "BoilPath points must be finite");
  const last = rounded[rounded.length - 1];
  if (!last || last[0] !== first[0] || last[1] !== first[1]) return [...rounded, [first[0], first[1]]];
  return rounded;
}

function pathD(points: readonly Pt[], closed: boolean): string {
  const first = points[0];
  if (!first) throw new StickPropError("SILHOUETTE_UNREADABLE", "BoilPath points must be finite");
  let d = `M ${fmt(first[0])} ${fmt(first[1])}`;
  for (let index = 1; index < points.length; index += 1) {
    const point = points[index];
    if (!point) continue;
    d += ` L ${fmt(point[0])} ${fmt(point[1])}`;
  }
  return closed ? `${d} Z` : d;
}

function mirrorPoint(point: Pt, axis: number): Pt {
  return [2 * axis - point[0], point[1]];
}

function scaleAbout(anchor: Pt, point: Pt, factor: number): Pt {
  return [anchor[0] + (point[0] - anchor[0]) * factor, anchor[1] + (point[1] - anchor[1]) * factor];
}

function containFactor(points: readonly Pt[], anchor: Pt, safe: StickSafeZone): number {
  let factor = 1;
  for (const point of points) {
    factor = Math.min(factor, axisLimit(anchor[0], point[0], safe.left, safe.right), axisLimit(anchor[1], point[1], safe.top, safe.bottom));
  }
  return factor;
}

function axisLimit(anchor: number, point: number, min: number, max: number): number {
  if (anchor < min || anchor > max) return 0;
  const delta = point - anchor;
  if (Math.abs(delta) < 1e-8) return 1;
  const limit = delta > 0 ? (max - anchor) / delta : (min - anchor) / delta;
  if (limit >= 1) return 1;
  return limit > 0 ? limit : 0;
}

function outside(point: Pt, safe: StickSafeZone): boolean {
  return point[0] < safe.left || point[0] > safe.right || point[1] < safe.top || point[1] > safe.bottom;
}

function inside(point: Pt, safe: StickSafeZone): boolean {
  return point[0] >= safe.left - 1e-6 && point[0] <= safe.right + 1e-6 && point[1] >= safe.top - 1e-6 && point[1] <= safe.bottom + 1e-6;
}

function bounds(points: readonly Pt[]): { minX: number; minY: number; maxX: number; maxY: number } {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const [x, y] of points) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return { minX, minY, maxX, maxY };
}

function polygonArea(points: readonly Pt[]): number {
  let sum = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    if (!current || !next) continue;
    sum += current[0] * next[1] - next[0] * current[1];
  }
  return Math.abs(sum) / 2;
}

function pointInPolygon(point: Pt, polygon: readonly Pt[]): boolean {
  const [x, y] = point;
  let insidePoly = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const current = polygon[index];
    const prior = polygon[previous];
    if (!current || !prior) continue;
    const intersects = current[1] > y !== prior[1] > y && x < ((prior[0] - current[0]) * (y - current[1])) / (prior[1] - current[1]) + current[0];
    if (intersects) insidePoly = !insidePoly;
  }
  return insidePoly;
}

function escapeAttr(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

// Import-time lock: a detail that leaves its silhouette fails before any caller renders.
StickProps({ props: STICK_PROP_LIBRARY, sockets: stickFigureSockets(DEFAULT_STICK_BONES) });
