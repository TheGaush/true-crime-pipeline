# Task 049 Handoff

- Task: Corner watermark detector (`CornerWatermarkScanner`)
- Branch: `task/049-agent3-watermark-detector`
- Worktree: `../tc-wt/task-049-agent3-watermark-detector`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/watermark_detector.py`
  - `packages/agent3_gatekeeper/tests/test_watermark_detector.py`
  - `.agent-handoffs/task-049.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_watermark_detector.py -q
```

17 passed.

- Incomplete: none
- Notes for the next agent:
  - `corner_safe_zones` crops the outer **15%** width × **15%** height at each corner; vision is injected per `(VideoFrame, CornerSafeZone)` with no network.
  - Agency OSD (`AXON BODY`, `WatchGuard HUD` variants) never fail the gate; broadcaster marks (`CourtTV`, `Fox`, `YouTube`) set `watermark_clean = 0` only when the same canonical label appears on **≥ 2** distinct sampled `frame_index` values (one-frame vision noise passes).
  - `WatermarkScanResult.to_audit_fields()` maps to pipeline `watermark_clean` audit columns for Task 058+ compliance receipt wiring.
  - Task 050 PII detector can assume `watermark_clean` was enforced upstream on FOIA bodycam before visual PII blur.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 049
TC-Track: Part 1
TC-Never-Merge: true
```