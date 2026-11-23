# Task 123 Handoff

- Task: 123 Implement Motif #9 — `TimelineDateScrubber`
- Branch: `task/123-motif-timeline-date-scrubber`
- Worktree: branch `task/123-motif-timeline-date-scrubber` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/motifs/TimelineDateScrubber.tsx`, `packages/render_catalog/tests/motifs/timeline_date_scrubber.test.tsx`, `.agent-handoffs/task-123.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. Task 110 and Task 114 were not imported and their files were not copied.
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Timeline date scrubber vitest: 7 passed. `pnpm --filter @tc/render_catalog test -- timeline_date_scrubber` exits 0 and prints nothing, because the Task 001 shell has no `test` script.
- Incomplete: root `vitest.config.mjs` includes `packages/**/*.test.ts` only, so `pnpm exec vitest run timeline_date_scrubber` reports no files. `node scripts/verify-harmony.mjs --task 123` still reports pre-existing model-id hits in Task 002 sources (`packages/shared_contracts/src/shared_contracts/models.py`, `packages/shared_contracts/src/shared_contracts/deprecated.py`, and `packages/shared-contracts-ts/src/models.ts`). Those files were not edited here. Scope, secrets, the diagram check, and `node schema/schema-test.js` passed. The frozen SQL `motif_registry` and `CATALOG_MOTIFS` still do not list `TimelineDateScrubber` (catalog slot 9 remains `CaseBoardSpine`). This task does not amend that contract.
- Notes for the next agent:

Commit only on `task/123-motif-timeline-date-scrubber`. Do not merge.

```
TC-Task-ID: 123
TC-Track: part2
TC-Never-Merge: true
```

## What landed

- `TimelineDateScrubber` draws a forensic date ruler for `fact_ledger` rows (`fact_id`, `datetime_iso`, `event_summary`). Notches sort by instant, then `fact_id`. Labels use the ISO wall clock, so `02:14:00-06:00` stays `02:14` and is not rewritten as UTC.
- A gap of four minutes or less is a cluster. Notch centers keep at least a label-width pitch, so a tight cluster does not collide. A longer jump is not stretched on a linear axis. It becomes a `// TIME GAP` divider, and leftover ruler width is shared by those dividers instead of by the real duration. On `ep_golden_01_20min` the six-minute gap and the multi-year gap are the same kind of divider. A pure linear axis of the 02:14 / 02:16 / 02:18 cluster plus `2021-06-18` stacks the cluster labels. The non-linear ruler does not.
- The focal card zooms from 1 to 1.5 as the playhead arrives on the focal notch (`focalFactId`, or the notch nearest the playhead). The card shows the ISO instant and a summary clamped to 12 words. The card, notches, and dividers stay inside the `1920x1080` safe zone (`paddingTop` 108, `paddingBottom` 194, bottom-right exclusion `22%` by `14%`).
- Each notch emits one `tick_sfx` cue at 48 kHz: 30 ms, nominal `-14 dBTP`, 60 ms cooldown. Hits inside the cooldown are suppressed. Triggers are `{ cue: "tick_sfx", sceneId, frame }` so Task 110's `dispatchMicroSfx` can take them later. This branch does not import `SfxRegistry.ts`.
- `<SafeZoneLayout>` is local to this file. `Illustrative2KPanZoom` is not implemented. No SVG turbulence and no `#C92A2A`.

Run the scrubber tests with the zero-spend setup file. The include override is required because the owned test path is `.tsx`:

```
node --input-type=module -e 'import { startVitest } from "vitest/node"; const vitest = await startVitest("test", ["packages/render_catalog/tests/motifs/timeline_date_scrubber.test.tsx"], { include: ["packages/render_catalog/tests/motifs/timeline_date_scrubber.test.tsx"], setupFiles: ["./scripts/vitest.setup.mjs"], environment: "node", watch: false }); await vitest.close();'
```
