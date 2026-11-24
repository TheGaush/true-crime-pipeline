# Task 036 Handoff

- Task: Secondary news text-only extractor (zero-pixel enforcement)
- Branch: `task/036-agent2-news-text-only`
- Worktree: `../tc-wt/task-036-agent2-news-text-only`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/news_text_only.py`
  - `packages/agent2_evidence/tests/test_news_text_only.py`
  - `.agent-handoffs/task-036.md`
- Dependencies added: none (`html.parser` stdlib only)
- Verification: `python -m pytest packages/agent2_evidence/tests/test_news_text_only.py` (see commit notes)
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 036
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`extract_news_text_only` in `packages/agent2_evidence/src/agent2_evidence/news_text_only.py`.

- Strips `img`, `video`, `picture`, `source`, and `audio` subtrees with `html.parser` before collecting visible text.
- Removes any `data:*;base64,...` payload from markup and stray text nodes via regex.
- Returns `NewsTextOnlyResult` with `doc_type == "news_text_only"` and `retained_media_bytes` measured on the extracted UTF-8 text (must be `0`).
- `measure_retained_media_bytes` treats leftover `data:...;base64` fragments and literal `<img` / `<video` substrings as retained media.

Tests cover an article embedding a base64 mugshot plus nested `picture` / `video` / `audio` tags. Output keeps article sentences, drops all media bytes, and never contains the mugshot blob or `<img` / `<video` markers.