"""Sole-writer SQLite WAL driver.

Import ``PipelineDb`` from this package. The src layout is mapped to the
``db`` distribution name in ``pyproject.toml``.
"""

from .connection import (
    MIN_SQLITE_VERSION,
    NetworkPathError,
    PipelineDb,
    SoleWriterOccupiedError,
    SqliteVersionError,
    WalModeError,
)

__all__ = [
    "MIN_SQLITE_VERSION",
    "NetworkPathError",
    "PipelineDb",
    "SoleWriterOccupiedError",
    "SqliteVersionError",
    "WalModeError",
]
