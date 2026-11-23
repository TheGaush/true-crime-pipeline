import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "safe_zone_scanner.py"
_SPEC = importlib.util.spec_from_file_location("tc169_zone", _PATH)
assert _SPEC and _SPEC.loader
zone = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = zone
_SPEC.loader.exec_module(zone)


def test_bottom_text_is_caught_and_parchment_and_foia_are_not():
    clean = np.full((1080, 1920, 3), (233, 226, 210), dtype=np.uint8)
    assert zone.scan_frame(clean, "clean", 1.0) == []
    stamped = clean.copy()
    image = Image.fromarray(stamped)
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 1000, 700, 1060], fill=(27, 27, 29))
    hits = zone.scan_frame(np.asarray(image), "bleed", 2.0)
    assert any(hit.margin_side == "bottom" and hit.scene_id == "bleed" for hit in hits)
    foia = image.copy()
    assert zone.scan_frame(np.asarray(foia), "bodycam", 2.0, exempt_safe_zone_foia=True) == []
