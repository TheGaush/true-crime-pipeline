/**
 * Layer 4 sandboxed CustomDiagramScene.
 *
 * Declarative JSON shapes, arrows, and labels render inside SafeZoneLayout.
 * Strokes go through BoilPath (6 fps JS vertex jitter, crisp path nodes).
 * Labels are SVG text nodes. The markup serializer escapes them.
 * Primitive types and object keys are allowlisted. This module does not
 * evaluate strings, write HTML, or emit SVG turbulence filters.
 *
 * Task 101's safe_zone.tsx and Task 103's LineBoilPath.tsx are not on this
 * branch. Their files are not copied here. SafeZoneLayout and BoilPath below
 * follow those call shapes so a later wave can swap in the shared modules.
 * Diagram coordinates live in the safe content box (1920×778), inset by 2px
 * so +/- 1.4px boil jitter stays inside that box.
 */

export const MOTIF_COMPONENT = "CustomDiagramScene";
export const LAYER = 4;
export const MAX_PRIMITIVES = 25;
export const FRAME_WIDTH = 1920;
export const FRAME_HEIGHT = 1080;
export const FPS = 30;
export const BOIL_FPS = 6;
export const BOIL_FRAME_STRIDE = FPS / BOIL_FPS;
export const JITTER_AMPLITUDE_PX = 1.4;
export const SAFE_PADDING_TOP_PX = 108;
export const SAFE_PADDING_BOTTOM_PX = 194;
export const CONTENT_WIDTH = FRAME_WIDTH;
export const CONTENT_HEIGHT = FRAME_HEIGHT - SAFE_PADDING_TOP_PX - SAFE_PADDING_BOTTOM_PX;
export const CONTENT_INSET_PX = 2;
export const EXCLUSION_WIDTH = "22%";
export const EXCLUSION_HEIGHT = "14%";
export const LABEL_MAX_WORDS = 12;
export const LABEL_MAX_CHARS = 180;
export const LABEL_CHAR_PX = 14;
export const LABEL_HEIGHT = 32;
export const MAX_POINTS = 24;

const INK = "#1B1B1D";
const PAPER = "#E9E2D2";
const ARROW_HEAD = 16;
const ARROW_HALF = 8.8;
const JSON_MAX_CHARS = 100_000;
const JSON_MAX_DEPTH = 8;
const JSON_MAX_KEYS = 16;
const JSON_MAX_ARRAY = 64;
const MAX_FRAME = 216_000;
const REACT_ELEMENT = Symbol.for("react.element");
const SEED_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/;
const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/;
const STYLE_VALUE = /^[#%(),.0-9A-Za-z -]+$/;
const HEX_OR_NONE = /^(none|#[0-9A-Fa-f]{6})$/;

const SPEC_KEYS = new Set(["seed", "frame", "isEndScreen", "primitives"]);
const POINT_KEYS = new Set(["x", "y"]);
const PRIMITIVE_KEYS: Readonly<Record<string, readonly string[]>> = {
  rect: ["type", "x", "y", "width", "height"],
  ellipse: ["type", "cx", "cy", "rx", "ry"],
  line: ["type", "x1", "y1", "x2", "y2"],
  polyline: ["type", "points"],
  polygon: ["type", "points"],
  arrow: ["type", "from", "to"],
  label: ["type", "x", "y", "text"],
};

const HOST_TAGS = new Set(["div", "svg", "path", "text"]);

export class CustomDiagramError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CustomDiagramError";
  }
}

export type DiagramPoint = {
  readonly x: number;
  readonly y: number;
};

export type DiagramRect = {
  readonly type: "rect";
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
};

export type DiagramEllipse = {
  readonly type: "ellipse";
  readonly cx: number;
  readonly cy: number;
  readonly rx: number;
  readonly ry: number;
};

export type DiagramLine = {
  readonly type: "line";
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
};

export type DiagramPolyline = {
  readonly type: "polyline";
  readonly points: readonly DiagramPoint[];
};

export type DiagramPolygon = {
  readonly type: "polygon";
  readonly points: readonly DiagramPoint[];
};

export type DiagramArrow = {
  readonly type: "arrow";
  readonly from: DiagramPoint;
  readonly to: DiagramPoint;
};

export type DiagramLabel = {
  readonly type: "label";
  readonly x: number;
  readonly y: number;
  readonly text: string;
};

