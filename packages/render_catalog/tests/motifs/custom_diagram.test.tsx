/**
 * Offline zero-spend checks for the sandboxed CustomDiagramScene.
 * Adversarial labels stay escaped SVG text. No network and no paid calls.
 */
import { readFileSync } from "node:fs";

import { expect, test } from "vitest";

import {
  BOIL_FPS,
  CONTENT_HEIGHT,
  CONTENT_INSET_PX,
  CONTENT_WIDTH,
  CustomDiagramError,
  CustomDiagramScene,
  FPS,
  FRAME_HEIGHT,
  FRAME_WIDTH,
  JITTER_AMPLITUDE_PX,
  LABEL_MAX_WORDS,
  MAX_PRIMITIVES,
  MOTIF_COMPONENT,
  SAFE_PADDING_BOTTOM_PX,
  SAFE_PADDING_TOP_PX,
  BoilPath,
  buildBoilGeometry,
  renderCustomDiagramMarkup,
  walkDiagram,
  type CustomDiagramSceneNode,
  type DiagramElement,
  type DiagramPoint,
} from "../../src/motifs/CustomDiagramScene.tsx";

const SOURCE = readFileSync(new URL("../../src/motifs/CustomDiagramScene.tsx", import.meta.url), "utf8");

const SCRIPT_LABEL = "<script>alert(1)</script>";
const BREAKOUT_LABEL = '</text><script>alert(1)</script>';

function rect(x = 40, y = 40, width = 120, height = 70) {
  return { type: "rect" as const, x, y, width, height };
}

function spec(primitives: readonly unknown[], patch: Record<string, unknown> = {}) {
  return {
    seed: "case127",
    frame: 0,
    primitives,
    ...patch,
  };
}

function scene(primitives: readonly unknown[], patch: Record<string, unknown> = {}): CustomDiagramSceneNode {
  return CustomDiagramScene(spec(primitives, patch));
}

function tags(markup: string): string[] {
  return [...markup.matchAll(/<\/?([A-Za-z][\w:.-]*)\b/g)].map((match) => match[1] ?? "");
}

function textNodes(root: DiagramElement): DiagramElement[] {
  return walkDiagram(root).filter((node) => node.type === "text");
}

function slot(root: DiagramElement, name: string): DiagramElement {
  const found = walkDiagram(root).find((node) => node.props["data-slot"] === name);
  if (!found) throw new Error(`missing slot ${name}`);
  return found;
}

test("provider keys stay unset and outbound fetch is blocked", async () => {
  expect(process.env.GEMINI_API_KEY).toBeUndefined();
  expect(process.env.DEEPSEEK_API_KEY).toBeUndefined();
  expect(process.env.ELEVENLABS_API_KEY).toBeUndefined();
  await expect(fetch("https://example.com/custom-diagram")).rejects.toThrow(/ZERO_SPEND_GUARD/);
});

