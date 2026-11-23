"""Spatial anchor validation against clean and corrupt stills."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "anchor_loader.py"
_SPEC = importlib.util.spec_from_file_location("tc_task143_anchor_loader", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_loader = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _loader
_SPEC.loader.exec_module(_loader)


def _still(path: Path, size=(2560, 1440), grid=False) -> None:
    image = Image.new("RGB", size, (0xE9, 0xE2, 0xD2))
    if grid:
        draw = ImageDraw.Draw(image)
        for index in range(1, 10):
            x = int(round(index * size[0] / 10))
            y = int(round(index * size[1] / 10))
            draw.line([(x, 0), (x, size[1])], fill=(0, 0, 0))
            draw.line([(0, y), (size[0], y)], fill=(0, 0, 0))
    image.save(path)


def test_derives_centers_and_accepts_a_clean_still(tmp_path: Path):
    path = tmp_path / "clean.png"
    _still(path)
    anchors = _loader.load_anchors(str(path), [{"col": "E", "row": 5, "span_cols": 2, "span_rows": 1, "target_zoom": 2.2}])
    assert len(anchors) == 1
    assert abs(anchors[0].x_px - (4.5 / 10) * 2560) < 1e-6
    assert abs(anchors[0].y_px - (4.5 / 10) * 1440) < 1e-6
    assert Path(path).stat().st_mtime


def test_rejects_low_res_missing_baked_grid_and_bad_coordinates(tmp_path: Path):
    small = tmp_path / "small.png"
    _still(small, (1280, 720))
    try:
        _loader.load_anchors(str(small), [{"col": "A", "row": 1, "span_cols": 1, "span_rows": 1}])
        assert False
    except _loader.AnchorBoundsError:
        pass
    missing = tmp_path / "gone.png"
    try:
        _loader.load_anchors(str(missing), [])
        assert False
    except _loader.Missing2KAssetError:
        pass
    gridded = tmp_path / "grid.png"
    _still(gridded, grid=True)
    try:
        _loader.load_anchors(str(gridded), [{"col": "A", "row": 1, "span_cols": 1, "span_rows": 1}])
        assert False
    except _loader.BakedGridError:
        pass
    clean = tmp_path / "clean.png"
    _still(clean)
    try:
        _loader.load_anchors(str(clean), [{"col": "A", "row": 1, "span_cols": 1, "span_rows": 1, "x_px": 2000, "y_px": 100}])
        assert False
    except _loader.AnchorBoundsError:
        pass
