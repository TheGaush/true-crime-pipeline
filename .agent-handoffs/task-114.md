# Task 114 Handoff

- Task: 114 `StickFigure` rig and fast JS boil consistency suite
- Branch: `task/114-stick-rig-consistency-suite`
- Worktree: `../tc-wt/task-114-stick-rig-consistency-suite` (this commit is on the primary clone; the sibling worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/tests/rig_consistency.test.tsx`, `.agent-handoffs/task-114.md`
- Dependencies added: none
- Verification: 9/9 passed offline. See below.
- Incomplete: `pnpm --filter @tc/render_catalog test -- rig_consistency` exits 0 without executing the suite. `@tc/render_catalog` has no `test` script, and `package.json` is outside this task. Root `vitest.config.mjs` includes `packages/**/*.test.ts` and does not collect this `.tsx` file.
- Notes for the next agent: import the rig from the Task 103–109 modules when those files are on the tree. This suite does not vendor them. `handcuffed` suppresses held props (`briefcase`, `flashlight`, `phone`, `document`) and emits `PRECEDENCE WARNING: handcuffed restrains both hands and suppresses held prop <id>`. Worn props stay attached.

Commit only on `task/114-stick-rig-consistency-suite`. Do not merge.

```
TC-Task-ID: 114
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`packages/render_catalog/tests/rig_consistency.test.tsx` certifies Layer 1:

- 14 poses (`idle` through `slumped`) × 10 emotions (`neutral` through `guilty`) = 140 pose-emotion permutations.
- Those 140 × 7 character props (`fedora`, `hoodie`, `badge`, `glasses`, `tie`, `scarf`, `briefcase`) = 980 combinations.
- Character id stays on the pose and emotion. Walk speed stays `96 px/s` and run speed stays `240 px/s`, signed by `L_TO_R` / `R_TO_L`, and `STATIC` is `0`. Other poses have no travel speed.
- RMS nod is `amplitude * 4.5` degrees and gesture bounce is `amplitude * 6` degrees on `NARRATION` only. `TWIST_PAD` and `FOIA_AUDIO_SLOT` stay at `0` on `ep_golden_01_20min` even when the envelope is `1`.
- JS boil ticks are `Math.floor(frame / 5)` at 30 fps (6 ticks per second). The same tick repeats. A closed polyline shares one seam perturbation inside `±1.4 px`. Markup is a `<path>` with no `<feTurbulence>`, `<feDisplacementMap>`, or `<filter>`.
- Paper plates are flat `#E9E2D2` with `paper_grain: 0` and `vignette: 0`. Two renders of the same combination match.
- The suite imports `scripts/vitest.setup.mjs`, scrubs provider keys, and rejects outbound `fetch`.

Tasks 101–113 are not copied onto this branch. When these files are present, the same tests call their exports:

- `packages/render_catalog/src/rig/StickPoses.ts`
- `packages/render_catalog/src/rig/StickEmotions.tsx`
- `packages/render_catalog/src/rig/StickProps.tsx`
- `packages/render_catalog/src/rig/LineBoilPath.tsx`
- `packages/render_catalog/src/rig/StickFigureGeometry.tsx` (its `BoilPath` import is rebound to the transpiled line-boil module)
- `packages/render_catalog/src/rig/useVoiceSyncMotion.ts`
- `packages/render_catalog/src/grade/GradeContract.tsx` (`useCaseBible()` is satisfied with `{ paperBgHex: "#E9E2D2" }` so the un-grained raster can run without React)
- `packages/render_catalog/src/index.ts` when it exports `REMOTION_ROOT` (`1920x1080 @ 30 fps`)

`task/111-kinetic-callout-subtitles`, `task/112-remotion-worker-pool-cache`, and `task/113-remotion-visual-regression` are not on `origin`. Any `packages/render_catalog/src/**/*.ts(x)` that does land is scanned for `<feTurbulence` and `<feDisplacementMap`.

## Verification

Standalone, with only the Task 001 `render_catalog` shell on the branch:

Root `vitest.config.mjs` does not collect `*.test.tsx`. Run the suite with an include override (this file is not part of the task commit; `artifacts/` is gitignored):

```js
import { defineConfig } from "vitest/config";

export default defineConfig({
  root: new URL("..", import.meta.url).pathname,
  test: {
    environment: "node",
    setupFiles: [new URL("../scripts/vitest.setup.mjs", import.meta.url).pathname],
    include: ["packages/render_catalog/tests/rig_consistency.test.tsx"],
  },
});
```

Save that as `artifacts/vitest.task114.mjs` and run:

```
pnpm exec vitest run --config artifacts/vitest.task114.mjs
```

```
✓ packages/render_catalog/tests/rig_consistency.test.tsx (9 tests) 244ms
Test Files  1 passed (1)
     Tests  9 passed (9)
```

The same 9 tests passed again (598ms, bind test 525ms) with the Task 103–109 sources checked out in the worktree and then removed before commit. Live `solvePose` speeds, emotion ids, prop sockets, boil ticks, RMS samples, locked bone length, and the un-grained `1920×1080` raster all matched this suite.

`pnpm --filter @tc/render_catalog test -- rig_consistency` exits 0 and prints nothing, because the package has no `test` script.

`node scripts/verify-harmony.mjs --task 114` still reports pre-existing model-id hits in Task 002 (`packages/shared_contracts/src/shared_contracts/models.py`, `deprecated.py`, and `packages/shared-contracts-ts/src/models.ts`). Those files were not edited here. Scope for this branch is the two owned paths.
