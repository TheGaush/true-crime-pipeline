"""Multi-provider USD budget admission for the orchestrator.

Reservations are written only to ``provider_spend_reservations`` in
``pipeline.db``. SQLite triggers ``trg_offline_test_zero_spend_guard`` and
``trg_provider_global_budget_cap_guard`` (loaded from ``schema/pipeline.sql``)
are the authority for dollar ceilings. This module executes the named
``reserve_provider_budget`` / ``settle_provider_budget`` statements inside
``BEGIN IMMEDIATE`` and surfaces trigger aborts as ``BudgetCapExceeded``. It
never opens ``telemetry.db`` for admission control.

Economics constants (``$135/mo`` ALL providers, ``$38/mo`` DeepSeek 0%-cache
ledger cap, ``$10.40/ep`` gemini omni video, ``10`` clips, ``80`` seconds) are
read from the repo-root ``providers.yaml``.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

_NAMED_QUERY = re.compile(r"^-- name:\s+(\S+)\s*$", re.MULTILINE)
_REQUIRED_QUERIES = ("reserve_provider_budget", "settle_provider_budget")
_TRIGGER_CODES = (
    "OFFLINE_TEST_ZERO_SPEND",
    "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED",
)

_FLOAT_MICRO_RE = re.compile(
    r"(?m)^\s*(all_providers_monthly_cap_micro_usd|"
    r"per_episode_video_cap_micro_usd):\s*(\d+)\s*$"
)
_GEMINI_VIDEO_RE = re.compile(
    r"(?m)^\s*(max_hero_clips|max_hero_duration_sec|episode_cap_micro_usd):\s*(\d+)\s*$"
)
_DEEPSEEK_MONTHLY_RE = re.compile(
    r"(?ms)provider_id:\s*deepseek_chat.*?monthly_cap_usd:\s*([\d.]+)"
)
_DEEPSEEK_LEDGER_RE = re.compile(
    r"(?m)^\s*-\s*provider_id:\s*deepseek_chat\s*$\n"
    r"(?:^\s*[^\n]+\n)*?"
    r"^\s*monthly_cap_micro_usd:\s*(\d+)\s*$",
    re.MULTILINE,
)


class BudgetCapExceeded(Exception):
    """A pipeline.db budget trigger or pre-insert guard rejected the write."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class ReservationNotOpen(Exception):
    """``settle_provider_budget`` matched no ``RESERVED`` or ``UNKNOWN_HOLD`` row."""


class GeminiOmniQuotaExceeded(Exception):
    """Per-episode hero clip count, duration, or USD estimate exceeds providers.yaml."""

    def __init__(self, message: str, *, code: str = "GEMINI_OMNI_EPISODE_QUOTA_EXCEEDED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProviderBudgetCaps:
    all_providers_monthly_cap_micro_usd: int
    per_episode_video_cap_micro_usd: int
    deepseek_monthly_cap_micro_usd: int
    max_hero_clips: int
    max_hero_duration_sec: int
    offline_test_cap_micro_usd: int = 0


@dataclass(frozen=True)
class ProviderReservation:
    reservation_id: str
    status: str
    estimated_micro_usd: int | None = None
    actual_micro_usd: int | None = None


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "schema" / "pipeline.sql").is_file() and (
            parent / "providers.yaml"
        ).is_file():
            return parent
    raise FileNotFoundError(
        "Could not locate schema/pipeline.sql and providers.yaml from budget_guardrails"
    )


