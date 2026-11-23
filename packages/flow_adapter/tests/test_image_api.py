import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_PATH = Path(__file__).resolve().parents[1] / "src" / "flow_adapter" / "image_api.py"
_SPEC = importlib.util.spec_from_file_location("tc154_image", _PATH)
assert _SPEC and _SPEC.loader
api = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = api
_SPEC.loader.exec_module(api)


class Transport:
    def generate(self, prompt, case_bible, size):
        assert size == "2K"
        assert "charcoal" in prompt or prompt
        return Image.new("RGB", (2048, 1152), (233, 226, 210))

    def edit(self, base, instruction, seed):
        edited = base.copy()
        draw = ImageDraw.Draw(edited)
        draw.rectangle([900, 400, 1100, 700], fill=(58, 79, 102))
        return edited


def test_resolution_gate_and_room_lock():
    made = api.generate_clean_2k_still("empty hallway charcoal", {"palette": "parchment"}, Transport())
    assert made.width >= 2048 and made.height >= 1152
    try:
        api._gate(Image.new("RGB", (1024, 576), (233, 226, 210)))
        assert False
    except api.ImageResolutionError:
        pass
    base = Image.new("RGB", (2048, 1152), (233, 226, 210))
    edited = api.edit_still_multiturn(base, "isolate the folder", 1, Transport())
    assert edited.ssim is not None and edited.ssim >= 0.85
    assert edited.warning is None
    bloody = Image.new("RGB", (2048, 1152), (233, 226, 210))
    ImageDraw.Draw(bloody).rectangle([100, 100, 400, 400], fill=(201, 42, 42))
    try:
        api._gate(bloody)
        assert False
    except api.ImageSafetyError:
        pass
