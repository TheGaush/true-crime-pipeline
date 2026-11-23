/**
 * Offline zero-spend checks for the 6 fps JS line boil.
 * Node's test runner loads the transpiled module. No network, no SVG filters.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { test } from 'node:test';

import {
  BOIL_FPS,
  BOIL_FRAME_STRIDE,
  CONTAINER_FPS,
  DEFAULT_SUBDIVISIONS,
  JITTER_AMPLITUDE_PX,
  BoilPath,
  boilRngSeed,
  boilTick,
  buildBoilGeometry,
  mulberry32,
  renderBoilPathMarkup,
} from '../src/rig/LineBoilPath.tsx';

const SOURCE_URL = new URL('../src/rig/LineBoilPath.tsx', import.meta.url);

const SQUARE = [
  { x: 10, y: 20 },
  { x: 110, y: 20 },
  { x: 110, y: 90 },
  { x: 10, y: 90 },
];

function square(frame, closed = true, subdivisions = 2) {
  return { points: SQUARE, seed: 'case-01', frame, closed, subdivisions };
}

function elementNames(markup) {
  const names = [];
  const pattern = /<\/?([A-Za-z][\w:.-]*)\b/g;
  for (const match of markup.matchAll(pattern)) names.push(match[1]);
  return names;
}

function displacement(geometry, origin) {
  const index = geometry.samples.findIndex((sample) => sample.origin === origin);
  assert.notEqual(index, -1);
  return geometry.perturbations[index];
}

test('quantizes 30 fps frames onto 6 fps ticks with Math.floor(frame / 5)', () => {
  assert.equal(CONTAINER_FPS, 30);
  assert.equal(BOIL_FPS, 6);
  assert.equal(BOIL_FRAME_STRIDE, 5);
  assert.equal(JITTER_AMPLITUDE_PX, 1.4);
  assert.equal(DEFAULT_SUBDIVISIONS, 4);
  for (const frame of [0, 1, 2, 3, 4]) assert.equal(boilTick(frame), 0, String(frame));
  for (const frame of [5, 6, 7, 8, 9]) assert.equal(boilTick(frame), 1, String(frame));
  assert.equal(boilTick(4.9), 0);
  assert.equal(boilTick(5), 1);
  assert.equal(boilTick(29), 5);
  assert.equal(boilTick(30), 6);
  assert.equal(boilTick(-1), -1);
  assert.equal(boilTick(-5), -1);
  assert.equal(boilTick(-6), -2);
});

test('Mulberry32 is the canonical uint32 generator', () => {
  const rng = mulberry32(1);
  const first = rng();
  assert.equal(first, 0.6270739405881613);
  assert.equal(rng(), 0.002735721180215478);
  assert.equal(boilRngSeed('case-01', 0), boilRngSeed('case-01', 0));
  assert.notEqual(boilRngSeed('case-01', 0), boilRngSeed('case-01', 1));
  assert.notEqual(boilRngSeed(1, 0), boilRngSeed('1', 0));
});

test('holds one path for five container frames, then advances', () => {
  const tick0 = renderBoilPathMarkup(square(0));
  for (const frame of [1, 2, 3, 4, 4.9]) {
    assert.equal(renderBoilPathMarkup(square(frame)), tick0);
  }
  const tick1 = renderBoilPathMarkup(square(5));
  assert.notEqual(tick1, tick0);
  for (const frame of [6, 7, 8, 9]) {
    assert.equal(renderBoilPathMarkup(square(frame)), tick1);
  }
  const paths = new Set();
  for (let frame = 0; frame < 30; frame += 1) paths.add(renderBoilPathMarkup(square(frame)));
  assert.equal(paths.size, 6);
});

test('is bit-deterministic for the same seed, points, and frame', () => {
  const a = buildBoilGeometry(square(12));
  const b = buildBoilGeometry(square(12));
  assert.deepEqual(a, b);
  assert.equal(renderBoilPathMarkup(square(12)), renderBoilPathMarkup(square(12)));
  assert.notEqual(renderBoilPathMarkup(square(0)), renderBoilPathMarkup({ ...square(0), seed: 'case-02' }));
  assert.equal(
    renderBoilPathMarkup(square(0)),
    '<path d="M 10.5607 20.801 L 60 18.7827 L 109.6757 20.4633 L 110.7474 55 L 110.7949 91.1356 L 60 89.6697 L 10.5607 90.801 L 9.3703 55 Z" fill="none" stroke="#161616" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" data-boil-tick="0" data-boil-fps="6" data-container-fps="30"/>',
  );
});

test('subdivides straight segments and flattens quadratic and cubic curves', () => {
  const line = buildBoilGeometry({
    points: [
      { x: 0, y: 0 },
      { x: 100, y: 0 },
    ],
    seed: 'line',
    frame: 0,
    subdivisions: 4,
  });
  assert.equal(line.samples.length, 5);
  assert.deepEqual(
    line.samples.map((sample) => sample.origin),
    [0, null, null, null, 1],
  );
  assert.equal(line.samples[2].x, 50);
  assert.equal(line.samples[2].y, 0);
  assert.equal(line.d.endsWith('Z'), false);

  const defaults = buildBoilGeometry({
    points: [
      { x: 0, y: 0 },
      { x: 40, y: 0 },
    ],
    seed: 'default',
    frame: 0,
  });
  assert.equal(defaults.samples.length, 1 + DEFAULT_SUBDIVISIONS);
  assert.equal(defaults.d.includes('Z'), false);

  const quadratic = buildBoilGeometry({
    points: [
      { x: 0, y: 0 },
      { x: 100, y: 0, curve: { kind: 'quadratic', c: { x: 50, y: 100 } } },
    ],
    seed: 'quad',
    frame: 0,
    subdivisions: 2,
  });
  assert.equal(quadratic.samples.length, 3);
  assert.equal(quadratic.samples[1].x, 50);
  assert.equal(quadratic.samples[1].y, 50);
  assert.equal(quadratic.samples[1].origin, null);

  const cubic = buildBoilGeometry({
    points: [
      { x: 0, y: 0 },
      {
        x: 90,
        y: 0,
        curve: { kind: 'cubic', c1: { x: 30, y: 60 }, c2: { x: 60, y: 60 } },
      },
    ],
    seed: 'cubic',
    frame: 0,
    subdivisions: 2,
  });
  assert.equal(cubic.samples[1].x, 45);
  assert.equal(cubic.samples[1].y, 45);
  assert.equal(cubic.samples[2].x, 90);
  assert.equal(cubic.samples[2].y, 0);
});

test('keeps every vertex inside the +/- 1.4 px normal bound', () => {
  for (let frame = 0; frame < 30; frame += 1) {
    const geometry = buildBoilGeometry(square(frame, true, 4));
    for (const delta of geometry.perturbations) {
      const distance = Math.hypot(delta.x, delta.y);
      assert.ok(distance <= JITTER_AMPLITUDE_PX + 1e-9, `${distance} at frame ${frame}`);
    }
  }
});

test('closed paths share one perturbation for point[0] and point[N-1]', () => {
  const closed = buildBoilGeometry(square(3, true, 1));
  const start = displacement(closed, 0);
  const end = displacement(closed, SQUARE.length - 1);
  assert.deepEqual(end, start);
  assert.ok(Math.hypot(start.x, start.y) > 0);
  const last = closed.perturbations[closed.perturbations.length - 1];
  assert.deepEqual(last, start);
  assert.deepEqual(closed.vertices[0], closed.vertices[closed.vertices.length - 1]);

  const gapBefore = {
    x: SQUARE[SQUARE.length - 1].x - SQUARE[0].x,
    y: SQUARE[SQUARE.length - 1].y - SQUARE[0].y,
  };
  const endIndex = closed.samples.findIndex((sample) => sample.origin === SQUARE.length - 1);
  const gapAfter = {
    x: closed.vertices[endIndex].x - closed.vertices[0].x,
    y: closed.vertices[endIndex].y - closed.vertices[0].y,
  };
  assert.ok(Math.abs(gapAfter.x - gapBefore.x) < 1e-9);
  assert.ok(Math.abs(gapAfter.y - gapBefore.y) < 1e-9);

  const duplicated = buildBoilGeometry({
    points: [...SQUARE, { x: SQUARE[0].x, y: SQUARE[0].y }],
    seed: 'case-01',
    frame: 3,
    closed: true,
    subdivisions: 1,
  });
  assert.deepEqual(duplicated.vertices[0], duplicated.vertices[duplicated.vertices.length - 1]);
  assert.deepEqual(displacement(duplicated, 0), displacement(duplicated, SQUARE.length));
  assert.notDeepEqual(displacement(duplicated, 0), displacement(duplicated, 1));

  let openEndpointsDiffer = false;
  for (let i = 0; i < 8; i += 1) {
    const open = buildBoilGeometry({
      points: [
        { x: 0, y: 0 },
        { x: 80, y: 0 },
      ],
      seed: `open-${i}`,
      frame: 0,
      closed: false,
      subdivisions: 1,
    });
    const a = open.perturbations[0];
    const b = open.perturbations[open.perturbations.length - 1];
    if (a.x !== b.x || a.y !== b.y) openEndpointsDiffer = true;
  }
  assert.equal(openEndpointsDiffer, true);
});

test('emits a single crisp path node and no turbulence or displacement primitives', () => {
  const element = BoilPath(square(0));
  assert.equal(element.type, 'path');
  assert.equal(element.key, null);
  assert.equal(element.$$typeof, Symbol.for('react.transitional.element'));
  assert.equal(element.props['data-boil-fps'], 6);
  assert.equal(element.props['data-container-fps'], 30);
  assert.equal(element.props['data-boil-tick'], 0);
  assert.equal(element.props.fill, 'none');
  assert.equal(element.props.stroke, '#161616');
  assert.equal(element.props.strokeWidth, 2);
  assert.equal(element.props.strokeLinecap, 'round');
  assert.equal(Object.hasOwn(element.props, 'filter'), false);
  assert.equal('children' in element, false);

  const markup = renderBoilPathMarkup({
    ...square(8),
    stroke: 'red"><feTurbulence',
    fill: 'none',
  });
  assert.deepEqual(elementNames(markup), ['path']);
  assert.equal(markup.includes('<feTurbulence'), false);
  assert.equal(markup.includes('<feDisplacementMap'), false);
  assert.equal(markup.includes('<filter'), false);
  assert.match(markup, /data-boil-tick="1"/);
  assert.match(markup, /data-boil-fps="6"/);
  assert.equal(markup.includes('stroke="red&quot;&gt;&lt;feTurbulence"'), true);
  assert.equal(markup.startsWith('<path '), true);
  assert.equal(markup.endsWith('/>'), true);

  const source = readFileSync(SOURCE_URL, 'utf8');
  assert.equal(source.includes('feTurbulence'), false);
  assert.equal(source.includes('feDisplacementMap'), false);
  assert.equal(source.includes('Math.random'), false);
  assert.equal(source.includes('<filter'), false);
});

test('boils a frame in under 2 ms and under the 0.5 ms design target', () => {
  const points = [];
  for (let i = 0; i < 60; i += 1) points.push({ x: i * 8, y: (i % 5) * 12 });
  const propsFor = (frame) => ({ points, seed: 'bench', frame, subdivisions: 4 });
  for (let frame = 0; frame < 10; frame += 1) BoilPath(propsFor(frame));
  const frames = 80;
  const started = performance.now();
  for (let frame = 0; frame < frames; frame += 1) renderBoilPathMarkup(propsFor(frame));
  const perFrame = (performance.now() - started) / frames;
  assert.ok(perFrame < 2, `expected < 2 ms/frame, measured ${perFrame.toFixed(4)} ms`);
  assert.ok(perFrame < 0.5, `expected < 0.5 ms/frame, measured ${perFrame.toFixed(4)} ms`);
});

test('rejects degenerate input', () => {
  assert.throws(() => boilTick(Number.NaN), TypeError);
  assert.throws(() => buildBoilGeometry({ points: [{ x: 0, y: 0 }], seed: 'x', frame: 0 }), RangeError);
  assert.throws(
    () =>
      buildBoilGeometry({
        points: [
          { x: 0, y: 0 },
          { x: Number.NaN, y: 1 },
        ],
        seed: 'x',
        frame: 0,
      }),
    TypeError,
  );
  assert.throws(
    () =>
      buildBoilGeometry({
        points: SQUARE,
        seed: 'x',
        frame: 0,
        subdivisions: 0,
      }),
    RangeError,
  );
  assert.throws(() => buildBoilGeometry({ points: SQUARE, seed: Number.POSITIVE_INFINITY, frame: 0 }), TypeError);
});