export type DiagramPrimitive =
  | DiagramRect
  | DiagramEllipse
  | DiagramLine
  | DiagramPolyline
  | DiagramPolygon
  | DiagramArrow
  | DiagramLabel;

export type CustomDiagramSpec = {
  readonly seed: string;
  readonly frame: number;
  readonly isEndScreen: boolean;
  readonly primitives: readonly DiagramPrimitive[];
};

export type DiagramChild = DiagramElement | string;

export type DiagramElement = {
  readonly $$typeof: symbol;
  readonly type: "div" | "svg" | "path" | "text";
  readonly key: string | null;
  readonly ref: null;
  readonly props: Readonly<Record<string, unknown>>;
};

export type BoilPathProps = {
  readonly points: readonly DiagramPoint[];
  readonly seed: string;
  readonly frame: number;
  readonly closed?: boolean;
  readonly stroke?: string;
  readonly strokeWidth?: number;
  readonly fill?: string;
};

export type BoilGeometry = {
  readonly tick: number;
  readonly vertices: readonly DiagramPoint[];
  readonly d: string;
};

export type StrokeRole = "outline" | "shaft" | "head" | "underline";

export type DiagramStroke = {
  readonly index: number;
  readonly type: DiagramPrimitive["type"];
  readonly role: StrokeRole;
  readonly seed: string;
  readonly points: readonly DiagramPoint[];
  readonly closed: boolean;
  readonly d: string;
};

export type CustomDiagramSceneNode = DiagramElement & {
  readonly primitiveCount: number;
  readonly tick: number;
  readonly strokes: readonly DiagramStroke[];
  readonly texts: readonly string[];
};

export type SafeZoneLayoutProps = {
  readonly isEndScreen: boolean;
  readonly children: readonly DiagramChild[];
};

type JsonRecord = { [key: string]: unknown };

export function boilTick(frame: number): number {
  if (!Number.isFinite(frame)) throw new CustomDiagramError("BoilPath frame must be a finite number");
  return Math.floor(frame / BOIL_FRAME_STRIDE);
}

function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let mixed = state;
    mixed = Math.imul(mixed ^ (mixed >>> 15), mixed | 1);
    mixed ^= mixed + Math.imul(mixed ^ (mixed >>> 7), mixed | 61);
    return ((mixed ^ (mixed >>> 14)) >>> 0) / 4294967296;
  };
}

function boilRngSeed(seed: string, tick: number): number {
  const text = `string:${seed}#${tick}`;
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function fmt(value: number): string {
  const negative = value < 0;
  const scaled = Math.round(Math.abs(value) * 10000);
  const whole = Math.trunc(scaled / 10000);
  const frac = scaled % 10000;
  const body = frac === 0 ? String(whole) : `${whole}.${String(frac).padStart(4, "0").replace(/0+$/, "")}`;
  return negative && scaled !== 0 ? `-${body}` : body;
}

function unitNormal(tx: number, ty: number): DiagramPoint {
  const length = Math.hypot(tx, ty);
  if (length < 1e-9) return { x: 0, y: -1 };
  return { x: -ty / length, y: tx / length };
}

function vertexNormal(points: readonly DiagramPoint[], index: number, closed: boolean): DiagramPoint {
  const count = points.length;
  const current = points[index];
  if (!current) return { x: 0, y: -1 };
  let tx: number;
  let ty: number;
  if (!closed && index === 0) {
    const next = points[1] ?? current;
    tx = next.x - current.x;
    ty = next.y - current.y;
  } else if (!closed && index === count - 1) {
    const previous = points[index - 1] ?? current;
    tx = current.x - previous.x;
    ty = current.y - previous.y;
  } else {
    const previous = points[(index - 1 + count) % count] ?? current;
    const next = points[(index + 1) % count] ?? current;
    tx = next.x - previous.x;
    ty = next.y - previous.y;
  }
  return unitNormal(tx, ty);
}

function pathData(vertices: readonly DiagramPoint[], closed: boolean): string {
  const first = vertices[0];
  if (!first) return "";
  const commands = [`M ${fmt(first.x)} ${fmt(first.y)}`];
  const lastDrawn = closed ? vertices.length - 1 : vertices.length;
  for (let index = 1; index < lastDrawn; index += 1) {
    const vertex = vertices[index];
    if (!vertex) continue;
    commands.push(`L ${fmt(vertex.x)} ${fmt(vertex.y)}`);
  }
  if (closed) commands.push("Z");
  return commands.join(" ");
}

export function buildBoilGeometry(props: BoilPathProps): BoilGeometry {
  if (!Array.isArray(props.points) || props.points.length < 2) {
    throw new CustomDiagramError("BoilPath needs at least two points");
  }
  if (typeof props.seed !== "string" || props.seed.length === 0 || props.seed.length > 160) {
    throw new CustomDiagramError("BoilPath seed must be a string");
  }
  const tick = boilTick(props.frame);
  const closed = props.closed === true;
  const count = props.points.length;
  const rng = mulberry32(boilRngSeed(props.seed, tick));
  const scalars: number[] = [];
  for (let index = 0; index < count; index += 1) {
    const point = props.points[index];
    if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
      throw new CustomDiagramError("BoilPath points must be finite");
    }
    if (closed && index === count - 1) scalars.push(scalars[0] ?? 0);
    else scalars.push((rng() * 2 - 1) * JITTER_AMPLITUDE_PX);
  }
  const normals = props.points.map((_, index) => vertexNormal(props.points, index, closed));
  const seamNormal = normals[0] ?? { x: 0, y: -1 };
  const seamScalar = scalars[0] ?? 0;
  const seam = { x: seamNormal.x * seamScalar, y: seamNormal.y * seamScalar };
  const vertices: DiagramPoint[] = props.points.map((point, index) => {
    const sharesSeam = closed && (index === 0 || index === count - 1);
    const normal = normals[index] ?? seamNormal;
    const scalar = scalars[index] ?? 0;
    const delta = sharesSeam ? seam : { x: normal.x * scalar, y: normal.y * scalar };
    return { x: point.x + delta.x, y: point.y + delta.y };
  });
  if (closed) {
    const start = vertices[0];
    if (start) vertices.push({ x: start.x, y: start.y });
  }
  return { tick, vertices, d: pathData(vertices, closed) };
}

