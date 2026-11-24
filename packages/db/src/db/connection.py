"""Expose the sole-writer driver as ``db.connection`` inside the package directory."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "connection.py"
_SPEC = importlib.util.spec_from_file_location("db._wal_connection", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"missing {_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

for _name, _value in vars(_MODULE).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value
