# Task 116 Handoff

- Task: 116 Implement Extended 2D Motif #5 — `TimelineScrubber`
- Branch: `task/116-motif-timeline-scrubber`
- Worktree: branch `task/116-motif-timeline-scrubber` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/motifs/TimelineScrubber.tsx`, `packages/render_catalog/tests/motifs/timeline_scrubber.test.tsx`, `.agent-handoffs/task-116.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. No Part 2 PR was imported.
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Timeline scrubber vitest: 5 passed. See the command below. `pnpm --filter @tc/render_catalog test -- timeline_scrubber` exits 0 and prints nothing, because the Task 001 shell has no `test` script.
- Incomplete: root `vitest.config.mjs` includes `packages/**/*.test.ts` only, so `pnpm exec vitest run timeline_scrubber` reports no files. `node scripts/verify-harmony.mjs --task 116` still reports pre-existing model-id hits in Task 002 sources (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files were not edited here.
- Notes for the next agent:

Commit only on `task/116-motif-timeline-scrubber`. Do not merge.

```
TC-Task-ID: 116
TC-Track: part2
TC-Never-Merge: true
```

## What landed

- `TimelineScrubber` draws a date scrub bar and an hour scrub bar for `fact_ledger` milestones (`fact_id`, `datetime_iso`, `event_summary`). Pins are sorted chronologically and carry `data-fact-id`.
- `<SafeZoneLayout>` is local to this file. The frame is `1920x1080`, `paddingTop` 108, `paddingBottom` 194, bottom-right exclusion `22%` by `14%`, `overflow: hidden`. Label boxes stay inside that content rect and off the caption bar.
- Multi-year jumps (the `2018 -> 2023` fixture, and `ep_golden_01_20min`) keep a minimum gap between pin labels and give leftover width to the real time gap. A pure linear axis overlaps those labels; the compressed axis does not. Date ticks coarsen to years on spans of 366 days or more, and overlapping tick labels are dropped. `RULE_07` clamps every on-screen label and the stored summary to 12 words.
- `Illustrative2KPanZoom` is not implemented. `assertExtendedMotifOwnership` rejects that row (`crime_scene_2k`) and accepts the golden `motif_registry_v1` row for `TimelineScrubber` (`render_catalog`, `is_mvp_4` 0). The frozen TypeScript `MOTIF_REGISTRY_V1` constant stays the four MVP motifs.

Run the scrubber tests with the zero-spend setup file. The include override is required because the owned test path is `.tsx`:

```
node --input-type=module -e 'import { startVitest } from "vitest/node"; const vitest = await startVitest("test", ["packages/render_catalog/tests/motifs/timeline_scrubber.test.tsx"], { include: ["packages/render_catalog/tests/motifs/timeline_scrubber.test.tsx"], setupFiles: ["./scripts/vitest.setup.mjs"], environment: "node", watch: false }); await vitest.close();'
```
