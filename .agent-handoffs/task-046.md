# Task 046 Handoff

- Task: Non-whitelisted pixel purge, ingest CFR/48 kHz normalization & 3P blocker
- Branch: `task/046-agent3-ingest-norm-pixel-purge`
- Worktree: `../tc-wt/task-046-agent3-ingest-norm-pixel-purge`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/ingest_normalizer.py`
  - `packages/agent3_gatekeeper/tests/test_ingest_normalizer.py`
  - `.agent-handoffs/task-046.md`
- Dependencies added: none (stdlib only; ffmpeg is planned, not executed)
- Verification: see commit notes (`pytest packages/agent3_gatekeeper/tests/test_ingest_normalizer.py`)
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 046
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`ingest_normalizer.py` in `packages/agent3_gatekeeper/src/agent3_gatekeeper/`.

- `CONTRABAND_TAGS`: `news`, `CC BY-NC`, `Ring CCTV`.
- `purge_contraband_file` unlinks contraband staging bytes and returns `refuse_reason=CONTRABAND_PIXEL_PURGE`, `normalized_cfr_30fps_48k=0`.
- `plan_cleared_ingest` returns the ffmpeg argv (no subprocess) that would produce **30 fps CFR**, **yuv420p** (video), **48 kHz stereo 24-bit PCM**, using `aresample=48000:resampler=soxr` and dual-mono `pan=stereo|c0=c0|c1=c0` for **8 kHz mono** 911 WAV sources.
- Cleared assets set `normalized_cfr_30fps_48k = 1`.
- `audit_staging_folder` purges contraband paths from a `(path, provenance_tag)` manifest.

Import: `from agent3_gatekeeper.ingest_normalizer import plan_cleared_ingest, purge_contraband_file`.

`packages/agent3_gatekeeper/pyproject.toml` was not changed.