# Task 103 Handoff

- Task: 103 Fast 6 fps JS line boil
- Branch: `task/103-fast-js-6fps-line-boil`
- Worktree: `../tc-wt/task-103-fast-js-6fps-line-boil`
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/rig/LineBoilPath.tsx`
  - `packages/render_catalog/tests/line_boil.test.tsx`
  - `.agent-handoffs/task-103.md`
- Dependencies added: none
- Verification: TypeScript 5.7.2 `tsc -p packages/render_catalog/tsconfig.json --noEmit` passed. `node --test` on the transpiled suite: 10/10 passed. React 19.2.0 `renderToStaticMarkup(<BoilPath />)` emitted one `<path>` and no turbulence or displacement nodes. A 60-point polyline at 4 subdivisions measured `0.380 ms/frame` (markup included), under the `0.5 ms` target and the `2 ms` test gate.
- Incomplete: `pnpm --filter @tc/render_catalog test -- line_boil` does not execute this suite. The Task 001 shell has no `test` script, and `package.json` is outside this task's write scope. pnpm skips a filtered package that lacks the script and exits 0. `pnpm install --frozen-lockfile` also fails because `pnpm-lock.yaml` is behind `packages/shared-contracts-ts/package.json` (`yaml`, `zod`); that lockfile was not edited.
- Notes for the next agent: import `{ BoilPath }` from `packages/render_catalog/src/rig/LineBoilPath.tsx`. Pass `points`, `seed`, and the Remotion `frame`. Do not add SVG turbulence or displacement primitives.

Commit only on the task branch. Do not merge. `TC-Never-Merge: true`.

```
TC-Task-ID: 103
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`BoilPath` replaces SVG turbulence / displacement filters with deterministic JS vertex jitter.

- Container is `30 fps`. The boil pose is `Math.floor(frame / 5)`, so frames `0..4` share tick `0` and frames `5..9` share tick `1`.
- Each segment is subdivided (`subdivisions`, default `4`, max `64`). Straight segments, quadratic curves (`curve.kind = 'quadratic'`), and cubic curves (`curve.kind = 'cubic'`) are flattened before jitter.
- Mulberry32 is seeded with FNV-1a of `typeof seed`, the seed, and the tick. Jitter is along the vertex normal in `[-1.4, +1.4]` px.
- `closed={true}` reuses the `points[0]` displacement vector for `points[n - 1]` and does not draw a second PRNG sample for that endpoint. A point list that already repeats its start is not wrapped again. The seam gap stays constant and the path closes with `Z`.
- The returned value is a React 19 host element (`Symbol.for('react.transitional.element')`, `type: 'path'`). Attributes are only `d`, paint, line caps, and `data-boil-tick` / `data-boil-fps` / `data-container-fps`. Paint strings are escaped when serialized. There is no `filter` attribute and no child nodes.
- Defaults: `fill="none"`, `stroke="#161616"`, `strokeWidth={2}`. `frame` is an argument. This module does not call Remotion.

Frame-0 snapshot for seed `case-01`, subdivisions `2`, square `(10,20)-(110,20)-(110,90)-(10,90)`:

```
M 10.5607 20.801 L 60 18.7827 L 109.6757 20.4633 L 110.7474 55 L 110.7949 91.1356 L 60 89.6697 L 10.5607 90.801 L 9.3703 55 Z
```

`points[0]` and `points[3]` both move by `(+0.5607, +0.801)`.

## Verification

`pnpm-lock.yaml` does not match the workspace, and this task cannot regenerate it. Typecheck used the TypeScript `5.7.2` declared in the root `package.json`, installed outside the repo:

```
tsc -p packages/render_catalog/tsconfig.json --noEmit
```

Tests were transpiled with that compiler (`module: ES2022`) and run with:

```
node --test packages/render_catalog/tests/line_boil.test.js
```

```
tests 10
pass 10
fail 0
```

React 19.2.0 server markup for `<BoilPath />` was a single `<path>` with `data-boil-fps="6"` and no `<filter>`, `feTurbulence`, or `feDisplacementMap` nodes.

`node scripts/verify-harmony.mjs --task 103` accepted the three owned paths. The model-id lint still fails on Task 002 files already on `main` (`packages/shared_contracts` and `packages/shared-contracts-ts`). This task did not edit them.

Bench: 60 points, `subdivisions: 4`, 80 frames, `0.380 ms/frame`.

## Notes for Task 104

```tsx
<BoilPath points={bone} seed={boneId} frame={frame} closed={false} />
```

`BoilPath` is also exported as `LineBoilPath`. Geometry is available from `buildBoilGeometry` for rig tests that need the perturbation vectors. React 18 will not recognize the transitional element symbol; spread `BoilPath(props).props` onto `<path>` in that case. This package still has no `react` dependency.