def load_provider_budget_caps(
    providers_yaml: Path | str | None = None,
) -> ProviderBudgetCaps:
    path = Path(providers_yaml) if providers_yaml is not None else _repo_root() / "providers.yaml"
    text = path.read_text(encoding="utf-8")
    all_cap = per_ep_cap = deepseek_cap = max_clips = max_dur = None

    for match in _FLOAT_MICRO_RE.finditer(text):
        key, value = match.group(1), int(match.group(2))
        if key == "all_providers_monthly_cap_micro_usd":
            all_cap = value
        elif key == "per_episode_video_cap_micro_usd":
            per_ep_cap = value

    ledger = _DEEPSEEK_LEDGER_RE.search(text)
    if ledger:
        deepseek_cap = int(ledger.group(1))

    for match in _GEMINI_VIDEO_RE.finditer(text):
        key, value = match.group(1), int(match.group(2))
        if key == "max_hero_clips":
            max_clips = value
        elif key == "max_hero_duration_sec":
            max_dur = value
        elif key == "episode_cap_micro_usd" and per_ep_cap is None:
            per_ep_cap = value

    if deepseek_cap is None:
        monthly = _DEEPSEEK_MONTHLY_RE.search(text)
        if monthly:
            deepseek_cap = int(float(monthly.group(1)) * 1_000_000)

    missing = [
        name
        for name, val in (
            ("all_providers_monthly_cap_micro_usd", all_cap),
            ("per_episode_video_cap_micro_usd", per_ep_cap),
            ("deepseek_monthly_cap_micro_usd", deepseek_cap),
            ("max_hero_clips", max_clips),
            ("max_hero_duration_sec", max_dur),
        )
        if val is None
    ]
    if missing:
        raise ValueError(f"{path} is missing budget fields: {', '.join(missing)}")

    return ProviderBudgetCaps(
        all_providers_monthly_cap_micro_usd=all_cap,
        per_episode_video_cap_micro_usd=per_ep_cap,
        deepseek_monthly_cap_micro_usd=deepseek_cap,
        max_hero_clips=max_clips,
        max_hero_duration_sec=max_dur,
    )


def deepseek_conservative_reservation_micro_usd(
    caps: ProviderBudgetCaps,
    *,
    episode_count: int = 1,
) -> int:
    """Upper-bound micro USD for one DeepSeek reservation at 0%-cache ledger solvency."""
    if episode_count < 1:
        raise ValueError("episode_count must be >= 1")
    return caps.deepseek_monthly_cap_micro_usd // max(1, episode_count)


def validate_gemini_omni_hero_quota(
    caps: ProviderBudgetCaps,
    *,
    clip_count: int,
    duration_sec: int,
    estimated_micro_usd: int,
) -> None:
    if clip_count > caps.max_hero_clips:
        raise GeminiOmniQuotaExceeded(
            f"hero clip count {clip_count} exceeds max_hero_clips={caps.max_hero_clips}"
        )
    if duration_sec > caps.max_hero_duration_sec:
        raise GeminiOmniQuotaExceeded(
            f"hero duration {duration_sec}s exceeds "
            f"max_hero_duration_sec={caps.max_hero_duration_sec}"
        )
    if estimated_micro_usd > caps.per_episode_video_cap_micro_usd:
        raise GeminiOmniQuotaExceeded(
            f"estimate {estimated_micro_usd} micro USD exceeds per-episode video cap "
            f"{caps.per_episode_video_cap_micro_usd}"
        )


def load_named_queries(queries_sql: Path) -> dict[str, str]:
    text = queries_sql.read_text(encoding="utf-8")
    marks = list(_NAMED_QUERY.finditer(text))
    found: dict[str, str] = {}
    for index, mark in enumerate(marks):
        start = mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        found[mark.group(1)] = text[start:end].strip()
    missing = [name for name in _REQUIRED_QUERIES if name not in found]
    if missing:
        raise FileNotFoundError(
            f"{queries_sql} is missing named queries: {', '.join(missing)}"
        )
    return found


def init_pipeline_db(path: Path, *, pipeline_sql: Path | str | None = None) -> None:
    ddl = Path(pipeline_sql) if pipeline_sql is not None else _repo_root() / "schema" / "pipeline.sql"
    script = ddl.read_text(encoding="utf-8")
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(script)
        conn.commit()
    finally:
        conn.close()


def _budget_code(exc: sqlite3.Error) -> str | None:
    message = str(exc)
    for code in _TRIGGER_CODES:
        if code in message:
            return code
    return None


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


