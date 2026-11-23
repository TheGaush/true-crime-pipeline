/**
 * Strict Zod parser for the Remotion episode clock.
 * Output is locked to 1920x1080 at 30 fps.
 *
 * Zod resolves from the Task 002 contract package. This task cannot edit
 * `packages/render_catalog/package.json`.
 */
import { z } from "../../shared-contracts-ts/node_modules/zod/index.js";

export const REMOTION_ROOT = {
  id: "TrueCrimeEpisode",
  fps: 30,
  width: 1920,
  height: 1080,
} as const;

export const END_SCREEN_SECONDS = 20;

const MOTIFS = [
  "StickmanStage",
  "AudioEvidenceCard",
  "RedactedDocReveal",
  "FoiaFootageFrame",
  "TimelineScrubber",
  "AnimatedMapRoute",
  "CellTowerTriangulation",
  "SplitScreenComparison",
  "CaseBoardSpine",
  "QuotePullout",
  "EvidenceGridMatrix",
  "ChapterSlateTransition",
  "Illustrative2KPanZoom",
  "HeroVideoBridge",
] as const;

const ENGINES = [
  "CODE_STICKMAN",
  "STILL_2K_PANZOOM",
  "AUDIO_EVIDENCE_CARD",
  "FOIA_REAL_FOOTAGE",
  "FLOW_HERO_VIDEO",
] as const;

const PROMPT_MODES = ["NONE", "TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"] as const;

export const SceneBeatSchema = z
  .object({
    scene_id: z.string().min(1),
    seq_index: z.number().int().positive(),
    motif_component: z.enum(MOTIFS),
    visual_engine: z.enum(ENGINES),
    prompt_mode: z.enum(PROMPT_MODES),
    start_frame: z.number().int().nonnegative(),
    duration_frames: z.number().int().positive(),
  })
  .strict();

export const EpisodeTimelineSchema = z
  .object({
    fps: z.literal(REMOTION_ROOT.fps),
    width: z.literal(REMOTION_ROOT.width),
    height: z.literal(REMOTION_ROOT.height),
    frame_count: z.number().int().positive(),
    scenes: z.array(SceneBeatSchema).min(1),
  })
  .strict()
  .superRefine((value, ctx) => {
    let cursor = 0;
    const seen = new Set<string>();
    for (let index = 0; index < value.scenes.length; index += 1) {
      const scene = value.scenes[index];
      if (!scene) continue;
      const path = ["scenes", index] as const;
      if (scene.seq_index !== index + 1) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `seq_index must be ${index + 1}`,
          path: [...path, "seq_index"],
        });
      }
      if (seen.has(scene.scene_id)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "duplicate scene_id",
          path: [...path, "scene_id"],
        });
      }
      seen.add(scene.scene_id);
      if (scene.start_frame !== cursor) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `start_frame must be ${cursor}`,
          path: [...path, "start_frame"],
        });
      }
      cursor += scene.duration_frames;
    }
    if (cursor !== value.frame_count) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "frame_count must equal the sum of duration_frames",
        path: ["frame_count"],
      });
    }
  });

const SceneTimelineJsonSchema = z
  .object({
    fps: z.literal(REMOTION_ROOT.fps),
    visual_engine: z.enum(ENGINES),
    motif_component: z.enum(MOTIFS),
    prompt_mode: z.enum(PROMPT_MODES),
    still_2k_id: z.string().min(1).nullable(),
    anchor_id: z.string().min(1).nullable(),
    start_frame: z.number().int().nonnegative(),
    duration_frames: z.number().int().positive(),
  })
  .strict();

const PackSceneSchema = z
  .object({
    scene_id: z.string().min(1),
    episode_id: z.string().min(1),
    scene_plan_id: z.string().min(1),
    start_ms: z.number().int().nonnegative(),
    end_ms: z.number().int().positive(),
    timeline_spec_json: SceneTimelineJsonSchema,
  })
  .passthrough();

const GoldenPackSchema = z
  .object({
    pack_id: z.string().min(1),
    timeline_spec: EpisodeTimelineSchema,
    scenes: z.array(PackSceneSchema).min(1),
  })
  .passthrough();

export type SceneBeat = z.infer<typeof SceneBeatSchema>;
export type EpisodeTimeline = z.infer<typeof EpisodeTimelineSchema>;

