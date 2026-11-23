"""YouTube Analytics poll plus Studio CSV ingest.

API rows never invent a monetization icon. CTR stays empty until a Studio
export or a manual entry supplies it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

PARTNER_HOURS = 8000.0


@dataclass(frozen=True)
class AnalyticsRow:
    episode_id: str
    adsense_status: str
    adsense_source: str
    ctr_pct: float | None
    watch_hours_total: float | None
    retention_30s_pct: float | None
    retention_min6_14_pct: float | None
    metrics_source: str
    adsense_checked_at: str | None = None
    rpm_micro_usd: int | None = None


def poll_analytics(client, episode_id: str, age_hours: float) -> AnalyticsRow:
    try:
        payload = client.query(episode_id)
    except PermissionError:
        return AnalyticsRow(episode_id, "NOT_LINKED", "UNAVAILABLE", None, None, None, None, "YT_ANALYTICS_API")
    minutes = payload.get("estimatedMinutesWatched")
    hours = None if minutes is None else float(minutes) / 60.0
    sparse = age_hours < 12 or not payload.get("retention")
    retention = payload.get("retention") or {}
    return AnalyticsRow(
        episode_id,
        "UNKNOWN",
        "UNAVAILABLE",
        None,
        hours,
        None if sparse else retention.get("s30"),
        None if sparse else retention.get("min6_14"),
        "YT_ANALYTICS_API",
    )


def ingest_studio_csv(path: str, checked_at: str) -> list[AnalyticsRow]:
    rows = []
    with Path(path).open(encoding="utf8", newline="") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                AnalyticsRow(
                    record["episode_id"],
                    record.get("adsense_status") or "UNKNOWN",
                    "STUDIO_CSV_EXPORT",
                    float(record["ctr_pct"]) if record.get("ctr_pct") else None,
                    float(record["watch_hours"]) if record.get("watch_hours") else None,
                    _optional(record.get("retention_30s_pct")),
                    _optional(record.get("retention_min6_14_pct")),
                    "STUDIO_CSV_EXPORT",
                    checked_at,
                    int(record["rpm_micro_usd"]) if record.get("rpm_micro_usd") else None,
                )
            )
    return rows


def manual_entry(episode_id: str, adsense_status: str, ctr_pct: float | None, checked_at: str) -> AnalyticsRow:
    return AnalyticsRow(episode_id, adsense_status, "MANUAL_CREATOR_ENTRY", ctr_pct, None, None, None, "MANUAL_CREATOR_ENTRY", checked_at)


def runway(watch_hours_total: float) -> dict:
    return {"target_hours": PARTNER_HOURS, "watch_hours_total": watch_hours_total, "remaining_hours": PARTNER_HOURS - watch_hours_total}


def _optional(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
