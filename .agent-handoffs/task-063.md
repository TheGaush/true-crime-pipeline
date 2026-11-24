# Task 063 Handoff

- Task: Google Vids audio-extraction optional fallback (`google-vids-tts-adapter@1`)
- Branch: `task/063-google-vids-tts-adapter`
- Worktree: `../tc-wt/task-063-google-vids-tts-adapter`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/google_vids_tts.py`
  - `packages/voice_sync/tests/test_google_vids_tts.py`
  - `.agent-handoffs/task-063.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/voice_sync/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/voice_sync/tests/test_google_vids_tts.py -q
```

12 passed.

- Incomplete: none
- Notes for the next agent:
  - `format_bracket_tag_script` maps `[calmly]` / `[dramatically]` markers into `[Direction: tag]` blocks for Google Vids voiceover scripts.
  - `GoogleVidsTtsAdapter.extract_voiceover` runs only when `GoogleVidsSelection(explicit=True)` and an injected `AudioStreamReader` are supplied; video-only exports raise `MissingAudioStreamError`.
  - Mastering is pure Python (no FFmpeg): resample to 48 kHz stereo, mild spectral tilt parity, integrated BS.1770-style K-weighted loudness to **-16.0 LUFS** (+/- 0.5 LU).
  - Tests inject PCM bytes via a small `_Stream` stand-in instead of parsing real MP4.
  - Task 065 stitcher can consume mastered PCM from this fallback when the operator manually exports Google Vids audio.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 063
TC-Track: Part 1
TC-Never-Merge: true
```