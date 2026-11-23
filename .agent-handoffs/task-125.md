# Task 125 Handoff

- Task: 125 Implement Motif #11 — `AlibiSplitScreen`
- Branch: `task/125-motif-alibi-split-screen`
- Worktree: branch `task/125-motif-alibi-split-screen` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch. PR https://github.com/TheGaush/true-crime-pipeline/pull/29 to `main`. Not merged.
- Owned paths touched: `packages/render_catalog/src/motifs/AlibiSplitScreen.tsx`, `packages/render_catalog/tests/motifs/alibi_split_screen.test.tsx`, `.agent-handoffs/task-125.md`
- Dependencies added: none. Task 110 and Task 114 were not imported. Their files were not copied. `packages/render_catalog/package.json` is outside this task.
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Alibi split vitest: 7 passed. See the command below. `pnpm --filter @tc/render_catalog test -- alibi_split_screen` exits 0 and prints nothing, because the Task 001 shell has no `test` script.
- Incomplete: root `vitest.config.mjs` includes `packages/**/*.test.ts` only, so `pnpm exec vitest run alibi_split_screen` reports no files. `node scripts/verify-harmony.mjs --task 125` still reports pre-existing model-id hits in Task 002 sources (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files were not edited here.
- Notes for the next agent:

Do not merge this branch.

```
TC-Task-ID: 125
TC-Track: part2
TC-Never-Merge: true
```

## What landed

- `AlibiSplitScreen` draws a suspect claim on the left and a primary record on the right. The claim accepts `suspect_statement` or `news_report`. The evidence accepts `police_affidavit` or `court_ruling`. The two panes must cite different facts. Body copy is clamped to 12 words.
- The crimson `CONFLICT` stamp (`#C92A2A`) appears on the 30 fps frame that contains `stampAtMs`. The single `conflict_stamp` cue keeps that integer millisecond: `start_sample = stampAtMs * 48` at 48 kHz. For the golden word "claim" that is `2746 ms`, sample `131808`, frame `82`. Frame 82 starts at sample `131200`, so the cue does not snap to the frame boundary. Duration is `400 ms` (`19200` samples) at `-6 dBTP` (`501187233` gain units), under the `-1.0 dBTP` ceiling. One stamp per scene, so the envelope does not stack. Task 110's `SfxRegistry.ts` was not copied.
- Shake is `translate()` on the inner graphic only. The safe-zone frame has no transform. Peak distance is clamped to `6 px`, and the graphic is inset `6 px` from the content rect (`paddingTop` 108, `paddingBottom` 194, bottom-right exclusion `22%` by `14%`). A requested `80 px` shake still lands on `6 px` and stays out of the caption bar, the exclusion box, and the end-screen mask. `<SafeZoneLayout>` is local to this file. Task 101's `safe_zone.tsx` was not copied.
- The golden turning point is scene 12 in all three packs. `turning_point_count` is 4. The narrator says "claim" at `292746 ms`. The hedged news fact is the claim. The porch-light affidavit is the primary record.
- The frozen SQL catalog's eleventh Remotion name remains `EvidenceGridMatrix`. Slot 8 remains `SplitScreenComparison`. `MOTIF_REGISTRY_V1` remains the four MVP motifs. This component's id is `AlibiSplitScreen`, motif number 11 for Task 125. `Illustrative2KPanZoom` is not implemented.

Run the motif tests with the zero-spend setup file. The include override is required because the owned test path is `.tsx`:

```
node --input-type=module -e 'import { startVitest } from "vitest/node"; const vitest = await startVitest("test", ["packages/render_catalog/tests/motifs/alibi_split_screen.test.tsx"], { include: ["packages/render_catalog/tests/motifs/alibi_split_screen.test.tsx"], setupFiles: ["./scripts/vitest.setup.mjs"], environment: "node", watch: false }); await vitest.close();'
```
