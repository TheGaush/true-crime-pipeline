"""Adversarial checks against bookends, safety, and the SFX synthesizer."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "src" / "python_motion"


def load(stem: str):
    spec = importlib.util.spec_from_file_location(f"tc140_{stem}", ROOT / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_crimson_props_do_not_survive_a_flow_bookend(tmp_path: Path):
    book = load("bookend_generator")
    pair = book.BookendGenerator().generate(
        book.BookendRequest(
            "scene_red",
            "FIRST_FRAME",
            4.0,
            str(tmp_path),
            keyframe_props=({"kind": "arrow", "color_hex": "#C92A2A"},),
        )
    )
    assert pair.safety_passed is True
    rgb = np.asarray(Image.open(pair.start_frame).convert("RGB"))
    red = rgb[..., 0].astype(np.int16)
    green = rgb[..., 1].astype(np.int16)
    blue = rgb[..., 2].astype(np.int16)
    assert int(np.count_nonzero((red > 160) & (red > green * 1.8) & (red > blue * 1.8))) == 0


def test_duration_edges_clamp_instead_of_crashing(tmp_path: Path):
    book = load("bookend_generator")
    short = book.BookendGenerator().generate(book.BookendRequest("s0", "FIRST_AND_LAST_FRAME", 0.0, str(tmp_path / "a")))
    long = book.BookendGenerator().generate(book.BookendRequest("s180", "FIRST_AND_LAST_FRAME", 180.0, str(tmp_path / "b")))
    assert short.duration_sec == 3.0
    assert long.duration_sec == 10.0


def test_parchment_passes_and_a_skin_field_does_not():
    safety = load("safety_validator")
    validator = safety.InputImageSafetyValidator()
    parchment = np.full((128, 128, 3), (233, 226, 210), dtype=np.uint8)
    assert validator.validate(parchment).passed is True
    skin = parchment.copy()
    skin[40:100, 40:100] = (180, 133, 109)
    verdict = validator.validate(skin)
    assert verdict.passed is False
    assert "SKIN_TONE_CLUSTER" in verdict.violations or "PHOTOREALISTIC_FACE" in verdict.violations


def test_five_hundred_cues_keep_hashes_and_stay_under_the_rss_ceiling():
    import resource

    sfx = load("sfx_synth")
    engine = sfx.SfxSynthesizer()
    first = engine.synthesize(sfx.SfxRequest("paper_slide", duration_ms=10, seed=0))
    for index in range(499):
        engine.synthesize(sfx.SfxRequest("paper_slide", duration_ms=10, seed=index % 8))
    again = engine.synthesize(sfx.SfxRequest("paper_slide", duration_ms=10, seed=0))
    assert again.sha256 == first.sha256
    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert rss_kb < 250 * 1024


def test_bad_duration_and_extreme_paths_raise_typed_errors():
    traj = load("trajectory_engine")
    try:
        traj.frame_count(0.0)
        assert False
    except traj.TrajectoryError:
        pass
    point = traj.catmull_rom([(0.0, 0.0), (10_000.0, -10_000.0)], 1.0)
    assert point == (10_000.0, -10_000.0)
    sfx = load("sfx_synth")
    cue = sfx.SfxSynthesizer().synthesize(sfx.SfxRequest("siren", duration_ms=0, seed=1))
    assert cue.cue_type == "paper_slide"
    assert cue.duration_ms == 10


def test_sfx_aliases_and_repeat_hashes_stay_stable(tmp_path: Path):
    sfx = load("sfx_synth")
    engine = sfx.SfxSynthesizer()
    first = engine.synthesize(sfx.SfxRequest("gavel", duration_ms=40, seed=2, cache_dir=str(tmp_path)))
    second = engine.synthesize(sfx.SfxRequest("stamp_thud", duration_ms=40, seed=2, cache_dir=str(tmp_path)))
    unknown = engine.synthesize(sfx.SfxRequest("not_a_cue", duration_ms=40, seed=2, cache_dir=str(tmp_path)))
    assert first.sha256 == second.sha256
    assert unknown.cue_type == "paper_slide"
    again = engine.synthesize(sfx.SfxRequest("typewriter_key", duration_ms=20, seed=9, cache_dir=str(tmp_path / "b")))
    repeat = engine.synthesize(sfx.SfxRequest("typewriter_key", duration_ms=20, seed=9, cache_dir=str(tmp_path / "b")))
    assert again.sha256 == repeat.sha256
