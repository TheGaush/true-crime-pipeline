/**
 * Deterministic 6 fps line boil for `@tc/render_catalog`.
 *
 * Strokes are crisp SVG `<path>` nodes. Vertex positions are perturbed in JS
 * with Mulberry32, then held for five container frames (`Math.floor(frame / 5)`
 * at 30 fps). This module does not emit SVG turbulence or displacement
 * primitives and does not read the network.
 *
 * `frame` is the Remotion container frame. Pass it in. There is no runtime
 * clock, so the same `(points, seed, frame)` pair always rebuilds the same path.
 */

export const CONTAINER_FPS = 30;
export const BOIL_FPS = 6;
/** Container frames per boil tick. `30 / 6`. */
export const BOIL_FRAME_STRIDE = CONTAINER_FPS / BOIL_FPS;
/** Normal-vector jitter bound, in SVG user units (px at 1080p). */
export const JITTER_AMPLITUDE_PX = 1.4;
export const DEFAULT_SUBDIVISIONS = 4;
const MAX_SUBDIVISIONS = 64;
const PATH_SCALE = 10000;

/**
 * React 19 host-element brand (`Symbol.for('react.transitional.element')`).
 * Returning this from `BoilPath` lets `<BoilPath />` reconcile as a DOM
 * `<path>` without a static `react` import (the package shell does not depend
 * on React yet; see the task handoff).
 */
const REACT_ELEMENT = Symbol.for('react.transitional.element');

export interface Vec2 {
  readonly x: number;
  readonly y: number;
}

export type BoilCurve =
  | { readonly kind: 'line' }
  | { readonly kind: 'quadratic'; readonly c: Vec2 }
  | { readonly kind: 'cubic'; readonly c1: Vec2; readonly c2: Vec2 };

/**
 * Polyline / curve anchor. `curve` describes the segment that *ends* on this
 * anchor. A closed path that does not repeat its start point uses
 * `points[0].curve` for the generated closing segment.
 */
export interface BoilPoint extends Vec2 {
  readonly curve?: BoilCurve;
}

export interface BoilPathProps {
  readonly points: readonly BoilPoint[];
  readonly seed: string | number;
  /** Remotion frame at {@link CONTAINER_FPS}. Quantized with `Math.floor(frame / 5)`. */
  readonly frame: number;
  /** Share one perturbation for `points[0]` and `points[n - 1]`. */
  readonly closed?: boolean;
  /** Equal steps per segment, including the segment end. Default {@link DEFAULT_SUBDIVISIONS}. */
  readonly subdivisions?: number;
  readonly stroke?: string;
  readonly strokeWidth?: number;
  readonly fill?: string;
}

export interface BoilPathAttributes {
  readonly d: string;
  readonly fill: string;
  readonly stroke: string;
  readonly strokeWidth: number;
  readonly strokeLinecap: 'round';
  readonly strokeLinejoin: 'round';
  readonly 'data-boil-tick': number;
  readonly 'data-boil-fps': typeof BOIL_FPS;
  readonly 'data-container-fps': typeof CONTAINER_FPS;
}

export interface BoilPathElement {
  readonly $$typeof: symbol;
  readonly type: 'path';
  readonly key: null;
  readonly ref: null;
  readonly props: BoilPathAttributes;
}

export interface BoilSample extends Vec2 {
  /** Index into the input `points`, or `null` for a subdivided interior sample. */
  readonly origin: number | null;
}

export interface BoilGeometry {
  readonly tick: number;
  /** Subdivided polyline before jitter. Closed paths repeat the start point at the end. */
  readonly samples: readonly BoilSample[];
  /** Samples after normal-vector jitter. */
  readonly vertices: readonly Vec2[];
  /** `vertices[i] - samples[i]`. Closed seams share the vector at both endpoints. */
  readonly perturbations: readonly Vec2[];
  readonly d: string;
}

interface ResolvedPoint extends Vec2 {
  readonly curve: BoilCurve;
}

interface Segment {
  readonly from: Vec2;
  readonly to: Vec2;
  readonly curve: BoilCurve;
  readonly destinationOrigin: number;
}

export function boilTick(frame: number): number {
  if (!Number.isFinite(frame)) {
    throw new TypeError(`BoilPath frame must be a finite number, received ${String(frame)}`);
  }
  return Math.floor(frame / BOIL_FRAME_STRIDE);
}

