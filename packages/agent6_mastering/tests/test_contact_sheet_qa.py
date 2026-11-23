import importlib.util
import sys
from pathlib import Path

from PIL import Image

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "contact_sheet_qa.py"
_SPEC = importlib.util.spec_from_file_location("tc170_sheet", _PATH)
assert _SPEC and _SPEC.loader
qa = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = qa
_SPEC.loader.exec_module(qa)


def test_five_frames_make_two_sheets_and_keep_scene_ids():
    frames = [(f"scene_{index}", Image.new("RGB", (320, 180), (233, 226, 210))) for index in range(5)]
    sheets = qa.build_sheets(frames)
    assert len(sheets) == 2
    seen = []

    def judge(_sheet, ids):
        seen.append(list(ids))
        if "scene_3" in ids:
            return [{"scene_id": "scene_3", "fix_type": "text_bounds"}, {"scene_id": "EMPTY_SLOT", "fix_type": "ignore"}]
        return []

    defects = qa.review(frames, judge)
    assert seen == [["scene_0", "scene_1", "scene_2", "scene_3"], ["scene_4"]]
    assert [(item.scene_id, item.fix_type) for item in defects] == [("scene_3", "text_bounds")]
