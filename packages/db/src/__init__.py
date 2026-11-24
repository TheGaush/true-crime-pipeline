"""True-crime pipeline database repositories."""

from accounts_repo import (
    DAILY_CREDITS_CAP,
    DAILY_RESET_OFFSET_MS,
    MONTHLY_CREDITS_CAP,
    AccountCreditSnapshot,
    AccountPoolLedger,
    CreditPool,
    DailyCreditsLockedError,
    DailyLockStatus,
    InsufficientCreditsError,
    ReserveOutcome,
    extract_named_query,
    load_named_query,
)

try:
    from connection import PipelineDb
except ImportError:  # Task 005 may not be merged yet
    PipelineDb = None  # type: ignore[misc, assignment]

__all__ = [
    "DAILY_CREDITS_CAP",
    "DAILY_RESET_OFFSET_MS",
    "MONTHLY_CREDITS_CAP",
    "AccountCreditSnapshot",
    "AccountPoolLedger",
    "CreditPool",
    "DailyCreditsLockedError",
    "DailyLockStatus",
    "InsufficientCreditsError",
    "PipelineDb",
    "ReserveOutcome",
    "extract_named_query",
    "load_named_query",
]