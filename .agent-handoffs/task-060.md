# Task 060 Handoff

- Task: Music-gated Demucs + visual/spoken PII scrub local benchmark
- Branch: `task/060-agent3-scrub-benchmark`
- Worktree: `../tc-wt/task-060-agent3-scrub-benchmark`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent3_gatekeeper/benchmarks/bench_scrub.py`
  - `packages/agent3_gatekeeper/tests/test_bench_scrub.py`
  - `.agent-handoffs/task-060.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_bench_scrub.py -q
```

9 passed.

- Incomplete: none
- Notes for the next agent:
  - `benchmark_music_gated_scrub` models music-gated Demucs vs unconditional Demucs plus simulated OpenCV/YOLO PII scrub on `SyntheticClipSpec` (durations only; no real media).
  - 8 kHz `call_911_wav` clips bypass music detection and set `demucs_skipped=True` with lower `estimated_cost` than `unconditional_demucs_cost`.
  - `music_detected=True` short clips set `demucs_applied=True`; analytical `peak_ram_gb` stays below `PEAK_RAM_CAP_GB` (4.0) for 10s–60s segments.
  - 30-minute `bodycam_mp4` with `event_timestamps_s` uses `pre_slice_bodycam_windows` (+/- 5s) so Demucs runs only on merged event windows, not the full 1800s.
  - No network and no real Demucs, OpenCV, or YOLO imports.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 060
TC-Track: Part 1
TC-Never-Merge: true
```