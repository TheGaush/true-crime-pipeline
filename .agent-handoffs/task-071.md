# Task 071 Handoff

- Task: `VoiceTrackManifest` serializer and per-chunk SHA-256 synthesis cache
- Branch: `task/071-voice-manifest-serializer`
- Worktree: `../tc-wt/task-071-voice-manifest-serializer`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/manifest_writer.py`
  - `packages/voice_sync/tests/test_manifest_writer.py`
  - `.agent-handoffs/task-071.md`
- Dependencies added: `shared_contracts` via `PYTHONPATH` (Pydantic models only; no new pip deps)
- Verification:

```
$env:PYTHONPATH="packages/voice_sync/src;packages/shared_contracts/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/voice_sync/tests/test_manifest_writer.py -q
```

- Incomplete: none
- Notes for the next agent:
  - `build_voice_track_manifest(episode_id, specs, cache=..., synthesize=...)` walks ordered `NarrationSegmentSpec` / `TwistPadSegmentSpec` / `FoiaSegmentSpec` rows, caches narration by `narration_text_sha256(text)`, and returns a validated `VoiceTrackManifest` plus `ManifestBuildStats`.
  - `replace_narration_chunk(...)` invalidates only the prior text hash for the edited narration segment, re-synthesizes that chunk, reuses untouched cache entries, and shifts downstream `start_ms` / word / cue globals when duration changes.
  - `serialize_manifest_payload` / `serialize_manifest_json` emit deterministic JSON for downstream persistence; YAML is not required for this task.
  - Task 072 E2E should inject real TTS/align/envelope producers into `NarrationSynthesizer` instead of the test stub.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 071
TC-Track: Part 1
TC-Never-Merge: true
```