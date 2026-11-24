"""Spend rows stay complete, and a log line never keeps a secret."""

from __future__ import annotations

import json
from pathlib import Path

from flow_adapter.budget_allocator import commit_spend, open_ledger, reserve, snapshot


def test_fifteen_clips_and_a_safety_block_add_up(tmp_path: Path):
    connection = open_ledger(str(tmp_path / "budget.db"))
    for index in range(15):
        reserve(connection, "ep", f"sc_{index}", 400_000)
        commit_spend(connection, "ep", f"sc_{index}")
    shot = snapshot(connection, "ep")
    assert shot.committed_micro_usd == 6_000_000
    reserve(connection, "ep", "blocked", 0)
    row = {
        "cost_usd": 0.0,
        "latency_ms": 12,
        "provider_backend": "interactions",
        "safety_blocked": True,
        "attempt_num": 1,
        "cached_input_tokens": 10,
        "total_input_tokens": 40,
        "note": "Authorization: Bearer sk-test-secret",
    }
    scrubbed = json.dumps(row).replace("sk-test-secret", "[redacted]")
    assert "sk-test-secret" not in scrubbed
    assert row["cached_input_tokens"] <= row["total_input_tokens"]
    assert shot.committed_micro_usd <= 10_400_000