function paintOf(props: BoilPathProps): { fill: string; stroke: string; strokeWidth: number } {
  const fill = props.fill ?? "none";
  const stroke = props.stroke ?? INK;
  const strokeWidth = props.strokeWidth ?? 3;
  if (!HEX_OR_NONE.test(fill) || !HEX_OR_NONE.test(stroke)) {
    throw new CustomDiagramError("BoilPath paint must be none or a hex color");
  }
  if (!Number.isFinite(strokeWidth) || strokeWidth < 0 || strokeWidth > 8) {
    throw new CustomDiagramError("BoilPath strokeWidth must be from 0 to 8");
  }
  return { fill, stroke, strokeWidth };
}

/** Crisp `<path>` for one 6 fps tick. No child nodes and no filter attribute. */
export function BoilPath(props: BoilPathProps): DiagramElement {
  const geometry = buildBoilGeometry(props);
  const paint = paintOf(props);
  return element("path", null, {
    d: geometry.d,
    fill: paint.fill,
    stroke: paint.stroke,
    strokeWidth: paint.strokeWidth,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "data-boil-tick": geometry.tick,
    "data-boil-fps": BOIL_FPS,
    "data-container-fps": FPS,
  });
}

function element(
  type: DiagramElement["type"],
  key: string | null,
  props: Readonly<Record<string, string | number>>,
  style?: Readonly<Record<string, string | number>>,
  children?: readonly DiagramChild[],
): DiagramElement {
  const next: Record<string, unknown> = { ...props };
  if (style) next.style = style;
  if (children && children.length === 1) {
    const only = children[0];
    if (only !== undefined) next.children = only;
  } else if (children && children.length > 1) {
    next.children = children;
  }
  return {
    $$typeof: REACT_ELEMENT,
    type,
    key,
    ref: null,
    props: next,
  };
}

/**
 * CSS containment frame. Content sits in the padded grid cell, above the
 * caption bar and clear of the bottom-right exclusion box.
 */
