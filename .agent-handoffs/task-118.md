# Task 118 Handoff

- Task: 118 — Implement Authoritative MVP Motif #4 `FoiaFootageFrame`
- Branch: `task/118-motif-foia-footage-frame`
- Worktree: `../tc-wt/task-118-motif-foia-footage-frame`
- Track: Part 2
- Status: Implemented on this branch. Not merged.
- Owned paths touched:
  - `packages/render_catalog/src/motifs/FoiaFootageFrame.tsx`
  - `packages/render_catalog/tests/motifs/foia_footage_frame.test.tsx`
  - `.agent-handoffs/task-118.md`
- Dependencies added: none. No `package.json` or lockfile edits. Remotion and React are not imported.
- Verification:
  - `pnpm exec vitest run --config vitest.foia.config.mjs -- foia_footage_frame` — 9 tests passed. The temp config only adds `packages/render_catalog/tests/motifs/foia_footage_frame.test.tsx` to the include (root `vitest.config.mjs` lists `*.test.ts`, not `*.tsx`) and loads `scripts/vitest.setup.mjs`. Provider keys are stripped. The suite fetches `https://example.com/foia.mp4` and gets `ZERO_SPEND_GUARD`. The config was not committed.
  - `pnpm --filter @tc/render_catalog typecheck` passed.
  - `pnpm --filter @tc/render_catalog test -- foia_footage_frame` exits 0 without running a script. `@tc/render_catalog` has no `test` script; that shell belongs to Task 001 and is outside this write scope.
  - `node scripts/verify-harmony.mjs --task 118` accepts these three paths. It still reports pre-existing model-id literals in the frozen Task 002 contracts (`packages/shared_contracts` and `packages/shared-contracts-ts`). Those files are not in this diff.
- Incomplete:
  - Task 109's `packages/render_catalog/src/grade/GradeContract.tsx` is not on this branch. Pass `gradeDelegate` (the same shape as `sceneGradeManifestDocument`) to use it. This file does not copy it.
  - Task 114's stick rig is not on this branch. Pass `pip.figure` to mount that node. This file does not copy the skeleton.
  - A Chromium Remotion render is not part of this task. The package shell does not depend on `remotion`, and `package.json` is outside the owned write scope. The MP4 probe reads ISO-BMFF boxes. It does not decode pixels.
- Notes for the next agent:

`FoiaFootageFrame()` takes in-memory MP4 bytes plus provenance. The clip must be a single `vide` track, constant 30 fps (timescale / sample delta, no edit list), and either 16:9 or 9:16 within 1%. Provenance must be `APPROVED`, not `RESTRICTED_NO_REUSE`, `contains_third_party_attach = 0`, `normalized_cfr_30fps_48k = 1`, visually blurred, and spoken-PII bleeped. `scrubbed_path` is a local path. `raw_path` is never drawn.

16:9 fills 1920×1080. 9:16 is a left pillar column inside the safe rect (top 108px, bottom 194px) with a dossier sidebar in the leftover width. The picture is not stretched. HUD, callout zoom, and the optional PiP stay in that safe rect and out of the bottom-right 22%×14% exclusion. Callout labels are 1–12 words. The zoom factor must be greater than 1.15.

`scene_grade_manifest.json` (`scene_grade_manifest.v1`, `contract_version` `v4`) sets the scene `apply_grade` and `needs_grade` to `false`. The bodycam mask is `apply_grade: false`. Paper grain and vignette stay at 0. There is no `<feTurbulence>` or `<feDisplacementMap>`. A StickFigure PiP that does not overlap the picture is a `narrator_pip_border` overlay (`apply_grade: true`) beside the footage. A PiP that sits on the picture is not given a graded rect, so those pixels stay exempt. A `gradeDelegate` that would grade any footage sample throws.

`STICK_POSES` lists the 14 Task 106 ids from `idle` through `slumped`. The solver is not imported.

```
TC-Task-ID: 118
TC-Track: part2
TC-Never-Merge: true
```