class BudgetGuardrails:
    """Reserve and settle provider USD against authoritative ``pipeline.db``."""

    def __init__(
        self,
        pipeline_db: Path | str,
        *,
        queries_sql: Path | str | None = None,
        providers_yaml: Path | str | None = None,
        busy_timeout_ms: int = 10_000,
    ) -> None:
        self.pipeline_db = Path(pipeline_db)
        root = _repo_root()
        queries_path = (
            Path(queries_sql) if queries_sql is not None else root / "schema" / "queries.sql"
        )
        self.queries = load_named_queries(queries_path)
        self.caps = load_provider_budget_caps(providers_yaml)
        self.busy_timeout_ms = busy_timeout_ms

    def reserve_provider_budget(
        self,
        *,
        reservation_id: str,
        episode_id: str | None,
        job_id: str,
        attempt_number: int,
        provider_id: str,
        purpose: str,
        year_month: str,
        estimated_micro_usd: int,
        now_ms: int,
        gemini_clip_count: int | None = None,
        gemini_duration_sec: int | None = None,
    ) -> ProviderReservation:
        if purpose == "OFFLINE_TEST" and estimated_micro_usd > self.caps.offline_test_cap_micro_usd:
            raise BudgetCapExceeded(
                "OFFLINE_TEST_ZERO_SPEND: Ordinary tests must use transport mocks with "
                "$0 estimated spend",
                code="OFFLINE_TEST_ZERO_SPEND",
            )

        if (
            provider_id == "gemini_omni"
            and purpose in ("PRODUCTION", "LIVE_SANDBOX")
            and gemini_clip_count is not None
            and gemini_duration_sec is not None
        ):
            validate_gemini_omni_hero_quota(
                self.caps,
                clip_count=gemini_clip_count,
                duration_sec=gemini_duration_sec,
                estimated_micro_usd=estimated_micro_usd,
            )

        def body(conn: sqlite3.Connection) -> ProviderReservation:
            row = conn.execute(
                self.queries["reserve_provider_budget"],
                {
                    "reservation_id": reservation_id,
                    "episode_id": episode_id,
                    "job_id": job_id,
                    "attempt_number": attempt_number,
                    "provider_id": provider_id,
                    "purpose": purpose,
                    "year_month": year_month,
                    "estimated_micro_usd": estimated_micro_usd,
                    "now_ms": now_ms,
                },
            ).fetchone()
            if row is None:
                raise RuntimeError("reserve_provider_budget did not return a row")
            return ProviderReservation(
                reservation_id=row["reservation_id"],
                estimated_micro_usd=row["estimated_micro_usd"],
                status=row["status"],
            )

        return self._immediate(body)

    def reserve_deepseek_conservative(
        self,
        *,
        reservation_id: str,
        episode_id: str | None,
        job_id: str,
        attempt_number: int,
        year_month: str,
        now_ms: int,
        purpose: str = "PRODUCTION",
    ) -> ProviderReservation:
        estimate = deepseek_conservative_reservation_micro_usd(self.caps)
        return self.reserve_provider_budget(
            reservation_id=reservation_id,
            episode_id=episode_id,
            job_id=job_id,
            attempt_number=attempt_number,
            provider_id="deepseek_chat",
            purpose=purpose,
            year_month=year_month,
            estimated_micro_usd=estimate,
            now_ms=now_ms,
        )

    def settle_provider_budget(
        self,
        *,
        reservation_id: str,
        actual_micro_usd: int,
        final_status: str,
        now_ms: int,
    ) -> ProviderReservation:
        def body(conn: sqlite3.Connection) -> ProviderReservation:
            row = conn.execute(
                self.queries["settle_provider_budget"],
                {
                    "reservation_id": reservation_id,
                    "actual_micro_usd": actual_micro_usd,
                    "final_status": final_status,
                    "now_ms": now_ms,
                },
            ).fetchone()
            if row is None:
                raise ReservationNotOpen(
                    f"reservation {reservation_id} is not RESERVED or UNKNOWN_HOLD"
                )
            return ProviderReservation(
                reservation_id=row["reservation_id"],
                actual_micro_usd=row["actual_micro_usd"],
                status=row["status"],
            )

        return self._immediate(body)

    def _immediate(self, body):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = body(conn)
            except sqlite3.Error as exc:
                _rollback(conn)
                code = _budget_code(exc)
                if code is not None:
                    raise BudgetCapExceeded(str(exc), code=code) from exc
                raise
            except Exception:
                _rollback(conn)
                raise
            else:
                try:
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    _rollback(conn)
                    raise
                return result
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        if self.pipeline_db.name == "telemetry.db":
            raise ValueError("telemetry.db must never be used for budget admission")
        conn = sqlite3.connect(
            self.pipeline_db,
            isolation_level=None,
            timeout=self.busy_timeout_ms / 1000,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
        conn.execute("PRAGMA journal_mode = WAL").fetchall()
        conn.execute("PRAGMA synchronous = FULL")
        return conn