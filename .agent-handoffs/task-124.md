# Task 124 Handoff

- Task: 124 Implement Motif #10 `CaseBoardSpine`
- Branch: `task/124-motif-case-board-spine`
- Worktree: primary clone, branched from `c914ae5` (no sibling `../tc-wt/` worktree)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/motifs/CaseBoardSpine.tsx`
  - `packages/render_catalog/tests/motifs/case_board_spine.test.tsx`
  - `.agent-handoffs/task-124.md`
- Dependencies added: none
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Direct vitest `case_board_spine` 9/9 passed with provider keys set in the environment (setup scrubbed them). Scope diff against `c914ae5` is the three owned paths.
- Incomplete: `safe_zone.tsx` is Task 101 and `src/sfx/SfxRegistry.ts` is Task 110. Neither file is on this branch. Task 114 is a stick-rig certification suite and does not export a module this board draws. `@tc/render_catalog` still has no `test` script, and root `vitest.config.mjs` includes `packages/**/*.test.ts` but not `*.test.tsx`. Both files are outside this task's write scope, so `pnpm --filter @tc/render_catalog test -- case_board_spine` cannot be wired here.
- Notes for the next agent: import `CaseBoardSpine`, `solveCaseBoardSpine`, and `snapCaseBoardReset` from `packages/render_catalog/src/motifs/CaseBoardSpine.tsx`. Do not copy `SafeZoneLayout` or `SfxRegistry` onto this branch. Do not merge (`TC-Never-Merge: true`).

Commit only on `task/124-motif-case-board-spine`. Do not merge or change git config. This branch is pushed only because the task assignment asked for a PR.

```
TC-Task-ID: 124
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`CaseBoardSpine` is motif 10. The SQL registry still lists that name after `SplitScreenComparison`. This file does not amend `MOTIF_REGISTRY_V1`.

The board is a 2-row corkboard inside Task 101's `SafeZoneLayout`. It holds 1–16 clue polaroids. Column count is `ceil(count / 2)`, so 3 clues use 2 columns, 8 use 4, and the Act 3 board of 16 uses 8. Cards, captions, rest pins, pin-drop circles, and crimson string bounds stay inside the safe content box (`top 108`, `bottom 194`) and out of the bottom-right 22% by 14% exclusion. A label or end-screen flag reserves the 144.9px caption slot so the lower row does not sit under it. Labels clamp at 12 words. Card geometry does not grow with the caption.

Each pin drops 18px and lands at frame `8 + index * 3` (100ms apart, past the 60ms cooldown). `dispatchMicroSfx` receives one `pin_thud` per clue on the `1920x1080 @ 30 fps` clock. The spine is a straight crimson `#C92A2A` path from pin i to pin i+1, drawn with `stroke-dashoffset` after the later pin lands. The camera eases from `1.65` to `1` across 150 frames (5 seconds). Frame 149 is the settled wide board. Strokes are plain paths. `apply-grade` / `needs-grade` are set so Agent 6 grades the shot once. This file does not draw paper grain or SVG turbulence filters.

`snapCaseBoardReset` places that 5-second shot on a completed scene, sentence, or call end. Window 1 is `210000–270000` ms, nominal `240000`. A 911 call from `230000` (3:50) to `255000` (4:15) snaps to `255000` instead of `240000`. A span that covers the nominal time and does not finish inside the window throws `BOUNDARY`. Later windows repeat every `240000` ms with the same ±30s flex.

## Imports

```ts
import { SafeZoneLayout } from "../safe_zone.js";
import { dispatchMicroSfx } from "../sfx/SfxRegistry.js";
```

Both lines carry `@ts-expect-error` until the modules resolve (today that is TS2307). Delete each directive when `tsc` reports it unused. The motif test substitutes those bindings with `typescript.transpileModule`. It does not reimplement the safe-zone frame or the SFX dispatcher.

## Verification

Package typecheck passed:

```
pnpm --filter @tc/render_catalog typecheck
```

Direct vitest (include override, repo zero-spend setup) passed 9/9. The override is not committed (root `vitest.config.mjs` is Task 001). Recreate it as `packages/render_catalog/vitest.case-board.config.mjs` with `setupFiles` pointing at `scripts/vitest.setup.mjs` and `include: ['packages/render_catalog/tests/motifs/case_board_spine.test.tsx']`, then:

```
pnpm exec vitest run --config packages/render_catalog/vitest.case-board.config.mjs
```

The run was started with `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, and `ELEVENLABS_API_KEY` set; the suite asserts those three are undefined after setup. No paid API calls.

`pnpm --filter @tc/render_catalog test -- case_board_spine` exits `0` and prints nothing. Task 001's package shell has no `test` script (only `typecheck`), so pnpm does not launch vitest. Root `vitest.config.mjs` includes `packages/**/*.test.ts` and not `*.test.tsx`. Both files are outside this task's write scope.

`node scripts/verify-harmony.mjs --task 124` accepts the owned paths, secrets, diagrams, and `schema/schema-test.js`. The model-id lint still reports Task 002 contract lines (`gemini-omni`, `VEO_3_1_LITE`, `vertex-veo-enterprise`) in `packages/shared_contracts/src/shared_contracts/deprecated.py`, `packages/shared_contracts/src/shared_contracts/models.py`, and `packages/shared-contracts-ts/src/models.ts`. This task did not touch those files.
