import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterAll, beforeEach, describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../../../..");
const gradePath = path.resolve(here, "../../src/grade/GradeContract.tsx");
const stickPath = path.resolve(here, "../../src/motifs/StickmanStage.tsx");
const themePath = path.resolve(here, "../../src/theme/CaseBibleContext.tsx");
const sourcePath = path.resolve(here, "../../src/motifs/HeroVideoBridge.tsx");
const STUB_MARK = "TC-TASK-119-TEST-STUB";

const GRADE_STUB = `/** ${STUB_MARK} — test double, not Task 109. Removed when the hero bridge test finishes. */
export function sceneNeedsGrade(scene: { visual_engine: string; motif_component?: string | null }): boolean {
  if (scene.visual_engine === "FOIA_REAL_FOOTAGE" || scene.motif_component === "FoiaFootageFrame") return false;
  return true;
}
`;

const STICK_STUB = `/** ${STUB_MARK} — test double, not Task 115. Removed when the hero bridge test finishes. */
export let stickmanStageCalls = 0;
export function resetStickmanStageCalls(): void {
  stickmanStageCalls = 0;
}
export function StickmanStage(props: {
  scene_id: string;
  episode_id: string;
  duration_ms: number;
  from_fallback: true;
}): { type: "StickmanStage"; props: typeof props & { "data-tc-role": "stickman-stage" } } {
  stickmanStageCalls += 1;
  return { type: "StickmanStage", props: { ...props, "data-tc-role": "stickman-stage" } };
}
`;

const THEME_STUB = `/** ${STUB_MARK} — test double, not Task 102. Removed when the hero bridge test finishes. */
export function useCaseBible(): { paperBgHex: string } {
  return { paperBgHex: "#E9E2D2" };
}
`;

function existingText(file: string): string | null {
  return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
}

function installStub(file: string, source: string): boolean {
  const current = existingText(file);
  const owned = current === null || current.includes(STUB_MARK);
  if (!owned) return false;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, source);
  return true;
}

const gradeOwned = installStub(gradePath, GRADE_STUB);
const stickOwned = installStub(stickPath, STICK_STUB);
const themeOwned = gradeOwned ? false : installStub(themePath, THEME_STUB);

function removeOwned(file: string, owned: boolean): void {
  if (!owned) return;
  if (fs.existsSync(file) && fs.readFileSync(file, "utf8").includes(STUB_MARK)) {
    fs.rmSync(file, { force: true });
  }
  const dir = path.dirname(file);
  if (fs.existsSync(dir) && fs.readdirSync(dir).length === 0) fs.rmdirSync(dir);
}

function removeStubs(): void {
  removeOwned(gradePath, gradeOwned);
  removeOwned(stickPath, stickOwned);
  removeOwned(themePath, themeOwned);
}

process.on("exit", removeStubs);

const bridge = await import("../../src/motifs/HeroVideoBridge.tsx");
const stickModule = stickOwned
  ? ((await import("../../src/motifs/StickmanStage.tsx")) as {
      stickmanStageCalls: number;
      resetStickmanStageCalls: () => void;
    })
  : null;

afterAll(removeStubs);

const {
  FRAME_HEIGHT,
  FRAME_WIDTH,
  HERO_SPEED_MAX,
  HERO_SPEED_MIN,
  HeroVideoBridge,
  assertWithinSpeedBounds,
  conformFlowFrame,
  fitHeroPlayback,
} = bridge;

interface FallbackSpec {
  engine: string;
  motif_component: string;
  still_2k_id?: string;
  anchor_id?: string;
  rule?: string;
}

interface PackScene {
  scene_id: string;
  episode_id: string;
  seq_index: number;
  visual_engine: string;
  start_ms: number;
  end_ms: number;
  fallback_spec_json: FallbackSpec | null;
}

interface PackJob {
  scene_id: string;
  state: string;
  resolution: string;
  duration_bucket_sec: number;
  attempts_used: number;
  fallback_spec_json: FallbackSpec;
}

