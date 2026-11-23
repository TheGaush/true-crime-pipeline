/**
 * Remotion workspace root for `@tc/render_catalog`.
 * Compositions stay on 1920x1080 at 30 fps. A 60 fps root is rejected.
 *
 * `<SafeZoneLayout>` lives in `./safe_zone.tsx`. This entry does not import it
 * because the package tsconfig has no `jsx` option.
 */
export {
  END_SCREEN_SECONDS,
  EpisodeTimelineSchema,
  REMOTION_ROOT,
  SceneBeatSchema,
  TimelineContractError,
  assertRemotionRoot,
  configureRemotionRoot,
  endScreenStartFrame,
  isEndScreenFrame,
  parseGoldenPack,
  parseTimelineSpec,
  remotionComposition,
} from "./parser.js";

export type { EpisodeTimeline, GoldenPackParse, RemotionComposition, SceneBeat } from "./parser.js";
