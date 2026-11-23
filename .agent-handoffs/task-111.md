# Task 111 Handoff

- Task: 111 — CSS-contained kinetic callouts and safe subtitles
- Branch: `task/111-kinetic-callout-subtitles`
- Worktree: `../tc-wt/task-111-kinetic-callout-subtitles`
- Track: Part 2
- Status: Implemented on this branch. Do not merge.
- Owned paths touched:
  - `packages/render_catalog/src/typography/SafeCallout.tsx`
  - `packages/render_catalog/tests/safe_callout.test.tsx`
  - `.agent-handoffs/task-111.md`
- Dependencies added: none. `package.json` is outside this task. React is imported and not declared here.
- Verification: Vitest 3.2.4 ran `packages/render_catalog/tests/safe_callout.test.tsx` — 14 passed, offline, provider keys unset, outbound fetch blocked. The same 14 passed when Task 101 `safe_zone.tsx`, Task 102 `CaseBibleContext.tsx`, and Task 108 `useVoiceSyncMotion.ts` were present on disk. Those files were removed before commit. `tsc -p packages/render_catalog/tsconfig.json --noEmit` passed. `node scripts/verify-harmony.mjs --task 111` accepts these three paths. The model-id lint still fails on frozen Task 002 literals in `packages/shared_contracts` and `packages/shared-contracts-ts`; this branch does not change them. `pnpm install --frozen-lockfile` still fails on the pre-existing lockfile drift (`yaml` and `zod` in `@tc/shared-contracts-ts`); the lockfile was not edited. `pnpm --filter @tc/render_catalog test -- safe_callout` exits 0 without launching Vitest.
- Incomplete: `pnpm --filter @tc/render_catalog test -- safe_callout` does not execute this suite. The Task 001 package shell has no `test` script, and root Vitest includes `*.test.ts` but not `*.test.tsx`. Both files are outside this write scope.
- Notes for the next agent:
  - `SafeCallout` renders inside Task 101 `SafeZoneLayout` and reads `measureSafeZone()` for the content, exclusion, caption bar, and end-screen card. Callout `top`/`left` are frame pixels. The safe-zone root is the positioned ancestor.
  - Location, timestamp, and action cards clamp to 12 words, require a `fact_ledger` id, and stay up for at least `1.0 + 0.3 * words` seconds. Highlight follows global `WordTimestamp[]`.
  - Overlapping Y slots move by 64px until they fit inside the usable safe zone. A step that would leave the zone is not taken.
  - The subtitle page is at most 12 words from narration timestamps. It is hidden when Task 108 reports a segment other than `NARRATION` (`TWIST_PAD`, `FOIA_AUDIO_SLOT`). Fact cards can remain during their hold, with no active word.
  - Ink, paper, slate, and evidence crimson come from Task 102 `useCaseBible()`. This file does not hardcode a palette.
  - Imports use `@ts-ignore` because those three modules are not on this branch. Do not vendor them here.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 111
TC-Track: part2
TC-Never-Merge: true
```
