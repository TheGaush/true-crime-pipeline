# Task 067 Handoff

- Task: Bounded cloud ASR wrapper (`<= 90s` / `<= 4 MiB` `16 kHz` mono FLAC slicer)
- Branch: `task/067-bounded-cloud-asr-slicer`
- Worktree: `../tc-wt/task-067-bounded-cloud-asr-slicer`
- Track: Part 1
- Status: Complete (offline)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/bounded_cloud_asr.py`
  - `packages/voice_sync/tests/test_bounded_cloud_asr.py`
  - `.agent-handoffs/task-067.md`
- Dependencies added: none (stdlib only)
- Verification: `pytest packages/voice_sync/tests/test_bounded_cloud_asr.py` with `PYTHONPATH=packages/voice_sync/src`
- Incomplete: none
- Notes for the next agent:
  - ffmpeg is **not** used; `48 kHz` stereo → `16 kHz` mono FLAC sizes are simulated via `estimate_flac_mono_16k_bytes()`.
  - `guard_before_transport()` hard-rejects payloads `> 7.5 MiB` or `> 115s` before mocked transport calls (`F-03`).
  - Spoken year `2023` normalizes to `twenty twenty three` on transcript hints carried with each chunk.
  - Task 068 cue/pronunciation gate can consume bounded optional cloud ASR output separately from WhisperX.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 067
TC-Track: Part 1
TC-Never-Merge: true
```