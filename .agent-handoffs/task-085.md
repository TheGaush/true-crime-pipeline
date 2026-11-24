# Task 085 Handoff

- Task: `RULE_11` split `prompt_mode` compressor (`FIRST_FRAME` / `FIRST_AND_LAST_FRAME` vs `TEXT_TO_VIDEO`)
- Branch: `task/085-linter-rule11-split-compressor`
- Worktree: `../tc-wt/task-085-linter-rule11-split-compressor`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/src/agent4_director/rules/rule_11_prompt_compress.py`
  - `packages/agent4_director/tests/test_rule_11.py`
  - `.agent-handoffs/task-085.md`
- Dependencies added: none (stdlib only in `agent4_director`)
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_11.py -q
```

- Incomplete: `RULE_12` anonymizer / cinematography bigram whitelist (Task 086) and linter_core wiring remain downstream.
- Notes for the next agent:
  - `compress_motion_prompt` strips appearance tokens (`hooded`, `detective`, `charcoal`, `coat`, `fedora`) for `FIRST_FRAME` and `FIRST_AND_LAST_FRAME`, normalizing leading `2D ink figure` subjects to `Figure`.
  - `TEXT_TO_VIDEO` passes prompts through unchanged so concise stylized labels (e.g. `Minimalist 2D stick figure`) are allowed.
  - Motion prompts are validated at **15–30 words** with bans on whole-word `no` and `don't show`.
  - Duration bounds: `TEXT_TO_VIDEO` and `FIRST_FRAME` **3s–15s**; `FIRST_AND_LAST_FRAME` **3s–10s** (milliseconds API on `Rule11Scene.duration_ms`).
  - Retired contracts `FRAMES_MOTION_ONLY` and `VEO_3_1_LITE` (including `Veo 3.1 Lite` text drift) hard-fail via `validate_rule_11`.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 085
TC-Track: Part 1
TC-Never-Merge: true
```