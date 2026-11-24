# Task 062 Handoff

- Task: Config-driven Gemini 3.8 TTS adapter with per-chunk LUFS/EQ consistency
- Branch: `task/062-gemini-tts-eq-consistent`
- Worktree: `../tc-wt/task-062-gemini-tts-eq-consistent`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/gemini_tts.py`
  - `packages/voice_sync/tests/test_gemini_tts.py`
  - `.agent-handoffs/task-062.md`
- Dependencies added: none (stdlib + wave only)
- Verification:

```
$env:PYTHONPATH="packages/voice_sync/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/voice_sync/tests/test_gemini_tts.py -q
```

- Incomplete: none
- Notes for the next agent:
  - `GeminiTtsAdapter.from_providers` reads `gemini-3.8-flash-tts` / `flash-lite-tts` from repo-root `providers.yaml` without hard-coding IDs in source.
  - Inject any `GeminiTtsClient` returning mono 24 kHz s16le PCM; each chunk gets the same `DIRECTING_STYLE_PREFIX` before synthesis.
  - Mastering chain: linear 24→48 kHz resample, mono→stereo, mild spectral tilt match (`REFERENCE_TILT_DB`), then BS.1770-style integrated loudness normalize to `-16.0 LUFS` (±0.5 LU).
  - `pcm_to_wav_bytes` / `wav_bytes_to_pcm` use the stdlib `wave` module — no FFmpeg.
  - Task 065 stitcher can consume `NormalizedChunk.pcm_s16le` at 48 kHz stereo.
  - No LLM, no network, no live API.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 062
TC-Track: Part 1
TC-Never-Merge: true
```