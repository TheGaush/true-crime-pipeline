# Task 052 Handoff

- Task: 052 Fact-Grounded, Topology-Safe Documentary Script Generator
- Branch: `task/052-agent3-grounded-script-gen`
- Worktree: `../tc-wt/task-052-agent3-grounded-script-gen`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/script_generator.py`
  - `packages/agent3_gatekeeper/tests/test_script_generator.py`
  - `.agent-handoffs/task-052.md`
- Dependencies added: none
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_script_generator.py -q
```

- Incomplete: none for this gate

## What landed

`GroundedScriptGenerator` compiles per-scene narration only when every `spatial_anchors` row is `LOCKED`. It computes `target_narration_words = (1200 - foia_total_sec) / 60 * 145`, builds topology-safe clauses from the fact ledger, stamps `narration_version_sha256`, and fills Stage-1 scene plan fields (`story_purpose`, `intended_audience_effect`, `approved_narration_text`, `cited_fact_ids`). Unknown or unsupplied fact citations reject compilation; successful runs set episode status `SCENE_PLAN_APPROVED`.

Import:

```python
from agent3_gatekeeper.script_generator import (
    GroundedScriptGenerator,
    compute_target_narration_words,
    EPISODE_STATUS_SCENE_PLAN_APPROVED,
)
```

`apply_external_narration` validates mocked LLM narration without network I/O. `craft_rubric.yaml` is not modified.

## Notes for the next agent

Commit only on `task/052-agent3-grounded-script-gen`. Do not merge, push, or change git config.

```
TC-Task-ID: 052
TC-Track: Part 1
TC-Never-Merge: true
```