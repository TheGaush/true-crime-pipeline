# Task 022 Handoff

- Task: 022 Comment Gap Miner & Safe-Title CTR Feasibility Check
- Branch: `task/022-agent1-comment-gap-safe-ctr`
- Worktree: `../tc-wt/task-022-agent1-comment-gap-safe-ctr`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched: `packages/agent1_scout/src/agent1_scout/comment_miner.py`, `packages/agent1_scout/tests/test_comment_miner.py`, `.agent-handoffs/task-022.md`
- Dependencies added: none (`packages/agent1_scout/pyproject.toml` was not changed)
- Verification: local `.venv` pytest, 20 passed
- Incomplete: none for this task
- Notes for the next agent: comments are `LEAD_ONLY`; `safe_title_ctr_ok == 0` rejects the candidate

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 022
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`CommentQualityGapMiner` in `packages/agent1_scout/src/agent1_scout/comment_miner.py`.

The constructor takes an injected `commentThreads.list` callable. `mine(video_id, *, title, description="", episode_analytics=None)` calls it once:

- `part="snippet"`
- `videoId`
- `maxResults=100`
- `order="relevance"`
- `textFormat="plainText"`

Only the top-level comment body is read. Replies and `nextPageToken` are ignored. There is no YouTube client, no `execute`, and no socket use. The clusterer id on the result and on every cluster is `comment-gap-miner@1`.

Before clustering, `strip_commenter_pii` removes HTML, emails, `@handles`, and phone-like numbers. Years (`1998`, `2004`) and short docket numbers (`14-2019`) stay. Prompt-injection sentences (`ignore previous instructions`, `system prompt`, `you are now`) are dropped and do not become questions.

Unanswered forensic questions are clustered on `who`, `where`, `when`, `weapon`, `timeline`, `alibi`, in that order. A question is answered when the title or description contains that axis's answer cue and every content token from the question. Statements are ignored. `unanswered_comment_questions` is the seed-packet list: at most 8 single-sentence strings, each at most 200 characters. `lead_classification` is `LEAD_ONLY`.

## Safe-title CTR

`safe_title_ctr_ok` is `1` only when the drafted documentary title is non-tabloid and still has a curiosity hook (`missing`, `unanswered`, `unknown`, `alibi`, `who` / `where` / `when` / `why`, `timeline`, and the other hook words in the module).

`CHOPPED UP IN BASEMENT?!` on a weak story (no forensic gap, no named subject, no year, no surviving hook) drafts `Local Incident Overview`, sets `safe_title_ctr_ok = 0`, `rejected = True`, `candidate_status = "REJECTED"`, and `policy_kill_reason = "TABLOID_GRAPHIC_TITLE_WEAK_STORY"`.

A graphic source title can still pass when the comments support a real gap. Example: that same screaming title plus "Who signed the night log?" and a Marcus Hale description becomes `Who signed the night log in the Hale Record` with `safe_title_ctr_ok = 1`.

A plain title with no hook, such as `Weekly Court Recap`, uses `SAFE_TITLE_LACKS_CURIOSITY_HOOK`.

The predicted hook is a bounded prior on the `ctr_pct` scale, not a network model:

- no curiosity hook: `1.0`
- hook present: `6.0 + 0.5` per unanswered cluster, capped at `+2.0` (`8.0`)

If `episode_analytics` is passed and that prediction is strictly below the median of non-null `ctr_pct` values, `safe_title_ctr_ok = 0` and `policy_kill_reason = "PREDICTED_HOOK_BELOW_MEDIAN_CTR"`. Equal to the median stays `1`. Null CTR rows and retention fields are ignored. History may be a sequence of numbers, dicts, or objects with `ctr_pct`, or a mapping with `rows` / `ctr_history`. `None` means no history and skips the median check.

Passing candidates stay `CANDIDATE`. This module does not write `GREENLIT`.

## Verification

`uv` is not required. `pyproject.toml` was not modified. `.venv` is gitignored and must not be committed.

```
PYTHONPATH=packages/agent1_scout/src
.venv\Scripts\python.exe -m pytest packages/agent1_scout/tests/test_comment_miner.py -q
```

20 passed in 0.27s.
