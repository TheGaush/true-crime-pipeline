# Task 091 Handoff

- Task: 091 Define `RenderBackendPort` interface seam
- Branch: `task/091-render-backend-port`
- Worktree: `../tc-wt/task-091-render-backend-port`
- Track: Part 1 · Developer A
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/orchestrator/src/orchestrator/render_port.py`
  - `packages/orchestrator/tests/test_render_port.py`
  - `.agent-handoffs/task-091.md`
- Dependencies added: none (`pyproject.toml` unchanged)
- Verification:
  - `$env:PYTHONPATH="packages/orchestrator/src"`
  - `..\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_render_port.py -q`
- Incomplete: none (Task 092 owns `RenderBackendStub`)
- Notes for the next agent:
  - `RenderBackendPort` in `orchestrator.render_port` is the Part 1 -> Part 2 seam (`render_code_scene`, `render_2k_panzoom`, `generate_flow_keyframes`, `dispatch_flow_jobs`, `assemble_master`).
  - AST tests scan all `packages/orchestrator/**/*.py` and fail on imports of `render_catalog`, `crime_scene_2k`, `flow_adapter`, or `agent6_mastering`.
  - `RENDER_CATALOG_MOTIF_NAMES_V1` mirrors the 12 `render_catalog` motifs; MVP slice is the first four.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 091
TC-Track: Part 1
TC-Never-Merge: true
```