import importlib
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "integration_bridge" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "python_motion" / "src"))
from integration_bridge.mvp_slice import SliceBlocked, connect, screen_narration, screen_source, seed

safety = importlib.import_module("python_motion.safety_validator")


def test_legal_blocks_hold(tmp_path: Path):
    try:
        screen_narration("The living minor was named on the tape.")
        assert False
    except SliceBlocked:
        pass
    try:
        screen_source("https://www.youtube.com/watch?v=abc")
        assert False
    except SliceBlocked:
        pass
    plate = np.zeros((128, 128, 3), dtype=np.uint8)
    plate[:, :, 0] = 210
    verdict = safety.InputImageSafetyValidator().validate(plate)
    assert verdict.passed is False
    assert "CRIMSON_BLOOD_CLUSTER" in verdict.violations
    connection = connect(str(tmp_path / "pipeline.db"))
    seed(connection)
    connection.commit()
    connection.execute(
        "UPDATE cases SET disposition_status = 'REVERSED', conviction_confirmed = 0, updated_at = 4000 WHERE case_id = 'case_slice'"
    )
    state = connection.execute("SELECT state FROM episodes WHERE episode_id = 'ep_slice'").fetchone()["state"]
    assert state == "QUARANTINED_LEGAL_HOLD"
    try:
        connection.execute("UPDATE episodes SET state = 'READY_TO_UPLOAD', updated_at = 5000 WHERE episode_id = 'ep_slice'")
        connection.commit()
        assert False
    except sqlite3.IntegrityError as error:
        assert "RELEASE_GATE_BLOCKED" in str(error)
