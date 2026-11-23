# Task 127 Handoff

- Task: 127 Implement Layer 4 sandboxed `CustomDiagramScene`
- Branch: `task/127-custom-diagram-sandbox`
- Worktree: primary clone, branched from `c914ae5` (Tasks 001–004). Sibling `../tc-wt/task-127-custom-diagram-sandbox` was not created.
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/motifs/CustomDiagramScene.tsx`
  - `packages/render_catalog/tests/motifs/custom_diagram.test.tsx`
  - `.agent-handoffs/task-127.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. React and Remotion are not imported.
- Verification: see below. 5/5 offline tests passed. `tsc -p packages/render_catalog/tsconfig.json --noEmit` passed.
- Incomplete: `pnpm --filter @tc/render_catalog test -- custom_diagram` exits 0 and runs nothing. The Task 001 shell has no `test` script, and root Vitest includes `*.test.ts` only. Both files belong to Task 001.
- Notes for the next agent: import `CustomDiagramScene` from `packages/render_catalog/src/motifs/CustomDiagramScene.tsx`. Do not merge.

Tasks 101 (`SafeZoneLayout`), 103 (`BoilPath`), 111, and 114 are open PRs and are not on this branch. Their files were not copied. This motif keeps local `SafeZoneLayout` and `BoilPath` functions with the same call shape (`isEndScreen` + children; `points`, `seed`, `frame`, `closed`).

## What landed

`CustomDiagramScene` is the Layer 4 declarative escape hatch. It is not one of the 12 `MOTIF_REGISTRY_V1` motifs and it does not draw `Illustrative2KPanZoom`.

Input is a JSON object or a JSON string:

- `seed`: token `[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}`
- `frame`: integer `0..216000` on the 30 fps clock
- `isEndScreen`: boolean, default false
- `primitives`: 0 to 25 allowlisted shapes

Allowlisted primitive types: `rect`, `ellipse`, `line`, `polyline`, `polygon`, `arrow`, `label`. Any other type (`script`, `foreignObject`, `iframe`, `image`, `use`, `Illustrative2KPanZoom`, …) throws `CustomDiagramError`. Keys are allowlisted per type. `on*` handlers, `href`, `__proto__`, `constructor`, `prototype`, accessors, functions, and symbol keys are rejected. Property reads use descriptors, so a getter is not invoked. JSON deeper than 8 levels, arrays longer than 64, or objects with more than 16 keys are rejected. Strings are not evaluated.

Coordinates are in the safe content box: `1920×778`, inset by `2px` so `±1.4px` boil jitter stays inside that box. The frame is `1920×1080` with `paddingTop: 108`, `paddingBottom: 194`, and a bottom-right `22%×14%` exclusion box. `isEndScreen` adds an empty end-screen mask (`right: 22%`, `bottom: 194`).

Shapes, arrow shafts, arrow heads, and label underlines are `BoilPath` strokes: Mulberry32 normal jitter, tick `Math.floor(frame / 5)`, crisp `<path>` nodes, `data-boil-fps="6"`. Closed paths share one seam delta for the first and last points and end in `Z`. Paint is ink `#1B1B1D` on parchment `#E9E2D2`. No `#C92A2A` and no SVG turbulence.

Labels are SVG `<text>` children. `renderCustomDiagramMarkup` escapes `&`, `<`, and `>`. A label whose text is `<script>alert(1)</script>` or `</text><script>alert(1)</script>` stays one text node. The serialized markup contains `&lt;script&gt;` and does not contain a `<script` element. `javascript:` in a label is text, not an `href`. Labels are at most 12 words and 180 characters.

## Verification

Provider keys were removed by `scripts/vitest.setup.mjs`. `fetch("https://example.com/...")` throws `ZERO_SPEND_GUARD`. No paid API calls.

`pnpm --filter @tc/render_catalog test -- custom_diagram` exits 0 and prints nothing. `package.json` is outside this write scope.

Equivalent zero-spend command, with Vitest 3.2.4 and a config that includes the `.tsx` test and `scripts/vitest.setup.mjs` (config kept outside the repo):

```
vitest run --config <temp>/vitest.config.mjs custom_diagram
```

Result: 5 passed. `tsc -p packages/render_catalog/tsconfig.json --noEmit` passed (TypeScript 5.7.2).

`node scripts/verify-harmony.mjs --task 127` accepts the owned paths. The model-id lint still fails on Task 002 files already on `main` (`packages/shared_contracts`, `packages/shared-contracts-ts`). Those files were not edited here.

```
TC-Task-ID: 127
TC-Track: part2
TC-Never-Merge: true
```
