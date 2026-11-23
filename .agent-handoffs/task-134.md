# Task 134 Handoff

- Task: 134 Implement Law 12 Input-Image Safety Validator
- Branch: `task/134-input-image-safety`
- Worktree: primary clone (no sibling worktree)
- Track: Part 2
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/python_motion/src/python_motion/safety_validator.py`
  - `packages/python_motion/tests/test_safety_validator.py`
  - `.agent-handoffs/task-134.md`
- Dependencies added: none
- Verification: `python3 -m pytest packages/python_motion/tests/test_safety_validator.py` — 20 passed in 0.15s
- Incomplete: `packages/python_motion/pyproject.toml` does not declare Pillow, NumPy, or OpenCV. Task 133 owns that file.
- Notes for the next agent: call `InputImageSafetyValidator().validate(image)`. Do not merge.

Commit only on `task/134-input-image-safety`. The branch is pushed for review. Do not merge. Do not change git config.

```
TC-Task-ID: 134
TC-Track: part2
TC-Never-Merge: true
```

## What landed

`InputImageSafetyValidator.validate` returns `ImageSafetyVerdict(passed, violations, red_pixel_pct, skin_pixel_pct)`. It accepts a uint8 `HxWx3` or `HxWx4` array (alpha ignored), a Pillow image, or a PNG path. The input buffer is not written. A failure is not cropped or blurred.

Violation codes, in this order:

1. `CRIMSON_BLOOD_CLUSTER` — an 8-connected component of at least 35 pixels with `R > 140`, `R - max(G, B) > 55`, `R - G > 55`, and `G < 100`.
2. `PHOTOREALISTIC_FACE` — an OpenCV frontal or profile Haar hit when `cv2` and its bundled cascades are installed, or a skin-toned region with two separated dark eyes and a lower dark mouth. Cascade files are never downloaded.
3. `SKIN_TONE_CLUSTER` — the largest 8-connected skin cluster is more than 3% of the inspected interior.
4. `FORBIDDEN_TEXT_BAND` — five or more consecutive high-frequency glyph rows (short ink runs whose shape changes from row to row).

The outer 16px is ignored for every check. Skin is OpenCV-scale HSV with `H` in `[2, 22]`, `S` in `[45, 175]`, `V` in `[80, 230]`, and `S < 35` excluded, so parchment `#E9E2D2` (`S` about 25) passes. Amber `#B8860B` (`R - G` is 50 and `G` is 134) passes. Blood `#C92A2A` fails once 35 pixels touch. A warm pixel with `G >= 100` is not crimson even when `R - max(G, B) > 55`.

`red_pixel_pct` counts every crimson pixel in the interior. `skin_pixel_pct` is only the largest skin cluster, so scattered specks that total more than 3% still pass. Exactly 3% passes. The margin is not a repair: pixels there are excluded from the measurement and the file is left as it was.

The task blurb also names a weapon silhouette check. The rejection rules do not, so a slate or ink prop is not rejected as a weapon.

`packages/python_motion/src/python_motion/__init__.py` already exists on `main` and was not replaced. The test loads `safety_validator.py` by path.

## Dependencies

None added. Task 133 owns `packages/python_motion/pyproject.toml` and `stickman_pil.py`. This branch does not create or edit either file. The suite imports NumPy and Pillow, which were already installed here. OpenCV is optional.

## Verification

Offline. No provider calls. Pytest loads `scripts/zero_spend_guard.py` from the repo `addopts`.

```
python3 -m pytest packages/python_motion/tests/test_safety_validator.py
```

20 passed in 0.15s.

`node scripts/verify-harmony.mjs --task 134` on this machine diffs against the local `main` ref, which is behind `origin/main`, so it lists Part 2 files that are already on `origin/main`. The branch diff against `origin/main` is only the three owned paths. Model-id lint still fails on Task 002 sources already on `main` (`packages/shared_contracts`, `packages/shared-contracts-ts`). This branch does not change them. Task 134's `Files:` line does not list the handoff, and `IMPLEMENTATION_TASKS.md` is outside this write scope.

## Notes for the next agent

Import `InputImageSafetyValidator` and `ImageSafetyVerdict` from `packages/python_motion/src/python_motion/safety_validator.py`. Require `passed is True` before uploading a keyframe. Do not copy Task 133 into this branch. Commit only on `task/134-input-image-safety`. Do not merge.
