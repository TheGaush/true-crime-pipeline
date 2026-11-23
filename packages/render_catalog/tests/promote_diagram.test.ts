import { mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import ts from "typescript";
import { afterEach, describe, expect, it } from "vitest";

import {
  CATALOG_MOTIFS_1_TO_12,
  FIRST_PROMOTED_MOTIF_NUMBER,
  PROMOTION_MIN_OCCURRENCES,
  PROMOTED_MOTIF_REGISTRY_FILENAME,
  RESERVED_MOTIFS,
  PromoteDiagramError,
  planDiagramPromotions,
  promoteDiagrams,
  renderMotifSource,
  type DiagramOccurrence,
  type PromotedMotifRegistry,
} from "../src/tools/promote_diagram.ts";

const ALIASES = ["SmsPhoneThread", "MapRouteTrace", "TimelineDateScrubber", "AlibiSplitScreen", "EvidenceMatchCard"] as const;
const dirs: string[] = [];

afterEach(async () => {
  await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function tempDir(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "tc-promote-diagram-"));
  dirs.push(dir);
  return dir;
}

function scenes(tag: string, ids: readonly string[], motif?: string): DiagramOccurrence[] {
  return ids.map((scene_id) => {
    const occurrence: DiagramOccurrence = { scene_id, diagram_tag: tag };
    if (motif !== undefined) occurrence.motif_component = motif;
    return occurrence;
  });
}

async function readRegistry(dir: string): Promise<PromotedMotifRegistry> {
  const text = await readFile(join(dir, PROMOTED_MOTIF_REGISTRY_FILENAME), "utf8");
  return JSON.parse(text) as PromotedMotifRegistry;
}

function assertTsxParses(source: string): void {
  const result = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.React,
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
    reportDiagnostics: true,
    fileName: "motif.tsx",
  });
  const errors = (result.diagnostics ?? [])
    .filter((item) => item.category === ts.DiagnosticCategory.Error)
    .map((item) => ts.flattenDiagnosticMessageText(item.messageText, "\n"));
  expect(errors).toEqual([]);
}

