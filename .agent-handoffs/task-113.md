# Task 113 Handoff

- Task: 113 Implement Visual Regression Snapshot & Frame-Hash Harness
- Branch: `task/113-remotion-visual-regression`
- Worktree: `../tc-wt/task-113-remotion-visual-regression`
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/renderer/FrameVerifier.ts`, `packages/render_catalog/tests/visual_regression.test.ts`, `.agent-handoffs/task-113.md`
- Dependencies added: none
- Verification: `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed. `pnpm exec vitest run packages/render_catalog/tests/visual_regression.test.ts` passed 16/16. `pnpm --filter @tc/render_catalog typecheck` passed. `pnpm --filter @tc/render_catalog test -- visual_regression` exits 0 and does not run the suite.
- Incomplete: the package shell has no `test` script, and `package.json` is outside this write scope. Root `pnpm test` still fails on the pre-existing `packages/shared-contracts-ts/test/parity.test.ts` file, which uses `node:test` and is not a Vitest suite. `node scripts/verify-harmony.mjs --task 113` still fails on frozen Task 002 model-id literals in `packages/shared_contracts` and `packages/shared-contracts-ts`.
- Notes for the next agent: import Task 107, Task 109, and Task 101. Do not copy their files onto this branch. Do not merge.

## What landed

`renderStill` paints a deterministic 1920×1080 RGBA still for the four `MOTIF_REGISTRY_V1` motifs (`StickmanStage`, `AudioEvidenceCard`, `RedactedDocReveal`, `FoiaFootageFrame`). The paper plate is flat `#E9E2D2`. Paper grain and vignette stay at 0.

Exclusion borders follow the CSS safe zone: top 108px, bottom 194px, bottom-right 22%×14%. A still passes when it is not blank, SSIM against the reference is at least `0.995`, and those borders contain no pixel whose contrast against the plate is above `4.5:1`. One-level font antialias noise stays above that SSIM line and does not trip the border audit. A different motif, a blank plate, and an ink mark in any exclusion border fail.

Frame identity is SHA-256 of `widthxheight\n` plus the RGBA bytes. Locked hashes cover frame 0 and the end-screen frame (`duration - 600`) of a 36,000-frame episode. The final 20 seconds draw a card that stays inside the content rect and left of the bottom-right exclusion.

`FoiaFootageFrame` may carry a high-contrast stamp in the top-right window (`y < 6%` of height and `x >= 70%` of width). `#C92A2A` in that window still fails. Other motifs do not get the exemption.

## Imports

These modules are loaded only when their files are already on the tree:

- `packages/render_catalog/src/rig/StickEmotions.js` (Task 107). `StickmanStage` strokes `resolveStickEmotion` paths. The built-in stick is used when the module is absent.
- `packages/render_catalog/src/grade/GradeContract.js` (Task 109). The plate comes from `renderUngradedFrame` / `rasterizeUngradedFrame`. `REMOTION_PAPER_GRAIN` or `REMOTION_VIGNETTE` other than 0 throws. FOIA exemption follows `sceneNeedsGrade === false`.
- `packages/render_catalog/src/safe_zone.js` (Task 101). `measureSafeZone` wins when it is exported. Padding other than 108/194 or an exclusion other than `22%`×`14%` throws.

A missing module, including a GradeContract whose Task 102 `useCaseBible` import cannot resolve, leaves that dependency null. The harness still paints the flat plate.

No Remotion package is installed. This package shell cannot take a new dependency.

## Verification detail

Offline only. `scripts/vitest.setup.mjs` strips `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, and `ELEVENLABS_API_KEY`, and blocks non-loopback sockets. No paid API calls.

`node scripts/verify-harmony.mjs --task 113` checks these three paths once `main` is `c914ae5`. It does not report them as out of scope. The model-id lint still reports Task 002 lines this branch does not change.

Further commits stay on `task/113-remotion-visual-regression`. Do not merge. Do not change git config.

```
TC-Task-ID: 113
TC-Track: part2
TC-Never-Merge: true
```
