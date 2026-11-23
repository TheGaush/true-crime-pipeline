import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "thumbnail_auditor.py"
_SPEC = importlib.util.spec_from_file_location("tc172_thumb", _PATH)
assert _SPEC and _SPEC.loader
thumb = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = thumb
_SPEC.loader.exec_module(thumb)


def test_policy_and_rotation():
    history = ["doorway_silhouette"]
    choice = thumb.next_archetype(history)
    image = thumb.render_candidate(choice, ["Case", "file"])
    verdict = thumb.audit(image, ["Case", "file"], choice, history)
    assert verdict.approved is True
    assert verdict.archetype != history[-1]
    clutter = thumb.audit(image, ["one", "two", "three", "four", "five"], choice, history)
    assert "WORD_COUNT" in clutter.reasons
    repeat = thumb.audit(image, ["Case"], choice, [choice])
    assert "REPEATED_ARCHETYPE" in repeat.reasons
    gory = np.asarray(image).copy()
    gory[200:280, 200:320] = (201, 42, 42)
    gore = thumb.audit(Image.fromarray(gory), ["Case"], choice, history)
    assert "GORE" in gore.reasons
    cold = thumb.next_archetype([])
    assert thumb.audit(thumb.render_candidate(cold, ["Open"]), ["Open"], cold, []).approved
