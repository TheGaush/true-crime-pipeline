# Task 059 Handoff

- Task: 059 Agent 3 Granular Legal, Spoken PII & Policy Red-Team Suite
- Branch: `task/059-agent3-redteam-suite`
- Worktree: `../tc-wt/task-059-agent3-redteam-suite`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/pipeline.py`
  - `packages/agent3_gatekeeper/tests/test_agent3_redteam.py`
  - `packages/agent3_gatekeeper/tests/audio_corpus/bodycam_reference.json`
  - `.agent-handoffs/task-059.md`
- Dependencies added: none
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_agent3_redteam.py -q
```

→ 13 passed

## What landed

`Agent3GatekeeperService` encodes nine offline red-team traps in one integration
pipeline. Other Agent 3 modules from Tasks 045–058 are not imported; rules are
local pure functions only. No sockets.

Import:

```python
from agent3_gatekeeper.pipeline import Agent3GatekeeperService, NINE_TRAP_IDS
```

### Nine traps certified

1. **Ring CCTV in MuckRock FOIA ZIP** → `RESTRICTED_NO_REUSE`, ingest blocked
2. **Wikimedia `CC BY-NC`** → rejected (`PROVENANCE_LICENSE_RESTRICTED`)
3. **`911_8khz_distorted.wav`** → Demucs bypass (`demucs_applied = 0`)
4. **`bodycam_440hz_music_042profanity.mp4`** → music gate + separate
   `asr_hypothesis_disagreement` vs `labeled_corpus_wer`
5. **Profanity at 0:42** mapped to cold open → bleep plan + post-scrub ASR clean
6. **Spoken phone & address** on `911_spoken_pii.wav` → tone-muted intervals
7. **CourtTV corner logo** fails watermark; **bystander face** fails until blurred
8. **Graphic how-phrasing** and **you-should legal advice** rewritten
9. **Unhedged `news_report` beat** → `RULE_09_UNHEDGED_NEWS_CITATION`

Edge: overlapping spoken PII + profanity intervals merge into one muted span.

## Notes for the next agent

Commit only on `task/059-agent3-redteam-suite`. Do not merge, push, or change
git config. Task 060 scrub benchmark may import metrics patterns from this suite.

```
TC-Task-ID: 059
TC-Track: Part 1
TC-Never-Merge: true
```