describe("planDiagramPromotions", () => {
  it("keeps motifs #1-#12 numbered from the frozen registry", () => {
    expect(CATALOG_MOTIFS_1_TO_12).toHaveLength(12);
    expect(PROMOTION_MIN_OCCURRENCES).toBe(3);
    expect(FIRST_PROMOTED_MOTIF_NUMBER).toBe(13);
    for (const [index, name] of CATALOG_MOTIFS_1_TO_12.entries()) {
      const reserved = RESERVED_MOTIFS.find((entry) => entry.motif_component === name);
      expect(reserved).toMatchObject({ motif_number: index + 1, reason: "catalog_12", owner_package: "render_catalog" });
    }
  });

  it("promotes a tag at three distinct scenes and ignores a repeat of the same scene", () => {
    const plan = planDiagramPromotions([
      ...scenes("cell_ping_fan", ["s3", "s1", "s1", "s2"]),
      ...scenes("rare_note", ["s1", "s2"]),
    ]);
    expect(plan.promoted).toEqual([
      {
        diagram_tag: "cell_ping_fan",
        motif_component: "CellPingFan",
        motif_number: 13,
        occurrence_count: 3,
        scene_ids: ["s1", "s2", "s3"],
      },
    ]);
    expect(plan.below_threshold).toEqual([
      { diagram_tag: "rare_note", occurrence_count: 2, scene_ids: ["s1", "s2"] },
    ]);
  });

  it("groups hyphen, snake, and Pascal spellings as one motif", () => {
    const plan = planDiagramPromotions([
      ...scenes("cell-ping-fan", ["s1"]),
      ...scenes("cell_ping_fan", ["s2"]),
      ...scenes("CellPingFan", ["s3"]),
    ]);
    expect(plan.promoted.map((motif) => motif.motif_component)).toEqual(["CellPingFan"]);
    expect(plan.promoted[0]?.scene_ids).toEqual(["s1", "s2", "s3"]);
  });

  it("assigns motif numbers from 13 in tag order", () => {
    const plan = planDiagramPromotions([
      ...scenes("zeta_chart", ["z1", "z2", "z3"]),
      ...scenes("alpha_board", ["a1", "a2", "a3"]),
    ]);
    expect(plan.promoted.map((motif) => [motif.motif_component, motif.motif_number])).toEqual([
      ["AlphaBoard", 13],
      ["ZetaChart", 14],
    ]);
  });

  it("rejects every catalog motif #1-#12 once it would be scaffolded", () => {
    for (const [index, name] of CATALOG_MOTIFS_1_TO_12.entries()) {
      const snake = name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
      expect(() => planDiagramPromotions(scenes(snake, ["a", "b", "c"]))).toThrow(PromoteDiagramError);
      try {
        planDiagramPromotions(scenes(name, ["a", "b", "c"]));
        throw new Error(`expected ${name} to be reserved`);
      } catch (error) {
        expect(error).toBeInstanceOf(PromoteDiagramError);
        expect(error).toMatchObject({
          code: "RESERVED_MOTIF",
          reserved_motif: name,
          motif_number: index + 1,
        });
      }
    }
  });

  it("rejects registry rows, the escape hatch, and drifted motif aliases", () => {
    const reserved = [
      ["Illustrative2KPanZoom", "crime_scene_2k"],
      ["HeroVideoBridge", "flow_adapter"],
      ["CustomDiagramScene", "escape"],
      ...ALIASES.map((name) => [name, "alias"] as const),
    ] as const;
    for (const [name] of reserved) {
      expect(() => planDiagramPromotions(scenes(name, ["a", "b", "c"]))).toThrow(PromoteDiagramError);
      try {
        planDiagramPromotions(scenes(name, ["a", "b", "c"]));
      } catch (error) {
        expect(error).toMatchObject({ code: "RESERVED_MOTIF", reserved_motif: name, motif_number: null });
      }
    }
  });

  it("treats a split spelling of motif #5 as TimelineScrubber", () => {
    expect(() => planDiagramPromotions(scenes("time_line_scrubber", ["a", "b", "c"]))).toThrow(PromoteDiagramError);
    try {
      planDiagramPromotions(scenes("time_line_scrubber", ["a", "b", "c"]));
    } catch (error) {
      expect(error).toMatchObject({ code: "RESERVED_MOTIF", reserved_motif: "TimelineScrubber", motif_number: 5 });
    }
  });

  it("does not promote a reserved tag that is still under the threshold", () => {
    const plan = planDiagramPromotions([
      ...scenes("timeline_scrubber", ["a", "b"]),
      ...scenes("cell_ping_fan", ["c1", "c2", "c3"]),
    ]);
    expect(plan.promoted.map((motif) => motif.motif_component)).toEqual(["CellPingFan"]);
    expect(plan.below_threshold.map((row) => row.diagram_tag)).toContain("TimelineScrubber");
  });

  it("ignores scenes that are not CustomDiagramScene", () => {
    const plan = planDiagramPromotions([
      ...scenes("cell_ping_fan", ["a", "b", "c"], "StickmanStage"),
      ...scenes("cell_ping_fan", ["d", "e"], "CustomDiagramScene"),
    ]);
    expect(plan.promoted).toEqual([]);
    expect(plan.below_threshold[0]?.occurrence_count).toBe(2);
  });
});

