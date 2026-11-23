# Task 112 Handoff

- Task: 112 Headless Remotion 30 fps worker pool and `<5s` re-render cache
- Branch: `task/112-remotion-worker-pool-cache`
- Worktree: `../tc-wt/task-112-remotion-worker-pool-cache`
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/renderer/RenderPool.ts`
  - `packages/render_catalog/tests/render_pool.test.ts`
  - `.agent-handoffs/task-112.md`
- Dependencies added: none
- Verification: offline vitest, 15 passed; package typecheck passed
- Incomplete: no `@remotion/bundler` encode; package shell has no `test` script
- Notes for the next agent: import `RenderPool` from `packages/render_catalog/src/renderer/RenderPool.ts`. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 112
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`RenderPool` is an in-process headless pool (default concurrency 2) for `1920x1080 @ 30 fps`.

- `bundle()` runs once per pool. The default bundle records composition `TrueCrimeEpisode` and does not download Remotion or call a provider.
- Cache key is `SHA-256(canonical_scene_json + case_bible_hash)` with no separator. Object key order does not change the key. A scene edit or a different case-bible hash is a miss.
- Changed scenes are rendered with the JS 6 fps boil clock (`Math.floor(frame / 5)`, stride 5). Scene JSON that mentions `feTurbulence` or `feDisplacementMap` is rejected.
- The renderer must write `{cacheKey}.tmp.mp4`. ffprobe then checks `1920x1080`, `30 fps`, and `nb_frames` when the file reports it. Only a passing probe is renamed onto `{cacheKey}.mp4`.
- A leftover valid `.tmp.mp4` from an interrupted render is probed and renamed. The encoder is not called again. A corrupt tmp is deleted and rendered again.
- A single-scene render whose work time is `>= 5000 ms` is deleted and not published.
- Remotion stays ungraded: paper grain `0`, vignette `0`. `FOIA_REAL_FOOTAGE` and `FoiaFootageFrame` set `apply_grade` / `needs_grade` to false. Other engines set them to true. The sidecar is `{cacheKey}.grade.json`.
- Tasks 101, 103, and 109 are read when their modules are already on disk (`REMOTION_ROOT` from `src/index.ts`, `BOIL_FPS` / `CONTAINER_FPS` / `BOIL_FRAME_STRIDE` from `src/rig/LineBoilPath.tsx`, grade exports from `src/grade/GradeContract.tsx`). Those files are not in this branch. Until Task 101 exports `REMOTION_ROOT`, the pool uses the locked 30 fps root. A 60 fps root, a boil stride other than 5, or a non-zero `REMOTION_PAPER_GRAIN` throws before encode.
- The default encoder is local `ffmpeg` (flat ungrained plate, no grain or vignette filters) and the default probe is local `ffprobe`. Pass `render` and `bundle` to swap in Remotion. Child processes do not inherit provider API keys.

`ep_golden_01_20min` scene `ep_golden_01_20min_s012` (`StickmanStage`, `CODE_STICKMAN`, 1200 frames / 40s) is the headless benchmark.

## Dependencies

None. `packages/render_catalog/package.json` is outside this write scope, so Remotion, React, and Zod were not added. `ffmpeg` and `ffprobe` are local binaries.

## Verification

Offline. Provider keys stripped. No paid render and no provider HTTP call. Vitest setup blocks non-loopback sockets.

- `pnpm exec vitest run packages/render_catalog/tests/render_pool.test.ts` — 15 passed. The golden scene test (first render, cache hit, changed-scene re-render) completed in about 3.5s, and each receipt's `workMs` and `elapsedMs` were under 5000.
- `pnpm --filter @tc/render_catalog typecheck` — passed.
- `pnpm --filter @tc/render_catalog test -- render_pool` exits 0 without running this suite. The Task 001 shell has no `test` script.

`node scripts/verify-harmony.mjs --task 112` accepts the three owned paths when `main` is `c914ae5`. The model-id lint still fails on Task 002 sources already on main (`packages/shared_contracts`, `packages/shared-contracts-ts`). This branch does not change them.

## Incomplete

- The default plate is a local ungraded 1080p30 encode, not a Chromium Remotion frame. Task 131 is the hardware benchmark for a real JS-boil render. Pass `bundle` and `render` to call `@remotion/bundler` / `@remotion/renderer` once those packages are declared.
- The catalog `< 5.0s` figure remains a design target for a warm Chromium re-render. This task enforces that budget on the pool's own encode and refuses to publish a slower one.

## Notes for the next agent

Import from `packages/render_catalog/src/renderer/RenderPool.ts`. Do not copy Tasks 101, 103, or 109 into this branch. Commit only on `task/112-remotion-worker-pool-cache`. Do not merge.
