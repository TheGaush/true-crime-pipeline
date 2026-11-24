"""Database package used by the sole-writer tests and the telemetry logger."""

from .connection import (
    MIN_SQLITE_VERSION,
    NetworkPathError,
    PipelineDb,
    SoleWriterOccupiedError,
    SqliteVersionError,
    WalModeError,
)
from .telemetry_repo import (
    CachedTokensExceedTotal,
    EpisodeSpend,
    InvalidRates,
    InvalidUsage,
    LoggedUsage,
    MissingRate,
    TelemetryCostError,
    TelemetryCostLogger,
    UnknownModel,
)

__all__ = [
    "MIN_SQLITE_VERSION",
    "NetworkPathError",
    "PipelineDb",
    "SoleWriterOccupiedError",
    "SqliteVersionError",
    "WalModeError",
    "CachedTokensExceedTotal",
    "EpisodeSpend",
    "InvalidRates",
    "InvalidUsage",
    "LoggedUsage",
    "MissingRate",
    "TelemetryCostError",
    "TelemetryCostLogger",
    "UnknownModel",
]