/** Canonical Mulberry32. `seed` is forced to uint32. Returns floats in `[0, 1)`. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** FNV-1a mixed with the boil tick. Stable across processes. */
export function boilRngSeed(seed: string | number, tick: number): number {
  const text = `${typeof seed}:${String(seed)}#${tick}`;
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function assertVec(value: Vec2, label: string): void {
  if (value === null || typeof value !== 'object' || !Number.isFinite(value.x) || !Number.isFinite(value.y)) {
    throw new TypeError(`${label} must be a finite {x, y} point`);
  }
}

function resolveCurve(point: BoilPoint, index: number): BoilCurve {
  const curve = point.curve;
  if (curve === undefined || curve.kind === 'line') return { kind: 'line' };
  if (curve.kind === 'quadratic') {
    assertVec(curve.c, `points[${index}].curve.c`);
    return { kind: 'quadratic', c: { x: curve.c.x, y: curve.c.y } };
  }
  if (curve.kind === 'cubic') {
    assertVec(curve.c1, `points[${index}].curve.c1`);
    assertVec(curve.c2, `points[${index}].curve.c2`);
    return {
      kind: 'cubic',
      c1: { x: curve.c1.x, y: curve.c1.y },
      c2: { x: curve.c2.x, y: curve.c2.y },
    };
  }
  throw new TypeError(`points[${index}].curve.kind is not supported`);
}

function resolvePoints(points: readonly BoilPoint[]): ResolvedPoint[] {
  if (!Array.isArray(points)) throw new TypeError('BoilPath points must be an array');
  return points.map((point, index) => {
    assertVec(point, `points[${index}]`);
    return { x: point.x, y: point.y, curve: resolveCurve(point, index) };
  });
}

function samePoint(a: Vec2, b: Vec2): boolean {
  return Math.abs(a.x - b.x) <= 1e-6 && Math.abs(a.y - b.y) <= 1e-6;
}

function resolveSubdivisions(value: number | undefined): number {
  if (value === undefined) return DEFAULT_SUBDIVISIONS;
  if (!Number.isInteger(value) || value < 1 || value > MAX_SUBDIVISIONS) {
    throw new RangeError(`BoilPath subdivisions must be an integer from 1 to ${MAX_SUBDIVISIONS}`);
  }
  return value;
}

function sampleSegment(from: Vec2, curve: BoilCurve, to: Vec2, t: number): Vec2 {
  if (t >= 1) return { x: to.x, y: to.y };
  if (t <= 0) return { x: from.x, y: from.y };
  if (curve.kind === 'line') {
    return { x: from.x + (to.x - from.x) * t, y: from.y + (to.y - from.y) * t };
  }
  if (curve.kind === 'quadratic') {
    const u = 1 - t;
    return {
      x: u * u * from.x + 2 * u * t * curve.c.x + t * t * to.x,
      y: u * u * from.y + 2 * u * t * curve.c.y + t * t * to.y,
    };
  }
  const u = 1 - t;
  const uu = u * u;
  const tt = t * t;
  return {
    x: uu * u * from.x + 3 * uu * t * curve.c1.x + 3 * u * tt * curve.c2.x + tt * t * to.x,
    y: uu * u * from.y + 3 * uu * t * curve.c1.y + 3 * u * tt * curve.c2.y + tt * t * to.y,
  };
}

function buildSegments(points: readonly ResolvedPoint[], wrap: boolean): Segment[] {
  const segments: Segment[] = [];
  for (let i = 1; i < points.length; i += 1) {
    const destination = points[i];
    const origin = points[i - 1];
    if (destination === undefined || origin === undefined) continue;
    segments.push({
      from: origin,
      to: destination,
      curve: destination.curve,
      destinationOrigin: i,
    });
  }
  if (wrap) {
    const first = points[0];
    const last = points[points.length - 1];
    if (first !== undefined && last !== undefined) {
      segments.push({
        from: last,
        to: first,
        curve: first.curve,
        destinationOrigin: 0,
      });
    }
  }
  return segments;
}

function subdivide(points: readonly ResolvedPoint[], wrap: boolean, steps: number): BoilSample[] {
  const first = points[0];
  if (first === undefined) return [];
  const samples: BoilSample[] = [{ x: first.x, y: first.y, origin: 0 }];
  for (const segment of buildSegments(points, wrap)) {
    for (let step = 1; step <= steps; step += 1) {
      const point = sampleSegment(segment.from, segment.curve, segment.to, step / steps);
      const isEnd = step === steps;
      samples.push({ x: point.x, y: point.y, origin: isEnd ? segment.destinationOrigin : null });
    }
  }
  return samples;
}

function unitNormal(tx: number, ty: number): Vec2 {
  const length = Math.hypot(tx, ty);
  if (length < 1e-9) return { x: 0, y: -1 };
  return { x: -ty / length, y: tx / length };
}

function vertexNormals(samples: readonly BoilSample[], closed: boolean): Vec2[] {
  const ring = closed ? samples.slice(0, -1) : samples;
  const count = ring.length;
  const normals: Vec2[] = [];
  for (let i = 0; i < count; i += 1) {
    const current = ring[i];
    if (current === undefined) continue;
    let tx: number;
    let ty: number;
    if (!closed && i === 0) {
      const next = ring[1] ?? current;
      tx = next.x - current.x;
      ty = next.y - current.y;
    } else if (!closed && i === count - 1) {
      const prev = ring[i - 1] ?? current;
      tx = current.x - prev.x;
      ty = current.y - prev.y;
    } else {
      const prev = ring[(i - 1 + count) % count] ?? current;
      const next = ring[(i + 1) % count] ?? current;
      tx = next.x - prev.x;
      ty = next.y - prev.y;
    }
    normals.push(unitNormal(tx, ty));
  }
  if (closed) {
    const seam = normals[0] ?? { x: 0, y: -1 };
    normals.push(seam);
  }
  return normals;
}

function signedJitter(rng: () => number): number {
  return (rng() * 2 - 1) * JITTER_AMPLITUDE_PX;
}

function fmt(value: number): string {
  const negative = value < 0;
  const scaled = Math.round(Math.abs(value) * PATH_SCALE);
  const whole = Math.trunc(scaled / PATH_SCALE);
  const frac = scaled % PATH_SCALE;
  const body =
    frac === 0 ? String(whole) : `${whole}.${String(frac).padStart(4, '0').replace(/0+$/, '')}`;
  return negative && scaled !== 0 ? `-${body}` : body;
}

function pathData(vertices: readonly Vec2[], closed: boolean): string {
  const first = vertices[0];
  if (first === undefined) return '';
  const commands = [`M ${fmt(first.x)} ${fmt(first.y)}`];
  const lastDrawn = closed ? vertices.length - 1 : vertices.length;
  for (let i = 1; i < lastDrawn; i += 1) {
    const vertex = vertices[i];
    if (vertex === undefined) continue;
    commands.push(`L ${fmt(vertex.x)} ${fmt(vertex.y)}`);
  }
  if (closed) commands.push('Z');
  return commands.join(' ');
}

/**
 * Subdivide polylines and quadratic/cubic segments, then jitter along vertex normals.
 * Draw order (locked for bit-stable paths):
 * 1. One Mulberry32 sample for `points[0]`.
 * 2. One sample per later original vertex. On `closed`, `points[n - 1]` reuses step 1
 *    and does not draw again.
 * 3. One sample per subdivided interior, in path order.
 * Closed endpoints then share that first displacement vector, so the seam gap
 * cannot open or close between ticks. A closed point list that already repeats
 * its start point is not wrapped a second time.
 */
export function buildBoilGeometry(props: BoilPathProps): BoilGeometry {
  const frameTick = boilTick(props.frame);
  if (typeof props.seed !== 'string' && typeof props.seed !== 'number') {
    throw new TypeError('BoilPath seed must be a string or a number');
  }
  if (typeof props.seed === 'number' && !Number.isFinite(props.seed)) {
    throw new TypeError('BoilPath numeric seed must be finite');
  }
  if (props.closed !== undefined && typeof props.closed !== 'boolean') {
    throw new TypeError('BoilPath closed must be a boolean');
  }
  const closed = props.closed === true;
  const steps = resolveSubdivisions(props.subdivisions);
  const points = resolvePoints(props.points);
  if (points.length < 2) {
    throw new RangeError('BoilPath needs at least two points');
  }
  const first = points[0];
  const last = points[points.length - 1];
  if (first === undefined || last === undefined) {
    throw new RangeError('BoilPath needs at least two points');
  }
  const endpointsMeet = closed && samePoint(first, last);
  if (closed && endpointsMeet && points.length < 3) {
    throw new RangeError('BoilPath closed paths need at least two distinct points');
  }
  const wrap = closed && !endpointsMeet;

  const samples = subdivide(points, wrap, steps);
  if (closed && samples.length > 1) {
    const end = samples[samples.length - 1];
    if (end !== undefined) {
      samples[samples.length - 1] = { x: first.x, y: first.y, origin: end.origin };
    }
  }
  const normals = vertexNormals(samples, closed);
  const rng = mulberry32(boilRngSeed(props.seed, frameTick));
  const lastOrigin = points.length - 1;
  const originScalar: number[] = [];
  for (let origin = 0; origin < points.length; origin += 1) {
    if (closed && origin === lastOrigin) originScalar.push(originScalar[0] ?? 0);
    else originScalar.push(signedJitter(rng));
  }

  const scalars: Array<number | null> = samples.map((sample) => {
    if (sample.origin === null) return null;
    return originScalar[sample.origin] ?? 0;
  });
  for (let i = 0; i < scalars.length; i += 1) {
    if (scalars[i] === null) scalars[i] = signedJitter(rng);
  }

  const seamNormal = normals[0] ?? { x: 0, y: -1 };
  const seamScalar = originScalar[0] ?? 0;
  const seamVector = { x: seamNormal.x * seamScalar, y: seamNormal.y * seamScalar };

  const vertices: Vec2[] = [];
  const perturbations: Vec2[] = [];
  for (let i = 0; i < samples.length; i += 1) {
    const sample = samples[i];
    const normal = normals[i] ?? seamNormal;
    if (sample === undefined) continue;
    const sharesSeam = closed && (sample.origin === 0 || sample.origin === lastOrigin);
    const scalar = scalars[i] ?? 0;
    const perturbation = sharesSeam ? seamVector : { x: normal.x * scalar, y: normal.y * scalar };
    perturbations.push(perturbation);
    vertices.push({ x: sample.x + perturbation.x, y: sample.y + perturbation.y });
  }

  if (closed && vertices.length > 1) {
    const start = vertices[0];
    const startDelta = perturbations[0];
    if (start !== undefined) vertices[vertices.length - 1] = { x: start.x, y: start.y };
    if (startDelta !== undefined) perturbations[perturbations.length - 1] = startDelta;
  }

  return { tick: frameTick, samples, vertices, perturbations, d: pathData(vertices, closed) };
}

function resolvePaint(props: BoilPathProps): { fill: string; stroke: string; strokeWidth: number } {
  const fill = props.fill ?? 'none';
  const stroke = props.stroke ?? '#161616';
  const strokeWidth = props.strokeWidth ?? 2;
  if (typeof fill !== 'string' || typeof stroke !== 'string') {
    throw new TypeError('BoilPath fill and stroke must be strings');
  }
  if (!Number.isFinite(strokeWidth) || strokeWidth < 0) {
    throw new RangeError('BoilPath strokeWidth must be a finite number >= 0');
  }
  return { fill, stroke, strokeWidth };
}

/** Host `<path>` element for the current 6 fps tick. No child nodes. */
export function BoilPath(props: BoilPathProps): BoilPathElement {
  const geometry = buildBoilGeometry(props);
  const paint = resolvePaint(props);
  return {
    $$typeof: REACT_ELEMENT,
    type: 'path',
    key: null,
    ref: null,
    props: {
      d: geometry.d,
      fill: paint.fill,
      stroke: paint.stroke,
      strokeWidth: paint.strokeWidth,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      'data-boil-tick': geometry.tick,
      'data-boil-fps': BOIL_FPS,
      'data-container-fps': CONTAINER_FPS,
    },
  };
}

export { BoilPath as LineBoilPath };

function escapeAttr(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

/** Serialize the host path. Attributes are whitelisted; paint strings are escaped. */
export function renderBoilPathMarkup(props: BoilPathProps): string {
  const { props: attributes } = BoilPath(props);
  return (
    `<path d="${escapeAttr(attributes.d)}"` +
    ` fill="${escapeAttr(attributes.fill)}"` +
    ` stroke="${escapeAttr(attributes.stroke)}"` +
    ` stroke-width="${attributes.strokeWidth}"` +
    ` stroke-linecap="${attributes.strokeLinecap}"` +
    ` stroke-linejoin="${attributes.strokeLinejoin}"` +
    ` data-boil-tick="${attributes['data-boil-tick']}"` +
    ` data-boil-fps="${attributes['data-boil-fps']}"` +
    ` data-container-fps="${attributes['data-container-fps']}"/>`
  );
}
