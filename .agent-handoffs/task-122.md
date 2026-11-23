# Task 122 Handoff

- Task: 122 Implement Authoritative MVP Motif #3 — `RedactedDocReveal`
- Branch: `task/122-motif-redacted-doc-reveal`
- Worktree: primary clone, branched from `c914ae5` (Tasks 001–004). Sibling `../tc-wt/task-122-motif-redacted-doc-reveal` was not created.
- Track: Part 2
- Status: committed on the task branch. PR https://github.com/TheGaush/true-crime-pipeline/pull/27 is open against `main` and must not be merged (`TC-Never-Merge`).
- Owned paths touched:
  - `packages/render_catalog/src/motifs/RedactedDocReveal.tsx`
  - `packages/render_catalog/tests/motifs/redacted_doc_reveal.test.tsx`
  - `.agent-handoffs/task-122.md`
- Dependencies added: none. Task 110 (`SfxRegistry`) and Task 114 (rig consistency) are not on this branch and were not copied. Task 101's `SafeZoneLayout` was not copied. React and Remotion are not imported.
- Verification: see below. 7/7 offline tests passed. `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed.
- Incomplete: `@tc/render_catalog` has no `test` script, and root Vitest includes `*.test.ts` only. Both belong to Task 001. The dispatcher and safe-zone component land on their own PRs.
- Notes for the next agent: import `RedactedDocReveal` from `packages/render_catalog/src/motifs/RedactedDocReveal.tsx`. Do not merge.

## What landed

`RedactedDocReveal` is MVP motif #3 in `MOTIF_REGISTRY_V1` (the task acceptance line says motif #4; the catalog and the task title both place this component third, after `StickmanStage` and `AudioEvidenceCard`). It paints a flat aged court filing at `1920×1080` and `30 fps`.

The sheet is `data-sheet="aged-court-filing"` with paper `#E4D2AE`. There is no paper grain, vignette, SVG turbulence, or `#C92A2A`. `filter` and `backgroundImage` are `none`. `data-paper-grain="0"`, `data-vignette="0"`, `data-apply-grade="true"`.

Safe zone, without importing Task 101: a slot at `top: 108`, `height: 778` (`padding` contract `108` / `194`), `overflow: hidden`, `data-safe-zone="css-contained"`. The sheet, caption, quote, marks, redaction bars, and citation badge are required to sit inside that slot and to miss the caption bar (`y >= 886`) and the bottom-right `22% × 14%` exclusion. A quote that wraps past the remaining column throws `RedactedDocError` (`wrapped quote leaves the safe zone`) instead of clipping into the exclusion.

Layout advance is a fixed `18 px` per character (`CHAR_WIDTH_PX`), so tests do not need a font engine. The default quote column is `640 px`, which wraps the golden sentence into three lines:

1. `The affirmed opinion at paragraph`
2. `18 is read from the primary court`
3. `record.`

Highlighter: one `<mark>` per line (`type: "mark"`). Width grows left to right from `word_timestamps[]`. A finished word includes the gap before the next word. A later line stays `sweep="pending"` and width `0` until the previous line is `full`. Phases are `pending`, `partial`, and `full`. Color is `#F3E37A`.

Clock: `nowMs = sceneStartMs + floor(frame * 1000 / 30)`. Frame `0` on a golden scene is before the first word, so every mark is pending. Frame `78` is `+2600 ms`, which is inside `primary` on line 2: line 1 full, line 2 partial, line 3 pending.

Redaction: default two affidavit bars (`#000000`, no text). `quoteRedactions` are half-open word indexes. A range that crosses a wrap becomes one bar per line, painted after the mark. Redacted tokens are not text nodes.

Citation badge: the caller passes `citation` (golden locator `2021 MT 142 at paragraph 18`). It is pinned to the bottom of the sheet, `fontWeight: 700`, and must fit the footer or the render throws.

`highlighter_glide`: one cue per line at that line's first `start_ms` (absolute timeline ms). `duration_ms` is `280`, `cooldown_ms` is `60`. A line that starts less than `60 ms` after the previous emitted cue is listed on `solved.suppressed` and omitted from `solved.cues`. This matches Task 110's published cue constants. `SfxRegistry.ts` is not imported.

`solveRedactedDoc(props)` returns the geometry and cues. `RedactedDocReveal(props)` returns that object on `.solved` plus a React-shaped element (`$$typeof: Symbol.for("react.element")`).

## Verification

Provider keys were set in the shell. `scripts/vitest.setup.mjs` removed them and blocks non-loopback `fetch`. No paid API calls.

`pnpm --filter @tc/render_catalog test -- redacted_doc_reveal` exits 0 and runs nothing. The Task 001 shell has no `test` script. `package.json` is outside this write scope.

Equivalent zero-spend command (temp config adds the `.tsx` test to Vitest and loads `scripts/vitest.setup.mjs`):

```
pnpm exec vitest run --config tmp-task-122-vitest.config.mjs redacted_doc_reveal
```

Result: 7 passed. `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed.

`node scripts/verify-harmony.mjs --task 122` accepts the owned paths. The same command still fails on pre-existing model-id hits in Task 002 (`packages/shared_contracts`, `packages/shared-contracts-ts`). Those files were not edited here.

```
TC-Task-ID: 122
TC-Track: part2
TC-Never-Merge: true
```
