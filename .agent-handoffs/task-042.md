# Task 042 Handoff

- Task: Early Image API 2K generator & margin 10x10 anchor lock
- Branch: `task/042-agent2-early-2k-anchor-lock`
- Worktree: `../tc-wt/task-042-agent2-early-2k-anchor-lock`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/early_2k_anchors.py`
  - `packages/agent2_evidence/tests/test_early_2k_anchors.py`
  - `.agent-handoffs/task-042.md`
- Dependencies added: none (runtime uses injected clients; tests use existing venv Pillow + PyYAML for `providers.yaml`)
- Verification:
  - `$env:PYTHONPATH="packages/agent2_evidence/src;packages/shared_contracts/src"`
  - `python -m pytest packages/agent2_evidence/tests/test_early_2k_anchors.py -v` → 5 passed
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 042
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`Early2KAnchorLockService` in `packages/agent2_evidence/src/agent2_evidence/early_2k_anchors.py`.

- Injects `ImageClient` and `VisionClient`; reads image/vision model ids from `providers.yaml` via `provider_registry` (no sockets).
- `cluster_physical_clues` dedupes and batches at most eight clues per 2K pass.
- Clean plate bytes are hashed once; `build_inspection_png_with_margin` adds a non-occluding 64px `A–J` / `1–10` border on a separate PNG for vision grounding only.
- `grounding_to_anchor_fields` maps `grid_cell` + `span_cols` / `span_rows` through `shared_contracts.grid.grid_cell_to_pixel_and_zoom` (`target_zoom` clamped 1.6–3.8).
- `still_assets` rows always carry `is_illustrative_reconstruction = 1` and disclaimer `ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO`.
- `spatial_anchors` start `DRAFT`; `transition_anchor_lock` enforces `DRAFT → IN_REVIEW → LOCKED` with SQLite-checked proof fields on lock.