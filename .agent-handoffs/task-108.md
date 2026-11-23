# Task 108 Handoff

- Task: 108
- Branch: `task/108-amplitude-nod-sync`
- Worktree: primary checkout on `task/108-amplitude-nod-sync` (runbook path `../tc-wt/task-108-amplitude-nod-sync` was not created)
- Track: Part 2
- Status: implemented, tests passed, not merged
- Owned paths touched:
  - `packages/render_catalog/src/rig/useVoiceSyncMotion.ts`
  - `packages/render_catalog/tests/voice_sync_motion.test.tsx`
  - `.agent-handoffs/task-108.md`
- Dependencies added: none copied. Runtime imports of Task 106 `StickPoses.ts` (`STICK_POSES`) and Task 107 `StickEmotions.tsx`.
- Verification: package typecheck passed. Vitest 7/7 passed (see below). Scope diff is the three owned paths against `c914ae5`.
- Incomplete: `@tc/render_catalog` still has no `test` script, and root `vitest.config.mjs` includes `packages/**/*.test.ts` but not `*.test.tsx`. Both files are outside this task's write scope, so `pnpm --filter @tc/render_catalog test -- voice_sync_motion` cannot be wired here. Task 107's branch was not on `origin` when this branch was cut, so `StickEmotions.tsx` is imported by filename and not called.
- Notes for the next agent: add `nodPitchDeg` to `headTilt` and `gestureBounceDeg` to the active shoulder. Do not merge this branch (`TC-Never-Merge: true`).

Commit only on the task branch. Do not merge or change git config. This branch is pushed only because the task assignment asked for a PR.

```
TC-Task-ID: 108
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`useVoiceSyncMotion` samples `VoiceTrackManifest.amplitude_envelope[]` at 30 fps (`Math.round` of the frame, then `floor(index * 1000 / 30)` milliseconds).

During `NARRATION` the sample scales two offsets:

- `nodPitchDeg = amplitude * 4.5` added to Task 106 `headTilt` (positive is forward; slumped is +38)
- `gestureBounceDeg = amplitude * 6` added to the shoulder with the larger absolute angle, `shoulderR` on a tie

`TWIST_PAD` and `FOIA_AUDIO_SLOT` force amplitude, nod, and bounce to exact `0` even when the envelope slot is `1`. A frame index outside the envelope is also `0` (the index is not clamped onto a neighbor sample). Non-finite samples are `0`. Finite samples above `1` clamp to `1` before scaling. Unknown segment kinds and timeline gaps stay at `0`.

`importStickPoses()` loads `./StickPoses.ts` and requires `STICK_POSES`. `importStickEmotions()` loads `./StickEmotions.tsx`. Neither file is in this commit. `origin/task/106-stick-figure-14-poses` (`6588b3f`) was read for the joint names only.

## Verification

Package typecheck passed:

```
pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit
```

Direct vitest (include override, repo zero-spend setup) passed 7/7:

```
pnpm exec vitest run --config vitest.voice.config.mjs
```

That config pointed `include` at `packages/render_catalog/tests/voice_sync_motion.test.tsx` and loaded `scripts/vitest.setup.mjs`. The run blocked `http://example.com/voice` with `ZERO_SPEND_GUARD` and saw no `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, or `ELEVENLABS_API_KEY`. No paid API calls.

The suite covers contract vector `v021`, all three `fixtures/golden_manifests/ep_golden_*` voice tracks (1,200,000 ms, identical segment timelines), hot envelopes on silence pads, and pose channels for `pointing` (`shoulderR`) and `phone_call` (`shoulderL`).

`pnpm --filter @tc/render_catalog test -- voice_sync_motion` exits `0` and prints nothing. Task 001's package shell has no `test` script (only `typecheck`), so pnpm does not launch vitest. Root `vitest.config.mjs` includes `packages/**/*.test.ts` and not `*.test.tsx`. Both files are outside this task's write scope.

`node scripts/verify-harmony.mjs --task 108` against local `main` at `c914ae5` checks the owned paths. The model-id scan still fails on frozen Task 002 literals in `packages/shared_contracts` and `packages/shared-contracts-ts` (`gemini-omni`, `VEO_3_1_LITE`). Those lines are not part of this diff.