test("an untrusted script string in a label is an escaped SVG text node", () => {
  let evalCalls = 0;
  const previousEval = globalThis.eval;
  globalThis.eval = ((code: string) => {
    evalCalls += 1;
    return previousEval(code);
  }) as typeof globalThis.eval;

  try {
    const rendered = scene([
      { type: "label", x: 40, y: 48, text: SCRIPT_LABEL },
      { type: "label", x: 40, y: 120, text: BREAKOUT_LABEL },
      { type: "label", x: 40, y: 190, text: 'a&b<c>"d' },
    ]);
    expect(evalCalls).toBe(0);
    expect(rendered.texts).toEqual([SCRIPT_LABEL, BREAKOUT_LABEL, 'a&b<c>"d']);
    expect(rendered.primitiveCount).toBe(3);

    const nodes = textNodes(rendered);
    expect(nodes).toHaveLength(3);
    expect(nodes.map((node) => node.type)).toEqual(["text", "text", "text"]);
    expect(nodes.map((node) => node.props.children)).toEqual(rendered.texts);
    expect(nodes.every((node) => node.props["data-text-node"] === "svg-text")).toBe(true);
    expect(walkDiagram(rendered).some((node) => node.type === ("script" as "text"))).toBe(false);

    const markup = renderCustomDiagramMarkup(spec(rendered.texts.map((text, index) => ({
      type: "label",
      x: 40,
      y: 48 + index * 72,
      text,
    }))));
    expect(markup).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(markup).toContain("&lt;/text&gt;&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(markup).toContain("a&amp;b&lt;c&gt;");
    expect(markup.includes("<script")).toBe(false);
    expect(markup.includes("</script")).toBe(false);
    expect(markup.match(/<text\b/g)).toHaveLength(3);
    expect(markup.match(/<\/text>/g)).toHaveLength(3);
    expect(tags(markup).every((tag) => ["div", "svg", "path", "text"].includes(tag))).toBe(true);
    expect(markup.includes("href=")).toBe(false);
    expect(markup.includes("javascript:")).toBe(false);

    const json = JSON.stringify(spec([{ type: "label", x: 40, y: 48, text: SCRIPT_LABEL }]));
    const fromJson = CustomDiagramScene(json);
    expect(fromJson.texts).toEqual([SCRIPT_LABEL]);
    expect(renderCustomDiagramMarkup(json).includes("<script")).toBe(false);
    expect(fromJson.texts[0]).toBe(SCRIPT_LABEL);

    const urlText = "javascript:alert(1)";
    const urlScene = scene([{ type: "label", x: 40, y: 48, text: urlText }]);
    const urlMarkup = renderCustomDiagramMarkup(spec([{ type: "label", x: 40, y: 48, text: urlText }]));
    expect(urlScene.texts).toEqual([urlText]);
    expect(textNodes(urlScene)[0]?.props.children).toBe(urlText);
    expect(urlMarkup.includes("href=")).toBe(false);
    expect(urlMarkup.includes(urlText)).toBe(true);
    expect(urlMarkup.includes("<script")).toBe(false);
  } finally {
    globalThis.eval = previousEval;
  }
});

test("structural script, handlers, and extra keys are rejected before render", () => {
  const attacks: unknown[] = [
    spec([{ type: "script", text: "alert(1)" }]),
    spec([{ type: "foreignObject", x: 10, y: 10 }]),
    spec([{ type: "iframe", src: "https://example.test" }]),
    spec([{ type: "image", href: "https://example.test/a.png" }]),
    spec([{ type: "use", href: "#payload" }]),
    spec([{ type: "Illustrative2KPanZoom" }]),
    spec([{ ...rect(), onClick: "alert(1)" }]),
    spec([{ ...rect(), onerror: "alert(1)" }]),
    spec([{ ...rect(), href: "javascript:alert(1)" }]),
    spec([{ type: "label", x: 40, y: 48, text: "ok", dangerouslySetInnerHTML: { __html: SCRIPT_LABEL } }]),
    spec([{ type: "label", x: 40, y: 48, text: "ok", html: SCRIPT_LABEL }]),
    spec([rect()], { html: SCRIPT_LABEL }),
    spec([rect()], { code: "alert(1)" }),
    "<script>alert(1)</script>",
    JSON.stringify(SCRIPT_LABEL),
    spec([{ type: "label", x: 40, y: 48, text: "one two three four five six seven eight nine ten eleven twelve thirteen" }]),
    spec([{ type: "label", x: 40, y: 48, text: "bad\u0000byte" }]),
    spec([{ type: "rect", x: "40", y: 40, width: 20, height: 20 }]),
    spec([rect()], { isEndScreen: "true" }),
    spec([rect()], { frame: 1.5 }),
    spec([rect()], { seed: "eval(1)" }),
    spec([rect()], { seed: "<script>" }),
    spec([{ type: "label", x: 40, y: 48, text: "javascript:alert(1)", href: "javascript:alert(1)" }]),
  ];

  for (const attack of attacks) {
    expect(() => CustomDiagramScene(attack)).toThrow(CustomDiagramError);
    expect(() => renderCustomDiagramMarkup(attack)).toThrow(CustomDiagramError);
  }

  expect(() => CustomDiagramScene(spec([{ type: "script", text: "alert(1)" }]))).toThrow(/rejected primitive type script/);
  expect(() => CustomDiagramScene(spec([{ ...rect(), onClick: "alert(1)" }]))).toThrow(/rejected handler onClick/);
  expect(() => CustomDiagramScene(spec([{ ...rect(), href: "javascript:alert(1)" }]))).toThrow(/href/);
  expect(() => scene([{ type: "label", x: 40, y: 48, text: "one two three four five six seven eight nine ten eleven twelve thirteen" }])).toThrow(
    /12 words/,
  );

  const dozen = "one two three four five six seven eight nine ten eleven twelve";
  expect(dozen.split(/\s+/)).toHaveLength(LABEL_MAX_WORDS);
  const dozenScene = scene([{ type: "label", x: 40, y: 48, text: dozen }]);
  expect(dozenScene.texts).toEqual([dozen]);

  const proto = '{"seed":"case127","frame":0,"primitives":[],"__proto__":{"pwned":true}}';
  expect(() => CustomDiagramScene(proto)).toThrow(/rejected key __proto__/);
  expect(({} as { pwned?: boolean }).pwned).toBeUndefined();

  const constructorPayload = '{"seed":"case127","frame":0,"primitives":[],"constructor":{"prototype":{"pwned":true}}}';
  expect(() => CustomDiagramScene(constructorPayload)).toThrow(/rejected key constructor/);

  const trapped: { seed: string; frame: number; primitives: unknown[] } = {
    seed: "case127",
    frame: 0,
    primitives: [rect()],
  };
  Object.defineProperty(trapped, "code", {
    enumerable: true,
    get() {
      throw new Error("getter ran");
    },
  });
  expect(() => CustomDiagramScene(trapped)).toThrow(/rejected accessor code/);

  expect(() =>
    CustomDiagramScene({
      seed: "case127",
      frame: 0,
      primitives: [function scripted() { return 1; }],
    }),
  ).toThrow(/not JSON data/);

  let nested: unknown = { x: 40, y: 40 };
  for (let depth = 0; depth < 12; depth += 1) nested = { box: nested };
  expect(() => CustomDiagramScene({ seed: "case127", frame: 0, primitives: [nested] })).toThrow(/too deep/);
});

test("shapes and arrows boil inside the safe zone, capped at 25 primitives", () => {
  expect(MAX_PRIMITIVES).toBe(25);
  expect(FRAME_WIDTH).toBe(1920);
  expect(FRAME_HEIGHT).toBe(1080);
  expect(CONTENT_WIDTH).toBe(1920);
  expect(CONTENT_HEIGHT).toBe(778);
  expect(SAFE_PADDING_TOP_PX).toBe(108);
  expect(SAFE_PADDING_BOTTOM_PX).toBe(194);
  expect(FPS).toBe(30);
  expect(BOIL_FPS).toBe(6);

  const rendered = scene(
    [
      rect(),
      { type: "ellipse", cx: 360, cy: 120, rx: 50, ry: 30 },
      { type: "line", x1: 80, y1: 220, x2: 260, y2: 220 },
      {
        type: "polyline",
        points: [
          { x: 80, y: 280 },
          { x: 140, y: 250 },
          { x: 220, y: 300 },
        ],
      },
      {
        type: "polygon",
        points: [
          { x: 420, y: 240 },
          { x: 520, y: 240 },
          { x: 470, y: 320 },
        ],
      },
      { type: "arrow", from: { x: 80, y: 420 }, to: { x: 280, y: 460 } },
      { type: "label", x: 80, y: 520, text: "exhibit A" },
    ],
    { frame: 4, isEndScreen: true },
  );

  expect(rendered.props["data-motif"]).toBe(MOTIF_COMPONENT);
  expect(rendered.props["data-safe-zone"]).toBe("css-contained");
  expect(rendered.props["data-code-execution"]).toBe("0");
  expect(rendered.props["data-end-screen"]).toBe("true");
  expect(rendered.props["data-layer"]).toBe("4");
  expect(rendered.props["data-owner"]).toBe("render_catalog");
  expect(rendered.props.style).toMatchObject({
    width: 1920,
    height: 1080,
    paddingTop: 108,
    paddingBottom: 194,
    overflow: "hidden",
    display: "grid",
    background: "#E9E2D2",
  });
  expect(rendered.tick).toBe(0);
  expect(rendered.props["data-boil-tick"]).toBe("0");
  expect(rendered.primitiveCount).toBe(7);

  const content = slot(rendered, "content");
  expect(content.props.style).toMatchObject({ overflow: "hidden", width: "100%", height: "100%" });
  const diagram = slot(rendered, "diagram");
  expect(diagram.type).toBe("svg");
  expect(diagram.props.width).toBe(1920);
  expect(diagram.props.height).toBe(778);
  expect(diagram.props.viewBox).toBe("0 0 1920 778");

  const exclusion = walkDiagram(rendered).find((node) => node.props["data-exclusion"] === "bottom-right");
  if (!exclusion) throw new Error("missing exclusion box");
  expect(exclusion.props.style).toMatchObject({ width: "22%", height: "14%", overflow: "hidden" });
  const mask = walkDiagram(rendered).find((node) => node.props["data-mask"] === "end-screen-card");
  if (!mask) throw new Error("missing end-screen mask");
  expect(mask.props.style).toMatchObject({ right: "22%", bottom: 194, overflow: "hidden" });
  expect(mask.props.children).toBeUndefined();

  expect(rendered.strokes.length).toBeGreaterThanOrEqual(7);
  for (const stroke of rendered.strokes) {
    const direct = BoilPath({
      points: stroke.points,
      seed: stroke.seed,
      frame: 4,
      closed: stroke.closed,
      strokeWidth: stroke.role === "underline" ? 2 : 3,
    });
    expect(direct.type).toBe("path");
    expect(direct.props.d).toBe(stroke.d);
    expect(direct.props["data-boil-fps"]).toBe(6);
    expect(direct.props["data-container-fps"]).toBe(30);
    expect(direct.props["data-boil-tick"]).toBe(0);
    expect(Object.hasOwn(direct.props, "filter")).toBe(false);
    expect(direct.props.children).toBeUndefined();
    expect(stroke.closed ? stroke.d.endsWith("Z") : stroke.d.endsWith("Z")).toBe(stroke.closed);

    const geometry = buildBoilGeometry({
      points: stroke.points,
      seed: stroke.seed,
      frame: 4,
      closed: stroke.closed,
    });
    expect(geometry.d).toBe(stroke.d);
    geometry.vertices.forEach((vertex, index) => {
      const origin = originPoint(stroke.points, stroke.closed, index);
      const distance = Math.hypot(vertex.x - origin.x, vertex.y - origin.y);
      expect(distance).toBeLessThanOrEqual(JITTER_AMPLITUDE_PX + 1e-9);
      expect(vertex.x).toBeGreaterThanOrEqual(CONTENT_INSET_PX - JITTER_AMPLITUDE_PX - 1e-6);
      expect(vertex.y).toBeGreaterThanOrEqual(CONTENT_INSET_PX - JITTER_AMPLITUDE_PX - 1e-6);
      expect(vertex.x).toBeLessThanOrEqual(CONTENT_WIDTH - CONTENT_INSET_PX + JITTER_AMPLITUDE_PX + 1e-6);
      expect(vertex.y).toBeLessThanOrEqual(CONTENT_HEIGHT - CONTENT_INSET_PX + JITTER_AMPLITUDE_PX + 1e-6);
    });
    if (stroke.closed) {
      const first = stroke.points[0];
      const last = stroke.points[stroke.points.length - 1];
      const start = geometry.vertices[0];
      const end = geometry.vertices[stroke.points.length - 1];
      if (!first || !last || !start || !end) throw new Error("missing stroke endpoints");
      expect(end.x - last.x).toBeCloseTo(start.x - first.x, 6);
      expect(end.y - last.y).toBeCloseTo(start.y - first.y, 6);
      expect(geometry.vertices[0]).toEqual(geometry.vertices[geometry.vertices.length - 1]);
    }
  }

  const roles = rendered.strokes.filter((stroke) => stroke.type === "arrow").map((stroke) => stroke.role);
  expect(roles).toEqual(["shaft", "head"]);
  expect(rendered.texts).toEqual(["exhibit A"]);

  const held = scene([rect()], { frame: 0 });
  const still = scene([rect()], { frame: 4 });
  const next = scene([rect()], { frame: 5 });
  expect(held.strokes[0]?.d).toBe(still.strokes[0]?.d);
  expect(held.strokes[0]?.d).not.toBe(next.strokes[0]?.d);
  expect(next.tick).toBe(1);
  expect(CustomDiagramScene(spec([rect()])).strokes).toEqual(held.strokes);

  const grid = Array.from({ length: 25 }, (_, index) => rect(20 + (index % 5) * 50, 20 + Math.floor(index / 5) * 50, 24, 24));
  const full = scene(grid);
  expect(full.primitiveCount).toBe(25);
  expect(full.strokes).toHaveLength(25);
  expect(() => scene([...grid, rect(400, 400, 20, 20)])).toThrow(/at most 25 primitives/);

  expect(() => scene([rect(40, 760, 30, 30)])).toThrow(/safe zone/);
  expect(() => scene([{ type: "arrow", from: { x: 8, y: 8 }, to: { x: 20, y: 8 } }])).toThrow(CustomDiagramError);
  expect(() => scene([])).not.toThrow();
  const empty = scene([]);
  expect(empty.primitiveCount).toBe(0);
  expect(empty.strokes).toEqual([]);
  expect(empty.texts).toEqual([]);
  expect(slot(empty, "diagram").type).toBe("svg");

  const markup = renderCustomDiagramMarkup(spec([
    rect(),
    { type: "arrow", from: { x: 80, y: 200 }, to: { x: 240, y: 200 } },
    { type: "label", x: 40, y: 48, text: SCRIPT_LABEL },
  ]));
  expect(markup.includes("<script")).toBe(false);
  expect(markup.includes("feTurbulence")).toBe(false);
  expect(markup.includes("feDisplacementMap")).toBe(false);
  expect(markup.includes("#C92A2A")).toBe(false);
  expect(tags(markup).includes("path")).toBe(true);
  expect(tags(markup).includes("text")).toBe(true);
});

test("the module does not call eval, build functions, or emit turbulence", () => {
  expect(/\beval\s*\(/.test(SOURCE)).toBe(false);
  expect(/\bnew\s+Function\b/.test(SOURCE)).toBe(false);
  expect(SOURCE.includes("Function(")).toBe(false);
  expect(SOURCE.includes("dangerouslySetInnerHTML")).toBe(false);
  expect(SOURCE.includes("innerHTML")).toBe(false);
  expect(SOURCE.includes("outerHTML")).toBe(false);
  expect(SOURCE.includes("document.write")).toBe(false);
  expect(SOURCE.includes("import(")).toBe(false);
  expect(SOURCE.includes("Math.random")).toBe(false);
  expect(SOURCE.includes("#C92A2A")).toBe(false);
  expect(SOURCE.includes("fe" + "Turbulence")).toBe(false);
  expect(SOURCE.includes("fe" + "DisplacementMap")).toBe(false);
  expect(SOURCE.includes("function SafeZoneLayout")).toBe(true);
  expect(SOURCE.includes("function BoilPath")).toBe(true);
  expect(SOURCE.includes("function CustomDiagramScene")).toBe(true);
  expect(SOURCE.includes("<SafeZoneLayout")).toBe(false);
  expect(SOURCE.includes("<BoilPath")).toBe(false);
});

function originPoint(points: readonly DiagramPoint[], closed: boolean, index: number): DiagramPoint {
  if (closed && index === points.length) {
    const first = points[0];
    if (!first) throw new Error("missing first point");
    return first;
  }
  const point = points[index];
  if (!point) throw new Error(`missing point ${index}`);
  return point;
}
