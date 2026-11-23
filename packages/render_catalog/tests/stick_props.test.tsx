import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  BoilPath,
  DEFAULT_STICK_BONES,
  EVIDENCE_CRIMSON_HEX,
  FRAME_SAFE_ZONE_1080,
  STICK_PROP_INK,
  STICK_PROP_LIBRARY,
  STICK_PROP_PAPER,
  STICK_PROP_SOCKET,
  StickPropError,
  StickProps,
  boilTick,
  isStickPropId,
  renderStickPropsSvg,
  serializeSvg,
  stickFigureSockets,
  translateStickSockets,
  type StickFacing,
  type StickPropId,
  type StickPropsInput,
  type SvgElement,
} from "../src/rig/StickProps.js";

const SOURCE_URL = new URL("../src/rig/StickProps.tsx", import.meta.url);

function socketsAt(x: number, y: number) {
  return stickFigureSockets(DEFAULT_STICK_BONES, { x, y });
}

function render(props: readonly StickPropId[], extra: Partial<Omit<StickPropsInput, "props">> = {}): SvgElement {
  const input: StickPropsInput = {
    props,
    sockets: extra.sockets ?? socketsAt(960, 700),
    seed: extra.seed ?? "snap",
    frame: extra.frame ?? 0,
  };
  if (extra.facing) input.facing = extra.facing;
  if (extra.ink) input.ink = extra.ink;
  if (extra.paper) input.paper = extra.paper;
  if (extra.safeZone) input.safeZone = extra.safeZone;
  return StickProps(input);
}

function mirrorOf(root: SvgElement): SvgElement {
  const mirror = root.children[0];
  if (!mirror) throw new Error("missing facing mirror");
  return mirror;
}

function propGroup(root: SvgElement, id: StickPropId): SvgElement {
  const found = mirrorOf(root).children.find((child) => child.attrs["data-prop"] === id);
  if (!found) throw new Error(`missing prop ${id}`);
  return found;
}

function pathsOf(group: SvgElement): SvgElement[] {
  return group.children.filter((child) => child.tag === "path");
}

function pathPoints(d: string): Array<[number, number]> {
  const nums = d.match(/-?\d+(?:\.\d+)?/g);
  if (!nums || nums.length % 2 !== 0) throw new Error(`bad path ${d}`);
  const points: Array<[number, number]> = [];
  for (let index = 0; index < nums.length; index += 2) {
    points.push([Number(nums[index]), Number(nums[index + 1])]);
  }
  return points;
}

function outerPoints(group: SvgElement): Array<[number, number]> {
  return pathsOf(group)
    .filter((path) => path.attrs.fill === STICK_PROP_INK)
    .flatMap((path) => pathPoints(path.attrs.d ?? ""));
}

