import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

import {
  REMOTION_ROOT,
  TimelineContractError,
  configureRemotionRoot,
  isEndScreenFrame,
  parseGoldenPack,
  parseTimelineSpec,
} from "../src/index.ts";
import { measureSafeZone, walkSafeZone, type Rect, type SafeZoneElement } from "../src/safe_zone.tsx";

const pack = JSON.parse(
  readFileSync(new URL("../../../fixtures/golden_manifests/ep_golden_01_20min/pack.json", import.meta.url), "utf8"),
) as { timeline_spec: unknown };

const LONG_LABEL = "Marlow County dispatcher already knew the affidavit locator before dawn ".repeat(4);

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

function node(root: SafeZoneElement, key: string, value: string): SafeZoneElement {
  const found = walkSafeZone(root).find((item) => item.dataset[key] === value);
  if (!found) throw new Error(`missing ${key}=${value}`);
  return found;
}

function tinyTimeline(fps: number) {
  return {
    fps,
    width: 1920,
    height: 1080,
    frame_count: 300,
    scenes: [
      {
        scene_id: "s1",
        seq_index: 1,
        motif_component: "StickmanStage",
        visual_engine: "CODE_STICKMAN",
        prompt_mode: "NONE",
        start_frame: 0,
        duration_frames: 150,
      },
      {
        scene_id: "s2",
        seq_index: 2,
        motif_component: "AudioEvidenceCard",
        visual_engine: "AUDIO_EVIDENCE_CARD",
        prompt_mode: "NONE",
        start_frame: 150,
        duration_frames: 150,
      },
    ],
  };
}

test("ep_golden_01_20min parses onto a 1920x1080 30 fps Remotion root", () => {
  const parsed = parseGoldenPack(pack);
  expect(parsed.packId).toBe("ep_golden_01_20min");
  expect(parsed.timeline.fps).toBe(30);
  expect(parsed.timeline.width).toBe(1920);
  expect(parsed.timeline.height).toBe(1080);
  expect(parsed.timeline.frame_count).toBe(36000);
  expect(parsed.timeline.scenes).toHaveLength(36);
  expect(parsed.composition).toEqual({
    id: "TrueCrimeEpisode",
    fps: 30,
    width: 1920,
    height: 1080,
    durationInFrames: 36000,
  });
  expect(parsed.composition.fps).toBe(REMOTION_ROOT.fps);
  const motifs = new Set<string>(parsed.timeline.scenes.map((scene) => scene.motif_component));
  for (const motif of ["StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame"]) {
    expect(motifs.has(motif)).toBe(true);
  }
  expect(isEndScreenFrame(35399, parsed.composition.durationInFrames)).toBe(false);
  expect(isEndScreenFrame(35400, parsed.composition.durationInFrames)).toBe(true);
});

test("rejects a 60 fps root, drifted raster size, unknown keys, and broken frame runs", () => {
  expect(() => parseTimelineSpec(tinyTimeline(60))).toThrow(/30/);
  expect(() =>
    configureRemotionRoot({ fps: 60, width: 1920, height: 1080, durationInFrames: 300 }),
  ).toThrow(TimelineContractError);
  expect(configureRemotionRoot({ durationInFrames: 36000 })).toEqual({
    id: "TrueCrimeEpisode",
    fps: 30,
    width: 1920,
    height: 1080,
    durationInFrames: 36000,
  });

  const parsed = parseGoldenPack(pack);
  const drifted = structuredClone(parsed.timeline);
  drifted.width = 1280;
  expect(() => parseTimelineSpec(drifted)).toThrow(/1920/);

  const extra = structuredClone(parsed.timeline) as unknown as Record<string, unknown>;
  extra.grain = true;
  expect(() => parseTimelineSpec(extra)).toThrow(/Unrecognized key/);

  const retired = structuredClone(parsed.timeline);
  const first = retired.scenes[0];
  if (!first) throw new Error("expected a scene");
  first.motif_component = "CrimeScenePanZoom" as "StickmanStage";
  expect(() => parseTimelineSpec(retired)).toThrow();

  const retiredMode = structuredClone(parsed.timeline);
  const second = retiredMode.scenes[1];
  if (!second) throw new Error("expected a scene");
  second.prompt_mode = "FRAMES_MOTION_ONLY" as "NONE";
  expect(() => parseTimelineSpec(retiredMode)).toThrow();

  const overlap = structuredClone(parsed.timeline);
  const third = overlap.scenes[2];
  if (!third) throw new Error("expected a scene");
  third.start_frame -= 1;
  expect(() => parseTimelineSpec(overlap)).toThrow(/start_frame/);
});