function loadGolden(): { scenes: PackScene[]; jobs: PackJob[] } {
  const packPath = path.join(repoRoot, "fixtures/golden_manifests/ep_golden_02_2strike_fallback/pack.json");
  const pack = JSON.parse(fs.readFileSync(packPath, "utf8")) as { scenes: PackScene[]; flow_job_cards: PackJob[] };
  return { scenes: pack.scenes, jobs: pack.flow_job_cards };
}

function sceneById(scenes: PackScene[], id: string): PackScene {
  const scene = scenes.find((item) => item.scene_id === id);
  if (!scene) throw new Error(`missing ${id}`);
  return scene;
}

function neighbors(scenes: PackScene[], scene: PackScene): { prev: string | null; next: string | null } {
  const prev = scenes.find((item) => item.seq_index === scene.seq_index - 1);
  const next = scenes.find((item) => item.seq_index === scene.seq_index + 1);
  return { prev: prev?.visual_engine ?? null, next: next?.visual_engine ?? null };
}

function acceptedInput(
  overrides: Partial<Parameters<typeof HeroVideoBridge>[0]> = {},
): Parameters<typeof HeroVideoBridge>[0] {
  return {
    scene_id: "hero_trim",
    episode_id: "ep_golden_02_2strike_fallback",
    start_ms: 0,
    end_ms: 7600,
    flow_state: "ACCEPTED",
    resolution: "720p",
    clip: {
      src: "workspace/flow_ingested/hero_trim.mp4",
      duration_ms: 8000,
      width: 1280,
      height: 720,
    },
    fallback_spec: {
      engine: "STILL_2K_PANZOOM",
      motif_component: "Illustrative2KPanZoom",
      still_2k_id: "still_00",
      anchor_id: "anchor_00",
      rule: "RULE_04",
    },
    prev_engine: "CODE_STICKMAN",
    next_engine: "CODE_STICKMAN",
    ...overrides,
  };
}

beforeEach(() => {
  stickModule?.resetStickmanStageCalls();
});

describe("hero playback fit", () => {
  it("trims a 7.6s scene against an 8.0s clip at 1.0x without rounding the millisecond", () => {
    const fit = fitHeroPlayback(7600, 8000);
    expect(fit.playbackRate).toBe(1);
    expect(fit.rateNumerator).toBe(1);
    expect(fit.rateDenominator).toBe(1);
    expect(fit.trimStartMs).toBe(0);
    expect(fit.trimEndMs).toBe(7600);
    expect(fit.timelineMs).toBe(7600);
    expect(fit.discardedTailMs).toBe(400);
    expect(fit.speedAdjusted).toBe(false);
    expect(fit.speedDistorted).toBe(false);
    expect(fit.trimEndFrame).toBe(228);
    expect(8000 / 7600).toBeGreaterThan(1);
    expect(8000 / 7600).toBeLessThanOrEqual(HERO_SPEED_MAX);
    expect(fit.playbackRate).toBe(1);
  });

  it("keeps a 7601 ms trim on the millisecond instead of snapping to a frame", () => {
    const fit = fitHeroPlayback(7601, 8000);
    expect(fit.playbackRate).toBe(1);
    expect(fit.trimEndMs).toBe(7601);
    expect(fit.timelineMs).toBe(7601);
    expect(fit.discardedTailMs).toBe(399);
    expect(fit.trimEndFrame).toBeNull();
    expect((7601 * 30) / 1000).toBeCloseTo(228.03, 5);
  });

  it("slows a shorter clip only inside 0.85x–1.15x", () => {
    const slowed = fitHeroPlayback(8000, 7600);
    expect(slowed.rateNumerator).toBe(19);
    expect(slowed.rateDenominator).toBe(20);
    expect(slowed.playbackRate).toBeCloseTo(0.95, 10);
    expect(slowed.trimEndMs).toBe(7600);
    expect(slowed.timelineMs).toBe(8000);
    expect(slowed.discardedTailMs).toBe(0);
    expect(slowed.speedAdjusted).toBe(true);
    expect(slowed.speedDistorted).toBe(false);
    expect(slowed.trimEndFrame).toBe(228);

    const floor = fitHeroPlayback(8000, 6800);
    expect(floor.rateNumerator).toBe(17);
    expect(floor.rateDenominator).toBe(20);
    expect(floor.playbackRate).toBeCloseTo(HERO_SPEED_MIN, 10);
    expect(floor.timelineMs).toBe(8000);

    expect(() => fitHeroPlayback(8000, 6799)).toThrow(/HERO_SPEED_BOUNDS/);
    expect(() => assertWithinSpeedBounds(HERO_SPEED_MIN)).not.toThrow();
    expect(() => assertWithinSpeedBounds(HERO_SPEED_MAX)).not.toThrow();
    expect(() => assertWithinSpeedBounds(1)).not.toThrow();
    expect(() => assertWithinSpeedBounds(0.84)).toThrow(/HERO_SPEED_BOUNDS/);
    expect(() => assertWithinSpeedBounds(1.16)).toThrow(/HERO_SPEED_BOUNDS/);
  });
});

