# Task 106 Handoff

- Task: 106
- Branch: `task/106-stick-figure-14-poses`
- Worktree: `../tc-wt/task-106-stick-figure-14-poses`
- Track: Part 2
- Status: implemented, tests passed, not merged
- Owned paths touched:
  - `packages/render_catalog/src/rig/StickPoses.ts`
  - `packages/render_catalog/tests/stick_poses.test.tsx`
  - `.agent-handoffs/task-106.md`
- Dependencies added: none
- Verification: `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed. Vitest 214/214 passed (see below). Scope diff is the three owned paths against `c914ae5`.
- Incomplete: `@tc/render_catalog` still has no `test` script, and root `vitest.config.mjs` includes `packages/**/*.test.ts` but not `*.test.tsx`. Both files are outside this task's write scope, so `pnpm --filter @tc/render_catalog test -- stick_poses` cannot be wired here.
- Notes for the next agent: import `STICK_POSES` from `StickPoses.ts`. Do not merge this branch (`TC-Never-Merge: true`).

Commit only on the task branch. Do not merge or change git config. This branch is pushed only because the task assignment asked for a PR.

```
TC-Task-ID: 106
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`StickPoses.ts` is a pure solver. It does not render bones and does not import Task 104/105 modules.

Locked order (`idle` through `slumped`):

`idle`, `walk_loop`, `run_loop`, `pointing`, `seated`, `evidence_hold`, `doorway_entry`, `listening`, `writing`, `phone_call`, `arms_crossed`, `handcuffed`, `kneeling`, `slumped`

Joint degrees, right-facing canonical space: `torsoLean`, `headTilt`, `shoulderL`, `shoulderR`, `elbowL`, `elbowR`, `hipL`, `hipR`, `kneeL`, `kneeR`. `0` is upright / arm or leg hanging / elbow and knee straight. Positive shoulders and hips swing forward. Positive elbows and knees bend. `travel_axis: "R_TO_L"` sets `facing = -1` and does not rewrite those angles.

`walk_loop` stride is `96 px/s` over an `800 ms` cycle (`76.8 px`). `run_loop` is `240 px/s` over `450 ms` (`108 px`). `L_TO_R` is positive, `R_TO_L` is the negation, `STATIC` keeps phase and velocity at `0` so the legs do not cycle in place. Other poses always have velocity `0`.

Every ordered pair, including self-transitions, blends angles and velocity with a cubic ease-in-out for `300 ms` (`9` frames at `30 fps`). Endpoint slope is `0`. `requestPose` snapshots the current sample, so a retarget during a blend does not pop. Asking for the pose already settled is a no-op and keeps the phase clock.

Task 133's `walking` id is not in this enum. Use `walk_loop`. `idle`, `pointing`, `seated`, `evidence_hold`, and `doorway_entry` match that list. `handcuffed` is here for the Task 114 precedence case.

## Verification

Package typecheck passed:

```
pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit
```

Direct vitest (include override, repo zero-spend setup) passed 214/214:

```
pnpm exec vitest run --config /tmp/vitest.stick-poses.config.mjs
```

That config pointed `include` at `packages/render_catalog/tests/stick_poses.test.tsx` and loaded `scripts/vitest.setup.mjs`. The run blocked `http://example.com` with `ZERO_SPEND_GUARD` and saw no `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, or `ELEVENLABS_API_KEY`. No paid API calls.

`pnpm --filter @tc/render_catalog test -- stick_poses` exits `0` and prints nothing. Task 001's package shell has no `test` script (only `typecheck`), so pnpm does not launch vitest. Root `vitest.config.mjs` includes `packages/**/*.test.ts` and not `*.test.tsx`. Both files are outside this task's write scope.

`node scripts/verify-harmony.mjs --task 106` against local `main` at `4ab4cd3` reports the whole Task 002–004 tree as out of scope, because that ref is behind `origin/main` (`c914ae5`). Diffed against `c914ae5`, the scope check is the three owned paths. The model-id scan still fails on frozen Task 002 literals in `packages/shared_contracts` and `packages/shared-contracts-ts` (`gemini-omni`, `VEO_3_1_LITE`). Those lines are not part of this diff.
