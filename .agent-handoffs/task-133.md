# Task 133 Handoff

- Task: 133 — Implement Monochrome PIL Stickman Parity Engine
- Branch: `cursor/task-133-stickman-pil-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-133-stickman-pil`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: `packages/python_motion/pyproject.toml`, `packages/python_motion/src/python_motion/stickman_pil.py`, `packages/python_motion/tests/test_stickman_pil.py`
- Dependencies added: declared `numpy`, `pillow`, `scipy`, and `opencv-python-headless` in the package project table. Nothing was added to the root lockfile.
- Verification: `python3 -m pytest packages/python_motion/tests/test_stickman_pil.py packages/python_motion/tests/test_safety_validator.py -q` — 33 passed.
- Incomplete: there is no checked-in `@tc/render_catalog` stickman PNG snapshot to score SSIM against. The suite scores SSIM of a plate against itself (1.0) and against a different stride (< 0.999), and it checks joint positions against the catalog bone convention.
- Notes for the next agent: `StickmanRenderer.render` draws at 2x and Lanczos-downsamples with OpenCV. Flow plates (`for_flow_keyframe=True`, the default) remap crimson props to slate, or to amber when the prop is a lamp, and drop caption, watermark, timestamp, label, and text props. The red trigger is `R > 160 and R > G * 1.8 and R > B * 1.8`. Bone degrees match `StickFigureGeometry`: positive degrees rotate toward screen-left in y-down space. Eight poses: idle, walking, pointing, seated, evidence_hold, doorway_entry, detective_silhouette, arms_crossed. Frames are only 1280x720 (6px stroke) or 1920x1080 (9px stroke). `seed` does not move pixels. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 133
TC-Track: Part 2
TC-Never-Merge: true
```