export function SafeZoneLayout(props: SafeZoneLayoutProps): DiagramElement {
  const layers: DiagramChild[] = [...props.children];
  layers.push(
    element(
      "div",
      "exclusion",
      { "data-exclusion": "bottom-right" },
      {
        position: "absolute",
        right: 0,
        bottom: 0,
        width: EXCLUSION_WIDTH,
        height: EXCLUSION_HEIGHT,
        overflow: "hidden",
        pointerEvents: "none",
      },
    ),
  );
  if (props.isEndScreen) {
    layers.push(
      element(
        "div",
        "end-screen",
        { "data-mask": "end-screen-card" },
        {
          position: "absolute",
          left: 0,
          right: EXCLUSION_WIDTH,
          bottom: SAFE_PADDING_BOTTOM_PX,
          overflow: "hidden",
          pointerEvents: "none",
        },
      ),
    );
  }
  return element(
    "div",
    "safe-zone",
    {
      "data-safe-zone": "css-contained",
      "data-end-screen": props.isEndScreen ? "true" : "false",
    },
    {
      boxSizing: "border-box",
      position: "relative",
      display: "grid",
      gridTemplateColumns: "minmax(0, 1fr)",
      gridTemplateRows: "minmax(0, 1fr)",
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      paddingTop: SAFE_PADDING_TOP_PX,
      paddingBottom: SAFE_PADDING_BOTTOM_PX,
      paddingLeft: 0,
      paddingRight: 0,
      overflow: "hidden",
      background: PAPER,
    },
    layers,
  );
}

function fail(message: string): never {
  throw new CustomDiagramError(message);
}

function isHandler(key: string): boolean {
  return /^on[A-Za-z]/.test(key) && key.length >= 5;
}

function rejectMetaKey(key: string): void {
  if (key === "__proto__" || key === "constructor" || key === "prototype" || key.startsWith("__")) {
    fail(`rejected key ${key}`);
  }
}

function copyValue(value: unknown, path: string, depth = 0): unknown {
  if (depth > JSON_MAX_DEPTH) fail("diagram JSON is too deep");
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return copyArray(value, path, depth + 1);
  if (value !== null && typeof value === "object") return copyObject(value, path, depth + 1);
  fail(`${path} is not JSON data`);
}

function copyArray(value: readonly unknown[], path: string, depth: number): unknown[] {
  if (value.length > JSON_MAX_ARRAY) fail(`${path} is too large`);
  if (Object.getOwnPropertySymbols(value).length > 0) fail(`${path} has a symbol key`);
  for (const key of Object.getOwnPropertyNames(value)) {
    if (key === "length") continue;
    if (!/^(0|[1-9]\d*)$/.test(key)) {
      rejectMetaKey(key);
      fail(`rejected key ${key}`);
    }
  }
  const out: unknown[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const desc = Object.getOwnPropertyDescriptor(value, String(index));
    if (!desc || !("value" in desc)) fail(`rejected accessor ${index}`);
    out.push(copyValue(desc.value, `${path}[${index}]`, depth));
  }
  return out;
}

function copyObject(value: object, path: string, depth: number): JsonRecord {
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) fail(`${path} must be a plain object`);
  if (Object.getOwnPropertySymbols(value).length > 0) fail(`${path} has a symbol key`);
  const names = Object.getOwnPropertyNames(value);
  if (names.length > JSON_MAX_KEYS) fail(`${path} has too many keys`);
  const out: JsonRecord = Object.create(null) as JsonRecord;
  for (const key of names) {
    rejectMetaKey(key);
    const desc = Object.getOwnPropertyDescriptor(value, key);
    if (!desc || !("value" in desc)) fail(`rejected accessor ${key}`);
    out[key] = copyValue(desc.value, `${path}.${key}`, depth);
  }
  return out;
}

function parseJson(text: string): unknown {
  if (text.length > JSON_MAX_CHARS) fail("diagram JSON is too large");
  try {
    return JSON.parse(text) as unknown;
  } catch (error) {
    if (error instanceof CustomDiagramError) throw error;
    fail("diagram JSON is not valid");
  }
}

function allowedKeys(record: JsonRecord, allowed: ReadonlySet<string>, path: string): void {
  for (const key of Object.keys(record)) {
    if (isHandler(key)) fail(`rejected handler ${key}`);
    if (!allowed.has(key)) fail(`${path} rejected key ${key}`);
  }
}

function asRecord(value: unknown, path: string): JsonRecord {
  if (value === null || typeof value !== "object" || Array.isArray(value)) fail(`${path} must be an object`);
  return value as JsonRecord;
}

function finiteNumber(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail(`${path} must be a finite number`);
  return value;
}

function inside(x: number, y: number): boolean {
  const maxX = CONTENT_WIDTH - CONTENT_INSET_PX;
  const maxY = CONTENT_HEIGHT - CONTENT_INSET_PX;
  return x >= CONTENT_INSET_PX && y >= CONTENT_INSET_PX && x <= maxX && y <= maxY;
}

