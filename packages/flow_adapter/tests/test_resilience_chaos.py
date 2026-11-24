"""Faults that must not double-charge or leave a third retry."""

from __future__ import annotations

from pathlib import Path

from flow_adapter.backend import open_ledger
from flow_adapter.budget_allocator import open_ledger as open_budget
from flow_adapter.budget_allocator import release, reserve, snapshot
from flow_adapter.circuit_breaker import CircuitBreaker, SceneTicket
from flow_adapter.drop_ingestor import DropRejectedError, ingest
from flow_adapter.omni_interactions import InteractionsBackend
from flow_adapter.backend import load_primary


def test_empty_drop_two_strikes_and_timeout_do_not_double_bill(tmp_path: Path):
    empty = tmp_path / "clip.mp4"
    empty.write_bytes(b"")
    try:
        ingest(str(empty), "sc", str(tmp_path / "out"), 1.0)
        assert False
    except DropRejectedError as error:
        assert "incomplete" in str(error).lower() or "Download" in str(error)
    breaker = CircuitBreaker(1.0)
    scene = SceneTicket("sc", "the figure runs down the hall", 4.0)
    assert breaker.fail(scene, None, None) == "RETRY"
    assert "runs" not in scene.prompt
    assert breaker.escrow_usd == 0.6
    assert breaker.fail(scene, None, None) == "fallback_triggered"
    assert breaker.fail(scene, None, None) == "fallback_triggered"
    ledger = open_budget(str(tmp_path / "budget.db"))
    reserve(ledger, "ep", "sc", 400_000)
    release(ledger, "ep", "sc")
    assert snapshot(ledger, "ep").reserved_micro_usd == 0
    config = load_primary(str(Path(__file__).resolve().parents[3] / "providers.yaml"))
    connection = open_ledger(str(tmp_path / "jobs.db"))

    class Storm:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, scene_id, prompt_mode, duration_sec, model_id):
            self.calls += 1
            raise TimeoutError("429")

        def poll(self, operation_id):
            return "FAILED"

    storm = Storm()
    backend = InteractionsBackend(config, connection, storm, api_key="local-test")
    result = backend.dispatch("ep", "sc", "TEXT_TO_VIDEO", 4)
    assert result.state == "UNKNOWN_RECONCILE"
    assert storm.calls == 1
    assert backend.reconcile() == ["sc"]
    status = connection.execute("SELECT status FROM budget_reservations WHERE scene_id='sc'").fetchone()[0]
    assert status == "RELEASED"
