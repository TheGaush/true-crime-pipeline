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

export {
  CODE_STICKMAN,
  MVP_MOTIF_IDS,
  RENDER_REPORT_FILENAME,
  SCENE_GRADE_MANIFEST_FILENAME,
  RenderCatalogCliError,
  cliMain,
  parseRenderCatalogArgv,
  runRenderCatalog,
  toFailure,
} from "./cli.js";

export type { RenderCatalogArgs, RenderCatalogFailure, RenderCatalogReport, RenderedSceneReport } from "./cli.js";