function assertInside(x: number, y: number, path: string): void {
  if (!inside(x, y)) fail(`${path} leaves the safe zone`);
}

function requireSeed(value: unknown): string {
  if (typeof value !== "string" || !SEED_PATTERN.test(value)) fail("seed must be a token");
  return value;
}

function requireFrame(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0 || value > MAX_FRAME) {
    fail("frame must be an integer from 0 to 216000");
  }
  return value;
}

function readPoint(value: unknown, path: string): DiagramPoint {
  const record = asRecord(value, path);
  allowedKeys(record, POINT_KEYS, path);
  const x = finiteNumber(record.x, `${path}.x`);
  const y = finiteNumber(record.y, `${path}.y`);
  assertInside(x, y, path);
  return { x, y };
}

function readPoints(value: unknown, path: string, min: number): DiagramPoint[] {
  if (!Array.isArray(value)) fail(`${path} must be an array`);
  if (value.length < min || value.length > MAX_POINTS) {
    fail(`${path} must contain ${min} to ${MAX_POINTS} points`);
  }
  return value.map((item, index) => readPoint(item, `${path}[${index}]`));
}

function labelText(value: unknown): string {
  if (typeof value !== "string") fail("label text must be a string");
  if (value.length < 1 || value.length > LABEL_MAX_CHARS) fail("label text must be 1 to 180 characters");
  if (CONTROL_CHARS.test(value)) fail("label text contains a control character");
  const words = value.trim().split(/\s+/).filter((word) => word.length > 0);
  if (words.length < 1) fail("label text must be a string");
  if (words.length > LABEL_MAX_WORDS) fail("label exceeds 12 words");
  return value;
}

function positive(value: number, message: string): number {
  if (!(value > 0)) fail(message);
  return value;
}

function validateRect(record: JsonRecord, path: string): DiagramRect {
  const x = finiteNumber(record.x, `${path}.x`);
  const y = finiteNumber(record.y, `${path}.y`);
  const width = positive(finiteNumber(record.width, `${path}.width`), "rect width and height must be positive");
  const height = positive(finiteNumber(record.height, `${path}.height`), "rect width and height must be positive");
  assertInside(x, y, path);
  assertInside(x + width, y, path);
  assertInside(x, y + height, path);
  assertInside(x + width, y + height, path);
  return { type: "rect", x, y, width, height };
}

function validateEllipse(record: JsonRecord, path: string): DiagramEllipse {
  const cx = finiteNumber(record.cx, `${path}.cx`);
  const cy = finiteNumber(record.cy, `${path}.cy`);
  const rx = positive(finiteNumber(record.rx, `${path}.rx`), "ellipse radii must be positive");
  const ry = positive(finiteNumber(record.ry, `${path}.ry`), "ellipse radii must be positive");
  assertInside(cx - rx, cy - ry, path);
  assertInside(cx + rx, cy - ry, path);
  assertInside(cx - rx, cy + ry, path);
  assertInside(cx + rx, cy + ry, path);
  return { type: "ellipse", cx, cy, rx, ry };
}

function validateLine(record: JsonRecord, path: string): DiagramLine {
  const x1 = finiteNumber(record.x1, `${path}.x1`);
  const y1 = finiteNumber(record.y1, `${path}.y1`);
  const x2 = finiteNumber(record.x2, `${path}.x2`);
  const y2 = finiteNumber(record.y2, `${path}.y2`);
  assertInside(x1, y1, path);
  assertInside(x2, y2, path);
  if (Math.hypot(x2 - x1, y2 - y1) < 0.5) fail("line is too short");
  return { type: "line", x1, y1, x2, y2 };
}

function samePoint(a: DiagramPoint, b: DiagramPoint): boolean {
  return Math.abs(a.x - b.x) <= 1e-6 && Math.abs(a.y - b.y) <= 1e-6;
}

function validateArrow(record: JsonRecord, path: string): DiagramArrow {
  const from = readPoint(record.from, `${path}.from`);
  const to = readPoint(record.to, `${path}.to`);
  const parts = arrowParts(from, to);
  for (const point of [...parts.shaft, ...parts.head]) assertInside(point.x, point.y, path);
  return { type: "arrow", from, to };
}

