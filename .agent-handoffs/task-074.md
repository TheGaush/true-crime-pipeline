# Task 074 handoff

Branch `task/074-agent4-byte0-prompt-cache`. Not merged. Not pushed.

## What landed

`packages/agent4_director/src/agent4_director/cached_director_client.py` builds director prompts in cache-friendly order:

1. **Byte 0** — global static rules JSON (`sort_keys=True`): 13 Laws, 12-motif catalog, split metaphor tables, `providers.yaml` runtime + video caps, manifests model id.
2. **Tier 2** — `CaseBible` + `spatial_anchors`.
3. **Tier 3** — dynamic `VoiceTrackManifest` scene tail.

`CachedDirectorClient` reads `DeepSeek-V4.1-Flash-1017` from `providers.yaml` (`manifests` role) and `gemini-omni-1.2-flash` from `video.primary.model_id` without copying ids into source.

## Invariants

- Cross-episode **byte-0 SHA-256** stays identical when Tier 2/3 change.
- `build_prompt_v1_bug()` (CaseBible before static rules) breaks that invariant — covered by regression tests.

## Verification

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_cached_director_client.py -p no:zero_spend_guard --import-mode=importlib
```

Tests add `packages/shared_contracts/src` on `sys.path` for fixture models only.