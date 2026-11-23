# Task 119 Handoff

- Task: 119 — Motif #5 `HeroVideoBridge`
- Branch: `task/119-motif-hero-video-bridge`
- Worktree: `../tc-wt/task-119-motif-hero-video-bridge`
- Track: Part 2
- Status: Implemented on this branch. Not merged.
- Owned paths touched:
  - `packages/render_catalog/src/motifs/HeroVideoBridge.tsx`
  - `packages/render_catalog/tests/motifs/hero_video_bridge.test.tsx`
  - `.agent-handoffs/task-119.md`
- Dependencies added: none. No `package.json` or lockfile edits. Remotion and React are not imported.
- Verification:
  - `pnpm exec vitest run --config vitest.hero.config.mjs` — 12 tests passed. The temp config only adds `packages/render_catalog/tests/motifs/hero_video_bridge.test.tsx` to the include list (root `vitest.config.mjs` lists `*.test.ts`, not `*.tsx`) and loads `scripts/vitest.setup.mjs` (provider keys stripped, outbound sockets blocked except loopback). The temp config was not committed.
  - `pnpm --filter @tc/render_catalog typecheck` passed.
  - `pnpm --filter @tc/render_catalog test -- hero_video_bridge` exits 0 without running a script. `@tc/render_catalog` has no `test` script; that shell belongs to Task 001 and is outside this write scope.
  - `node scripts/verify-harmony.mjs --task 119` accepts the owned paths. It still reports pre-existing model-id literals in the frozen Task 002 contracts (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files are not in this diff.
- Incomplete:
  - Task 109's `packages/render_catalog/src/grade/GradeContract.tsx` is not on this branch. `HeroVideoBridge` imports `sceneNeedsGrade`.
  - Task 115's `packages/render_catalog/src/motifs/StickmanStage.tsx` is not on this branch. A `CODE_STICKMAN` / `StickmanStage` fallback calls that named export.
  - A Chromium Remotion render is not part of this task. The package shell does not depend on `remotion`, and `package.json` is outside the owned write scope. The bridge returns a plain element descriptor.
- Notes for the next agent:

Base commit is `c914ae5` (Tasks 001–004). This branch does not reimplement those tasks and does not copy Tasks 109 or 115.

`HeroVideoBridge()` resolves one Flow hero scene:

- `ACCEPTED` plays a local relative MP4. `720p` (`1280x720`) is scaled uniformly by `1.5` onto `1920x1080` (`conform: "720p->1080p"`, `objectFit: "fill"`). An already `1080p` source stays `1:1`. `360p` and `4k` are refused.
- Surplus media is trimmed at `1.0x`. A `7.6s` scene (`7600` ms) with an `8.0s` clip (`8000` ms) sets `trimEndMs` to `7600`, `playbackRate` to `1`, `discardedTailMs` to `400`, and `trimEndFrame` to `228`. `7601` ms stays `7601` and `trimEndFrame` is `null` so the cut is not snapped to a frame. The `8000/7600` ratio sits inside `1.15x` and is not used.
- A shorter clip slows to `clipMs/sceneMs` only when that fraction is inside `0.85x–1.15x` (integer hundredths). `6800/8000` is the floor. `6799/8000` throws `HERO_SPEED_BOUNDS`. The bridge never speeds a clip up.
- `SWITCHED_TO_FALLBACK` ignores any supplied clip, keeps `duration_ms`, sets `data-gap-ms` to `0`, and mounts `fallback_spec`. The engine must differ from `prev_engine` and from `next_engine` (`RULE_04`). `FLOW_HERO_VIDEO` cannot be its own fallback. A fallback `sceneNeedsGrade` marks false (FOIA) throws `SINGLE_GRADE`.
- Golden `ep_golden_02_2strike_fallback` scene `s029` is the strike-2 case: neighbors are `CODE_STICKMAN`, fallback is `STILL_2K_PANZOOM` / `Illustrative2KPanZoom` with `still_02` and `anchor_004`. The other nine hero jobs are eight `ACCEPTED` plays and one `STRIKE_1_RETRY_SAFE` withhold. Strike 1 does not play and does not switch. Fallback objects may use `engine` (golden pack) or `visual_engine` (v4 `FallbackSpec`).
- Accepted and stylized fallback plates set `apply_grade` and `needs_grade` true, `paper_grain` 0, `vignette` 0, `remotion_grain_applied` false, and `children` null. Agent 6 owns the single grade pass. `CODE_STICKMAN` + `StickmanStage` delegates to Task 115 with `{ scene_id, episode_id, duration_ms, from_fallback: true }`. Other code motifs switch without that delegate. `Illustrative2KPanZoom` stays owned by `crime_scene_2k`; this bridge only names `still_2k_id` and `anchor_id`.

The hero test writes `TC-TASK-119-TEST-STUB` doubles for GradeContract and StickmanStage only when those files are missing or still contain that marker, then deletes them. It does not overwrite a real Task 109 or Task 115 module. If the real grade module is present and Task 102's theme module is missing, the test installs a `useCaseBible` double the same way. Do not commit those doubles.

```
TC-Task-ID: 119
TC-Track: part2
TC-Never-Merge: true
```
