# Task 121 Handoff

- Task: 121 Implement Motif #7 — `MapRouteTrace`
- Branch: `task/121-motif-map-route-trace`
- Worktree: branch `task/121-motif-map-route-trace` (primary clone; sibling `../tc-wt/` worktree was not created)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched: `packages/render_catalog/src/motifs/MapRouteTrace.tsx`, `packages/render_catalog/tests/motifs/map_route_trace.test.tsx`, `.agent-handoffs/task-121.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. Tasks 111 and 114 were not imported.
- Verification: `pnpm --filter @tc/render_catalog typecheck` passed. Map route vitest: 6 passed. See the command below. `pnpm --filter @tc/render_catalog test -- map_route_trace` exits 0 and prints nothing, because the Task 001 shell has no `test` script.
- Incomplete: root `vitest.config.mjs` includes `packages/**/*.test.ts` only, so `pnpm exec vitest run map_route_trace` reports no files. `node scripts/verify-harmony.mjs --task 121` still reports pre-existing model-id hits in Task 002 sources (`packages/shared_contracts` and `packages/shared-contracts-ts`) when those files are present. Those files were not edited here.
- Notes for the next agent:

Commit only on `task/121-motif-map-route-trace`. Do not merge.

```
TC-Task-ID: 121
TC-Track: part2
TC-Never-Merge: true
```

## What landed

- `MapRouteTrace` draws a schematic blueprint for a multi-stop route. The plate is an SVG grid, a dashed full polyline, a solid traveled polyline, stop pins, and a marker. The drive-time HUD shows the route name, `SCHEMATIC · NO TILES`, elapsed drive, and claimed drive. Coordinates are caller-supplied numbers in `[0, 1]`.
- `<SafeZoneLayout>` is local to this file. The frame is `1920x1080`, `paddingTop` 108, `paddingBottom` 194, bottom-right exclusion `22%` by `14%`, `overflow: hidden`. The board stays inside that content rect, off the caption bar, off the exclusion box, and off the end-screen card. Task 101's `safe_zone.tsx` was not copied.
- Per-leg timestamp callouts cite `fact_id`. Display text is clamped to 12 words. Hold time is `ceil((1 + 0.3 * words) * 30)` frames. Callouts that would overlap shift on a 64 px Y grid and stay inside the board, clear of the HUD. Task 111's `SafeCallout.tsx` was not copied.
- The marker eases with `easeInOutCubic` along each leg, so the opening step is smaller than the mid-leg step. A leg shorter than `1e-6` in normalized space keeps the marker on that pin and pulses its radius. It does not divide by the leg length.
- The NJ Route 9 fixture is four schematic stops: bay lot `22:10`, mile 12 `22:18` (8 min), shore diner `22:31` (13 min), claimed end `22:44` (13 min). At frame 60 the marker is halfway along the first leg and the HUD reads `ELAPSED 04:00` / `CLAIMED 34:00`. At frame 420 every stop's timestamp is on screen and the elapsed time equals the claimed 34:00.
- The rendered tree has `tiles="0"`, node types `div`, `svg`, `line`, `polyline`, and `circle` only, and no `http` URL. Labels that contain `http://`, `https://`, or a tile host are rejected. No `<image>` element is emitted.
- The frozen SQL catalog's seventh Remotion name remains `CellTowerTriangulation`. The procedural map row remains `AnimatedMapRoute`. `MOTIF_REGISTRY_V1` remains the four MVP motifs. This component's id is `MapRouteTrace`, motif number 7 for Task 121. `Illustrative2KPanZoom` is not implemented.

Run the motif tests with the zero-spend setup file. The include override is required because the owned test path is `.tsx`:

```
node --input-type=module -e 'import { startVitest } from "vitest/node"; const vitest = await startVitest("test", ["packages/render_catalog/tests/motifs/map_route_trace.test.tsx"], { include: ["packages/render_catalog/tests/motifs/map_route_trace.test.tsx"], setupFiles: ["./scripts/vitest.setup.mjs"], environment: "node", watch: false }); await vitest.close();'
```
