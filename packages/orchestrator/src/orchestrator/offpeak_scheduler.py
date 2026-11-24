"""DeepSeek off-peak batch window scheduler (UTC).

Heavy Agent 2 / Agent 4 LLM batches are deferred into the configured off-peak
UTC window unless ``force_peak`` overrides scheduling. Window bounds are read
from ``providers.yaml`` when present; see ``DEFAULT_OFF_PEAK_UTC_WINDOW``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml

DEFAULT_OFF_PEAK_UTC_WINDOW = "00:00-08:00"
DEFAULT_MAX_WAIT_HOURS = 12.0
DEEPSEEK_PROVIDER_ID = "deepseek_chat"
HEAVY_AGENTS = frozenset({"agent2", "agent4", "agent2_evidence", "agent4_director"})

Clock = Callable[[], datetime]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_providers_path() -> Path:
    return _repo_root() / "providers.yaml"


def parse_utc_window(spec: str) -> tuple[time, time]:
    """Parse ``HH:MM-HH:MM`` into UTC ``time`` bounds (end exclusive)."""
    text = spec.strip().upper().replace("UTC", "").strip()
    if "-" not in text:
        raise ValueError(f"off-peak window must look like HH:MM-HH:MM, got {spec!r}")
    start_s, end_s = (part.strip() for part in text.split("-", 1))
    return _parse_hhmm(start_s), _parse_hhmm(end_s)


def _parse_hhmm(value: str) -> time:
    hour_s, minute_s = value.split(":", 1)
    hour = int(hour_s)
    minute = int(minute_s)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid UTC time {value!r}")
    return time(hour=hour, minute=minute, tzinfo=UTC)


def utc_now_in_window(now: datetime, window_start: time, window_end: time) -> bool:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    current = now.timetz()
    if window_start < window_end:
        return window_start <= current < window_end
    return current >= window_start or current < window_end


def next_off_peak_start(now: datetime, window_start: time, window_end: time) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    if utc_now_in_window(now, window_start, window_end):
        return now
    today_start = datetime.combine(now.date(), window_start, tzinfo=UTC)
    if now < today_start and window_start < window_end:
        return today_start
    return today_start + timedelta(days=1)


def wait_seconds_until_off_peak(
    now: datetime, window_start: time, window_end: time
) -> float:
    target = next_off_peak_start(now, window_start, window_end)
    return max(0.0, (target - now.astimezone(UTC)).total_seconds())


@dataclass(frozen=True)
class OffPeakWindow:
    utc_spec: str
    start: time
    end: time
    source: Literal["providers.yaml", "default"]


@dataclass(frozen=True)
class OffPeakConfig:
    window: OffPeakWindow
    max_wait_hours: float
    used_default_window: bool


def _deepseek_off_peak_mapping(doc: dict[str, Any]) -> dict[str, Any] | None:
    providers = doc.get("providers")
    if not isinstance(providers, dict):
        return None
    deepseek = providers.get(DEEPSEEK_PROVIDER_ID)
    if not isinstance(deepseek, dict):
        return None
    off_peak = deepseek.get("off_peak")
    if isinstance(off_peak, dict):
        return off_peak
    batch = deepseek.get("batch")
    if isinstance(batch, dict) and isinstance(batch.get("off_peak"), dict):
        return batch["off_peak"]
    return None


def _window_spec_from_mapping(off_peak: dict[str, Any]) -> str | None:
    for key in ("utc_window", "window_utc", "utc"):
        raw = off_peak.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    start = off_peak.get("start") or off_peak.get("utc_start")
    end = off_peak.get("end") or off_peak.get("utc_end")
    if isinstance(start, str) and isinstance(end, str):
        return f"{start.strip()}-{end.strip()}"
    return None


def load_off_peak_config(providers_path: Path | None = None) -> OffPeakConfig:
    path = providers_path or default_providers_path()
    if not path.is_file():
        start, end = parse_utc_window(DEFAULT_OFF_PEAK_UTC_WINDOW)
        return OffPeakConfig(
            window=OffPeakWindow(
                utc_spec=DEFAULT_OFF_PEAK_UTC_WINDOW,
                start=start,
                end=end,
                source="default",
            ),
            max_wait_hours=DEFAULT_MAX_WAIT_HOURS,
            used_default_window=True,
        )
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        doc = {}
    off_peak = _deepseek_off_peak_mapping(doc) or {}
    spec = _window_spec_from_mapping(off_peak)
    max_wait = off_peak.get("max_wait_hours", DEFAULT_MAX_WAIT_HOURS)
    try:
        max_wait_f = float(max_wait)
    except (TypeError, ValueError):
        max_wait_f = DEFAULT_MAX_WAIT_HOURS
    if not spec:
        start, end = parse_utc_window(DEFAULT_OFF_PEAK_UTC_WINDOW)
        return OffPeakConfig(
            window=OffPeakWindow(
                utc_spec=DEFAULT_OFF_PEAK_UTC_WINDOW,
                start=start,
                end=end,
                source="default",
            ),
            max_wait_hours=max_wait_f,
            used_default_window=True,
        )
    start, end = parse_utc_window(spec)
    return OffPeakConfig(
        window=OffPeakWindow(
            utc_spec=spec,
            start=start,
            end=end,
            source="providers.yaml",
        ),
        max_wait_hours=max_wait_f,
        used_default_window=False,
    )


class ScheduleAction(StrEnum):
    START_NOW = "start_now"
    WAIT_FOR_OFF_PEAK = "wait_for_off_peak"


@dataclass(frozen=True)
class HeavyRunPlan:
    action: ScheduleAction
    now: datetime
    wait_until: datetime | None
    wait_seconds: float
    in_off_peak_window: bool
    force_peak: bool
    off_peak_discount_eligible: bool
    reason: str


def resolve_force_peak(
    force_peak: bool | None,
    *,
    single_episode_urgent: bool,
    background_pre_staging: bool,
) -> bool:
    if force_peak is not None:
        return force_peak
    if single_episode_urgent:
        return True
    if background_pre_staging:
        return False
    return False


def is_background_pre_staging(
    conveyor_episode: int | None, target_episode: int | None
) -> bool:
    if conveyor_episode is None or target_episode is None:
        return False
    return target_episode - conveyor_episode >= 2


class OffPeakScheduler:
    """Routes heavy DeepSeek batches into the configured off-peak UTC window."""

    def __init__(
        self,
        config: OffPeakConfig,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.config = config
        self._clock = clock or (lambda: datetime.now(UTC))

    @classmethod
    def from_providers(
        cls,
        providers_path: Path | None = None,
        *,
        clock: Clock | None = None,
    ) -> OffPeakScheduler:
        return cls(load_off_peak_config(providers_path), clock=clock)

    def now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def plan_heavy_batch(
        self,
        *,
        agent: str,
        force_peak: bool | None = None,
        single_episode_urgent: bool = False,
        conveyor_episode: int | None = None,
        target_episode: int | None = None,
    ) -> HeavyRunPlan:
        agent_key = agent.strip().lower()
        if agent_key not in HEAVY_AGENTS:
            now = self.now()
            return HeavyRunPlan(
                action=ScheduleAction.START_NOW,
                now=now,
                wait_until=None,
                wait_seconds=0.0,
                in_off_peak_window=False,
                force_peak=True,
                off_peak_discount_eligible=False,
                reason=f"agent {agent!r} is not a heavy DeepSeek batch agent",
            )

        background = is_background_pre_staging(conveyor_episode, target_episode)
        peak_override = resolve_force_peak(
            force_peak,
            single_episode_urgent=single_episode_urgent,
            background_pre_staging=background,
        )

        now = self.now()
        window = self.config.window
        in_window = utc_now_in_window(now, window.start, window.end)

        if peak_override or in_window:
            reason = (
                "force_peak override"
                if peak_override and not in_window
                else "inside off-peak UTC window"
                if in_window
                else "force_peak with in-window start"
            )
            return HeavyRunPlan(
                action=ScheduleAction.START_NOW,
                now=now,
                wait_until=now,
                wait_seconds=0.0,
                in_off_peak_window=in_window,
                force_peak=peak_override,
                off_peak_discount_eligible=in_window and not peak_override,
                reason=reason,
            )

        wait_seconds = wait_seconds_until_off_peak(now, window.start, window.end)
        wait_until = now + timedelta(seconds=wait_seconds)
        max_wait_seconds = self.config.max_wait_hours * 3600.0
        if wait_seconds > max_wait_seconds:
            return HeavyRunPlan(
                action=ScheduleAction.START_NOW,
                now=now,
                wait_until=now,
                wait_seconds=0.0,
                in_off_peak_window=False,
                force_peak=True,
                off_peak_discount_eligible=False,
                reason=(
                    f"wait {wait_seconds / 3600:.2f}h exceeds max_wait_hours="
                    f"{self.config.max_wait_hours:g}; starting at peak"
                ),
            )

        return HeavyRunPlan(
            action=ScheduleAction.WAIT_FOR_OFF_PEAK,
            now=now,
            wait_until=wait_until,
            wait_seconds=wait_seconds,
            in_off_peak_window=False,
            force_peak=False,
            off_peak_discount_eligible=True,
            reason="heavy background batch deferred to off-peak UTC window",
        )
