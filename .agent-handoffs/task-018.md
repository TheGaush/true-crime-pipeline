# Task 018 — Canonical alias expander (`alias-expander@1`)

Branch: `task/018-agent1-alias-expander`. Do not merge.

## What landed

`CanonicalAliasExpander` in `packages/agent1_scout/src/alias_expander.py`.

- Expands grounded `CaseFacts` into 3–4 YouTube search aliases (hard cap of 4 after normalization and deduplication).
- Canonical slots: suspect full name + year, victim name + crime, city + case nickname, unique forensic detail. Slots with missing inputs are omitted from the `<data>` envelope instead of inventing text.
- Clickbait-only titles (no person or place names in the title string) return `AliasExpansionDeferred` with reason `waiting for youtube-xray name extraction`; the injected LLM is not called.
- Case facts and available slots are sent inside a `<data>...</data>` envelope. The model response is parsed as JSON (or line-based fallback), then each query is normalized (`casefold`, collapse whitespace, strip punctuation) and deduplicated.
- Model routing accepts an explicit `model_id` or defaults via `default_model_id()` from a providers-shaped dict (`prompt_contracts[alias-expander@1]` or a DeepSeek `alias_expansion` role). No provider id is hardcoded in the module.

## Tests

From `packages/agent1_scout`:

`python -m pytest tests/test_alias_expander.py`

Offline fake LLM only; no network.