function bounds(points: readonly (readonly [number, number])[]) {
  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function expectCode(run: () => void, code: string): void {
  try {
    run();
    expect.fail(`expected ${code}`);
  } catch (error) {
    expect(error).toBeInstanceOf(StickPropError);
    expect((error as StickPropError).code).toBe(code);
  }
}

describe("stick prop library", () => {
  it("locks the ten silhouette props and their sockets", () => {
    expect(STICK_PROP_LIBRARY).toEqual([
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
    ]);
    expect(isStickPropId("badge")).toBe(true);
    expect(isStickPropId("hat")).toBe(false);
    expect(STICK_PROP_SOCKET.fedora).toBe("crown");
    expect(STICK_PROP_SOCKET.hoodie).toBe("neck");
    expect(STICK_PROP_SOCKET.badge).toBe("chest");
    expect(STICK_PROP_SOCKET.glasses).toBe("brow");
    expect(STICK_PROP_SOCKET.tie).toBe("neck");
    expect(STICK_PROP_SOCKET.scarf).toBe("neck");
    expect(STICK_PROP_SOCKET.briefcase).toBe("hand");
    expect(STICK_PROP_SOCKET.flashlight).toBe("hand");
    expect(STICK_PROP_SOCKET.phone).toBe("hand");
    expect(STICK_PROP_SOCKET.document).toBe("hand");
    expect(FRAME_SAFE_ZONE_1080).toEqual({ top: 108, right: 1920, bottom: 886, left: 0 });
  });

  it("builds idle sockets from the locked bone lengths", () => {
    const sockets = socketsAt(100, 400);
    expect(sockets.torsoAxisX).toBe(100);
    expect(sockets.hip).toEqual({ x: 100, y: 400 });
    expect(sockets.neck.y).toBeCloseTo(400 - DEFAULT_STICK_BONES.torsoLen, 2);
    expect(sockets.headCenter.y).toBeCloseTo(sockets.neck.y - sockets.headRadius * 1.15, 2);
    expect(sockets.crown.y).toBeCloseTo(sockets.headCenter.y - sockets.headRadius, 2);
    expect(sockets.brow.x).toBeGreaterThan(sockets.headCenter.x);
    expect(sockets.brow.y).toBe(sockets.headCenter.y);
    expect(sockets.chest.y).toBeGreaterThan(sockets.neck.y);
    expect(sockets.chest.y).toBeLessThan(sockets.hip.y);
    expect(sockets.hand.x).toBeGreaterThan(sockets.torsoAxisX);
    expect(sockets.hand.y).toBeCloseTo(sockets.shoulder.y + DEFAULT_STICK_BONES.upperArm + DEFAULT_STICK_BONES.forearm, 2);
    expect(sockets.knee.y).toBeCloseTo(sockets.hip.y + DEFAULT_STICK_BONES.thigh, 2);
    expect(sockets.foot.y).toBeCloseTo(sockets.knee.y + DEFAULT_STICK_BONES.shin, 2);
    expect(sockets.crown.y).toBeLessThan(sockets.foot.y);
  });

  it("rejects broken bones and keeps head radius attached to the crown", () => {
    expectCode(() => stickFigureSockets({ ...DEFAULT_STICK_BONES, headRadius: 0 }), "INVALID_BONES");
    expectCode(() => stickFigureSockets({ ...DEFAULT_STICK_BONES, shin: -1 }), "INVALID_BONES");
    expectCode(() => stickFigureSockets({ ...DEFAULT_STICK_BONES, thigh: Number.NaN }), "INVALID_BONES");
    const sockets = socketsAt(0, 0);
    const moved = translateStickSockets(sockets, 12.5, -4);
    expect(moved.torsoAxisX).toBe(12.5);
    expect(moved.headRadius).toBe(sockets.headRadius);
    expect(moved.crown.y - sockets.crown.y).toBeCloseTo(-4, 2);
    expectCode(() => StickProps({ props: ["fedora"], sockets: { ...sockets, headRadius: sockets.headRadius + 5 } }), "INVALID_SOCKET");
    expectCode(
      () => StickProps({ props: ["phone"], sockets: { ...sockets, hand: { x: Number.POSITIVE_INFINITY, y: 0 } } }),
      "INVALID_SOCKET",
    );
    expectCode(() => translateStickSockets(sockets, Number.NaN, 0), "INVALID_SOCKET");
  });

  it("quantizes the boil clock on a 5-frame step", () => {
    expect(boilTick(0)).toBe(0);
    expect(boilTick(4)).toBe(0);
    expect(boilTick(4.9)).toBe(0);
    expect(boilTick(5)).toBe(1);
    expect(boilTick(10)).toBe(2);
    expectCode(() => boilTick(-1), "INVALID_FRAME");
    expectCode(() => boilTick(Number.POSITIVE_INFINITY), "INVALID_FRAME");
  });

  it("draws every prop as crisp BoilPath silhouettes", () => {
    const root = render([...STICK_PROP_LIBRARY]);
    const svg = serializeSvg(root);
    expect(root.attrs["data-component"]).toBe("StickProps");
    expect(root.attrs["data-contract"]).toBe("stick-prop-library-v1");
    expect(root.attrs["data-boil-tick"]).toBe("0");
    expect(mirrorOf(root).children.map((child) => child.attrs["data-prop"])).toEqual([...STICK_PROP_LIBRARY]);
    expect(svg).not.toMatch(/feTurbulence|feDisplacementMap|<filter|filter=/);
    expect(svg.toUpperCase()).not.toContain(EVIDENCE_CRIMSON_HEX);
    const counts: Record<StickPropId, number> = {
      fedora: 2,
      hoodie: 2,
      badge: 2,
      glasses: 3,
      tie: 1,
      scarf: 3,
      briefcase: 2,
      flashlight: 2,
      phone: 3,
      document: 5,
    };
    for (const id of STICK_PROP_LIBRARY) {
      const group = propGroup(root, id);
      const paths = pathsOf(group);
      expect(paths, id).toHaveLength(counts[id]);
      expect(group.attrs["data-socket"]).toBe(STICK_PROP_SOCKET[id]);
      expect(paths.every((path) => path.attrs["data-component"] === "BoilPath")).toBe(true);
      expect(paths.every((path) => path.attrs["data-closed"] === "true")).toBe(true);
      expect(paths.every((path) => path.attrs.stroke === "none")).toBe(true);
      const outers = paths.filter((path) => path.attrs.fill === STICK_PROP_INK);
      const details = paths.filter((path) => path.attrs.fill === STICK_PROP_PAPER);
      expect(outers.length).toBeGreaterThan(0);
      expect(outers.length + details.length).toBe(paths.length);
      for (const path of paths) {
        const points = pathPoints(path.attrs.d ?? "");
        expect(points[0]).toEqual(points[points.length - 1]);
        expect(path.attrs.d?.endsWith(" Z")).toBe(true);
        expect(path.attrs["data-seed"]).toBe(`snap:0:${id}:${path.attrs["data-seed"]?.split(":").at(-1)}`);
      }
      const box = bounds(outerPoints(group));
      const floor = 0.45 * DEFAULT_STICK_BONES.headRadius - 0.05;
      expect(box.maxX - box.minX).toBeGreaterThanOrEqual(floor);
      expect(box.maxY - box.minY).toBeGreaterThanOrEqual(floor);
      expect(box.maxX).toBeGreaterThan(root.attrs["data-torso-axis"] ? Number(root.attrs["data-torso-axis"]) : 0);
    }
  });

  it("snapshots the canonical fedora and badge overlay", () => {
    const svg = renderStickPropsSvg({
      props: ["fedora", "badge"],
      sockets: socketsAt(480, 640),
      seed: "case",
      frame: 0,
      facing: "right",
    });
    expect(svg).toMatchInlineSnapshot(`
      "<g data-component="StickProps" data-contract="stick-prop-library-v1" data-facing="right" data-torso-axis="480" data-boil-tick="0">
        <g data-component="FacingMirror" transform="translate(480 0) scale(1 1) translate(-480 0)">
          <g data-prop="fedora" data-socket="crown" data-slot="0" data-anchor-x="480" data-anchor-y="452.6">
            <path data-component="BoilPath" data-seed="case:0:fedora:silhouette" data-closed="true" d="M 454.8 457.64 L 454.8 451.88 L 462.72 451.16 L 462 430.28 L 477.12 423.8 L 496.56 429.56 L 498.72 451.16 L 538.32 456.2 L 538.32 463.4 L 454.8 462.68 L 454.8 457.64 Z" fill="#1B1B1D" stroke="none"/>
            <path data-component="BoilPath" data-seed="case:0:fedora:band" data-closed="true" d="M 464.88 450.44 L 495.84 450.44 L 495.84 452.6 L 464.88 452.6 L 464.88 450.44 Z" fill="#E9E2D2" stroke="none"/>
          </g>
          <g data-prop="badge" data-socket="chest" data-slot="0" data-anchor-x="480" data-anchor-y="590.5">
            <path data-component="BoilPath" data-seed="case:0:badge:silhouette" data-closed="true" d="M 484.32 567.46 L 490.8 567.46 L 490.8 573.22 L 503.76 573.94 L 506.64 584.74 L 500.88 602.02 L 492.96 611.38 L 485.04 602.02 L 482.16 584.74 L 485.04 573.94 L 484.32 573.22 L 484.32 567.46 Z" fill="#1B1B1D" stroke="none"/>
            <path data-component="BoilPath" data-seed="case:0:badge:stripe" data-closed="true" d="M 486.48 589.06 L 500.16 589.78 L 498.72 594.82 L 487.2 594.1 L 486.48 589.06 Z" fill="#E9E2D2" stroke="none"/>
          </g>
        </g>
      </g>"
    `);
  });

  it("snapshots every outer silhouette path", () => {
    const paths = Object.fromEntries(
      STICK_PROP_LIBRARY.map((id) => {
        const group = propGroup(render([id], { sockets: socketsAt(0, 0), seed: "geo" }), id);
        return [id, pathsOf(group).filter((path) => path.attrs.fill === STICK_PROP_INK).map((path) => path.attrs.d)];
      }),
    );
    expect(paths).toMatchInlineSnapshot(`
      {
        "badge": [
          "M 4.32 -72.54 L 10.8 -72.54 L 10.8 -66.78 L 23.76 -66.06 L 26.64 -55.26 L 20.88 -37.98 L 12.96 -28.62 L 5.04 -37.98 L 2.16 -55.26 L 5.04 -66.06 L 4.32 -66.78 L 4.32 -72.54 Z",
        ],
        "briefcase": [
          "M -11.88 22.96 L 41.4 22.96 L 47.16 31.6 L 47.16 38.08 L 41.4 38.08 L 41.4 55 L -11.88 55 L -11.88 22.96 Z",
          "M 6.84 22.96 L 6.84 6.4 L 11.16 0.64 L 24.12 0.64 L 29.16 4.96 L 29.16 22.96 L 24.12 22.96 L 24.12 10.72 L 11.88 10.72 L 11.88 22.96 L 6.84 22.96 Z",
        ],
        "document": [
          "M -3.6 -8 L 24.12 -8 L 33.48 1.36 L 33.48 42.4 L -3.6 42.4 L -3.6 -8 Z",
        ],
        "fedora": [
          "M -25.2 -182.36 L -25.2 -188.12 L -17.28 -188.84 L -18 -209.72 L -2.88 -216.2 L 16.56 -210.44 L 18.72 -188.84 L 58.32 -183.8 L 58.32 -176.6 L -25.2 -177.32 L -25.2 -182.36 Z",
        ],
        "flashlight": [
          "M -3.6 12.16 L 38.52 12.16 L 38.52 6.4 L 57.6 6.4 L 57.6 28 L 38.52 28 L 38.52 22.24 L -3.6 22.24 L -3.6 12.16 Z",
        ],
        "glasses": [
          "M 25.2 -161.48 L 42.48 -161.48 L 44.64 -154.28 L 42.48 -142.76 L 25.2 -142.76 L 23.04 -151.4 L 25.2 -161.48 Z",
          "M 25.2 -153.56 L -11.88 -150.68 L -11.88 -145.64 L 25.2 -147.8 L 25.2 -153.56 Z",
        ],
        "hoodie": [
          "M -7.2 -57.8 L -12.6 -97.4 L -41.4 -153.2 L -30.6 -192.8 L 3.6 -199.28 L 34.2 -176.6 L 25.2 -117.2 L 14.4 -56 L -7.2 -57.8 Z",
        ],
        "phone": [
          "M 1.8 -3.68 L 4.68 -8 L 26.28 -8 L 29.16 -3.68 L 29.16 39.52 L 26.28 43.84 L 4.68 43.84 L 1.8 39.52 L 1.8 -3.68 Z",
        ],
        "scarf": [
          "M -22.32 -117.92 L 17.28 -120.08 L 19.8 -103.52 L -18 -101.36 L -22.32 -117.92 Z",
          "M 3.6 -105.68 L 12.96 -103.52 L 15.12 -68.6 L 10.8 -51.68 L 4.32 -56.72 L 0.72 -51.68 L -2.16 -66.8 L 0.72 -102.8 L 3.6 -105.68 Z",
          "M -17.28 -107.12 L -7.92 -109.28 L -5.76 -90.2 L -14.4 -81.92 L -20.88 -92.72 L -17.28 -107.12 Z",
        ],
        "tie": [
          "M -7.92 -110 L 10.08 -109.28 L 5.76 -99.2 L 12.24 -70.4 L 0.72 -56.72 L -7.92 -72.2 L -5.76 -99.2 L -7.92 -110 Z",
        ],
      }
    `);
  });

  it("mirrors facing around the torso axis without rewriting asymmetric outlines", () => {
    for (const id of STICK_PROP_LIBRARY) {
      const right = render([id], { facing: "right", sockets: socketsAt(100, 500) });
      const left = render([id], { facing: "left", sockets: socketsAt(100, 500) });
      expect(serializeSvg(propGroup(left, id))).toBe(serializeSvg(propGroup(right, id)));
      expect(mirrorOf(right).attrs.transform).toBe("translate(100 0) scale(1 1) translate(-100 0)");
      expect(mirrorOf(left).attrs.transform).toBe("translate(100 0) scale(-1 1) translate(-100 0)");
      const axis = 100;
      const canonical = outerPoints(propGroup(right, id));
      expect(Math.max(...canonical.map((point) => point[0]))).toBeGreaterThan(axis);
      const mirrored = canonical.map(([x, y]) => [2 * axis - x, y] as const);
      expect(Math.min(...mirrored.map((point) => point[0]))).toBeLessThan(axis);
    }
    const negative = render(["badge"], { sockets: socketsAt(-20, 500), facing: "right" });
    expect(mirrorOf(negative).attrs.transform).toBe("translate(-20 0) scale(1 1) translate(20 0)");
  });

  it("keeps the fedora brim and badge tab asymmetric while the longer side leads", () => {
    const root = render(["fedora", "badge"], { sockets: socketsAt(200, 500) });
    for (const id of ["fedora", "badge"] as const) {
      const points = outerPoints(propGroup(root, id));
      const anchor = Number(propGroup(root, id).attrs["data-anchor-x"]);
      const minX = Math.min(...points.map((point) => point[0]));
      const maxX = Math.max(...points.map((point) => point[0]));
      expect(maxX - anchor).toBeGreaterThan(anchor - minX);
      const mid = (minX + maxX) / 2;
      const symmetric = points.every((point) =>
        points.some((other) => Math.abs(other[0] - (2 * mid - point[0])) < 0.02 && Math.abs(other[1] - point[1]) < 0.02),
      );
      expect(symmetric).toBe(false);
    }
  });

  it("anchors a prop to its socket and separates props that share the hand", () => {
    const sockets = socketsAt(300, 640);
    const fedora = propGroup(render(["fedora"], { sockets }), "fedora");
    expect(Number(fedora.attrs["data-anchor-x"])).toBeCloseTo(sockets.crown.x, 2);
    expect(Number(fedora.attrs["data-anchor-y"])).toBeCloseTo(sockets.crown.y, 2);
    expect(fedora.attrs["data-slot"]).toBe("0");
    const held = ["briefcase", "flashlight", "phone", "document"] as const;
    const together = render(held, { sockets });
    const boxes = held.map((id) => bounds(outerPoints(propGroup(together, id))));
    for (let index = 1; index < boxes.length; index += 1) {
      const previous = boxes[index - 1];
      const current = boxes[index];
      if (!previous || !current) continue;
      expect(current.minX).toBeGreaterThanOrEqual(previous.maxX - 0.05);
    }
    expect(Number(propGroup(together, "flashlight").attrs["data-slot"])).toBe(1);
    expect(Number(propGroup(together, "flashlight").attrs["data-anchor-x"])).toBeCloseTo(
      sockets.hand.x + 2.1 * sockets.headRadius,
      2,
    );
    const flipped = render(["flashlight", "briefcase"], { sockets });
    const flash = bounds(outerPoints(propGroup(flipped, "flashlight")));
    const brief = bounds(outerPoints(propGroup(flipped, "briefcase")));
    expect(brief.minX).toBeGreaterThanOrEqual(flash.maxX - 0.05);
  });

  it("layers neckwear and keeps the boil tick out of the geometry", () => {
    const layered = render(["scarf", "tie", "hoodie", "fedora"]);
    expect(mirrorOf(layered).children.map((child) => child.attrs["data-prop"])).toEqual(["scarf", "tie", "hoodie", "fedora"]);
    const early = render(["phone"], { frame: 4 });
    const next = render(["phone"], { frame: 5 });
    expect(early.attrs["data-boil-tick"]).toBe("0");
    expect(next.attrs["data-boil-tick"]).toBe("1");
    expect(pathsOf(propGroup(early, "phone")).map((path) => path.attrs.d)).toEqual(
      pathsOf(propGroup(next, "phone")).map((path) => path.attrs.d),
    );
    expect(pathsOf(propGroup(next, "phone"))[0]?.attrs["data-seed"]).toContain(":1:phone:");
    expect(renderStickPropsSvg({ props: ["tie"], sockets: socketsAt(1, 2), seed: "same" })).toBe(
      renderStickPropsSvg({ props: ["tie"], sockets: socketsAt(1, 2), seed: "same" }),
    );
  });

  it("leaves path data untouched when the figure already sits inside the safe zone", () => {
    const sockets = socketsAt(960, 700);
    const input = { props: ["fedora", "badge"] as const, sockets, seed: "safe", frame: 0 };
    expect(renderStickPropsSvg({ ...input, safeZone: FRAME_SAFE_ZONE_1080 })).toBe(renderStickPropsSvg(input));
  });

  it("shrinks a prop that barely crosses the safe edge and still mirrors", () => {
    const sockets = socketsAt(400, 500);
    const unscaled = outerPoints(propGroup(render(["flashlight"], { sockets }), "flashlight"));
    const tip = Math.max(...unscaled.map((point) => point[0]));
    const safeZone = { top: -2000, right: tip - 2, bottom: 4000, left: -2000 };
    const right = render(["flashlight"], { sockets, safeZone, facing: "right" });
    const left = render(["flashlight"], { sockets, safeZone, facing: "left" });
    expect(serializeSvg(propGroup(left, "flashlight"))).toBe(serializeSvg(propGroup(right, "flashlight")));
    const fitted = outerPoints(propGroup(right, "flashlight"));
    expect(Math.max(...fitted.map((point) => point[0]))).toBeLessThanOrEqual(safeZone.right + 1e-6);
    const axis = sockets.torsoAxisX;
    const mirroredMin = Math.min(...fitted.map(([x]) => 2 * axis - x));
    expect(mirroredMin).toBeGreaterThanOrEqual(safeZone.left - 1e-6);
    expect(fitted).not.toEqual(unscaled);
  });

  it("refuses a socket or a mirrored socket outside the safe zone, and a clip that would erase the silhouette", () => {
    const base = socketsAt(400, 0);
    const outside = translateStickSockets(base, 0, 50 - base.crown.y);
    const wide = { top: 108, right: 5000, bottom: 5000, left: -5000 };
    expectCode(() => render(["fedora"], { sockets: outside, safeZone: wide }), "SOCKET_OUTSIDE_SAFE_ZONE");
    const edge = socketsAt(10, 500);
    const narrow = { top: -2000, right: 4000, bottom: 4000, left: 0 };
    expectCode(() => render(["flashlight"], { sockets: edge, safeZone: narrow }), "SOCKET_OUTSIDE_SAFE_ZONE");
    const tight = translateStickSockets(base, 0, 112 - base.crown.y);
    expectCode(() => render(["fedora"], { sockets: tight, safeZone: wide }), "SILHOUETTE_UNREADABLE");
  });

  it("rejects unknown, duplicate, and unsafe inputs", () => {
    const sockets = socketsAt(0, 0);
    expectCode(() => StickProps({ props: ["hat" as StickPropId], sockets }), "UNKNOWN_STICK_PROP");
    expectCode(() => StickProps({ props: ["tie", "tie"], sockets }), "DUPLICATE_STICK_PROP");
    expectCode(() => StickProps({ props: "tie" as unknown as StickPropId[], sockets }), "INVALID_INPUT");
    expectCode(() => StickProps({ props: [], sockets, facing: "north" as StickFacing }), "INVALID_FACING");
    expectCode(() => StickProps({ props: [], sockets, frame: -2 }), "INVALID_FRAME");
    expectCode(() => StickProps({ props: [], sockets, seed: "" }), "INVALID_SEED");
    expectCode(() => StickProps({ props: [], sockets, seed: "bad\nseed" }), "INVALID_SEED");
    expectCode(() => StickProps({ props: ["badge"], sockets, ink: "red" }), "INVALID_COLOR");
    expectCode(() => StickProps({ props: ["badge"], sockets, ink: EVIDENCE_CRIMSON_HEX }), "SILHOUETTE_UNREADABLE");
    expectCode(() => StickProps({ props: ["badge"], sockets, paper: "#c92a2a" }), "SILHOUETTE_UNREADABLE");
    expectCode(() => StickProps({ props: [], sockets, safeZone: { top: 10, bottom: 10, left: 0, right: 10 } }), "INVALID_SAFE_ZONE");
    const empty = render([]);
    expect(mirrorOf(empty).children).toEqual([]);
    const escaped = renderStickPropsSvg({ props: ["tie"], sockets, seed: `a<b>&"c` });
    expect(escaped).toContain("a&lt;b&gt;&amp;&quot;c");
    expect(escaped).not.toContain("a<b>");
  });

  it("BoilPath is a crisp closed polyline and refuses crimson or a hairline stroke", () => {
    const path = BoilPath({ points: [[0, 0], [12, 0], [12, 8]], seed: "unit", closed: true, fill: STICK_PROP_INK });
    expect(path.attrs.d).toBe("M 0 0 L 12 0 L 12 8 L 0 0 Z");
    expect(path.attrs["data-component"]).toBe("BoilPath");
    expect(serializeSvg(path)).not.toMatch(/feTurbulence|feDisplacementMap|filter/);
    const open = BoilPath({ points: [[1, 2], [3, 4]], seed: 7, fill: "#3A4F66" });
    expect(open.attrs.d).toBe("M 1 2 L 3 4");
    expect(open.attrs["data-seed"]).toBe("7");
    expectCode(() => BoilPath({ points: [[0, 0], [1, 1]], seed: "x", fill: EVIDENCE_CRIMSON_HEX }), "SILHOUETTE_UNREADABLE");
    expectCode(() => BoilPath({ points: [[0, 0], [8, 0], [8, 8]], seed: "x", fill: STICK_PROP_INK, stroke: STICK_PROP_INK, strokeWidth: 1 }), "SILHOUETTE_UNREADABLE");
    expectCode(() => BoilPath({ points: [[Number.NaN, 0]], seed: "x", fill: STICK_PROP_INK }), "SILHOUETTE_UNREADABLE");
  });

  it("does not reach for filters, clocks, or random jitter in the prop source", () => {
    const source = readFileSync(SOURCE_URL, "utf8");
    expect(source).not.toMatch(/feTurbulence|feDisplacementMap|<filter|Math\.random|Date\.now|performance\.now|fetch\(/);
  });
});
