# Task 035 handoff

- Task: MuckRock & state-statute FOIA package downloader
- Branch: `task/035-agent2-foia-downloader`
- Worktree: `../tc-wt/task-035-agent2-foia-downloader`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/foia_downloader.py`
  - `packages/agent2_evidence/tests/test_foia_downloader.py`
  - `packages/agent2_evidence/tests/fixtures/marlow_foia_package.zip`
  - `packages/agent2_evidence/conftest.py`
  - `.agent-handoffs/task-035.md`
- Dependencies added: none (`pyproject.toml` unchanged)
- Verification:
  - `.venv` + `PYTHONPATH=packages/agent2_evidence/src`
  - `pytest packages/agent2_evidence/tests/test_foia_downloader.py`
- Incomplete: none
- Notes for the next agent:
  - `FoiaPackageDownloader.stage` accepts exactly one of `zip_path`, `zip_bytes`, or `zip_bytes_source` (offline only).
  - Staging root is `{staging_parent}/raw_foia/{case_id}/`; assets ship with `cleared=false` for Agent 3.
  - `ring_doorbell_neighbor.mp4` and `officer_bodycam.mp4` keep distinct basenames and distinct `origin` metadata from `foia_package_manifest.json`.
  - PDF text uses stdlib stream parsing; empty text sets `needs_ocr=true` (no OCR library).

```
TC-Task-ID: 035
TC-Track: Part 1
TC-Never-Merge: true
```