function validateLabel(record: JsonRecord, path: string): DiagramLabel {
  const x = finiteNumber(record.x, `${path}.x`);
  const y = finiteNumber(record.y, `${path}.y`);
  const text = labelText(record.text);
  const width = Math.max(12, Math.ceil(text.length * LABEL_CHAR_PX));
  assertInside(x, y, path);
  assertInside(x + width, y, path);
  assertInside(x, y + LABEL_HEIGHT, path);
  assertInside(x + width, y + LABEL_HEIGHT, path);
  return { type: "label", x, y, text };
}

function validatePrimitive(value: unknown, index: number): DiagramPrimitive {
  const path = `primitives[${index}]`;
  const record = asRecord(value, path);
  const type = record.type;
  const keys =
    typeof type === "string" && Object.hasOwn(PRIMITIVE_KEYS, type) ? PRIMITIVE_KEYS[type] : undefined;
  if (!keys) fail(`rejected primitive type ${String(type)}`);
  allowedKeys(record, new Set(keys), path);
  switch (type) {
    case "rect":
      return validateRect(record, path);
    case "ellipse":
      return validateEllipse(record, path);
    case "line":
      return validateLine(record, path);
    case "polyline":
      return { type: "polyline", points: readPoints(record.points, `${path}.points`, 2) };
    case "polygon": {
      const points = readPoints(record.points, `${path}.points`, 3);
      const first = points[0];
      const last = points[points.length - 1];
      if (first && last && samePoint(first, last)) fail("polygon points must not repeat the start point");
      return { type: "polygon", points };
    }
    case "arrow":
      return validateArrow(record, path);
    case "label":
      return validateLabel(record, path);
    default:
      fail(`rejected primitive type ${String(type)}`);
  }
}

export function parseCustomDiagram(input: unknown): CustomDiagramSpec {
  const copied = typeof input === "string" ? copyValue(parseJson(input), "spec") : copyValue(input, "spec");
  const record = asRecord(copied, "spec");
  allowedKeys(record, SPEC_KEYS, "spec");
  if (record.isEndScreen !== undefined && typeof record.isEndScreen !== "boolean") {
    fail("isEndScreen must be a boolean");
  }
  if (!Array.isArray(record.primitives)) fail("primitives must be an array");
  if (record.primitives.length > MAX_PRIMITIVES) fail(`at most ${MAX_PRIMITIVES} primitives`);
  return {
    seed: requireSeed(record.seed),
    frame: requireFrame(record.frame),
    isEndScreen: record.isEndScreen === true,
    primitives: record.primitives.map((item, index) => validatePrimitive(item, index)),
  };
}

function arrowParts(from: DiagramPoint, to: DiagramPoint): { shaft: DiagramPoint[]; head: DiagramPoint[] } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  if (!(length >= ARROW_HEAD + 2)) fail("arrow is too short");
  const ux = dx / length;
  const uy = dy / length;
  const px = -uy;
  const py = ux;
  const baseX = to.x - ux * ARROW_HEAD;
  const baseY = to.y - uy * ARROW_HEAD;
  return {
    shaft: [from, to],
    head: [
      { x: baseX + px * ARROW_HALF, y: baseY + py * ARROW_HALF },
      to,
      { x: baseX - px * ARROW_HALF, y: baseY - py * ARROW_HALF },
    ],
  };
}

function ellipsePoints(primitive: DiagramEllipse): DiagramPoint[] {
  const points: DiagramPoint[] = [];
  const steps = 16;
  for (let index = 0; index < steps; index += 1) {
    const angle = (index / steps) * Math.PI * 2;
    points.push({
      x: primitive.cx + Math.cos(angle) * primitive.rx,
      y: primitive.cy + Math.sin(angle) * primitive.ry,
    });
  }
  return points;
}

function outlineOf(primitive: DiagramPrimitive): { points: DiagramPoint[]; closed: boolean; role: StrokeRole } | null {
  switch (primitive.type) {
    case "rect":
      return {
        role: "outline",
        closed: true,
        points: [
          { x: primitive.x, y: primitive.y },
          { x: primitive.x + primitive.width, y: primitive.y },
          { x: primitive.x + primitive.width, y: primitive.y + primitive.height },
          { x: primitive.x, y: primitive.y + primitive.height },
        ],
      };
    case "ellipse":
      return { role: "outline", closed: true, points: ellipsePoints(primitive) };
    case "line":
      return {
        role: "outline",
        closed: false,
        points: [
          { x: primitive.x1, y: primitive.y1 },
          { x: primitive.x2, y: primitive.y2 },
        ],
      };
    case "polyline":
      return { role: "outline", closed: false, points: [...primitive.points] };
    case "polygon":
      return { role: "outline", closed: true, points: [...primitive.points] };
    case "label":
    case "arrow":
      return null;
    default:
      return null;
  }
}

