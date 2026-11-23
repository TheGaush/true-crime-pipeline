# Task 115 Handoff

- Task: 115 Implement MVP Motif #1 `StickmanStage`
- Branch: `task/115-motif-stickman-stage`
- Worktree: primary clone, branched from `c914ae5` (no sibling `../tc-wt/` worktree)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/motifs/StickmanStage.tsx`
  - `packages/render_catalog/tests/motifs/stickman_stage.test.tsx`
  - `.agent-handoffs/task-115.md`
- Dependencies added: none
- Verification: `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed. Vitest `stickman_stage` 11/11 passed with provider keys set in the environment (setup scrubbed them). Scope diff against `c914ae5` is the three owned paths.
- Incomplete: `safe_zone.tsx` is Task 101 and `StickFigureGeometry.tsx` is Task 104. Neither file is on this branch. `@tc/render_catalog` still has no `test` script, and root `vitest.config.mjs` includes `packages/**/*.test.ts` but not `*.test.tsx`. Both files are outside this task's write scope, so `pnpm --filter @tc/render_catalog test -- stickman_stage` cannot be wired here.
- Notes for the next agent: import `StickmanStage` and `solveStickmanStage` from `packages/render_catalog/src/motifs/StickmanStage.tsx`. Do not copy `SafeZoneLayout` or `StickFigureGeometry` onto this branch. Do not merge (`TC-Never-Merge: true`).

Commit only on `task/115-motif-stickman-stage`. Do not merge or change git config. This branch is pushed only because the task assignment asked for a PR.

```
TC-Task-ID: 115
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`StickmanStage` is MVP motif #1. It blocks 1–5 stick figures on one ground line inside Task 101's `SafeZoneLayout` and draws each figure through Task 104's `StickFigureGeometry`.

Six noir architectural presets, in registry order: `alley_night`, `precinct_hallway`, `interrogation_room`, `courthouse_steps`, `apartment_doorway`, `evidence_desk`. Each preset owns a ground line, a pose id (`walk_loop`, `seated`, `doorway_entry`, or `evidence_hold`), a camera-travel length, and a vector set (walls, doors, steps, jambs, desk). `STATIC` turns a walk or run pose into `idle` and holds the camera. Strokes are `currentColor`. The stage sets `apply-grade` / `needs-grade` so Agent 6 can grade the shot once. This file does not draw paper grain.

Screen pelvis centers stay at least `180px` apart. A bunched cast is pushed apart, then shifted back into the safe interval (`top 108`, `bottom 194`, horizontal inset `5 + 68 * scale`). Head circles use the locked rest rig (`headRadius 22`, torso `70`). Overlapping circles throw `HEAD_COLLISION`. A requested scale that cannot fit five figures shrinks until the safe band holds them.

The camera eases with a cubic ease-in-out along `travel_axis` (`L_TO_R` positive, `R_TO_L` negative, `STATIC` zero). Endpoint slope is 0. Figures track that camera, so screen gaps do not change during the shot and world x stays locked to `cameraWorldX`. A directional shot may follow another only on the same axis. `STATIC` is a hold. `previousAxis` plus a reversed axis throws `AXIS_CONTINUITY`. `chainCameraEntries` carries `exitWorldX` into the next entry without a teleport.

`ep_golden_01_20min` has 10 non-adjacent `CODE_STICKMAN` / `StickmanStage` scenes (1200 frames each). The cast is `narrator`, `defendant`, and `caller`. Presets cycle through all six. Travel axes cycle `L_TO_R`, `R_TO_L`, `STATIC`, and a consecutive `seq_index` pair would keep the same axis.

## Imports

```ts
import { SafeZoneLayout } from "../safe_zone.js";
import { StickFigureGeometry } from "../rig/StickFigureGeometry.js";
```

Both lines carry `@ts-expect-error` until the modules resolve (today that is TS2307). Delete each directive when `tsc` reports it unused. The motif test substitutes those bindings with `typescript.transpileModule`. It does not reimplement the safe-zone frame or the stick rig.

## Verification

Package typecheck passed:

```
pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit
```

Direct vitest (include override, repo zero-spend setup) passed 11/11. The override is not committed (root `vitest.config.mjs` is Task 001). Recreate it as `packages/render_catalog/vitest.stickman.config.mjs` with `root` set to that package, `setupFiles` pointing at `scripts/vitest.setup.mjs`, and `include: ['tests/motifs/stickman_stage.test.tsx']`, then:

```
pnpm exec vitest run --config packages/render_catalog/vitest.stickman.config.mjs
```

The run was started with `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, and `ELEVENLABS_API_KEY` set; the suite asserts those three are undefined after setup. No paid API calls.

`pnpm --filter @tc/render_catalog test -- stickman_stage` exits `0` and prints nothing. Task 001's package shell has no `test` script (only `typecheck`), so pnpm does not launch vitest. Root `vitest.config.mjs` includes `packages/**/*.test.ts` and not `*.test.tsx`. Both files are outside this task's write scope.

`pnpm --filter @tc/render_catalog typecheck` passed.

`node scripts/verify-harmony.mjs --task 115` accepted the 3 owned paths, secrets, diagrams, and `schema/schema-test.js`. The model-id lint still reports Task 002 contract lines (`gemini-omni`, `VEO_3_1_LITE`, `vertex-veo-enterprise`) in `packages/shared_contracts/src/shared_contracts/deprecated.py`, `packages/shared_contracts/src/shared_contracts/models.py`, and `packages/shared-contracts-ts/src/models.ts`. This task did not touch those files.
