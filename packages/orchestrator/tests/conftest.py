"""Path setup for isolated orchestrator tests."""

from __future__ import annotations

import sys
from pathlib import Path

ORCHESTRATOR_SRC = Path(__file__).resolve().parents[1] / "src"
SHARED_CONTRACTS_SRC = Path(__file__).resolve().parents[2] / "shared_contracts" / "src"
SHARED_CONTRACTS_TESTS = Path(__file__).resolve().parents[2] / "shared_contracts" / "tests"
for path in (ORCHESTRATOR_SRC, SHARED_CONTRACTS_SRC, SHARED_CONTRACTS_TESTS):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)