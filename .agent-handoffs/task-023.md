# Task 023 Handoff

- Task: 023 Gemini YouTube URL X-Ray with age-restricted metadata fallback
- Branch: `task/023-agent1-gemini-xray-fallback`
- Worktree: `../tc-wt/task-023-agent1-gemini-xray-fallback`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent1_scout/src/agent1_scout/gemini_xray.py`
  - `packages/agent1_scout/tests/test_gemini_xray.py`
  - `.agent-handoffs/task-023.md`
- Dependencies added: none (`pyproject.toml` was not changed)
- Verification: local `.venv` (`--system-site-packages`), `PYTHONPATH=packages/agent1_scout/src`, `python -m pytest packages/agent1_scout/tests/test_gemini_xray.py -q` → 9 passed
- Incomplete: none for this task
- Notes for the next agent:

`GeminiYouTubeXRayClient` is `youtube-xray@2`. Construct it with an injected Gemini client (`inspect_youtube_urls(model, urls)`) and an injected YouTube client (`videos.list` and `commentThreads.list`). `inspect` sends at most 5 YouTube watch URLs. It does not download MP4s. `captions.download` is not implemented; any captions request raises `UnsupportedCaptionsDownload`.

The model id is loaded from `providers.yaml` by `load_youtube_xray_model_id`. That loader is the only reader. It selects the first model under a `gemini*` provider family whose roles include `youtube_xray`. The current registry entry is the first `gemini_text` model. Do not copy that id into package source.

Successful playback returns factual lead keys with `source_mode=AGENTIC_VIDEO` and `facts_confirmed=True`. `PLAYBACK_RESTRICTED` or `AGE_GATED` (return value or exception code) falls back to authorized `videos.list` fields `title`, `description`, and `tags`, plus public comment questions. That result is `LEAD_ONLY`. Comments and metadata are not confirmed facts. An empty description fills SeedPacket-shaped lead keys from comment entity mentions and the supplied `search_snippets`, still `LEAD_ONLY`.

The package lives at `src/agent1_scout/` so the module imports as `agent1_scout.gemini_xray`. `providers.yaml` was not edited. No network client is called.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 023
TC-Track: Part 1
TC-Never-Merge: true
```