describe("promoteDiagrams", () => {
  it("scaffolds a Zod schema and React template in a temp directory", async () => {
    const dir = await tempDir();
    const result = await promoteDiagrams({
      outDir: dir,
      occurrences: scenes("cell_ping_fan", ["s1", "s2", "s3"], "CustomDiagramScene"),
    });
    expect(result.files_written.map((file) => file.slice(dir.length + 1)).sort()).toEqual([
      "CellPingFan.tsx",
      PROMOTED_MOTIF_REGISTRY_FILENAME,
    ]);
    const source = await readFile(join(dir, "CellPingFan.tsx"), "utf8");
    expect(source).toContain('import { z } from "zod"');
    expect(source).toContain(".strict()");
    expect(source).toContain("export function CellPingFan");
    expect(source).toContain("export const MOTIF_NUMBER = 13");
    expect(source).toContain("paddingTop: 108");
    expect(source).toContain("paddingBottom: 194");
    expect(source).toContain("RULE_07");
    expect(source).not.toContain("eval(");
    expect(source).not.toContain("feTurbulence");
    expect(source).not.toContain("feDisplacementMap");
    expect(source).not.toContain("dangerouslySetInnerHTML");
    expect(source).not.toContain("<script");
    for (const name of CATALOG_MOTIFS_1_TO_12) expect(source).not.toContain(name);
    assertTsxParses(source);

    const registry = await readRegistry(dir);
    expect(registry).toMatchObject({
      schema: "promoted_motif_registry.v1",
      owner_package: "render_catalog",
      first_motif_number: 13,
      reserved_catalog_12: [...CATALOG_MOTIFS_1_TO_12],
    });
    expect(registry.motifs).toEqual([
      {
        motif_component: "CellPingFan",
        motif_number: 13,
        diagram_tag: "cell_ping_fan",
        occurrence_count: 3,
        scene_ids: ["s1", "s2", "s3"],
        owner_package: "render_catalog",
        is_mvp_4: false,
        catalog_12: false,
      },
    ]);
    expect(registry.motifs.every((motif) => motif.motif_number >= 13 && motif.catalog_12 === false)).toBe(true);
  });

  it("writes nothing below the threshold and does not create a registry", async () => {
    const dir = await tempDir();
    const result = await promoteDiagrams({
      outDir: dir,
      occurrences: scenes("cell_ping_fan", ["s1", "s2"]),
    });
    expect(result.promoted).toEqual([]);
    expect(result.files_written).toEqual([]);
    expect(await readdir(dir)).toEqual([]);
  });

  it("rejects a reserved name before creating an output directory", async () => {
    const parent = await tempDir();
    const outDir = join(parent, "not-created");
    await expect(
      promoteDiagrams({ outDir, occurrences: scenes("timeline_scrubber", ["a", "b", "c"]) }),
    ).rejects.toMatchObject({
      name: "PromoteDiagramError",
      code: "RESERVED_MOTIF",
      reserved_motif: "TimelineScrubber",
      motif_number: 5,
    });
    await expect(stat(outDir)).rejects.toThrow();
  });

  it("rejects a mixed batch before any file is written", async () => {
    const dir = await tempDir();
    await expect(
      promoteDiagrams({
        outDir: dir,
        occurrences: [
          ...scenes("cell_ping_fan", ["c1", "c2", "c3"]),
          ...scenes("StickmanStage", ["a", "b", "c"]),
        ],
      }),
    ).rejects.toMatchObject({ code: "RESERVED_MOTIF", reserved_motif: "StickmanStage", motif_number: 1 });
    expect(await readdir(dir)).toEqual([]);
  });

  it("rejects an unsafe tag before any file is written", async () => {
    const dir = await tempDir();
    await expect(
      promoteDiagrams({
        outDir: dir,
        occurrences: [
          ...scenes("../CellPingFan", ["a", "b", "c"]),
          ...scenes("cell_ping_fan", ["d", "e", "f"]),
        ],
      }),
    ).rejects.toMatchObject({ code: "BAD_TAG" });
    expect(await readdir(dir)).toEqual([]);
  });

  it("refuses to overwrite an existing component file", async () => {
    const dir = await tempDir();
    await writeFile(join(dir, "CellPingFan.tsx"), "keep\n");
    await expect(
      promoteDiagrams({
        outDir: dir,
        occurrences: [
          ...scenes("cell_ping_fan", ["a", "b", "c"]),
          ...scenes("zeta_chart", ["z1", "z2", "z3"]),
        ],
      }),
    ).rejects.toMatchObject({ code: "EXISTS" });
    expect(await readFile(join(dir, "CellPingFan.tsx"), "utf8")).toBe("keep\n");
    expect(await readdir(dir)).toEqual(["CellPingFan.tsx"]);
  });

  it("appends a later motif without rewriting the earlier scaffold", async () => {
    const dir = await tempDir();
    await promoteDiagrams({ outDir: dir, occurrences: scenes("alpha_board", ["a1", "a2", "a3"]) });
    const first = await readFile(join(dir, "AlphaBoard.tsx"), "utf8");
    const registry = await readFile(join(dir, PROMOTED_MOTIF_REGISTRY_FILENAME), "utf8");
    const again = await promoteDiagrams({ outDir: dir, occurrences: scenes("alpha_board", ["a1", "a2", "a3"]) });
    expect(again.files_written).toEqual([]);
    expect(again.already_registered.map((motif) => motif.motif_number)).toEqual([13]);
    expect(await readFile(join(dir, PROMOTED_MOTIF_REGISTRY_FILENAME), "utf8")).toBe(registry);

    const second = await promoteDiagrams({ outDir: dir, occurrences: scenes("zeta_chart", ["z1", "z2", "z3"]) });
    expect(second.promoted.map((motif) => [motif.motif_component, motif.motif_number])).toEqual([["ZetaChart", 14]]);
    expect(await readFile(join(dir, "AlphaBoard.tsx"), "utf8")).toBe(first);
    const merged = await readRegistry(dir);
    expect(merged.motifs.map((motif) => [motif.motif_component, motif.motif_number])).toEqual([
      ["AlphaBoard", 13],
      ["ZetaChart", 14],
    ]);
  });

  it("scaffolds a near-miss name that is not motif #1", async () => {
    const dir = await tempDir();
    const result = await promoteDiagrams({
      outDir: dir,
      occurrences: scenes("stickman_stage_notes", ["n1", "n2", "n3"]),
    });
    expect(result.promoted[0]).toMatchObject({ motif_component: "StickmanStageNotes", motif_number: 13 });
    const names = (await readdir(dir)).filter((name) => name.endsWith(".tsx"));
    expect(names).toEqual(["StickmanStageNotes.tsx"]);
    expect(names).not.toContain("StickmanStage.tsx");
  });

  it("collects tags from a mixed timeline document", async () => {
    const dir = await tempDir();
    const result = await promoteDiagrams({
      outDir: dir,
      document: {
        scenes: [
          { scene_id: "s1", motif_component: "StickmanStage" },
          { scene_id: "s2", motif_component: "CustomDiagramScene", diagram_tag: "cell_ping_fan" },
          { scene_id: "s3", motif_component: "CustomDiagramScene", tag: "cell-ping-fan" },
          { scene_id: "s10", visual: { motif_component: "CustomDiagramScene", diagram: { tag: "CellPingFan" } } },
          { scene_id: "s11", motif_component: "CustomDiagramScene", primitives: [] },
          { scene_id: "s5", motif_component: "CustomDiagramScene", diagram_tag: "rare_note" },
        ],
      },
    });
    expect(result.promoted).toEqual([
      {
        diagram_tag: "cell_ping_fan",
        motif_component: "CellPingFan",
        motif_number: 13,
        occurrence_count: 3,
        scene_ids: ["s10", "s2", "s3"],
      },
    ]);
    expect(result.below_threshold).toEqual([
      { diagram_tag: "rare_note", occurrence_count: 1, scene_ids: ["s5"] },
    ]);
  });

  it("rejects a tagged diagram that has no scene id before writing", async () => {
    const parent = await tempDir();
    const outDir = join(parent, "missing-scene");
    await expect(
      promoteDiagrams({
        outDir,
        document: { motif_component: "CustomDiagramScene", diagram_tag: "cell_ping_fan" },
      }),
    ).rejects.toMatchObject({ code: "BAD_OCCURRENCE" });
    await expect(stat(outDir)).rejects.toThrow();
  });

  it("leaves a corrupt registry untouched when a new scaffold is refused", async () => {
    const dir = await tempDir();
    const planted = `${JSON.stringify({ schema: "promoted_motif_registry.v1", motifs: [] })}\n`;
    await writeFile(join(dir, PROMOTED_MOTIF_REGISTRY_FILENAME), planted);
    await expect(
      promoteDiagrams({ outDir: dir, occurrences: scenes("cell_ping_fan", ["a", "b", "c"]) }),
    ).rejects.toMatchObject({ code: "BAD_REGISTRY" });
    expect(await readFile(join(dir, PROMOTED_MOTIF_REGISTRY_FILENAME), "utf8")).toBe(planted);
    expect(await readdir(dir)).toEqual([PROMOTED_MOTIF_REGISTRY_FILENAME]);
  });

  it("writes the same bytes for the same occurrences", async () => {
    const left = await tempDir();
    const right = await tempDir();
    const occurrences = [
      ...scenes("zeta_chart", ["z2", "z1", "z3"]),
      ...scenes("alpha_board", ["a1", "a2", "a3"]),
    ];
    await promoteDiagrams({ outDir: left, occurrences });
    await promoteDiagrams({ outDir: right, occurrences });
    for (const name of ["AlphaBoard.tsx", "ZetaChart.tsx", PROMOTED_MOTIF_REGISTRY_FILENAME]) {
      expect(await readFile(join(left, name), "utf8")).toBe(await readFile(join(right, name), "utf8"));
    }
  });

  it("refuses to render a reserved component even as a string", () => {
    expect(() =>
      renderMotifSource({
        diagram_tag: "timeline_scrubber",
        motif_component: "TimelineScrubber",
        motif_number: 13,
        occurrence_count: 3,
        scene_ids: ["a", "b", "c"],
      }),
    ).toThrow(PromoteDiagramError);
  });
});
