# Task 126 Handoff

- Task: 126 — Motif #12 `EvidenceMatchCard`
- Branch: `task/126-motif-evidence-match-card`
- Worktree: `../tc-wt/task-126-motif-evidence-match-card`
- Track: Part 2
- Status: Implemented on the task branch. Not merged.
- Owned paths touched:
  - `packages/render_catalog/src/motifs/EvidenceMatchCard.tsx`
  - `packages/render_catalog/tests/motifs/evidence_match_card.test.tsx`
  - `.agent-handoffs/task-126.md`
- Dependencies added: none
- Verification:
  - `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed.
  - Vitest 3.2.7: 6/6 passed on `packages/render_catalog/tests/motifs/evidence_match_card.test.tsx` with `scripts/vitest.setup.mjs` (provider keys stripped, outbound fetch blocked). No paid API calls.
  - `pnpm --filter @tc/render_catalog test -- evidence_match_card` exits 0 and does not launch Vitest. The Task 001 package shell has no `test` script, and root Vitest includes `*.test.ts` only. Both files are outside this write scope.
  - `node scripts/verify-harmony.mjs --task 126` accepts the owned paths. The model-id lint still fails on frozen Task 002 literals in `packages/shared_contracts` and `packages/shared-contracts-ts`. This diff does not touch them.
- Incomplete:
  - The package `test` script is still the Task 001 shell, so the acceptance command does not execute this suite until a later task owns `package.json` or `vitest.config.mjs`.
- Notes for the next agent:
  - Branched from `c914ae5` (Tasks 001–004). Those tasks were not reimplemented.
  - Task 110 and Task 114 are not imported. Their files are not on this branch.
  - `camera_shutter` cues are already on the 48 kHz mix clock: 90 ms, nominal -8 dBTP, 60 ms cooldown, peak at or below -1.0 dBTP. Default shutters are frame 0 and frame 2 (samples 0 and 3200). A second shutter inside 60 ms is suppressed.
  - Dossier boxes share one width and height. `object-fit: contain` letterboxes a 16:9 plate and pillarboxes a 9:16 plate inside those boxes. Swapping aspects does not change the box size.
  - Crimson `#C92A2A` is only on the comparison-arrow shaft and head. Arrows draw across 18 frames and stay in the gutter.
  - Safe-zone pixel boundaries are `SAFE_MARGIN_X = 96` and `SAFE_MARGIN_Y = 54`. CSS padding is 96 left/right, 108 top, 194 bottom (242 bottom on the end screen).
  - Frozen catalog slot 12 remains `ChapterSlateTransition`. `MOTIF_REGISTRY_V1` stays the four MVP motifs. This branch does not edit the registry.
  - Remotion does not bake a texture overlay. `apply-grade` is `true` for one later Agent 6 pass.

Do not merge.

```
TC-Task-ID: 126
TC-Track: part2
TC-Never-Merge: true
```
