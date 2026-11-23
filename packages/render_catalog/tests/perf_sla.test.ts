/**
 * Task 131 SLA. A 10s 1080p30 scene must re-render in under 5s warm and 6.5s
 * cold, with identical PNG hashes at frames 0, 150, and 299, and with zero
 * SVG turbulence in the catalog AST and in the Chromium DOM.
 */

import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test, vi } from "vitest";

vi.mock("react", () => ({
  createContext: (value: unknown) => ({ Provider: "Provider", Consumer: "Consumer", _value: value }),
  createElement: (type: unknown, props?: Record<string, unknown> | null, ...children: unknown[]) => ({
    type,
    props: { ...(props ?? {}), children },
  }),
  useContext: () => null,
  useMemo: (factory: () => unknown) => factory(),
}));

import {
  COLD_BUDGET_MS,
  MOTION_ARCHETYPES,
  SCENE_FRAMES,
  WARM_BUDGET_MS,
  WITNESS_FRAMES,
  installForbiddenRandom,
  runJsBoilBench,
  scanSourceText,
} from "../benchmarks/js_boil_bench.ts";

test("the AST scan counts JSX filters and ignores comments, strings, and regexes", () => {
  const text = [
    "const note = '<feTurbulence /> in a string';",
    "const pattern = /feDisplacementMap/i;",
    "// <feTurbulence /> stays in this comment",
    "const kept = <path d=\"M0 0 L10 10\" />;",
    "const leaked = <feTurbulence type=\"fractalNoise\" />;",
    "const grain = <canvas data-grain=\"paper\" />;",
    "createElement('feDisplacementMap');",
    "createElement('canvas', { className: 'film-grain' });",
  ].join("\n");
  const hits = scanSourceText("fixture.tsx", text);
  const names = hits.map((hit) => `${hit.kind}:${hit.name}:${hit.filmGrain}`).sort();
  expect(names).toEqual([
    "createElement:canvas:true",
    "createElement:feDisplacementMap:false",
    "jsx:canvas:true",
    "jsx:feTurbulence:false",
  ]);
});

test("Math.random throws while the heal bench is measuring", () => {
  const restore = installForbiddenRandom();
  try {
    expect(() => Math.random()).toThrow(/Forbidden/);
  } finally {
    restore();
  }
  expect(Math.random()).toBeGreaterThanOrEqual(0);
});

test("twelve archetype heals stay inside the 5s warm and 6.5s cold budgets", async () => {
  const dir = mkdtempSync(join(tmpdir(), "tc-perf-sla-"));
  const outPath = join(dir, "remotion_js_boil_perf.json");
  const report = await runJsBoilBench({ outPath, concurrency: 4, chromium: true });

  expect(report.schema).toBe("remotion_js_boil_perf.v1");
  expect(report.fps).toBe(30);
  expect(report.boil_fps).toBe(6);
  expect(report.duration_frames).toBe(SCENE_FRAMES);
  expect(report.concurrency).toBe(4);
  expect(report.budgets_ms).toEqual({ warm: WARM_BUDGET_MS, cold: COLD_BUDGET_MS });
  expect(report.fe_turbulence_nodes).toBe(0);
  expect(report.fe_displacement_map_nodes).toBe(0);
  expect(report.film_grain_canvas_nodes).toBe(0);
  expect(report.chromium.fe_turbulence).toBe(0);
  expect(report.chromium.fe_displacement_map).toBe(0);
  expect(report.chromium.canvas).toBe(0);
  expect(report.chromium.film_grain_canvas).toBe(0);
  expect(report.chromium.cold_start_ms).toBeGreaterThan(0);
  expect(report.archetypes.map((row) => row.id)).toEqual(MOTION_ARCHETYPES.map((row) => row.id));
  expect(report.archetypes.map((row) => row.alias)).toEqual([
    "StickmanStage",
    "AudioEvidenceCard",
    "EvidenceDocumentZoom",
    "FoiaFootageFrame",
    "TimelineScrubber",
    "QuotePullout",
    "AnimatedMapRoute",
    "CellTowerTriangulation",
    "CaseBoardSpine",
    "SplitScreenEvidence",
    "EvidenceGridMatrix",
    "ChapterSlateTransition",
  ]);

  for (const row of report.archetypes) {
    expect(row.warm_ms, `${row.id} warm`).toBeLessThan(WARM_BUDGET_MS);
    expect(row.cold_ms, `${row.id} cold`).toBeLessThan(COLD_BUDGET_MS);
    expect(row.nb_frames).toBe(300);
    expect(row.boil_ticks).toBe(60);
    expect(row.boil_hold, row.id).toBe(true);
    expect(row.repeat_hashes_match, row.id).toBe(true);
    expect(row.banned_component_tags, row.id).toEqual([]);
    expect(row.component_tags, row.id).toBeGreaterThan(0);
    expect(row.css_compositor_only).toBe(true);
    for (const frame of WITNESS_FRAMES) {
      expect(row.frame_hashes[String(frame) as "0" | "150" | "299"], `${row.id}#${frame}`).toMatch(/^[0-9a-f]{64}$/);
    }
  }

  expect(report.archetypes.find((row) => row.alias === "AnimatedMapRoute")?.dense_callouts).toBe(25);
  expect(report.archetypes.find((row) => row.id === "CaseBoardSpine")?.dense_pins).toBe(16);
  expect(report.percentiles_ms.warm.p50).toBeLessThan(WARM_BUDGET_MS);
  expect(report.percentiles_ms.warm.p99).toBeLessThan(WARM_BUDGET_MS);
  expect(report.percentiles_ms.cold.p99).toBeLessThan(COLD_BUDGET_MS);
  expect(report.frame_time_histogram_us.reduce((sum, bin) => sum + bin.count, 0)).toBe(12 * 60);
  expect(report.heap_watermark_bytes).toBeGreaterThan(0);
  expect(report.pass).toBe(true);

  const written = JSON.parse(readFileSync(outPath, "utf8")) as { pass: boolean; archetypes: unknown[] };
  expect(written.pass).toBe(true);
  expect(written.archetypes).toHaveLength(12);
}, 180_000);
