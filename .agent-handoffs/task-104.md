# Task 104 Handoff

- Task: 104 Parametric StickFigure core geometry rig
- Branch: `task/104-stick-figure-core-rig`
- Worktree: primary clone, branched from `c914ae5` (no sibling worktree)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/rig/StickFigureGeometry.tsx`
  - `packages/render_catalog/tests/stick_geometry.test.tsx`
  - `.agent-handoffs/task-104.md`
- Dependencies added: none
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Vitest `stick_geometry` 11/11 passed with provider keys set in the environment (setup scrubbed them). `node scripts/verify-harmony.mjs --task 104` accepted the 3 owned paths, secrets, diagrams, and `schema/schema-test.js`. The model-id lint still reports Task 002 contract lines (`VEO_3_1_LITE`, `gemini-omni-1.2-flash`, `vertex-veo-enterprise`) in `packages/shared_contracts` and `packages/shared-contracts-ts`. This task did not touch those files.
- Incomplete: `LineBoilPath.tsx` is Task 103 and is not on this branch. `package.json` still has no `test` script, and root `vitest.config.mjs` includes `*.test.ts` only. Both files are outside this task's write scope.
- Notes for the next agent: import `solveStickFigure` and `StickFigureGeometry` from `packages/render_catalog/src/rig/StickFigureGeometry.tsx`. Do not copy `BoilPath`.

## What landed

Parametric stick skeleton at 1920×1080. Locked lengths at scale 1 are `headRadius 22`, `torsoLen 70`, `upperArm 36`, `forearm 32`, `thigh 46`, `shin 42`. Distance between a bone's endpoints is `LOCKED_BONE_RATIOS[ratio] * appliedScale` for every joint angle and both facings. The head is a closed 16-segment loop with radius `headRadius * appliedScale`. The neck segment uses that same radius.

Joint angles are degrees. Zero keeps the torso and head pointing up and the limbs hanging with the torso. Positive degrees rotate toward screen-left. `facing: "left"` mirrors local x about the pelvis.

`solveStickFigure` clamps the pelvis so the head circle and every socket stay in the CSS safe rect: top `108`, bottom `1080 - 194`, left `0`, right `1920`. A scale that cannot fit shrinks `appliedScale` and leaves the ratios intact. `isEndScreen` also runs `separateFromRect` against the bottom-right `22% × 14%` box (`left 1497.6`, `top 928.8`). That box sits inside the bottom 18% pad, so a figure already in the safe rect does not move again.

`StickFigureGeometry` builds a React element (`$$typeof: Symbol.for("react.element")`, `type: "g"`) whose children use Task 103's `BoilPath` as the element type. It does not call `BoilPath`, so a hook-based boil still runs under React. Each child gets `points`, `seed` (`boneSeed`), `closed`, `frame`, `strokeWidth: 9`, `stroke: "currentColor"`, and `fill: "none"`. No hex palette and no SVG turbulence filter.

Sockets: `crown` (fedora), `brow` (glasses), `neck` (tie, scarf), `chest` (badge, hoodie), `hip`, `handLeft` / `handRight` (briefcase, flashlight, phone, document), plus elbow, knee, and ankle.

## BoilPath import

```ts
import { BoilPath } from "./LineBoilPath.js";
```

`LineBoilPath.tsx` is not in this branch. The import line carries `@ts-expect-error` until that module resolves cleanly (today it is TS2307; a `.tsx` target without `jsx` in tsconfig is TS6142). Delete the directive when `tsc` reports it unused. Do not vendor the boil.

The geometry test substitutes the binding with `typescript.transpileModule` so the suite can run before Task 103 is merged. It does not reimplement vertex jitter.

## Verification

`@tc/render_catalog` has no `test` script, and the root Vitest include does not match `*.test.tsx`. Changing either file is outside this task. Equivalent zero-spend command (setup file still scrubs provider keys and blocks non-loopback fetch):

```
pnpm exec vitest run --config /tmp/task-104-vitest.config.mjs stick_geometry
```

`/tmp/task-104-vitest.config.mjs` uses `scripts/vitest.setup.mjs` and include `packages/render_catalog/tests/stick_geometry.test.tsx`. Result: 11 passed. `pnpm --filter @tc/render_catalog typecheck` passed.

```
TC-Task-ID: 104
TC-Track: part2
TC-Never-Merge: true
```
