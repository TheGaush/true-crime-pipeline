# Task 047 Handoff

- Task: 047 Music-Gated Demucs + Honest ASR Disagreement & Labeled-Corpus WER
- Branch: `task/047-agent3-music-gated-demucs`
- Worktree: `../tc-wt/task-047-agent3-music-gated-demucs`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/demucs_stripper.py`
  - `packages/agent3_gatekeeper/tests/test_demucs_stripper.py`
  - `packages/agent3_gatekeeper/tests/audio_corpus/bodycam_reference.json`
  - `.agent-handoffs/task-047.md`
- Dependencies added: none
- Verification: `PYTHONPATH=packages/agent3_gatekeeper/src` and `task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_demucs_stripper.py -q`
- Incomplete: none for this gate

## What landed

`MusicGatedDemucsIsolator` gates Demucs on an injected music detector and compares injected pre/post ASR hypotheses. It does not run Demucs, YAMNet, PANNs, or network I/O. Eight-kHz 911 telephony assets bypass detection entirely (`music_detected = 0`, `demucs_applied = 0`). Pure speech with a negative detector skips Demucs the same way.

Production disagreement uses `asr_hypothesis_disagreement` (token edit distance over the longer hypothesis). It is never labeled WER. When disagreement exceeds `0.10` or injected ASR confidence is low, `human_audio_review_required = 1`.

Offline QA uses `labeled_corpus_wer(hypothesis, reference)` against human ground truth. Reference fixtures live under `packages/agent3_gatekeeper/tests/audio_corpus/`.

Import: `from agent3_gatekeeper.demucs_stripper import MusicGatedDemucsIsolator`

## Notes for the next agent

Commit only on `task/047-agent3-music-gated-demucs`. Do not merge, push, or change git config.

```
TC-Task-ID: 047
TC-Track: Part 1
TC-Never-Merge: true
```