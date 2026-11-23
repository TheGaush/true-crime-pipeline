/**
 * Task 104 geometry tests.
 *
 * Task 103's `LineBoilPath.tsx` is not on this branch. The rig imports it.
 * These tests substitute that binding while loading the real solver, so the
 * suite stays offline and does not vendor BoilPath.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { describe, expect, it } from "vitest";

const require = createRequire(import.meta.url);
const ts = require("typescript") as typeof import("typescript");

interface Point {
  x: number;
  y: number;
}

interface Bone {
  id: string;
  ratio: RatioName;
  points: Point[];
  closed: boolean;
}

type RatioName = "headRadius" | "torsoLen" | "upperArm" | "forearm" | "thigh" | "shin";

interface Solved {
  requestedScale: number;
  appliedScale: number;
  anchor: Point;
  facing: "left" | "right";
  head: { center: Point; radius: number };
  bones: Bone[];
  sockets: Record<string, Point>;
  safeRect: { left: number; top: number; right: number; bottom: number };
  isEndScreen: boolean;
}

interface StickNode {
  $$typeof: symbol;
  type: unknown;
  key: string | null;
  props: {
    children: Array<{ type: unknown; key: string | null; props: Record<string, unknown> }>;
    [key: string]: unknown;
  };
  solved: Solved;
}

interface GeometryModule {
  LOCKED_BONE_RATIOS: Record<RatioName, number>;
  SOCKET_IDS: readonly string[];
  BONE_IDS: readonly string[];
  HEAD_SEGMENTS: number;
  STICK_STROKE_PX: number;
  SAFE_PADDING_TOP: number;
  SAFE_PADDING_BOTTOM: number;
  boneSeed: (seed: number, boneId: string) => number;
  separateFromRect: (
    bounds: { minX: number; maxX: number; minY: number; maxY: number },
    obstacle: { left: number; top: number; right: number; bottom: number },
  ) => Point;
  endScreenExclusionRect: () => { left: number; top: number; right: number; bottom: number };
  solveStickFigure: (props: Record<string, unknown>) => Solved;
  StickFigureGeometry: (props: Record<string, unknown>) => StickNode;
}

const SOURCE_URL = new URL("../src/rig/StickFigureGeometry.tsx", import.meta.url);
const SOURCE = readFileSync(SOURCE_URL, "utf8");

function loadGeometry(boilPath: () => never): GeometryModule {
  const matched = SOURCE.match(
    /import\s*\{\s*BoilPath\s*\}\s*from\s*["']\.\/LineBoilPath\.js["'];?/,
  );
  if (!matched) {
    throw new Error("StickFigureGeometry must import { BoilPath } from ./LineBoilPath.js");
  }
  const rewritten = SOURCE.replace(matched[0], "");
  const printed = ts.transpileModule(rewritten, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: "StickFigureGeometry.tsx",
  }).outputText;
  const exports: Record<string, unknown> = {};
  const runner = new Function("BoilPath", "exports", printed) as (
    boilPath: () => never,
    exports: Record<string, unknown>,
  ) => void;
  runner(boilPath, exports);
  return exports as unknown as GeometryModule;
}

const BoilPath = (() => {
  throw new Error("BoilPath is a React element type and must not be called");
}) as () => never;

const geometry = loadGeometry(BoilPath);

const RATIOS = ["headRadius", "torsoLen", "upperArm", "forearm", "thigh", "shin"] as const;

function zeros(): Record<string, number> {
  return {
    torsoDeg: 0,
    headDeg: 0,
    upperArmLeftDeg: 0,
    forearmLeftDeg: 0,
    upperArmRightDeg: 0,
    forearmRightDeg: 0,
    thighLeftDeg: 0,
    shinLeftDeg: 0,
    thighRightDeg: 0,
    shinRightDeg: 0,
  };
}

function hypot(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function lcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(1664525, state) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function assertContained(solved: Solved): void {
  const { safeRect, head, sockets } = solved;
  expect(head.center.y - head.radius).toBeGreaterThanOrEqual(safeRect.top - 1e-6);
  expect(head.center.y + head.radius).toBeLessThanOrEqual(safeRect.bottom + 1e-6);
  expect(head.center.x - head.radius).toBeGreaterThanOrEqual(safeRect.left - 1e-6);
  expect(head.center.x + head.radius).toBeLessThanOrEqual(safeRect.right + 1e-6);
  for (const point of Object.values(sockets)) {
    expect(point.x).toBeGreaterThanOrEqual(safeRect.left - 1e-6);
    expect(point.x).toBeLessThanOrEqual(safeRect.right + 1e-6);
    expect(point.y).toBeGreaterThanOrEqual(safeRect.top - 1e-6);
    expect(point.y).toBeLessThanOrEqual(safeRect.bottom + 1e-6);
  }
  const exclusion = geometry.endScreenExclusionRect();
  for (const point of Object.values(sockets)) {
    const inside =
      point.x > exclusion.left &&
      point.x < exclusion.right &&
      point.y > exclusion.top &&
      point.y < exclusion.bottom;
    expect(inside).toBe(false);
  }
}

function assertLengths(solved: Solved): void {
  expect(solved.appliedScale).toBeGreaterThan(0);
  expect(solved.appliedScale).toBeLessThanOrEqual(solved.requestedScale + 1e-9);
  for (const bone of solved.bones) {
    const expected = geometry.LOCKED_BONE_RATIOS[bone.ratio] * solved.appliedScale;
    if (bone.closed) {
      expect(bone.points[0]).toEqual(bone.points[bone.points.length - 1]);
      for (const point of bone.points) {
        expect(hypot(point, solved.head.center)).toBeCloseTo(expected, 5);
      }
    } else {
      expect(bone.points).toHaveLength(2);
      const start = bone.points[0];
      const end = bone.points[1];
      if (!start || !end) throw new Error(`missing endpoints for ${bone.id}`);
      expect(hypot(start, end)).toBeCloseTo(expected, 5);
    }
  }
}

describe("stick figure geometry", () => {
  it("imports Task 103 BoilPath instead of copying the boil", () => {
    expect(SOURCE).toMatch(/import\s*\{\s*BoilPath\s*\}\s*from\s*["']\.\/LineBoilPath\.js["']/);
    expect(SOURCE.includes("feTurbulence")).toBe(false);
    expect(SOURCE.includes("feDisplacementMap")).toBe(false);
    expect(SOURCE.includes("LineBoilPath.tsx")).toBe(false);
    expect(Object.keys(geometry.LOCKED_BONE_RATIOS).sort()).toEqual([...RATIOS].sort());
    for (const name of RATIOS) {
      expect(geometry.LOCKED_BONE_RATIOS[name]).toBeGreaterThan(0);
    }
    expect(Object.isFrozen(geometry.LOCKED_BONE_RATIOS)).toBe(true);
  });

  it("renders every bone through BoilPath elements inside the safe zone", () => {
    const node = geometry.StickFigureGeometry({
      x: 960,
      y: 540,
      scale: 1,
      seed: 7,
      frame: 11,
      joints: zeros(),
    });
    expect(node.$$typeof).toBe(Symbol.for("react.element"));
    expect(node.type).toBe("g");
    expect(node.props["data-stick-figure"]).toBe("true");
    expect(node.props.children).toHaveLength(geometry.BONE_IDS.length);
    expect(JSON.stringify(node.props)).not.toContain("feTurbulence");
    expect(JSON.stringify(node.props)).not.toContain("#");
    const seenSeeds = new Set<number>();
    node.props.children.forEach((child, index) => {
      const bone = node.solved.bones[index];
      if (!bone) throw new Error(`missing bone ${index}`);
      expect(child.type).toBe(BoilPath);
      expect(child.key).toBe(bone.id);
      expect(child.props.points).toBe(bone.points);
      expect(child.props.closed).toBe(bone.closed);
      expect(child.props.frame).toBe(11);
      expect(child.props.strokeWidth).toBe(geometry.STICK_STROKE_PX);
      expect(child.props.stroke).toBe("currentColor");
      expect(child.props.fill).toBe("none");
      expect(child.props.seed).toBe(geometry.boneSeed(7, bone.id));
      seenSeeds.add(child.props.seed as number);
    });
    expect(seenSeeds.size).toBe(geometry.BONE_IDS.length);
    const head = node.solved.bones.find((bone) => bone.id === "head");
    expect(head?.closed).toBe(true);
    expect(head?.points).toHaveLength(geometry.HEAD_SEGMENTS + 1);
    expect(node.solved.anchor).toEqual({ x: 960, y: 540 });
    expect(node.solved.appliedScale).toBe(1);
    assertLengths(node.solved);
    assertContained(node.solved);
    for (const id of geometry.SOCKET_IDS) {
      expect(node.solved.sockets[id]).toBeDefined();
    }
  });

  it("keeps absolute lengths when only the joint angles change", () => {
    const base = { x: 960, y: 540, scale: 1.25, facing: "right" as const, joints: zeros() };
    const bent = geometry.solveStickFigure({
      ...base,
      joints: { ...zeros(), upperArmRightDeg: -70, forearmRightDeg: 40, thighLeftDeg: 25, headDeg: -15 },
    });
    const straight = geometry.solveStickFigure(base);
    expect(bent.appliedScale).toBe(straight.appliedScale);
    expect(bent.anchor).toEqual(straight.anchor);
    for (const bone of straight.bones) {
      const other = bent.bones.find((candidate) => candidate.id === bone.id);
      if (!other) throw new Error(`missing ${bone.id}`);
      expect(other.ratio).toBe(bone.ratio);
      if (bone.closed) {
        expect(other.points).toHaveLength(bone.points.length);
      } else {
        const a0 = bone.points[0];
        const a1 = bone.points[1];
        const b0 = other.points[0];
        const b1 = other.points[1];
        if (!a0 || !a1 || !b0 || !b1) throw new Error(`missing endpoints for ${bone.id}`);
        expect(hypot(b0, b1)).toBeCloseTo(hypot(a0, a1), 6);
      }
    }
  });

  it("clamps a head that enters the top 10%", () => {
    const solved = geometry.solveStickFigure({ x: 960, y: 100, scale: 1, joints: zeros() });
    expect(solved.anchor.y).toBeGreaterThan(100);
    expect(solved.head.center.y - solved.head.radius).toBeCloseTo(geometry.SAFE_PADDING_TOP, 6);
    expect(solved.appliedScale).toBe(1);
    assertLengths(solved);
    assertContained(solved);
  });

  it("clamps a head that enters the bottom 18%", () => {
    const solved = geometry.solveStickFigure({
      x: 960,
      y: 800,
      scale: 1,
      joints: { ...zeros(), torsoDeg: 180 },
    });
    const safeBottom = 1080 - geometry.SAFE_PADDING_BOTTOM;
    expect(solved.head.center.y + solved.head.radius).toBeCloseTo(safeBottom, 6);
    expect(solved.anchor.y).toBeLessThan(800);
    expect(solved.appliedScale).toBe(1);
    assertLengths(solved);
    assertContained(solved);
  });

  it("shrinks scale when the figure cannot fit, and keeps the ratios", () => {
    const solved = geometry.solveStickFigure({
      x: 960,
      y: 540,
      scale: 1_000_000,
      joints: zeros(),
    });
    expect(solved.appliedScale).toBeLessThan(solved.requestedScale);
    expect(solved.appliedScale).toBeGreaterThan(1);
    assertLengths(solved);
    assertContained(solved);
    const again = geometry.solveStickFigure({
      x: 960,
      y: 540,
      scale: 1_000_000,
      joints: zeros(),
    });
    expect(again).toEqual(solved);
  });

  it("mirrors facing without changing bone length", () => {
    const joints = { ...zeros(), upperArmRightDeg: -90, forearmRightDeg: 0 };
    const right = geometry.solveStickFigure({ x: 960, y: 540, scale: 1, facing: "right", joints });
    const left = geometry.solveStickFigure({ x: 960, y: 540, scale: 1, facing: "left", joints });
    expect(right.anchor).toEqual({ x: 960, y: 540 });
    expect(left.anchor).toEqual(right.anchor);
    expect(left.appliedScale).toBe(right.appliedScale);
    expect(right.sockets.handRight.x).toBeGreaterThan(right.anchor.x);
    expect(left.sockets.handRight.x).toBeLessThan(left.anchor.x);
    expect(right.sockets.handRight.x - right.anchor.x).toBeCloseTo(
      -(left.sockets.handRight.x - left.anchor.x),
      6,
    );
    expect(hypot(right.sockets.elbowRight, right.sockets.handRight)).toBeCloseTo(
      hypot(left.sockets.elbowRight, left.sockets.handRight),
      6,
    );
    assertLengths(right);
    assertLengths(left);
  });

  it("keeps geometry frame-invariant and forwards the frame to BoilPath", () => {
    const early = geometry.StickFigureGeometry({ x: 960, y: 540, frame: 0, seed: 3, joints: zeros() });
    const later = geometry.StickFigureGeometry({ x: 960, y: 540, frame: 4, seed: 3, joints: zeros() });
    expect(later.solved.bones).toEqual(early.solved.bones);
    for (const child of later.props.children) expect(child.props.frame).toBe(4);
    for (const child of early.props.children) expect(child.props.frame).toBe(0);
  });

  it("rejects non-finite placement and a non-positive scale", () => {
    expect(() => geometry.solveStickFigure({ x: Number.NaN, y: 0 })).toThrow(/finite/);
    expect(() => geometry.solveStickFigure({ x: 0, y: Number.POSITIVE_INFINITY })).toThrow(/finite/);
    expect(() => geometry.solveStickFigure({ x: 0, y: 0, scale: 0 })).toThrow(/scale/);
    expect(() => geometry.solveStickFigure({ x: 0, y: 0, scale: -2 })).toThrow(/scale/);
    expect(() => geometry.solveStickFigure({ x: 0, y: 0, facing: "up" })).toThrow(/facing/);
    expect(() => geometry.solveStickFigure({ x: 0, y: 0, joints: { torsoDeg: Number.NaN } })).toThrow(
      /torsoDeg/,
    );
  });

  it("pushes bounds out of the end-screen rectangle", () => {
    const exclusion = geometry.endScreenExclusionRect();
    expect(exclusion.left).toBeCloseTo(1920 * 0.78, 6);
    expect(exclusion.top).toBeCloseTo(1080 * 0.86, 6);
    const push = geometry.separateFromRect(
      { minX: exclusion.left - 10, maxX: exclusion.left + 40, minY: exclusion.top + 5, maxY: exclusion.bottom },
      exclusion,
    );
    expect(push.x).toBeLessThan(0);
    expect(push.y).toBe(0);
    const clear = geometry.separateFromRect(
      { minX: 0, maxX: 10, minY: 0, maxY: 10 },
      exclusion,
    );
    expect(clear).toEqual({ x: 0, y: 0 });
  });

  it("holds the bone-length invariant across 100 random joint configurations", () => {
    const random = lcg(104);
    const jointNames = Object.keys(zeros());
    for (let sample = 0; sample < 100; sample += 1) {
      const joints: Record<string, number> = {};
      for (const name of jointNames) joints[name] = random() * 360 - 180;
      const solved = geometry.solveStickFigure({
        x: random() * 2400 - 200,
        y: random() * 1400 - 200,
        scale: 0.2 + random() * 8,
        facing: random() < 0.5 ? "left" : "right",
        isEndScreen: random() < 0.5,
        joints,
        seed: sample,
        frame: sample,
      });
      assertLengths(solved);
      assertContained(solved);
      expect(solved.bones.map((bone) => bone.id)).toEqual([...geometry.BONE_IDS]);
    }
  });
});
