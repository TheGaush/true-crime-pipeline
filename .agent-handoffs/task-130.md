# Task 130 Handoff

- Task: 130
- Branch: `task/130-catalog-css-safezone-audit`
- Worktree: `../tc-wt/task-130-catalog-css-safezone-audit`
- Track: Part 2
- Status: implemented, tests passed, not merged
- Owned paths touched:
  - `packages/render_catalog/src/guards/RuntimeGuards.ts`
  - `packages/render_catalog/tests/runtime_guards.test.ts`
  - `.agent-handoffs/task-130.md`
- Dependencies added: none
- Verification: direct vitest `packages/render_catalog/tests/runtime_guards.test.ts` passed 2/2. Chromium measured 69 painted text boxes across the 12 motif modules on main and found 0 exclusion-zone leaks. An unclamped 12-word wrap reached y=3058.34; the SafeZoneLayout label clamp held it at y=884.98 (height 144.89, max-height 144.9).
- Incomplete: `@tc/render_catalog` still has no `test` script, so `pnpm --filter @tc/render_catalog test -- runtime_guards` does not launch vitest. `package.json` is outside this task's write scope.
- Notes for the next agent: call `auditSafeZoneInChromium()`. Do not merge this branch (`TC-Never-Merge: true`).

Commit only on the task branch. Do not merge or change git config. This branch is pushed only because the task assignment asked for a PR.

```
TC-Task-ID: 130
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`RuntimeGuards.ts` renders the twelve motif modules that are on main and measures `getBoundingClientRect()` in headless Chromium.

Audited modules: `StickmanStage`, `AudioEvidenceCard`, `RedactedDocReveal`, `FoiaFootageFrame`, `TimelineScrubber`, `SmsPhoneThread`, `MapRouteTrace`, `TimelineDateScrubber`, `CaseBoardSpine`, `AlibiSplitScreen`, `EvidenceMatchCard`, `HeroVideoBridge`. `CustomDiagramScene` is the sandbox and is not one of the twelve.

Each motif that takes a caption receives the 12-word label `Unbroken warehouse ledger showing twelve maximal caption tokens before the safe clamp`. `AudioEvidenceCard` and `HeroVideoBridge` have no caption field; their painted badge and full-frame plate are still measured. `SafeZoneLayout` is also rendered at rest and on the end screen with that same label.

Bands checked against `SafeZoneLayout`: top 108px (10% of 1080), bottom 194px (the 18% band, 0.4px under 194.4), bottom-right exclusion 22% by 14% (422.4 by 151.2 at x=1497.6, y=928.8). A painted box leaks only when it overlaps one of those bands by more than 1px after `overflow: hidden` ancestors clip it. That clip is what keeps the evidence-match captions, which sit on a 2px dossier border, out of the bottom band.

The wrap probe places twelve long tokens at y=740.1 in a 180px column. Without the label CSS the box runs to y=3058.34. With `overflow: hidden`, `-webkit-line-clamp: 3`, and `max-height: 144.9px` the measured bottom is 884.98, at or above the 885px line.

## Verification

```
pnpm exec vitest run packages/render_catalog/tests/runtime_guards.test.ts
```

2 passed. The Chromium case launched `/usr/bin/google-chrome` headless against a local `file://` audit page. No paid API calls.

`pnpm --filter @tc/render_catalog test -- runtime_guards` cannot run vitest: the package script list is only `typecheck`, and that file is outside this write scope.

Package `tsc` still reports pre-existing errors in motif, theme, and callout files (missing `react` types, unused `@ts-expect-error`, safe-zone child types). `RuntimeGuards.ts` adds none of those. Node imports use the same `@ts-expect-error` runtime note as `FrameVerifier.ts` because this package does not depend on `@types/node`.
