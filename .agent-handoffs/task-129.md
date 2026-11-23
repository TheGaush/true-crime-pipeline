# Task 129 Handoff

- Task: 129 Implement `CustomDiagramScene` Promotion & Registry Tooling
- Branch: `task/129-custom-diagram-promoter`
- Worktree: branch `task/129-custom-diagram-promoter` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/tools/promote_diagram.ts`
  - `packages/render_catalog/tests/promote_diagram.test.ts`
  - `.agent-handoffs/task-129.md`
- Dependencies added: none
- Verification: offline vitest, 22 passed; package typecheck passed
- Incomplete: `packages/render_catalog/package.json` has no `test` script, so the filter command does not execute this suite
- Notes for the next agent: import `promoteDiagrams` from `packages/render_catalog/src/tools/promote_diagram.ts`. Do not merge.

Commit only on `task/129-custom-diagram-promoter`. The branch is pushed for review. Do not merge. Do not change git config.

```
TC-Task-ID: 129
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`promoteDiagrams` counts `CustomDiagramScene` tags and, at three distinct `scene_id`s, writes a Zod + React motif scaffold into `outDir`. Promoted motif numbers start at 13. Motifs #1–#12 are refused before any file is created.

Reserved names, in `schema/pipeline.sql` `motif_registry` order and `code-animation-catalog.md`:

1. `StickmanStage`
2. `AudioEvidenceCard`
3. `RedactedDocReveal`
4. `FoiaFootageFrame`
5. `TimelineScrubber`
6. `AnimatedMapRoute`
7. `CellTowerTriangulation`
8. `SplitScreenComparison`
9. `CaseBoardSpine`
10. `QuotePullout`
11. `EvidenceGridMatrix`
12. `ChapterSlateTransition`

Also refused: `Illustrative2KPanZoom` (`crime_scene_2k`), `HeroVideoBridge` (`flow_adapter`), the Layer 4 name `CustomDiagramScene`, and component names other Part 2 tasks already use inside that numbering (`SmsPhoneThread`, `MapRouteTrace`, `TimelineDateScrubber`, `AlibiSplitScreen`, `EvidenceMatchCard`). A split spelling such as `time_line_scrubber` still collides with `TimelineScrubber`. A near-miss such as `stickman_stage_notes` is allowed and becomes motif #13 `StickmanStageNotes`.

Snake, kebab, and Pascal spellings of one tag share a count. Two scenes, or three copies of one scene, do not scaffold. A batch that mixes a promotable tag with a reserved tag writes nothing. An existing `{Component}.tsx` is not overwritten. A later tag appends at the next free number and leaves the earlier scaffold bytes unchanged.

Each scaffold is `{Motif}.tsx` plus `promoted_motif_registry.json` (`promoted_motif_registry.v1`). The module exports `planDiagramPromotions`, `promoteDiagrams`, `renderMotifSource`, and `collectCustomDiagramOccurrences`. Generated labels are React text children inside a 1920×1080 safe-zone frame (`paddingTop` 108, `paddingBottom` 194). The scaffold calls Zod `.strict()`, clamps labels at 12 words (`RULE_07`), and does not emit `eval(`, `<script`, `dangerouslySetInnerHTML`, `feTurbulence`, or `feDisplacementMap`.

## Dependencies

None. Tasks 127 and 128 are not on `main` and were not imported. Their files were not copied. `packages/render_catalog/package.json` is outside this write scope, so `zod` and `react` were not added. The generated modules import them for a later catalog task. This tool does not execute those imports.

## Verification

Offline. Provider keys are stripped by `scripts/vitest.setup.mjs`. No paid call and no provider HTTP call.

- `pnpm exec vitest run packages/render_catalog/tests/promote_diagram.test.ts` — 22 passed.
- `pnpm --filter @tc/render_catalog typecheck` — passed.
- `pnpm --filter @tc/render_catalog test -- promote_diagram` exits 0 without running this suite. The Task 001 shell has no `test` script.
- `node scripts/verify-harmony.mjs --task 129` accepts these owned paths. The model-id lint still fails on Task 002 sources already on `main` (`packages/shared_contracts`, `packages/shared-contracts-ts`). This branch does not change them.

## Notes for the next agent

Call `promoteDiagrams({ outDir, occurrences })` or pass a timeline `document`. `collectCustomDiagramOccurrences` reads `diagram_tag`, `tag`, or `diagram.tag` on `motif_component: "CustomDiagramScene"`. Do not copy Tasks 115–128 into this branch. Commit only on `task/129-custom-diagram-promoter`. Do not merge.
