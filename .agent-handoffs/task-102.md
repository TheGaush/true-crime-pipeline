# Task 102 Handoff

- Task: 102 CaseBible Style DNA React theme provider
- Branch: `task/102-case-bible-theme-provider`
- Worktree: primary checkout (this agent did not create `../tc-wt/task-102-case-bible-theme-provider`)
- Track: Part 2
- Status: committed on the task branch, opened as a never-merge PR against `main`
- Owned paths touched:
  - `packages/render_catalog/src/theme/CaseBibleContext.tsx`
  - `packages/render_catalog/tests/theme.test.tsx`
  - `.agent-handoffs/task-102.md`
- Dependencies added: none (package.json is outside this task)
- Verification: 16/16 theme tests passed under the zero-spend Vitest setup. See below.
- Incomplete: package `test` script, `react` dependency, and `jsx` / `allowImportingTsExtensions` compiler flags. Task 101's `safe_zone.tsx` is not on this branch.
- Notes for the next agent: import `SafeZoneLayout` from `../safe_zone.tsx`. Do not merge this branch. `TC-Never-Merge: true`.

## What landed

`useCaseBible()` locks a v4 `CaseBible` and hands out camelCase fields: `paperBgHex`, `inkHex`, `slateHex`, `evidenceCrimsonHex`, `flowKeyframeSafePalette`, and `character(characterId)` → `{ characterId, prop, colorHex }`. Input keys stay the contract's snake_case (`style_dna_json`, `characters_json`, `color_hex`). Unknown fields are rejected. Omitted hex fields throw. Nothing in this file fills in `#E9E2D2`, `#1B1B1D`, `#3A4F66`, or `#C4A574`.

Contrast uses WCAG relative luminance. Ink, slate, evidence crimson, and every character color must be at least `3.5:1` against `paper_bg_hex`. Flow-keyframe swatches are not contrast-checked, because that list includes the paper color itself. The canonical vector suspect coat `#C4A574` on paper `#E9E2D2` is `1.81:1` and throws. `#C92A2A` on that paper is `4.23:1` and is a legal Remotion accent. `#C92A2A` is still banned from `flow_keyframe_safe_palette` even when `evidence_crimson_hex` is a different red. That ban is the only hex literal in the theme module.

`CaseBibleCharacter` calls `theme.character(characterId)` during render. A missing entry throws `CaseBibleError: unregistered characterId: …`. `useCaseBible()` outside `CaseBibleProvider` throws `useCaseBible() requires CaseBibleProvider`.

`CaseBibleSafeZone` is the Task 101 import. It passes `isEndScreen` through to `SafeZoneLayout` from `../safe_zone.tsx` and paints `paperBgHex` / `inkHex` on the inner surface. This branch does not copy `safe_zone.tsx`, `parser.ts`, or `index.ts`. Task 101 does not name a parser function, so this task does not guess one.

Elements are `createElement` calls. `packages/render_catalog/tsconfig.json` has no `jsx` option, and this task cannot edit it.

The golden-pack `case_bible` object (`role_id`, nested `palette.charcoal`) is not the v4 contract. `lockCaseBible` rejects it. Pass the shared-contract `CaseBible` (`character_id`, `prop`, `color_hex`, and the five style hex fields).

## Verification

Provider keys were unset. `scripts/vitest.setup.mjs` blocked non-loopback `fetch`. No paid API calls.

`pnpm --filter @tc/render_catalog test -- theme` exits 0 and runs nothing: the package has no `test` script, and pnpm treats a missing `test` script as success. `package.json` is outside the owned scope, so the script was not added.

The suite was run with Vitest 3.2.4, React 19.2.0, and `@types/react` installed outside the repo. A temporary `safe_zone.tsx` existed only so the static import could resolve; `vi.mock` replaced it. That file was deleted before commit.

```
16 passed
packages/render_catalog/tests/theme.test.tsx
```

`tsc -p packages/render_catalog/tsconfig.json --noEmit` fails on `import "../safe_zone.tsx"` until `jsx` and `allowImportingTsExtensions` are enabled, and until `react` types plus Task 101's module are present. With those flags, React types, and a compatible `SafeZoneLayout`, `tsc` exited 0.

## Notes for the next agent

Commit only on `task/102-case-bible-theme-provider`. Do not merge. Do not change git config.

```
TC-Task-ID: 102
TC-Track: part2
TC-Never-Merge: true
```
