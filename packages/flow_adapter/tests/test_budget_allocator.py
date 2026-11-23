import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "flow_adapter" / "budget_allocator.py"
_SPEC = importlib.util.spec_from_file_location("tc159_budget", _PATH)
assert _SPEC and _SPEC.loader
budget = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = budget
_SPEC.loader.exec_module(budget)


def test_cap_unknown_hold_and_daily_lock(tmp_path: Path):
    connection = budget.open_ledger(str(tmp_path / "pipeline.db"))
    budget.reserve(connection, "ep", "a", 4_000_000)
    budget.mark_unknown(connection, "ep", "a")
    shot = budget.snapshot(connection, "ep")
    assert shot.unknown_hold_micro_usd == 4_000_000
    assert shot.remaining_cap_micro_usd == 6_400_000
    try:
        budget.reserve(connection, "ep", "b", 7_000_000)
        assert False
    except budget.BudgetCapError:
        pass
    budget.release(connection, "ep", "a")
    assert budget.snapshot(connection, "ep").remaining_cap_micro_usd == budget.EPISODE_CAP_MICRO_USD
    reset = budget.refill_account(connection, "tab-1", 1_000)
    assert reset - 1_000 == 86_700_000
    try:
        budget.refill_account(connection, "tab-1", reset - 1)
        assert False
    except budget.BudgetCapError:
        pass
    assert budget.refill_account(connection, "tab-1", reset) == reset + 86_700_000
