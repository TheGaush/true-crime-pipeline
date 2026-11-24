import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from integration_bridge.pipeline_run import workflow_report


def test_six_agents_run_offline_in_order():
    report = workflow_report()
    assert [stage["agent"] for stage in report] == [1, 2, 3, 4, 5, 6]
    assert [stage["name"] for stage in report] == [
        "scout",
        "evidence",
        "shield",
        "director",
        "render",
        "master",
    ]
    assert all(stage["passed"] for stage in report)
    assert report[4]["live"] is False
    assert report[3]["live"] is False
