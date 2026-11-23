"""Corner clamps, narrow caps, and tall-span zoom."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "crop_math.py"
_SPEC = importlib.util.spec_from_file_location("tc_task145_crop_math", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_crop = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _crop
_SPEC.loader.exec_module(_crop)


def test_corners_narrow_tall_and_wide():
    width, height = 2560, 1440
    center = _crop.crop_window(width, height, "E", 5, 2, 2)
    center.assert_inside(width, height)
    assert _crop.ZOOM_MIN <= center.zoom <= _crop.ZOOM_MAX
    narrow = _crop.crop_window(width, height, "E", 5, 1, 1)
    assert abs(narrow.zoom - 3.8) < 1e-6
    wide = _crop.crop_window(width, height, "E", 5, 6, 4)
    assert abs(wide.zoom - 1.6) < 1e-6
    tall = _crop.crop_window(width, height, "C", 4, 1, 4)
    assert abs(tall.zoom - 2.0) < 1e-6
    for col, row in (("A", 1), ("J", 1), ("A", 10), ("J", 10)):
        window = _crop.crop_window(width, height, col, row, 1, 1, target_zoom=3.2)
        window.assert_inside(width, height)
        assert window.clamped is True
        assert window.zoom == 3.2
