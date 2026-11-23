# Task 132 Handoff

- Task: 132 — Build `render_catalog` CLI, `--mvp-4-motifs` & `--scene` Re-Render Entrypoint
- Branch: `cursor/task-132-render-catalog-cli-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-132-render-catalog-cli`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: `packages/render_catalog/src/cli.ts`, `packages/render_catalog/src/index.ts`, `packages/render_catalog/tests/cli_rerender.test.ts`
- Dependencies added: none
- Verification: `pnpm exec vitest run packages/render_catalog/tests/cli_rerender.test.ts` (5 passed). `tsc -p packages/render_catalog/tsconfig.json --noEmit` reports no errors in `cli.ts` or `index.ts`. Pre-existing package typecheck failures (react, jsx, motif casts) remain on main and were not edited.
- Incomplete: `@tc/render_catalog` has no `test` script, so the acceptance line `pnpm --filter @tc/render_catalog test -- cli_rerender` cannot run without editing `package.json`, which is outside this task's Files list. Direct vitest covers the same file.
- Notes for the next agent: Default selection is `visual_engine == CODE_STICKMAN`. `--mvp-4-motifs` keeps StickmanStage, AudioEvidenceCard, RedactedDocReveal, and FoiaFootageFrame even when those rows are not CODE_STICKMAN. `--scene` on an unknown id, a non-stickman engine, or a motif outside the MVP slice exits 2 before any output write. Plates come from RenderPool (ffmpeg lavfi), not BatchCompiler's skeletal MP4, so ffprobe sees `30/1` and exact `nb_frames`. The grade contract is a small module written beside the per-scene bundle so RenderPool does not import `GradeContract.tsx` (that file pulls React). Bundle dirs are `.bundles/<episode_id>/<scene_id>`. A second run with the same schema stamp sets `bundle_reused`. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 132
TC-Track: Part 2
TC-Never-Merge: true
```
