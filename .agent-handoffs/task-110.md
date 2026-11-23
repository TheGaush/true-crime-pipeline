# Task 110 Handoff

- Task: 110 Implement Built-In Micro-SFX Trigger Dispatcher
- Branch: `task/110-micro-sfx-dispatcher`
- Worktree: branch `task/110-micro-sfx-dispatcher` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/sfx/SfxRegistry.ts`, `packages/render_catalog/tests/sfx.test.ts`, `.agent-handoffs/task-110.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task.
- Verification: `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` and `pnpm exec vitest run packages/render_catalog/tests/sfx.test.ts` (13 passed).
- Incomplete: `pnpm --filter @tc/render_catalog test -- sfx` exits 0 without running tests, because the Task 001 shell has no `test` script.
- Notes for the next agent:

Commit only on `task/110-micro-sfx-dispatcher`. Do not merge.

```
TC-Task-ID: 110
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`dispatchMicroSfx` emits `MicroSfxCue[]` for Agent 6 at 48 kHz. The eight cues are `typing_tap`, `highlighter_glide`, `camera_shutter`, `pin_thud`, `conflict_stamp`, `tick_sfx`, `radio_squelch`, and `tape_click`.

Timestamps are integer mix samples. A frame on the 30 fps clock is `frame * 1600` samples. An integer millisecond is `offsetMs * 48` samples. A cue at 60 ms stays on sample 2880, inside frame 1, and is not rounded out to frame 2 (sample 3200). `cue_id` is `${sceneId}:${cue}:${start_sample}`.

More than 12 requested cues in any 1 second window is a burst. Emitted cues must be at least 60 ms (2880 samples) apart; closer requests are dropped and are not in the Agent 6 JSON. Burst cues taper by right-shifting their gain units (full, 1/2, 1/4, …). Overlapping envelopes are also clamped so the summed gain stays at or below -1.0 dBTP (891250938 / 1000000000). The same input always exports the same JSON. Sort order is sample, then registry order, then scene id, then input order.

Import `dispatchMicroSfx` and `exportMicroSfxCues` from `packages/render_catalog/src/sfx/SfxRegistry.ts`. This task does not edit `src/index.ts`. The module imports that file and reads `REMOTION_ROOT` when Task 101 has exported it. Until that lands, pass `clock: { fps: 30, width: 1920, height: 1080 }`. A clock that disagrees with `REMOTION_ROOT`, and a 60 fps root, both throw `SfxDispatchError`.

Agent 6 should place each cue at `start_sample` and scale it by `gain_units / gain_unit_scale`. Skip `gain_units === 0`. The duration and nominal dBTP on each definition are this dispatcher's peak-occupancy envelope, not the Task 137 WAV synthesizer.

`node scripts/verify-harmony.mjs --task 110` accepts these three paths. The same command still fails on pre-existing model-id hits in Task 002 sources (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files were not edited here. Tests run under the repo vitest setup, which strips provider API keys and blocks non-loopback sockets. No paid API calls.
