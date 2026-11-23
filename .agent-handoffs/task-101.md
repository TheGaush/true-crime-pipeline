# Task 101 Handoff

- Task: 101 Bootstrap Remotion `30 fps` workspace, Zod parser, and CSS safe-zone frame
- Branch: `task/101-remotion-30fps-css-safezone`
- Worktree: branch `task/101-remotion-30fps-css-safezone` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/index.ts`, `packages/render_catalog/src/parser.ts`, `packages/render_catalog/src/safe_zone.tsx`, `packages/render_catalog/tests/parser.test.ts`, `.agent-handoffs/task-101.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. Zod is imported from the Task 002 install at `packages/shared-contracts-ts/node_modules/zod` (`zod@3.25.76`).
- Verification: `pnpm exec vitest run packages/render_catalog/tests/parser.test.ts` (3 passed) and `pnpm --filter @tc/render_catalog typecheck`.
- Incomplete: `pnpm --filter @tc/render_catalog test -- parser` exits 0 without running tests, because the Task 001 shell has no `test` script. `remotion` and `react` are not dependencies, and `tsconfig` has no `jsx` flag, so `<SafeZoneLayout>` is a React-style element tree rather than JSX.
- Notes for the next agent:

Commit only on `task/101-remotion-30fps-css-safezone`. Do not merge.

```
TC-Task-ID: 101
TC-Track: part2
TC-Never-Merge: true
```

## What landed

- Remotion root lock: `1920x1080` at `30 fps` (`REMOTION_ROOT`, `configureRemotionRoot`). A `60 fps` root throws `TimelineContractError`. The final 20 seconds start at `durationInFrames - 600`.
- Zod parser (`EpisodeTimelineSchema`, `.strict()`) for the episode `timeline_spec` and `parseGoldenPack` for `fixtures/golden_manifests/ep_golden_01_20min`. Frames are contiguous, `frame_count` is the sum of `duration_frames`, and each scene's `timeline_spec_json` matches its millisecond span at 30 fps. `ep_golden_01_20min` is 36 scenes and 36000 frames.
- `<SafeZoneLayout isEndScreen>` is a CSS grid frame with a flex content slot. `paddingTop` is `108`, `paddingBottom` is `194`, and the bottom-right exclusion box is `22%` by `14%`. A 3-line label uses `overflow: hidden`, `WebkitLineClamp: 3`, and `font-size` / `max-height` clamps so the box stays above the caption bar. `isEndScreen` adds an end-screen card mask inset from that same right edge.

Import the parser from `packages/render_catalog/src/index.ts`. Import `SafeZoneLayout` from `packages/render_catalog/src/safe_zone.tsx`. In-package relative imports use a `.js` specifier so `tsc` accepts them under `NodeNext` without `allowImportingTsExtensions`.

`node scripts/verify-harmony.mjs --task 101` still reports pre-existing model-id hits in Task 002 sources (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files were not edited here.
