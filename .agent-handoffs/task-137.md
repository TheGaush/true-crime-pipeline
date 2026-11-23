# Task 137 Handoff

- Task: 137 — Build Procedural SciPy Documentary SFX WAV Synthesizer
- Branch: `cursor/task-137-sfx-synth-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-137-sfx-synth`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: `packages/python_motion/src/python_motion/sfx_synth.py`, `packages/python_motion/tests/test_sfx_synth.py`
- Dependencies added: none. NumPy and SciPy were already declared by Task 133.
- Verification: `python3 -m pytest packages/python_motion/tests/test_sfx_synth.py -q` — 6 passed in 0.74s. ffprobe reads `pcm_s16le` at 48000 Hz.
- Incomplete: none in the owned files.
- Notes for the next agent: `SfxSynthesizer.synthesize` writes 48 kHz 16-bit PCM. Peak stays at or under -3.0 dBFS and DC offset stays under 0.001. Percussive cues use a 1 ms onset and a fade-out of `min(5 ms, n/4)`. Cache files live under the requested directory as `{cue}__s{seed}__d{duration}__i{intensity}__c{channels}.wav`. `gavel` maps to `stamp_thud`, `click` maps to `typewriter_key`, unknown names map to `paper_slide`. `siren` and `911` also map to `paper_slide` and are never synthesized. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 137
TC-Track: Part 2
TC-Never-Merge: true
```
