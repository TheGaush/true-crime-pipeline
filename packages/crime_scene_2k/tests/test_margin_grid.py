"""Margin ticks stay outside the clean still."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "margin_grid.py"
_SPEC = importlib.util.spec_from_file_location("tc_task144_margin_grid", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_grid = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _grid
_SPEC.loader.exec_module(_grid)


def test_inner_pixels_survive_and_columns_hit_the_edge(tmp_path: Path):
    source = Image.new("RGB", (2048, 1152), (0xE9, 0xE2, 0xD2))
    source.putpixel((10, 10), (1, 2, 3))
    preview = _grid.render_margin_grid(source)
    assert preview.size == (2048 + 128, 1152 + 128)
    assert _grid.interior_matches(source, preview)
    assert preview.getpixel((0, 0)) == (0x1B, 0x1B, 0x1D)
    path = tmp_path / "clean.png"
    source.save(path)
    written = _grid.write_preview(str(path), str(tmp_path / "clean_grid_preview.png"))
    assert written.size[0] == source.size[0] + 128
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
