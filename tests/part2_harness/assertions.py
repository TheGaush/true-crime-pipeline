"""Checks for the golden Part 2 metrics file."""

from __future__ import annotations

import json
from pathlib import Path


def assert_metrics(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf8"))
    if payload.get("remote_calls") != 0:
        raise AssertionError("a remote call was recorded")
    if payload.get("turbulence_nodes") != 0:
        raise AssertionError("a turbulence node was found")
    if payload.get("callout_error_px", 9) > 1.0:
        raise AssertionError("callout drift")
    if payload.get("episodes") != ["ep_golden_01", "ep_golden_02", "ep_golden_03"]:
        raise AssertionError("episode set")
    return payload
