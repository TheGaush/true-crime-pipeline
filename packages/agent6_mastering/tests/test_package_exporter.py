import importlib.util
import json
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "package_exporter.py"
_SPEC = importlib.util.spec_from_file_location("tc173_export", _PATH)
assert _SPEC and _SPEC.loader
exporter = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = exporter
_SPEC.loader.exec_module(exporter)


def test_package_appears_only_after_a_passing_certificate(tmp_path: Path):
    files = {
        "final_1080p30.mp4": b"mp4",
        "variant_a": b"a",
        "variant_b": b"b",
        "variant_c": b"c",
        "chapters": b"00:00 Open\n",
    }
    meta = {
        "seo": {"title": "Case"},
        "provenance": {"episode_cost_usd": 0.0, "sfx": "procedural"},
        "qa": {"passed": False, "lufs": -14.0},
    }
    try:
        exporter.export_package(str(tmp_path), "ep_golden_01", files, meta)
        assert False
    except exporter.ExportError:
        pass
    assert not (tmp_path / "ep_golden_01").exists()
    meta["qa"]["passed"] = True
    final = exporter.export_package(str(tmp_path), "ep_golden_01", files, meta)
    assert final.name == "ep_golden_01"
    seo = json.loads((final / "seo_metadata.json").read_text(encoding="utf8"))
    assert seo["youtube_synthetic_disclosure_required"] is True
    assert (final / "provenance_bundle.json").is_file()
    assert (final / "qa_certificate.json").is_file()
    assert not (tmp_path / ".staging_ep_golden_01").exists()