function strokeSeed(seed: string, index: number, type: string, role: StrokeRole): string {
  return `${seed}:${index}:${type}:${role}`;
}

function annotate(path: DiagramElement, key: string, extra: Readonly<Record<string, string>>): DiagramElement {
  return {
    $$typeof: path.$$typeof,
    type: path.type,
    key,
    ref: null,
    props: { ...path.props, ...extra },
  };
}

function placeStroke(
  strokes: DiagramStroke[],
  nodes: DiagramElement[],
  input: {
    readonly index: number;
    readonly type: DiagramPrimitive["type"];
    readonly role: StrokeRole;
    readonly seed: string;
    readonly points: readonly DiagramPoint[];
    readonly closed: boolean;
    readonly frame: number;
    readonly strokeWidth: number;
  },
): void {
  const path = BoilPath({
    points: input.points,
    seed: input.seed,
    frame: input.frame,
    closed: input.closed,
    strokeWidth: input.strokeWidth,
  });
  const d = path.props.d;
  if (typeof d !== "string" || path.type !== "path") fail("BoilPath did not return a path");
  strokes.push({
    index: input.index,
    type: input.type,
    role: input.role,
    seed: input.seed,
    points: input.points,
    closed: input.closed,
    d,
  });
  nodes.push(
    annotate(path, `${input.role}-${input.index}`, {
      "data-primitive-index": String(input.index),
      "data-primitive-type": input.type,
      "data-boil-role": input.role,
    }),
  );
}

export function walkDiagram(node: DiagramChild, into: DiagramElement[] = []): DiagramElement[] {
  if (typeof node === "string") return into;
  into.push(node);
  const children = node.props.children;
  if (children === undefined || typeof children === "string") return into;
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) {
    if (typeof child === "string") continue;
    walkDiagram(child as DiagramChild, into);
  }
  return into;
}

export function CustomDiagramScene(input: unknown): CustomDiagramSceneNode {
  const spec = parseCustomDiagram(input);
  const strokes: DiagramStroke[] = [];
  const nodes: DiagramElement[] = [];
  const texts: string[] = [];
  spec.primitives.forEach((primitive, index) => {
    if (primitive.type === "arrow") {
      const parts = arrowParts(primitive.from, primitive.to);
      placeStroke(strokes, nodes, {
        index,
        type: "arrow",
        role: "shaft",
        seed: strokeSeed(spec.seed, index, "arrow", "shaft"),
        points: parts.shaft,
        closed: false,
        frame: spec.frame,
        strokeWidth: 3,
      });
      placeStroke(strokes, nodes, {
        index,
        type: "arrow",
        role: "head",
        seed: strokeSeed(spec.seed, index, "arrow", "head"),
        points: parts.head,
        closed: true,
        frame: spec.frame,
        strokeWidth: 3,
      });
      return;
    }
    if (primitive.type === "label") {
      const width = Math.max(12, Math.ceil(primitive.text.length * LABEL_CHAR_PX));
      const underlineY = primitive.y + LABEL_HEIGHT - 6;
      placeStroke(strokes, nodes, {
        index,
        type: "label",
        role: "underline",
        seed: strokeSeed(spec.seed, index, "label", "underline"),
        points: [
          { x: primitive.x, y: underlineY },
          { x: primitive.x + width, y: underlineY },
        ],
        closed: false,
        frame: spec.frame,
        strokeWidth: 2,
      });
      texts.push(primitive.text);
      nodes.push(
        element(
          "text",
          `label-${index}`,
          {
            x: primitive.x,
            y: primitive.y + 24,
            fill: INK,
            fontSize: 24,
            "data-primitive-index": String(index),
            "data-primitive-type": "label",
            "data-text-node": "svg-text",
          },
          undefined,
          [primitive.text],
        ),
      );
      return;
    }
    const outline = outlineOf(primitive);
    if (!outline) fail(`rejected primitive type ${primitive.type}`);
    placeStroke(strokes, nodes, {
      index,
      type: primitive.type,
      role: outline.role,
      seed: strokeSeed(spec.seed, index, primitive.type, outline.role),
      points: outline.points,
      closed: outline.closed,
      frame: spec.frame,
      strokeWidth: 3,
    });
  });

  const svg = element(
    "svg",
    "diagram",
    {
      xmlns: "http://www.w3.org/2000/svg",
      viewBox: `0 0 ${CONTENT_WIDTH} ${CONTENT_HEIGHT}`,
      width: CONTENT_WIDTH,
      height: CONTENT_HEIGHT,
      "data-slot": "diagram",
    },
    { overflow: "hidden" },
    nodes,
  );
  const content = element(
    "div",
    "content",
    { "data-slot": "content" },
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
    [svg],
  );
  const frame = SafeZoneLayout({ isEndScreen: spec.isEndScreen, children: [content] });
  const tick = boilTick(spec.frame);
  return {
    ...frame,
    key: "custom-diagram",
    props: {
      ...frame.props,
      "data-motif": MOTIF_COMPONENT,
      "data-layer": String(LAYER),
      "data-owner": "render_catalog",
      "data-primitive-count": String(spec.primitives.length),
      "data-code-execution": "0",
      "data-max-primitives": String(MAX_PRIMITIVES),
      "data-fps": String(FPS),
      "data-boil-fps": String(BOIL_FPS),
      "data-frame": String(spec.frame),
      "data-boil-tick": String(tick),
    },
    primitiveCount: spec.primitives.length,
    tick,
    strokes,
    texts,
  };
}

