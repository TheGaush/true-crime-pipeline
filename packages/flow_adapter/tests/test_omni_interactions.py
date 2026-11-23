"""Offline interactions backend: modes, crash recovery, and the episode cap."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SRC))
import flow_adapter.backend as backend
import flow_adapter.omni_interactions as omni


class Transport:
    def __init__(self, fail: bool = False, empty: bool = False) -> None:
        self.fail = fail
        self.empty = empty
        self.created = 0

    def create(self, scene_id: str, prompt_mode: str, duration_sec: float, model_id: str) -> dict:
        self.created += 1
        if self.fail:
            raise TimeoutError(scene_id)
        return {"id": f"op-{scene_id}", "output_tokens": 0 if self.empty else 10, "mode": prompt_mode, "model": model_id, "duration": duration_sec}

    def poll(self, operation_id: str) -> str:
        return "SUCCEEDED"


def test_modes_crash_and_cap(tmp_path):
    config = backend.load_primary(str(REPO / "providers.yaml"))
    assert config.episode_cap_micro_usd == 10_400_000
    assert config.prompt_modes["TEXT_TO_VIDEO"]["frames"] == 0
    assert config.prompt_modes["FIRST_AND_LAST_FRAME"]["max_sec"] == 10
    connection = backend.open_ledger(str(tmp_path / "pipeline.db"))
    service = omni.InteractionsBackend(config, connection, Transport(), "test-key")
    text = service.dispatch("ep", "t2v", "TEXT_TO_VIDEO", 4)
    one = service.dispatch("ep", "one", "FIRST_FRAME", 5)
    two = service.dispatch("ep", "two", "FIRST_AND_LAST_FRAME", 8)
    assert text.frames_required == 0 and one.frames_required == 1 and two.frames_required == 2
    crashed = omni.InteractionsBackend(config, connection, Transport(fail=True), "test-key")
    unknown = crashed.dispatch("ep", "lost", "TEXT_TO_VIDEO", 4)
    assert unknown.state == "UNKNOWN_RECONCILE"
    assert crashed.reconcile() == ["lost"]
    blocked = omni.InteractionsBackend(config, connection, Transport(empty=True), "test-key")
    assert blocked.dispatch("ep", "safe", "TEXT_TO_VIDEO", 4).state == "SAFETY_BLOCK"
    try:
        service.dispatch("ep", "over", "TEXT_TO_VIDEO", 4)
        # still under cap; force the cap with a direct reserve
        backend.reserve(connection, "ep", "huge", config.episode_cap_micro_usd, config.episode_cap_micro_usd)
        raised = False
    except backend.BudgetCapError:
        raised = True
    assert raised is True
    try:
        omni.InteractionsBackend(config, connection, Transport(), None).dispatch("ep", "x", "TEXT_TO_VIDEO", 4)
        assert False
    except omni.MissingProviderCredentialsError:
        pass
