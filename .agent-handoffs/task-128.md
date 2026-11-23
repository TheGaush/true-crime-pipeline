# Task 128 Handoff

- Task: 128 TimelineSpec full-catalog and MVP-slice BatchCompiler
- Branch: `task/128-timeline-spec-batch-compiler`
- Worktree: `../tc-wt/task-128-timeline-spec-batch-compiler`
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/renderer/BatchCompiler.ts`
  - `packages/render_catalog/tests/batch_compiler.test.ts`
  - `.agent-handoffs/task-128.md`
- Dependencies added: none
- Verification: offline vitest, 11 passed; package typecheck passed
- Incomplete: scene MP4s are 1080p30 ISO-BMFF containers, not Remotion pictures
- Notes for the next agent: import `BatchCompiler` from `packages/render_catalog/src/renderer/BatchCompiler.ts`. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 128
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`BatchCompiler.compile` reads a golden-pack `timeline_spec` (30 fps, 1920×1080, contiguous frames) and writes three products:

- `{scene_id}.mp4` for every scene this package compiles. The container timescale is 30 and `mvhd` duration is the frame count. `tkhd` size is 1920×1080. The file has no picture samples, no paper grain, and no vignette.
- `scene_grade_manifest.json` — one manifest for the whole timeline. `remotion_grain_applied`, `remotion_vignette_applied`, `paper_grain`, and `vignette` are zero. `single_grade_pass` is true and `grade_owner` is `agent6_single_pass`.
- `micro_sfx_cues.json` — sample-accurate cues at 48 kHz. A later cue closer than 60 ms (2880 samples) is listed under `suppressed` with reason `cooldown`.

`apply_grade` is false for `FOIA_REAL_FOOTAGE` and `FoiaFootageFrame`. It is true for code, audio-evidence, 2K, Flow, and every other stylized engine. That matches the Task 109 single-pass contract. `AudioEvidenceCard` stays graded.

Routing follows `schema/pipeline.sql` `motif_registry` and `code-animation-catalog.md`:

- The 12 `@tc/render_catalog` motifs compile in full-catalog mode: `StickmanStage`, `AudioEvidenceCard`, `RedactedDocReveal`, `FoiaFootageFrame`, `TimelineScrubber`, `AnimatedMapRoute`, `CellTowerTriangulation`, `SplitScreenComparison`, `CaseBoardSpine`, `QuotePullout`, `EvidenceGridMatrix`, `ChapterSlateTransition`.
- `CustomDiagramScene` compiles in full mode as the Layer 4 escape hatch. It is outside the 12.
- `--mvp-4-motifs` (`mvp4Motifs: true`) encodes only `StickmanStage`, `AudioEvidenceCard`, `RedactedDocReveal`, and `FoiaFootageFrame`. The other render_catalog motifs stay in the manifest as `out_of_slice`.
- `Illustrative2KPanZoom` is `delegated` to `crime_scene_2k`. An accepted `HeroVideoBridge` is `delegated` to `flow_adapter`. A latent `fallback_spec` on an `ACCEPTED` job does not swap.
- `SWITCHED_TO_FALLBACK` replaces the hero with `fallback_spec` at the same frames (`gap_ms: 0`). The grade row records `requested_motif_component` and the active motif. A fallback of `FLOW_HERO_VIDEO`, or one whose active engine matches the previous or next scene, throws `RULE_04` before any file is written.
- Any other flow state (`STRIKE_1_RETRY_SAFE` included) is `withheld`: the planned hero stays in the manifest with `mp4_relpath: null`.

Signature cues on compiled scenes: `tape_click` (audio card), `highlighter_glide` (redacted doc), `radio_squelch` (FOIA frame and cell-tower), `tick_sfx` (timeline scrubber), `conflict_stamp` (split screen), `pin_thud` (case board), `camera_shutter` (evidence grid). `room_tone` plan cues are beds and are not copied into the micro-SFX list. `typing_tap` is accepted only as an explicit `micro_sfx` trigger.

Names that are not in the registry (`SmsPhoneThread`, `MapRouteTrace`, `TimelineDateScrubber`, `AlibiSplitScreen`, `EvidenceMatchCard`) throw `UNKNOWN_MOTIF`. Scene JSON that mentions `feTurbulence` or `feDisplacementMap` throws `SVG_FILTER` before any write.

On each of the three golden packs the compiler routes all 36 scenes, encodes 19 render_catalog MP4s (the four MVP motifs; these packs have no extended catalog scenes), and leaves 2K and Flow with their owners. `ep_golden_02_2strike_fallback` scene `s029` becomes delegated `Illustrative2KPanZoom` with `apply_grade: true`. Scene `s008` stays a withheld `HeroVideoBridge`. Eight accepted heroes keep `HeroVideoBridge`.

## Dependencies

None. Tasks 109, 110, 112, and 115–127 are open PRs and were not imported. `packages/render_catalog/package.json` is outside this write scope, so Remotion, React, and Zod were not added. The compiler does not call ffmpeg or a provider.

## Verification

Offline. Provider keys stripped by `scripts/vitest.setup.mjs`. No paid render and no provider HTTP call.

- `pnpm exec vitest run packages/render_catalog/tests/batch_compiler.test.ts` — 11 passed.
- `pnpm --filter @tc/render_catalog typecheck` — passed.
- `pnpm --filter @tc/render_catalog test -- batch_compiler` exits 0 without running this suite. The Task 001 shell has no `test` script.
- `node scripts/verify-harmony.mjs --task 128` accepts the owned paths. The model-id lint still fails on Task 002 sources already on main (`packages/shared_contracts`, `packages/shared-contracts-ts`). This branch does not change them.

## Incomplete

- The MP4 is a timed 1080p30 container, not a Chromium frame. Task 112 owns the headless pool. Pass its encoder once that branch is merged; this branch does not copy it.
- `scene_grade_manifest.json` uses the Task 109 field names (`apply_grade`, `needs_grade`, `is_foia`, `exempt_from_grain`, `remotion_grain_applied`) plus route fields (`compile_status`, `fallback_applied`, `owner_package`, `mp4_relpath`). It does not import `GradeContract.tsx`.

## Notes for the next agent

Import from `packages/render_catalog/src/renderer/BatchCompiler.ts`. Do not copy Tasks 109–127 into this branch. Commit only on `task/128-timeline-spec-batch-compiler`. Do not merge.
