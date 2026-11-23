# Task 109 Handoff

- Task: 109 — Remove double-grading from Remotion and emit `needs_grade` metadata
- Branch: `task/109-single-pass-grade-metadata`
- Worktree: `../tc-wt/task-109-single-pass-grade-metadata`
- Track: Part 2
- Status: Implemented on this branch. Not merged.
- Owned paths touched:
  - `packages/render_catalog/src/grade/GradeContract.tsx`
  - `packages/render_catalog/tests/grade.test.tsx`
  - `.agent-handoffs/task-109.md`
- Dependencies added: none. No `package.json` or lockfile edits. Remotion and React are not imported.
- Verification:
  - `pnpm exec vitest run --config /tmp/vitest.grade.config.mjs -- grade` — 9 tests passed. The temp config only adds `packages/render_catalog/tests/grade.test.tsx` to the root Vitest include (root `vitest.config.mjs` lists `*.test.ts`, not `*.tsx`) and loads `scripts/vitest.setup.mjs` (provider keys stripped, outbound sockets blocked except loopback).
  - `pnpm --filter @tc/render_catalog typecheck` passed.
  - `pnpm --filter @tc/render_catalog test -- grade` exits 0 without running a script. `@tc/render_catalog` has no `test` script; that shell belongs to Task 001 and is outside this write scope.
- Incomplete:
  - Task 102's `packages/render_catalog/src/theme/CaseBibleContext.tsx` is not on this branch. It is imported, not copied.
  - A Chromium Remotion render is not part of this task. The package shell does not depend on `remotion`, and `package.json` is outside the owned write scope.
- Notes for the next agent:

`GradeContract()` calls Task 102's named export `useCaseBible()`. The theme may expose `paperBgHex`, top-level `paper_bg_hex`, or `style_dna_json.paper_bg_hex`. Those strings must agree. The default frozen paper is `#E9E2D2`.

Remotion's plate is one flat `div` (`data-tc-role="ungraded-paper-bg"`). `paperGrain` and `vignette` are `0`. `filter` is `"none"`, `backgroundImage` is `"none"`, and there are no child overlays. `rasterizeUngradedFrame` fills every pixel with `paperBgHex`.

`sceneGradeManifestDocument()` returns `scene_grade_manifest.json` (`schema` `scene_grade_manifest.v1`, `contract_version` `v4`, `1920x1080`, `fps` `30`). Per scene, `needs_grade === apply_grade`. `FOIA_REAL_FOOTAGE` and motif `FoiaFootageFrame` are `apply_grade: false`, `exempt_from_grain: true`, `is_foia: true`. `CODE_STICKMAN`, `STILL_2K_PANZOOM`, `FLOW_HERO_VIDEO`, and `AUDIO_EVIDENCE_CARD` are `apply_grade: true`. `remotion_grain_applied` and `remotion_vignette_applied` are `false` on the manifest and on every scene. `grain_phase` is `null`, so Remotion has no grain phase to reset at a cut. Agent 6 owns the single pass (`grade_owner: "agent6_single_pass"`).

A `bodycam_inset` is always an `ungraded_masks` entry with `apply_grade: false`. A `narrator_pip` border is a `stylized_overlays` entry with `apply_grade: true`, and any overlap with the inset is an `ungraded_holes` rect. `gradeTargetAt` checks the inset before the border.

The grade test writes a one-function `useCaseBible` double at `packages/render_catalog/src/theme/CaseBibleContext.tsx` only when that file is missing or still contains the marker `TC-TASK-109-TEST-STUB`, then deletes it. It does not overwrite a real Task 102 module. Do not commit that double.

Task 167 also names `AUDIO_EVIDENCE_CARD` as grain-exempt. This task follows `code-animation-catalog.md` and `mastering-loudness-and-qa.md`: every non-FOIA scene, including the audio card, is `apply_grade: true`. Reconcile that before Agent 6 grades.

```
TC-Task-ID: 109
TC-Track: part2
TC-Never-Merge: true
```
