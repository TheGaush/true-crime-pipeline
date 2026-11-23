# Task 131 Handoff

- Task: 131 Benchmark `<5s` JS-Boil Remotion Re-Render Performance
- Branch: `cursor/task-131-js-boil-bench-c1ed`
- Worktree: primary clone (no sibling worktree)
- Track: Part 2
- Status: committed on this branch. Do not merge.
- Owned paths touched:
  - `packages/render_catalog/benchmarks/js_boil_bench.ts`
  - `packages/render_catalog/tests/perf_sla.test.ts`
  - `.agent-handoffs/task-131.md`
- Dependencies added: none
- Verification: `pnpm exec vitest run packages/render_catalog/tests/perf_sla.test.ts` — 3 passed. The twelve-archetype heal, including Chromium, finished in about 8.7s of wall clock.
- Incomplete: `@tc/render_catalog` has no `bench:js-boil` script. `package.json` is outside this task's Files list, so the bench is `runJsBoilBench()` from the test and from the benchmark module.
- Notes for the next agent: call `runJsBoilBench()`. Do not merge.

Commit only on this branch. Do not merge. Do not change git config.

```
TC-Task-ID: 131
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`runJsBoilBench()` measures a 10.0s, 1920×1080, 30 fps heal for all twelve motif modules. Strokes use Task 103 `buildBoilGeometry` at 6 fps (`Math.floor(frame / 5)`). Frames 0 and 4 share a path; frame 5 does not. Witness PNGs at frames 0, 150, and 299 are hashed. A second pass must repeat those hashes. Each pass also encodes a 300-frame ungraded plate and checks `nb_frames`.

Cold time re-reads and re-parses that motif's source. Warm time reuses the parsed bundle. Both run at concurrency 4. `Math.random` throws for the duration of the bench. The catalog AST (TypeScript) must contain zero `feTurbulence`, zero `feDisplacementMap`, and zero film-grain `canvas` nodes. One headless Chromium dump of the serialized scenes checks the same tags in the DOM. Chromium startup is reported as `chromium.cold_start_ms` and is not added twelve times onto the heal clock.

Archetype aliases used by the task brief: `EvidenceDocumentZoom` (RedactedDocReveal), `AnimatedMapRoute` (25 callout leaders), `SplitScreenEvidence` (AlibiSplitScreen). CaseBoardSpine draws 16 corkboard pins. The generated SVG uses stroke geometry only, so pin and callout shadows are not CSS filters.

Budgets are 5,000 ms warm and 6,500 ms cold. The report is `artifacts/benchmarks/remotion_js_boil_perf.json` (gitignored). `pass` is true only when every archetype is inside both budgets, the plate has 300 frames, the hashes match, and both scans are clean.

`HeroVideoBridge` is imported on demand because `GradeContract` pulls `react` through `CaseBibleContext`. The SLA test supplies a tiny `react` mock. React is not a package dependency.

## Verification

Offline. No provider calls. Pytest's socket guard is not on this Vitest path; the bench does not open a provider socket. Chromium loads a `file://` audit page.

```
pnpm exec vitest run packages/render_catalog/tests/perf_sla.test.ts
```

3 passed. `node scripts/verify-harmony.mjs --task 131` accepts the two owned paths. The handoff is outside the Files line. Model-id lint still fails on Task 002 sources already on `main`. This branch does not change them.

## Notes for the next agent

Import `runJsBoilBench` from `packages/render_catalog/benchmarks/js_boil_bench.ts`. Require `report.pass === true` before treating a heal as inside the SLA. Do not add `<feTurbulence>` back. Do not merge.