describe("720p to 1080p conform", () => {
  it("scales a 720p frame uniformly onto 1920x1080", () => {
    const conform = conformFlowFrame("720p", 1280, 720);
    expect(conform).toEqual({
      sourceWidth: 1280,
      sourceHeight: 720,
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      scaleX: 1.5,
      scaleY: 1.5,
      conform: "720p->1080p",
      objectFit: "fill",
    });
    expect(FRAME_WIDTH).toBe(1920);
    expect(FRAME_HEIGHT).toBe(1080);
    expect(conformFlowFrame("1080p", 1920, 1080).conform).toBe("1080p");
    expect(conformFlowFrame("1080p", 1920, 1080).scaleX).toBe(1);
    expect(() => conformFlowFrame("720p", 1920, 1080)).toThrow(/1280x720/);
    expect(() => conformFlowFrame("360p" as "720p", 640, 360)).toThrow(/720p or 1080p/);
  });
});

describe("HeroVideoBridge", () => {
  it("plays the trimmed 720p clip and leaves the fallback latent", () => {
    const result = HeroVideoBridge(acceptedInput());
    expect(result.mode).toBe("play");
    expect(result.flow_mounted).toBe(true);
    expect(result.fallback_active).toBe(false);
    expect(result.active_engine).toBe("FLOW_HERO_VIDEO");
    expect(result.active_motif).toBe("HeroVideoBridge");
    expect(result.apply_grade).toBe(true);
    expect(result.needs_grade).toBe(true);
    expect(result.grade_owner).toBe("agent6_single_pass");
    expect(result.remotion_grain_applied).toBe(false);
    expect(result.remotion_vignette_applied).toBe(false);
    expect(result.paper_grain).toBe(0);
    expect(result.vignette).toBe(0);
    expect(result.playback?.trimEndMs).toBe(7600);
    expect(result.playback?.playbackRate).toBe(1);
    expect(result.playback?.speedDistorted).toBe(false);
    expect(result.conform?.conform).toBe("720p->1080p");
    expect(result.latent_fallback?.engine).toBe("STILL_2K_PANZOOM");
    expect(result.active_fallback).toBeNull();
    expect(result.delegate).toBeNull();
    expect(result.element.type).toBe("video");
    expect(result.element.props.src).toBe("workspace/flow_ingested/hero_trim.mp4");
    expect(result.element.props.playbackRate).toBe(1);
    expect(result.element.props.trimEndMs).toBe(7600);
    expect(result.element.props["data-paper-grain"]).toBe("0");
    expect(result.element.props["data-vignette"]).toBe("0");
    expect(result.element.props["data-apply-grade"]).toBe("true");
    expect(result.element.props.style.filter).toBe("none");
    expect(result.element.props.style.backgroundImage).toBe("none");
    expect(result.element.props.children).toBeNull();
    expect(result.element.props.style.width).toBe(1920);
    expect(result.element.props.style.height).toBe(1080);
    expect(stickModule?.stickmanStageCalls ?? 0).toBe(0);
  });

  it("refuses a remote or traversing clip path", () => {
    expect(() =>
      HeroVideoBridge(acceptedInput({ clip: { src: "https://example.com/a.mp4", duration_ms: 8000, width: 1280, height: 720 } })),
    ).toThrow(/local relative path/);
    expect(() =>
      HeroVideoBridge(acceptedInput({ clip: { src: "../secret.mp4", duration_ms: 8000, width: 1280, height: 720 } })),
    ).toThrow(/without traversal/);
    expect(() =>
      HeroVideoBridge(acceptedInput({ clip: { src: "/tmp/hero.mp4", duration_ms: 8000, width: 1280, height: 720 } })),
    ).toThrow(/without traversal/);
  });

  it("switches ep_golden_02 scene s029 to a non-neighbor still and ignores the Flow file", () => {
    const { scenes, jobs } = loadGolden();
    const scene = sceneById(scenes, "ep_golden_02_2strike_fallback_s029");
    const job = jobs.find((item) => item.scene_id === scene.scene_id);
    const beside = neighbors(scenes, scene);
    expect(scene.visual_engine).toBe("FLOW_HERO_VIDEO");
    expect(beside.prev).toBe("CODE_STICKMAN");
    expect(beside.next).toBe("CODE_STICKMAN");
    expect(scene.end_ms - scene.start_ms).toBe(8000);
    expect(job?.state).toBe("SWITCHED_TO_FALLBACK");
    expect(job?.attempts_used).toBe(2);
    expect(job?.resolution).toBe("720p");
    expect(job?.fallback_spec_json).toEqual(scene.fallback_spec_json);

    const result = HeroVideoBridge({
      scene_id: scene.scene_id,
      episode_id: scene.episode_id,
      start_ms: scene.start_ms,
      end_ms: scene.end_ms,
      flow_state: "SWITCHED_TO_FALLBACK",
      resolution: "720p",
      clip: {
        src: "workspace/flow_ingested/ep_golden_02_2strike_fallback_s029.mp4",
        duration_ms: 8000,
        width: 1280,
        height: 720,
      },
      fallback_spec: scene.fallback_spec_json,
      prev_engine: beside.prev,
      next_engine: beside.next,
    });

    expect(result.mode).toBe("fallback");
    expect(result.flow_mounted).toBe(false);
    expect(result.fallback_active).toBe(true);
    expect(result.duration_ms).toBe(8000);
    expect(result.active_engine).toBe("STILL_2K_PANZOOM");
    expect(result.active_motif).toBe("Illustrative2KPanZoom");
    expect(result.active_fallback?.still_2k_id).toBe("ep_golden_02_2strike_fallback_still_02");
    expect(result.active_fallback?.anchor_id).toBe("ep_golden_02_2strike_fallback_anchor_004");
    expect(result.active_fallback?.rule).toBe("RULE_04");
    expect(result.active_engine).not.toBe(beside.prev);
    expect(result.active_engine).not.toBe(beside.next);
    expect(result.playback).toBeNull();
    expect(result.delegate).toBeNull();
    expect(result.apply_grade).toBe(true);
    expect(result.needs_grade).toBe(true);
    expect(result.paper_grain).toBe(0);
    expect(result.vignette).toBe(0);
    expect(result.remotion_grain_applied).toBe(false);
    expect(result.element.type).toBe("div");
    expect(result.element.props.src).toBeUndefined();
    expect(result.element.props["data-tc-role"]).toBe("hero-fallback");
    expect(result.element.props["data-gap-ms"]).toBe("0");
    expect(result.element.props["data-fallback-engine"]).toBe("STILL_2K_PANZOOM");
    expect(result.element.props["data-still-2k-id"]).toBe("ep_golden_02_2strike_fallback_still_02");
    expect(result.element.props.children).toBeNull();
    expect(result.element.props.style.filter).toBe("none");
    expect(stickModule?.stickmanStageCalls ?? 0).toBe(0);
  });

  it("routes every ep_golden_02 hero job without mounting a neighbor engine", () => {
    const { scenes, jobs } = loadGolden();
    const heroes = scenes.filter((scene) => scene.visual_engine === "FLOW_HERO_VIDEO");
    expect(heroes).toHaveLength(10);
    for (const scene of heroes) {
      const job = jobs.find((item) => item.scene_id === scene.scene_id);
      const beside = neighbors(scenes, scene);
      expect(job?.fallback_spec_json.engine).toBe("STILL_2K_PANZOOM");
      expect(job?.fallback_spec_json.engine).not.toBe(beside.prev);
      expect(job?.fallback_spec_json.engine).not.toBe(beside.next);
      const result = HeroVideoBridge({
        scene_id: scene.scene_id,
        episode_id: scene.episode_id,
        start_ms: scene.start_ms,
        end_ms: scene.end_ms,
        flow_state: job?.state as "ACCEPTED" | "SWITCHED_TO_FALLBACK" | "STRIKE_1_RETRY_SAFE",
        resolution: "720p",
        clip:
          job?.state === "ACCEPTED"
            ? {
                src: `workspace/flow_ingested/${scene.scene_id}.mp4`,
                duration_ms: (job?.duration_bucket_sec ?? 0) * 1000,
                width: 1280,
                height: 720,
              }
            : null,
        fallback_spec: scene.fallback_spec_json,
        prev_engine: beside.prev,
        next_engine: beside.next,
      });
      expect(result.paper_grain).toBe(0);
      expect(result.vignette).toBe(0);
      expect(result.element.props.children).toBeNull();
      if (job?.state === "ACCEPTED") {
        expect(result.mode).toBe("play");
        expect(result.flow_mounted).toBe(true);
        expect(result.fallback_active).toBe(false);
        expect(result.apply_grade).toBe(true);
        expect(result.conform?.conform).toBe("720p->1080p");
        expect(result.playback?.playbackRate).toBe(1);
        expect(result.playback?.trimEndMs).toBe(scene.end_ms - scene.start_ms);
      } else if (job?.state === "SWITCHED_TO_FALLBACK") {
        expect(result.mode).toBe("fallback");
        expect(result.flow_mounted).toBe(false);
        expect(result.active_engine).toBe("STILL_2K_PANZOOM");
      } else {
        expect(job?.state).toBe("STRIKE_1_RETRY_SAFE");
        expect(result.mode).toBe("withheld");
        expect(result.flow_mounted).toBe(false);
        expect(result.fallback_active).toBe(false);
        expect(result.apply_grade).toBeNull();
        expect(result.element.props["data-tc-role"]).toBe("hero-video-withheld");
        expect(result.latent_fallback?.engine).toBe("STILL_2K_PANZOOM");
      }
    }
  });

  it("rejects a fallback that matches either neighbor and does not call StickmanStage", () => {
    const base = {
      scene_id: "hero_neighbor",
      episode_id: "ep_golden_02_2strike_fallback",
      start_ms: 0,
      end_ms: 8000,
      flow_state: "SWITCHED_TO_FALLBACK" as const,
      resolution: "720p" as const,
      clip: {
        src: "workspace/flow_ingested/hero_neighbor.mp4",
        duration_ms: 8000,
        width: 1280,
        height: 720,
      },
      prev_engine: "CODE_STICKMAN",
      next_engine: "FOIA_REAL_FOOTAGE",
    };
    expect(() =>
      HeroVideoBridge({
        ...base,
        fallback_spec: { engine: "CODE_STICKMAN", motif_component: "StickmanStage", rule: "RULE_04" },
      }),
    ).toThrow(/previous scene/);
    expect(() =>
      HeroVideoBridge({
        ...base,
        prev_engine: "AUDIO_EVIDENCE_CARD",
        next_engine: "STILL_2K_PANZOOM",
        fallback_spec: { engine: "STILL_2K_PANZOOM", motif_component: "Illustrative2KPanZoom", rule: "RULE_04" },
      }),
    ).toThrow(/next scene/);
    expect(() =>
      HeroVideoBridge({
        ...base,
        fallback_spec: { engine: "FLOW_HERO_VIDEO", motif_component: "HeroVideoBridge", rule: "RULE_04" },
      }),
    ).toThrow(/cannot be FLOW_HERO_VIDEO/);
    expect(() =>
      HeroVideoBridge({
        ...base,
        prev_engine: "CODE_STICKMAN",
        next_engine: "AUDIO_EVIDENCE_CARD",
        fallback_spec: { engine: "FOIA_REAL_FOOTAGE", motif_component: "FoiaFootageFrame", rule: "RULE_04" },
      }),
    ).toThrow(/SINGLE_GRADE/);
    expect(stickModule?.stickmanStageCalls ?? 0).toBe(0);
  });

  it("delegates a neighbor-safe stickman fallback to StickmanStage", () => {
    const result = HeroVideoBridge({
      scene_id: "hero_stick",
      episode_id: "ep_golden_02_2strike_fallback",
      start_ms: 1000,
      end_ms: 9000,
      flow_state: "SWITCHED_TO_FALLBACK",
      resolution: "720p",
      clip: null,
      fallback_spec: JSON.stringify({
        visual_engine: "CODE_STICKMAN",
        motif_component: "StickmanStage",
        reason: "strike 2",
      }),
      prev_engine: "FOIA_REAL_FOOTAGE",
      next_engine: "AUDIO_EVIDENCE_CARD",
    });
    expect(result.mode).toBe("fallback");
    expect(result.flow_mounted).toBe(false);
    expect(result.duration_ms).toBe(8000);
    expect(result.active_engine).toBe("CODE_STICKMAN");
    expect(result.active_motif).toBe("StickmanStage");
    expect(result.apply_grade).toBe(true);
    expect(result.element.props["data-gap-ms"]).toBe("0");
    expect(result.element.props.children).toBeNull();
    if (stickOwned) {
      expect(stickModule?.stickmanStageCalls).toBe(1);
      expect(result.delegate).toMatchObject({
        type: "StickmanStage",
        props: {
          scene_id: "hero_stick",
          episode_id: "ep_golden_02_2strike_fallback",
          duration_ms: 8000,
          from_fallback: true,
          "data-tc-role": "stickman-stage",
        },
      });
    } else {
      expect(result.delegate).not.toBeNull();
    }
  });

  it("withholds a strike-1 retry instead of playing or switching", () => {
    const result = HeroVideoBridge(
      acceptedInput({
        flow_state: "STRIKE_1_RETRY_SAFE",
        end_ms: 8000,
        clip: {
          src: "workspace/flow_ingested/hero_trim.mp4",
          duration_ms: 8000,
          width: 1280,
          height: 720,
        },
      }),
    );
    expect(result.mode).toBe("withheld");
    expect(result.flow_mounted).toBe(false);
    expect(result.fallback_active).toBe(false);
    expect(result.apply_grade).toBeNull();
    expect(result.playback).toBeNull();
    expect(result.latent_fallback?.engine).toBe("STILL_2K_PANZOOM");
    expect(result.element.props["data-flow-state"]).toBe("STRIKE_1_RETRY_SAFE");
    expect(() => HeroVideoBridge(acceptedInput({ flow_state: "SWITCHED_TO_FALLBACK", fallback_spec: null }))).toThrow(
      /requires fallback_spec/,
    );
  });

  it("keeps grain and model literals out of the bridge source", () => {
    const source = fs.readFileSync(sourcePath, "utf8");
    expect(source.includes("feTurbulence")).toBe(false);
    expect(source.includes("feDisplacementMap")).toBe(false);
    expect(source.includes("gemini-omni")).toBe(false);
    expect(source.includes("fetch(")).toBe(false);
    expect(/veo/i.test(source)).toBe(false);
  });
});
