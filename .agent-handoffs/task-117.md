# Task 117 Handoff

- Task: 117 Implement MVP Motif #3 — `AudioEvidenceCard`
- Branch: `task/117-motif-audio-evidence-card`
- Worktree: primary clone, branched from `c914ae5` (Tasks 001–004). Sibling `../tc-wt/task-117-motif-audio-evidence-card` was not created.
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/render_catalog/src/motifs/AudioEvidenceCard.tsx`
  - `packages/render_catalog/tests/motifs/audio_evidence_card.test.tsx`
  - `.agent-handoffs/task-117.md`
- Dependencies added: none. `packages/render_catalog/package.json` is outside this task. React and Remotion are not imported.
- Verification: see below. 6/6 offline tests passed. `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed.
- Incomplete: `@tc/render_catalog` has no `test` script, and root Vitest includes `*.test.ts` only. Both files belong to Task 001. Task 111 (`SafeCallout`) and Task 114 (rig consistency suite) are not on this branch and were not copied.
- Notes for the next agent: import `AudioEvidenceCard` from `packages/render_catalog/src/motifs/AudioEvidenceCard.tsx`. Do not merge.

## What landed

`AudioEvidenceCard` is the Remotion MVP motif for a 911 / interrogation audio card at `1920×1080` and `30 fps`. The plate is a flat noir booth (`data-room="noir-911-booth"`). It is not `Illustrative2KPanZoom` and it does not pan a 2K still. Remotion applies no paper grain and no vignette (`filter: "none"`, `backgroundImage: "none"`, `data-paper-grain="0"`). Paint hexes are motif art. `#C92A2A` is not used. There is no SVG turbulence.

Safe-zone content sits in a slot at `top: 108`, `height: 778` (bottom inset `194`). Badge, Law 6 banner, waveform, desk, and window stay inside that slot, so they miss the caption bar (`y >= 886`) and the bottom-right `22% × 14%` exclusion.

Badge, one label only:

- `showDramatizationBadge === true` → `TRANSCRIPT DRAMATIZATION · TTS READING`
- `showDramatizationBadge === false` → `ARCHIVAL 911 AUDIO (FOIA)`

Anything other than a boolean throws. The same PCM keeps the same spectrum when the badge flips. Both badges are `fontWeight: 700` and `fontSize: 40`. Golden `ep_golden_01_20min` scenes `s003`, `s005`, and `s007` are `AUDIO_EVIDENCE_CARD` plans whose acceptance line is `TRANSCRIPT DRAMATIZATION`. The rendered badge starts with that phrase and adds ` · TTS READING`, which is the string Task 117 requires.

Law 6 visual lead-in is an integer `lCutMs` from `600` to `1000`. Lead length is `round(lCutMs * 30 / 1000)` frames (`600 → 18`, `800 → 24`, `1000 → 30`). Local frames before that hold every bar at `0` (`data-waveform="held"`). The log spectrum is already computed. On the lead frame the bars go live. `audioOnMs` is `sceneStartMs + lCutMs`. A card that starts at timeline `0` still keeps the full lead: the 911 audio begins later, it is not scheduled before timestamp `0`. The banner text is `LAW 6 L-CUT {ms} ms`.

FFT: pass `pcmSamples` (power of two, length `16`–`1024`) or linear `fftMagnitudes` (1–513 bins), not both. `fftMagnitudes()` is a rectangular-window one-sided DFT (DC through Nyquist). A 1 kHz sine at 8 kHz over 256 samples peaks at bin `32` with magnitude `128`. `logScaledSpectrum()` peak-normalizes, then maps `(20*log10(max(m, 1e-4)) + 80) / 80`. `m=1 → 1`, `m=0.1 → 0.75`, `m=0.01 → 0.5`, `m<=1e-4 → 0`. The returned node is a React element (`$$typeof: Symbol.for("react.element")`, `type: "div"`) plus `badge`, `spectrum`, `linearMagnitudes`, `lCut`, `phase`, and `audioOnMs`.

## Verification

Provider keys were set in the shell. `scripts/vitest.setup.mjs` removed them and blocks non-loopback `fetch`. No paid API calls.

`pnpm --filter @tc/render_catalog test -- audio_evidence_card` exits 0 and runs nothing. The Task 001 shell has no `test` script, and pnpm treats a missing script as success. `package.json` is outside this write scope.

Equivalent zero-spend command (temp config adds the `.tsx` test to Vitest and loads `scripts/vitest.setup.mjs`):

```
pnpm exec vitest run --config tmp-task-117-vitest.config.mjs audio_evidence_card
```

Result: 6 passed. `pnpm exec tsc -p packages/render_catalog/tsconfig.json --noEmit` passed.

`node scripts/verify-harmony.mjs --task 117` accepts the three owned paths once `main` is `c914ae5`. The same command still fails on pre-existing model-id hits in Task 002 (`packages/shared_contracts`, `packages/shared-contracts-ts`). Those files were not edited here.

```
TC-Task-ID: 117
TC-Track: part2
TC-Never-Merge: true
```