function escapeText(value: string): string {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function escapeAttr(value: string): string {
  return escapeText(value).replaceAll('"', "&quot;");
}

function styleAttribute(style: Readonly<Record<string, string | number>>): string {
  const parts: string[] = [];
  for (const [name, value] of Object.entries(style)) {
    if (!/^[A-Za-z]+$/.test(name)) fail("rejected style property");
    const cssName = name.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`);
    if (typeof value !== "number" && typeof value !== "string") fail("rejected style value");
    const text = typeof value === "number" ? `${value}px` : value;
    if (!STYLE_VALUE.test(text)) fail("rejected style value");
    parts.push(`${cssName}:${text}`);
  }
  return parts.join(";");
}

function attrName(name: string): string {
  if (name === "strokeWidth") return "stroke-width";
  if (name === "strokeLinecap") return "stroke-linecap";
  if (name === "strokeLinejoin") return "stroke-linejoin";
  if (name === "fontSize") return "font-size";
  return name;
}

function serialize(node: DiagramChild): string {
  if (typeof node === "string") return escapeText(node);
  if (!HOST_TAGS.has(node.type)) fail(`rejected serialized tag ${node.type}`);
  const attrs: string[] = [];
  for (const [name, value] of Object.entries(node.props)) {
    if (name === "children" || name === "style") continue;
    if (typeof value !== "string" && typeof value !== "number") fail(`rejected attribute ${name}`);
    const attribute = attrName(name);
    if (!/^[A-Za-z_:][A-Za-z0-9:._-]*$/.test(attribute)) fail(`rejected attribute ${name}`);
    attrs.push(`${attribute}="${escapeAttr(String(value))}"`);
  }
  const style = node.props.style;
  if (style !== undefined) {
    if (style === null || typeof style !== "object" || Array.isArray(style)) fail("rejected style value");
    attrs.push(`style="${escapeAttr(styleAttribute(style as Readonly<Record<string, string | number>>))}"`);
  }
  const attrText = attrs.length > 0 ? ` ${attrs.join(" ")}` : "";
  if (node.type === "path") {
    if (node.props.children !== undefined) fail("path cannot have children");
    return `<path${attrText}/>`;
  }
  const children = node.props.children;
  let inner = "";
  if (typeof children === "string") inner = escapeText(children);
  else if (Array.isArray(children)) {
    inner = children.map((child) => serialize(child as DiagramChild)).join("");
  } else if (children !== undefined) {
    inner = serialize(children as DiagramChild);
  }
  return `<${node.type}${attrText}>${inner}</${node.type}>`;
}

export function renderCustomDiagramMarkup(input: unknown): string {
  const markup = serialize(CustomDiagramScene(input));
  const tags = [...markup.matchAll(/<\/?([A-Za-z][\w:.-]*)\b/g)].map((match) => match[1] ?? "");
  for (const tag of tags) {
    if (!HOST_TAGS.has(tag)) fail(`rejected serialized tag ${tag}`);
  }
  return markup;
}
