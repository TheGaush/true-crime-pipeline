# Task 064 Handoff

- Task: DeepSeek Speech TTS failover adapter
- Branch: `task/064-deepseek-tts-adapter`
- Worktree: `../tc-wt/task-064-deepseek-tts-adapter`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/deepseek_tts.py`
  - `packages/voice_sync/tests/test_deepseek_tts.py`
  - `.agent-handoffs/task-064.md`
- Dependencies added: none (stdlib + wave only; providers.yaml parsed in-module)
- Verification:

```powershell
$env:PYTHONPATH="packages/voice_sync/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/voice_sync/tests/test_deepseek_tts.py -q
```

- Incomplete: none
- Notes for the next agent:
  - `load_deepseek_tts_config` reads the DeepSeek speech model from the first `deepseek_chat.models[].id`, the failover model id from `tts.models` with role `alternate` (`flash-lite-tts`), and a conservative `micro_usd_per_char` planning rate from `micro_usd_per_usd` + `tts.usd_per_episode_with_vision_qa_conservative`.
  - Inject any `DeepSeekHttpClient` implementing `post(path=..., json_body=...) -> HttpResponse`; the module itself imports no HTTP/socket libraries.
  - `DeepSeekTtsAdapter.synthesize_episode` keeps one active `voice_id` per episode; mid-episode primary `503` engages failover, marks earlier chunks `needs_resynthesis`, and re-synthesizes them on the failover voice/model so chunk timbre matches.
  - Mastering: 24 kHz mono PCM from HTTP → 48 kHz stereo, tilt match, integrated `-16.0 LUFS` (±0.5 LU).
  - Task 065 stitcher can consume `NormalizedChunk.pcm_s16le`.
  - No live API calls in tests.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 064
TC-Track: Part 1
TC-Never-Merge: true
```