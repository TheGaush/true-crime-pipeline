# Task 120 Handoff

- Task: 120 Implement Motif #6 — `SmsPhoneThread`
- Branch: `task/120-motif-sms-phone-thread`
- Worktree: branch `task/120-motif-sms-phone-thread` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/motifs/SmsPhoneThread.tsx`, `packages/render_catalog/tests/motifs/sms_phone_thread.test.tsx`, `.agent-handoffs/task-120.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. No Part 2 PR was imported.
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Sms phone thread vitest: 7 passed. See the command below. `pnpm --filter @tc/render_catalog test -- sms_phone_thread` exits 0 and prints nothing, because the Task 001 shell has no `test` script.
- Incomplete: root `vitest.config.mjs` includes `packages/**/*.test.ts` only, so `pnpm exec vitest run sms_phone_thread` reports no files. `node scripts/verify-harmony.mjs --task 120` still reports pre-existing model-id hits in Task 002 sources (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files were not edited here.
- Notes for the next agent:

Commit only on `task/120-motif-sms-phone-thread`. Do not merge.

```
TC-Task-ID: 120
TC-Track: part2
TC-Never-Merge: true
```

## What landed

- `SmsPhoneThread` draws a dark evidence chat inside a phone bezel. Inbound bubbles sit on the left, outbound bubbles on the right, and the highlighted bubble uses an amber border. The status line reads `EVIDENCE SMS`.
- `<SafeZoneLayout>` is local to this file. The frame is `1920x1080`, `paddingTop` 108, `paddingBottom` 194, bottom-right exclusion `22%` by `14%`, `overflow: hidden`. The phone stays inside that content rect, off the caption bar, and off the end-screen card. Task 101's `safe_zone.tsx` was not copied.
- Ten or more messages that exceed the glass ease-scroll over 8 frames. The bezel and the screen both set `overflow: hidden`. Rows above the glass have no visible rect. The newest row is fully inside the screen once the ease finishes. A single frame never jumps the scroll by 32 px or more on the 12-message fixture.
- Typing dots show only inside a message's typing window. `typing_tap` cues use the 48 kHz mix clock (`1600` samples per 30 fps frame), a 40 ms envelope, and a 60 ms cooldown. Taps closer than 60 ms are dropped. A run denser than 12 cues in one second tapers gain. Nominal peak is `-12 dBTP`. Task 110's `SfxRegistry.ts` was not copied. Cue envelopes are shorter than the cooldown, so kept taps do not overlap.
- The golden fixture cites `ep_golden_01_20min` `temporal_fact_ledger` in time order: affidavit, porch-light clue, news report, ruling. Bodies are the ledger summaries. The clue bubble is the highlight.
- The frozen SQL catalog's sixth Remotion name remains `AnimatedMapRoute`. `MOTIF_REGISTRY_V1` remains the four MVP motifs. This component's id is `SmsPhoneThread`, motif number 6 for Task 120. `Illustrative2KPanZoom` is not implemented.

Run the motif tests with the zero-spend setup file. The include override is required because the owned test path is `.tsx`:

```
node --input-type=module -e 'import { startVitest } from "vitest/node"; const vitest = await startVitest("test", ["packages/render_catalog/tests/motifs/sms_phone_thread.test.tsx"], { include: ["packages/render_catalog/tests/motifs/sms_phone_thread.test.tsx"], setupFiles: ["./scripts/vitest.setup.mjs"], environment: "node", watch: false }); await vitest.close();'
```
