import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "analytics_feedback" / "yt_poller.py"
_SPEC = importlib.util.spec_from_file_location("tc184_poller", _PATH)
assert _SPEC and _SPEC.loader
poller = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = poller
_SPEC.loader.exec_module(poller)


class Client:
    def __init__(self, payload=None, linked=True) -> None:
        self.payload = payload or {}
        self.linked = linked

    def query(self, episode_id: str) -> dict:
        if not self.linked:
            raise PermissionError(episode_id)
        return self.payload


def test_api_stays_unknown_and_csv_can_fill_ctr(tmp_path: Path):
    young = poller.poll_analytics(Client({"estimatedMinutesWatched": 30, "retention": {"s30": 0.0}}), "ep", 2)
    assert young.adsense_status == "UNKNOWN"
    assert young.adsense_source == "UNAVAILABLE"
    assert young.ctr_pct is None
    assert young.retention_30s_pct is None
    assert young.watch_hours_total == 0.5
    mature = poller.poll_analytics(
        Client({"estimatedMinutesWatched": 120, "averageViewPercentage": 40, "retention": {"s30": 71.0, "min6_14": 44.0}}),
        "ep",
        48,
    )
    assert mature.retention_30s_pct == 71.0
    assert mature.metrics_source == "YT_ANALYTICS_API"
    unlinked = poller.poll_analytics(Client(linked=False), "ep", 48)
    assert unlinked.adsense_status == "NOT_LINKED"
    csv_path = tmp_path / "studio.csv"
    csv_path.write_text("episode_id,ctr_pct,rpm_micro_usd,adsense_status,watch_hours\nep,4.5,1800000,MONETIZED,120\n", encoding="utf8")
    imported = poller.ingest_studio_csv(str(csv_path), "2026-11-24T00:00:00Z")[0]
    assert imported.adsense_source == "STUDIO_CSV_EXPORT"
    assert imported.ctr_pct == 4.5
    assert imported.rpm_micro_usd == 1_800_000
    manual = poller.manual_entry("ep", "MONETIZED", 3.0, "2026-11-24T00:00:00Z")
    assert manual.adsense_source == "MANUAL_CREATOR_ENTRY"
    assert poller.runway(120)["remaining_hours"] == 7880
