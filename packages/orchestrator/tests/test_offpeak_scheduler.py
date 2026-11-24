"""Off-peak DeepSeek batch scheduler tests (injected UTC clock)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.offpeak_scheduler import (
    DEFAULT_OFF_PEAK_UTC_WINDOW,
    OffPeakScheduler,
    ScheduleAction,
    default_providers_path,
    load_off_peak_config,
    parse_utc_window,
    resolve_force_peak,
    utc_now_in_window,
    wait_seconds_until_off_peak,
)


def _clock_at(iso: str):
    fixed = datetime.fromisoformat(iso).replace(tzinfo=UTC)

    def _now() -> datetime:
        return fixed

    return _now


def test_repo_providers_yaml_has_no_off_peak_window():
    cfg = load_off_peak_config(default_providers_path())
    assert cfg.used_default_window is True
    assert cfg.window.utc_spec == DEFAULT_OFF_PEAK_UTC_WINDOW
    assert cfg.window.source == "default"


def test_loads_off_peak_from_yaml_when_present(tmp_path: Path):
    yaml_path = tmp_path / "providers.yaml"
    yaml_path.write_text(
        """
providers:
  deepseek_chat:
    off_peak:
      utc_window: "22:00-06:00"
      max_wait_hours: 8
""",
        encoding="utf-8",
    )
    cfg = load_off_peak_config(yaml_path)
    assert cfg.used_default_window is False
    assert cfg.window.utc_spec == "22:00-06:00"
    assert cfg.max_wait_hours == 8.0


@pytest.mark.parametrize(
    ("iso", "expected"),
    [
        ("2026-01-15T02:00:00+00:00", True),
        ("2026-01-15T12:00:00+00:00", False),
        ("2026-01-15T08:00:00+00:00", False),
    ],
)
def test_default_window_membership(iso: str, expected: bool):
    start, end = parse_utc_window(DEFAULT_OFF_PEAK_UTC_WINDOW)
    now = datetime.fromisoformat(iso)
    assert utc_now_in_window(now, start, end) is expected


def test_background_episode_n_plus_two_waits_at_noon_utc():
    sched = OffPeakScheduler.from_providers(clock=_clock_at("2026-06-01T12:00:00+00:00"))
    plan = sched.plan_heavy_batch(
        agent="agent2",
        conveyor_episode=1,
        target_episode=3,
    )
    assert plan.action is ScheduleAction.WAIT_FOR_OFF_PEAK
    assert plan.wait_seconds == pytest.approx(12 * 3600, rel=1e-6)
    assert plan.force_peak is False
    assert plan.wait_until == datetime(2026, 6, 2, 0, 0, tzinfo=UTC)


def test_background_batch_starts_inside_off_peak_at_two_utc():
    sched = OffPeakScheduler.from_providers(clock=_clock_at("2026-06-01T02:00:00+00:00"))
    plan = sched.plan_heavy_batch(
        agent="agent4",
        conveyor_episode=1,
        target_episode=3,
    )
    assert plan.action is ScheduleAction.START_NOW
    assert plan.in_off_peak_window is True
    assert plan.off_peak_discount_eligible is True
    assert plan.wait_seconds == 0.0


def test_single_episode_urgent_defaults_force_peak_at_noon():
    sched = OffPeakScheduler.from_providers(clock=_clock_at("2026-06-01T12:00:00+00:00"))
    plan = sched.plan_heavy_batch(
        agent="agent2",
        single_episode_urgent=True,
    )
    assert plan.action is ScheduleAction.START_NOW
    assert plan.force_peak is True
    assert resolve_force_peak(None, single_episode_urgent=True, background_pre_staging=False)


def test_explicit_force_peak_overrides_wait():
    sched = OffPeakScheduler.from_providers(clock=_clock_at("2026-06-01T12:00:00+00:00"))
    plan = sched.plan_heavy_batch(
        agent="agent4",
        force_peak=True,
        conveyor_episode=1,
        target_episode=3,
    )
    assert plan.action is ScheduleAction.START_NOW
    assert plan.force_peak is True


def test_wait_seconds_until_next_off_peak_from_noon():
    start, end = parse_utc_window(DEFAULT_OFF_PEAK_UTC_WINDOW)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert wait_seconds_until_off_peak(now, start, end) == pytest.approx(12 * 3600)