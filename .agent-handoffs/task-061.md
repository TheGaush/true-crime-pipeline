# Task 061 Handoff

- Task: Script beat and FOIA-slot chunker (`voice-segmented-chunker@1`)
- Branch: `task/061-voice-segmented-chunker`
- Worktree: `../tc-wt/task-061-voice-segmented-chunker`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/chunker.py`
  - `packages/voice_sync/tests/test_chunker.py`
  - `.agent-handoffs/task-061.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/voice_sync/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/voice_sync/tests/test_chunker.py -q
```

- Incomplete: none
- Notes for the next agent:
  - `build_tts_segment_plan(case_id, beats)` accepts ordered `NarrationBeat` and `FoiaAudioSlotBeat` values and returns a `TtsSegmentPlan` with `NARRATION`, optional `TWIST_PAD` (`is_plot_twist`), and `FOIA_AUDIO_SLOT` rows.
  - `chunk_narration_text` packs sentences into 150–450 word chunks (never mid-sentence); short narration between FOIA beats may stay below 150 words as its own chunk.
  - Task 062+ TTS adapters and Task 065 stitcher should consume `TtsSegmentPlan` segment order via `seq_index` without merging across `FOIA_AUDIO_SLOT` boundaries.
  - No network and no shared_contracts import requirement for chunking itself.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 061
TC-Track: Part 1
TC-Never-Merge: true
```