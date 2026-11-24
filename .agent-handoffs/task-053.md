# Task 053 Handoff

- Task: "That vs. How" AdSense & defamation forensic rewriter (`that-vs-how-linter@1`)
- Branch: `task/053-agent3-that-vs-how-linter`
- Worktree: `../tc-wt/task-053-agent3-that-vs-how-linter`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/that_vs_how_linter.py`
  - `packages/agent3_gatekeeper/tests/test_that_vs_how_linter.py`
  - `.agent-handoffs/task-053.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_that_vs_how_linter.py -q
```

40 passed.

- Incomplete: none
- Notes for the next agent:
  - `lint_text` NFKC-normalizes input, splits on sentence boundaries, rewrites mechanism/suffering/how-framing sentences into clinical attributed `"that"` templates, then runs `zero_tolerance_scan` on the full rewritten block.
  - Sentences that already use attributed `"that"` phrasing with no banned hits pass through unchanged.
  - Homoglyph cases rely on NFKC (fullwidth Latin, ligatures) before token scan.
  - Task 056 AdSense gate can require `that_vs_how_passed` on narration text before setting compliance flags.
  - No LLM, no network, no live API.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 053
TC-Track: Part 1
TC-Never-Merge: true
```