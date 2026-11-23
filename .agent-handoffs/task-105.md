# Task 105 Handoff

- Task: 105 Implement `StickFigure` silhouette prop library
- Branch: `task/105-stick-figure-prop-library`
- Worktree: `../tc-wt/task-105-stick-figure-prop-library`
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/rig/StickProps.tsx`, `packages/render_catalog/tests/stick_props.test.tsx`, `.agent-handoffs/task-105.md`
- Dependencies added: none
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Vitest file `packages/render_catalog/tests/stick_props.test.tsx` — 17 passed (see below). No paid API calls.
- Incomplete: not mounted from `packages/render_catalog/src/index.ts` (Task 101). No vertex jitter (Task 103). No React wrapper (shell has no `jsx` and no React dependency; both files are outside this write scope).
- Notes for the next agent: sockets below are the idle attachment frame. Do not pre-mirror socket x and also set `facing="left"`.

Commit only on the task branch. Do not merge.

```
TC-Task-ID: 105
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`StickProps` draws the ten silhouette props as crisp `BoilPath` polylines:

`fedora` (crown), `hoodie` (neck), `badge` (chest), `glasses` (brow), `tie` (neck), `scarf` (neck), `briefcase` (hand), `flashlight` (hand), `phone` (hand), `document` (hand).

Outlines are authored facing right. Left facing is one SVG group, `translate(torsoAxisX) scale(-1 1) translate(-torsoAxisX)`, so the fedora brim and the badge keep their shape. Path `d` is identical for both facings. The longer brim side and the badge's forward edge lead the facing direction after that transform.

`BoilPath` in this file is the crisp polyline (`points`, `seed`, `closed`). It does not import `LineBoilPath.tsx` and it does not copy Task 103's Mulberry32 jitter. Seeds are `${seed}:${Math.floor(frame / 5)}:${prop}:${part}` at 30 fps. Ink is `#1B1B1D`. Paper cutouts (hatband, badge stripe, lens, flashlight lens, phone screen, document bars) are `#E9E2D2`. `#C92A2A` is rejected. There is no `<feTurbulence>`, `<feDisplacementMap>`, or `filter`.

Held props that share `hand` are slotted `2.1` head radii forward so the outer boxes do not overlap. Callers choose paint order. Pass `hoodie` before `fedora` if the hat should sit on the hood.

`stickFigureSockets(bones, origin)` places an idle rig. Origin is the hip. Y grows down. `torsoAxisX` is the hip x. Head center is `1.15` head radii above the neck (a `0.15` radius chin gap). Crown is one head radius above the head center. Brow is `0.72` radii forward of the head center. Chest is `45%` of `torsoLen` above the hip. The hand hangs at `shoulder + upperArm + forearm`, `0.45` radii forward of the axis. Canonical bones are `DEFAULT_STICK_BONES`: head `36`, torso `110`, upper arm `64`, forearm `56`, thigh `78`, shin `72`. Prop size follows `headRadius`, which must match the crown-to-head-center distance within `0.05` px.

`FRAME_SAFE_ZONE_1080` is `{ top: 108, right: 1920, bottom: 886, left: 0 }` (10% top, 18% bottom of 1080). Pass it as `safeZone`. The socket and its mirror must sit inside the rect. The prop scales about its anchor until both facings fit. If that scale would drop either side of the outer box under `0.45` head radii, `StickProps` throws `SILHOUETTE_UNREADABLE` instead of emitting a speck. A figure that already fits is not rescaled.

The shell `tsconfig` has no `jsx` flag and the package has no React dependency. `StickProps` and `BoilPath` return `{ tag, attrs, children }`. `renderStickPropsSvg` serializes that tree. Task 101 can host it in Remotion without this file importing React.

`packages/render_catalog/src/index.ts` was not edited.

## Verification

`pnpm --filter @tc/render_catalog typecheck` passed.

Root `vitest.config.mjs` includes `packages/**/*.test.ts` and does not collect `*.test.tsx`. `@tc/render_catalog` has no `test` script (`package.json` is the Task 001 shell and is outside this write scope). `pnpm --filter @tc/render_catalog test -- stick_props` exits 0 without running a test: pnpm skips a filtered script that the package does not define.

The owned file was run with Vitest include pointed at `packages/render_catalog/tests/stick_props.test.tsx`, `environment: node`, and `scripts/vitest.setup.mjs` (provider keys scrubbed, non-loopback fetch blocked). Result: 17 passed. Coverage includes all 10 props, both facings, brim/badge asymmetry, hand-slot separation, boil ticks 0 and 1 with unchanged geometry, safe-zone fit / refusal, crimson rejection, and inline SVG snapshots. No new dependencies. No network calls from the tests.

`node scripts/verify-harmony.mjs --task 105` accepts these three paths. The same command still fails on pre-existing `VEO_3_1_LITE` literals in the Task 002 shared contracts (`veo` matches the model-id lint). This task did not edit those files.

## Notes for the next agent

- Import `packages/render_catalog/src/rig/StickProps.ts`. Do not expect a React element until the shell grows a JSX flag.
- Task 103 can wrap the same `points` / `seed` / `closed` values. Do not add jitter inside this file.
- Task 104's sockets should use these names (`crown`, `headCenter`, `brow`, `neck`, `chest`, `shoulder`, `hand`, `hip`, `knee`, `foot`) plus `torsoAxisX` and `headRadius`, in the same Y-down frame.
- Task 106 should pass canonical right-facing sockets and a `facing` flag.