export type RemotionComposition = {
  readonly id: typeof REMOTION_ROOT.id;
  readonly fps: typeof REMOTION_ROOT.fps;
  readonly width: typeof REMOTION_ROOT.width;
  readonly height: typeof REMOTION_ROOT.height;
  readonly durationInFrames: number;
};

export type GoldenPackParse = {
  readonly packId: string;
  readonly timeline: EpisodeTimeline;
  readonly composition: RemotionComposition;
};

export class TimelineContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TimelineContractError";
  }
}

export function assertRemotionRoot(container: { fps: number; width: number; height: number }): void {
  if (
    container.fps !== REMOTION_ROOT.fps ||
    container.width !== REMOTION_ROOT.width ||
    container.height !== REMOTION_ROOT.height
  ) {
    throw new TimelineContractError(
      `Remotion root is locked to ${REMOTION_ROOT.width}x${REMOTION_ROOT.height} @ ${REMOTION_ROOT.fps} fps, received ${container.width}x${container.height} @ ${container.fps} fps`,
    );
  }
}

export function remotionComposition(durationInFrames: number): RemotionComposition {
  if (!Number.isInteger(durationInFrames) || durationInFrames <= 0) {
    throw new TimelineContractError("Remotion durationInFrames must be a positive integer");
  }
  return {
    id: REMOTION_ROOT.id,
    fps: REMOTION_ROOT.fps,
    width: REMOTION_ROOT.width,
    height: REMOTION_ROOT.height,
    durationInFrames,
  };
}

export function configureRemotionRoot(requested: {
  fps?: number;
  width?: number;
  height?: number;
  durationInFrames: number;
}): RemotionComposition {
  assertRemotionRoot({
    fps: requested.fps ?? REMOTION_ROOT.fps,
    width: requested.width ?? REMOTION_ROOT.width,
    height: requested.height ?? REMOTION_ROOT.height,
  });
  return remotionComposition(requested.durationInFrames);
}

export function endScreenStartFrame(durationInFrames: number): number {
  const composition = remotionComposition(durationInFrames);
  return composition.durationInFrames - END_SCREEN_SECONDS * composition.fps;
}

export function isEndScreenFrame(frame: number, durationInFrames: number): boolean {
  if (!Number.isInteger(frame) || frame < 0) {
    throw new TimelineContractError("frame must be a non-negative integer");
  }
  return frame >= endScreenStartFrame(durationInFrames);
}

export function parseTimelineSpec(input: unknown): EpisodeTimeline {
  const timeline = EpisodeTimelineSchema.parse(input);
  assertRemotionRoot(timeline);
  return timeline;
}

export function parseGoldenPack(pack: unknown): GoldenPackParse {
  const parsed = GoldenPackSchema.parse(pack);
  const timeline = parseTimelineSpec(parsed.timeline_spec);
  if (parsed.scenes.length !== timeline.scenes.length) {
    throw new TimelineContractError("golden pack scenes must match timeline_spec.scenes");
  }
  const byId = new Map(parsed.scenes.map((scene) => [scene.scene_id, scene]));
  if (byId.size !== parsed.scenes.length) {
    throw new TimelineContractError("golden pack scene_id values must be unique");
  }
  for (const beat of timeline.scenes) {
    const scene = byId.get(beat.scene_id);
    if (!scene) throw new TimelineContractError(`timeline scene ${beat.scene_id} is missing from the pack`);
    const embedded = scene.timeline_spec_json;
    if (
      embedded.fps !== timeline.fps ||
      embedded.start_frame !== beat.start_frame ||
      embedded.duration_frames !== beat.duration_frames ||
      embedded.motif_component !== beat.motif_component ||
      embedded.visual_engine !== beat.visual_engine ||
      embedded.prompt_mode !== beat.prompt_mode
    ) {
      throw new TimelineContractError(`scene ${beat.scene_id} timeline_spec_json drifted from timeline_spec`);
    }
    if ((scene.end_ms - scene.start_ms) * timeline.fps !== beat.duration_frames * 1000) {
      throw new TimelineContractError(`scene ${beat.scene_id} duration_frames must match start_ms/end_ms at 30 fps`);
    }
  }
  return {
    packId: parsed.pack_id,
    timeline,
    composition: remotionComposition(timeline.frame_count),
  };
}