test("safe-zone CSS keeps a 3-line label and the end-screen card out of the caption bar", () => {
  const resting = measureSafeZone({ isEndScreen: false, label: LONG_LABEL });
  const frameStyle = resting.element.props.style;
  expect(frameStyle.display).toBe("grid");
  expect(frameStyle.boxSizing).toBe("border-box");
  expect(frameStyle.overflow).toBe("hidden");
  expect(frameStyle.paddingTop).toBe(108);
  expect(frameStyle.paddingBottom).toBe(194);
  expect(frameStyle.width).toBe(1920);
  expect(frameStyle.height).toBe(1080);

  const content = node(resting.element, "slot", "content");
  expect(content.props.style.display).toBe("flex");
  expect(content.props.style.overflow).toBe("hidden");

  const exclusion = node(resting.element, "exclusion", "bottom-right");
  expect(exclusion.props.style.width).toBe("22%");
  expect(exclusion.props.style.height).toBe("14%");
  expect(exclusion.props.style.overflow).toBe("hidden");

  const label = node(resting.element, "slot", "label");
  expect(label.props.style.overflow).toBe("hidden");
  expect(label.props.style.WebkitLineClamp).toBe(3);
  expect(label.props.style.maxHeight).toBe("clamp(82.8px, 7.59vw, 144.9px)");
  expect(label.props.style.fontSize).toBe("clamp(24px, 2.2vw, 42px)");
  expect(label.props.children).toBe(LONG_LABEL);
  expect(walkSafeZone(resting.element).some((item) => item.dataset.mask === "end-screen-card")).toBe(false);

  expect(resting.content).toEqual({ x: 0, y: 108, width: 1920, height: 778 });
  expect(resting.exclusion.x).toBeCloseTo(1497.6, 5);
  expect(resting.exclusion.y).toBeCloseTo(928.8, 5);
  expect(resting.exclusion.width).toBeCloseTo(422.4, 5);
  expect(resting.exclusion.height).toBeCloseTo(151.2, 5);
  expect(resting.captionBar).toEqual({ x: 0, y: 886, width: 1920, height: 194 });
  expect(resting.label).not.toBeNull();
  if (!resting.label) throw new Error("expected a label box");
  expect(resting.label.height).toBeCloseTo(144.9, 5);
  expect(resting.label.y).toBeGreaterThanOrEqual(108);
  expect(resting.label.y + resting.label.height).toBeCloseTo(886, 5);
  expect(overlaps(resting.label, resting.captionBar)).toBe(false);
  expect(overlaps(resting.label, resting.exclusion)).toBe(false);
  expect(overlaps(resting.content, resting.exclusion)).toBe(false);
  expect(overlaps(resting.content, resting.captionBar)).toBe(false);

  const ending = measureSafeZone({ isEndScreen: true, label: LONG_LABEL });
  expect(ending.element.dataset["end-screen"]).toBe("true");
  expect(ending.label).toBeNull();
  const card = node(ending.element, "mask", "end-screen-card");
  expect(card.props.style.overflow).toBe("hidden");
  expect(card.props.style.WebkitLineClamp).toBe(3);
  expect(card.props.style.maxHeight).toBe("clamp(82.8px, 7.59vw, 144.9px)");
  expect(card.props.style.right).toBe("22%");
  expect(card.props.style.bottom).toBe(194);
  expect(ending.endScreenCard).not.toBeNull();
  if (!ending.endScreenCard) throw new Error("expected an end-screen card");
  expect(ending.endScreenCard.width).toBeCloseTo(1497.6, 5);
  expect(ending.endScreenCard.height).toBeCloseTo(144.9, 5);
  expect(ending.endScreenCard.y + ending.endScreenCard.height).toBeCloseTo(886, 5);
  expect(ending.endScreenCard.x + ending.endScreenCard.width).toBeCloseTo(ending.exclusion.x, 5);
  expect(overlaps(ending.endScreenCard, ending.captionBar)).toBe(false);
  expect(overlaps(ending.endScreenCard, ending.exclusion)).toBe(false);
});
