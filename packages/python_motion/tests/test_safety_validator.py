"""Synthetic gauntlet for the Law 12 input-image safety validator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "python_motion" / "safety_validator.py"
)
_SPEC = importlib.util.spec_from_file_location("tc_task134_safety_validator", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_safety = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _safety
_SPEC.loader.exec_module(_safety)

PARCHMENT = (233, 226, 210)  # #E9E2D2
AMBER = (184, 134, 11)  # #B8860B
BLOOD = (201, 42, 42)  # #C92A2A
INK = (27, 27, 29)  # #1B1B1D
SLATE = (58, 79, 102)  # #3A4F66
SKIN = (180, 133, 109)  # OpenCV HSV H=10 S=100 V=180
WARM = (210, 140, 10)  # R - max(G, B) > 55, but G >= 100
MARGIN = 16


def frame(height: int, width: int, color: tuple[int, int, int] = PARCHMENT) -> np.ndarray:
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:] = color
    return image


def validator():
    return _safety.InputImageSafetyValidator()


def test_verdict_fields_and_passed_matches_violations() -> None:
    verdict = validator().validate(frame(80, 80))
    assert set(verdict.__dataclass_fields__) == {
        "passed",
        "violations",
        "red_pixel_pct",
        "skin_pixel_pct",
    }
    assert verdict.passed is True
    assert verdict.violations == []
    assert verdict.red_pixel_pct == 0.0
    assert verdict.skin_pixel_pct == 0.0
    with pytest.raises(ValueError):
        _safety.ImageSafetyVerdict(True, ["CRIMSON_BLOOD_CLUSTER"], 0.0, 0.0)


def test_parchment_background_passes() -> None:
    verdict = validator().validate(frame(96, 120, PARCHMENT))
    assert verdict.passed is True
    assert verdict.violations == []
    assert verdict.red_pixel_pct == 0.0
    assert verdict.skin_pixel_pct == 0.0


def test_amber_lamp_passes() -> None:
    image = frame(96, 120)
    image[24:80, 20:70] = AMBER
    verdict = validator().validate(image)
    assert verdict.passed is True
    assert verdict.violations == []
    assert verdict.red_pixel_pct == 0.0
    assert verdict.skin_pixel_pct == 0.0


def test_warm_highlight_with_green_at_least_100_is_not_crimson() -> None:
    image = frame(96, 120)
    image[20:70, 20:80] = WARM
    verdict = validator().validate(image)
    assert verdict.passed is True
    assert _safety.CRIMSON_BLOOD_CLUSTER not in verdict.violations
    assert verdict.red_pixel_pct == 0.0


def test_monochrome_stick_scene_passes() -> None:
    image = frame(180, 220)
    image[40:70, 96:126] = INK
    image[70:120, 106:118] = INK
    image[78:88, 60:170] = INK
    image[120:160, 96:106] = INK
    image[120:160, 118:128] = INK
    image[36:78, 24:58] = AMBER
    image[132:152, 150:196] = SLATE
    verdict = validator().validate(image)
    assert verdict.passed is True
    assert verdict.violations == []


def test_blood_cluster_of_35_fails_and_34_passes() -> None:
    fail = frame(80, 100)
    fail[24:29, 24:31] = BLOOD  # 5 * 7 = 35
    failed = validator().validate(fail)
    assert failed.passed is False
    assert failed.violations == [_safety.CRIMSON_BLOOD_CLUSTER]
    interior = (80 - 2 * MARGIN) * (100 - 2 * MARGIN)
    assert failed.red_pixel_pct == pytest.approx(100.0 * 35 / interior)
    assert failed.skin_pixel_pct == 0.0

    ok = frame(80, 100)
    ok[24:28, 24:31] = BLOOD  # 4 * 7 = 28
    ok[28, 24:30] = BLOOD  # +6 = 34
    passed = validator().validate(ok)
    assert passed.passed is True
    assert passed.violations == []
    assert passed.red_pixel_pct == pytest.approx(100.0 * 34 / interior)


def test_diagonal_cluster_is_one_component() -> None:
    image = frame(90, 90)
    for offset in range(35):
        image[20 + offset, 20 + offset] = BLOOD
    verdict = validator().validate(image)
    assert verdict.passed is False
    assert verdict.violations == [_safety.CRIMSON_BLOOD_CLUSTER]


def test_separate_red_components_under_35_pass() -> None:
    image = frame(100, 120)
    image[24, 24:54] = BLOOD  # 30
    image[40, 24:54] = BLOOD  # 30, not 8-connected to the first
    verdict = validator().validate(image)
    assert verdict.passed is True
    interior = (100 - 2 * MARGIN) * (120 - 2 * MARGIN)
    assert verdict.red_pixel_pct == pytest.approx(100.0 * 60 / interior)


def test_crimson_inside_the_outer_margin_is_ignored() -> None:
    hidden = frame(90, 120)
    hidden[2:7, 30:42] = BLOOD  # 5 * 12 = 60, entirely in the top 16px
    assert validator().validate(hidden).passed is True
    assert validator().validate(hidden).red_pixel_pct == 0.0

    straddling = frame(90, 90)
    straddling[10:17, 24:29] = BLOOD  # 7 * 5 = 35, only y=16 is inside
    assert validator().validate(straddling).passed is True

    inside = frame(90, 90)
    inside[16:23, 24:29] = BLOOD  # same 35 pixels, fully inside
    verdict = validator().validate(inside)
    assert verdict.violations == [_safety.CRIMSON_BLOOD_CLUSTER]


def test_featureless_skin_over_and_under_three_percent() -> None:
    image = frame(132, 132)
    image[16:36, 16:31] = SKIN  # 20 * 15 = 300 of 100 * 100 interior = 3%
    at_limit = validator().validate(image)
    assert at_limit.passed is True
    assert at_limit.skin_pixel_pct == pytest.approx(3.0)
    assert _safety.SKIN_TONE_CLUSTER not in at_limit.violations

    image[36, 16] = SKIN  # 301st pixel, still one component
    over = validator().validate(image)
    assert over.passed is False
    assert over.violations == [_safety.SKIN_TONE_CLUSTER]
    assert over.skin_pixel_pct == pytest.approx(3.01)

    small = frame(132, 132)
    small[16:26, 16:26] = SKIN  # 100 / 10000 = 1%
    under = validator().validate(small)
    assert under.passed is True
    assert under.skin_pixel_pct == pytest.approx(1.0)


def test_scattered_skin_specks_do_not_sum_into_a_cluster() -> None:
    image = frame(132, 132)
    # 20 islands of 20 pixels = 4% of the interior, each island 0.2%.
    for row in range(4):
        for col in range(5):
            y = 16 + row * 8
            x = 16 + col * 10
            image[y : y + 4, x : x + 5] = SKIN
    verdict = validator().validate(image)
    assert verdict.passed is True
    assert verdict.skin_pixel_pct == pytest.approx(0.2)
    assert verdict.violations == []


def test_skin_toned_face_under_three_percent_fails() -> None:
    image = frame(200, 200)
    image[60:88, 80:106] = SKIN
    image[66:71, 84:89] = (15, 12, 10)
    image[66:71, 96:101] = (15, 12, 10)
    image[78:83, 88:98] = (25, 18, 16)
    verdict = validator().validate(image)
    interior = (200 - 2 * MARGIN) ** 2
    assert verdict.skin_pixel_pct < 3.0
    assert verdict.skin_pixel_pct == pytest.approx(100.0 * int((image[16:-16, 16:-16] == SKIN).all(axis=2).sum()) / interior)
    assert verdict.passed is False
    assert verdict.violations == [_safety.PHOTOREALISTIC_FACE]


def test_rendered_text_band_fails_and_a_single_letter_does_not() -> None:
    caption = frame(120, 280)
    _draw(caption, (40, 48), "CASE FILE 14")
    failed = validator().validate(caption)
    assert failed.passed is False
    assert failed.violations == [_safety.FORBIDDEN_TEXT_BAND]
    assert failed.red_pixel_pct == 0.0
    assert failed.skin_pixel_pct == 0.0

    letter = frame(120, 280)
    _draw(letter, (40, 48), "A")
    assert validator().validate(letter).passed is True


def test_text_inside_the_outer_margin_is_ignored() -> None:
    image = frame(120, 280)
    _draw(image, (4, 1), "CASE FILE 14")
    assert validator().validate(image).passed is True


def test_light_text_on_charcoal_fails() -> None:
    image = frame(120, 280, INK)
    _draw(image, (36, 40), "CASE FILE 14", fill=PARCHMENT)
    verdict = validator().validate(image)
    assert verdict.violations == [_safety.FORBIDDEN_TEXT_BAND]


def test_failure_does_not_modify_crop_or_blur_the_image() -> None:
    image = frame(96, 96)
    image[20:27, 20:25] = BLOOD
    before = image.copy()
    verdict = validator().validate(image)
    assert verdict.passed is False
    assert np.array_equal(image, before)
    assert not hasattr(verdict, "image")
    assert not hasattr(verdict, "cropped")


def test_rgba_alpha_is_ignored_and_pillow_image_is_accepted() -> None:
    rgb = frame(80, 90)
    rgb[24:31, 24:29] = BLOOD
    rgba = np.dstack([rgb, np.full(rgb.shape[:2], 10, dtype=np.uint8)])
    array_verdict = validator().validate(rgba)
    pillow_verdict = validator().validate(Image.fromarray(rgb, mode="RGB"))
    assert array_verdict.violations == [_safety.CRIMSON_BLOOD_CLUSTER]
    assert pillow_verdict.violations == array_verdict.violations
    assert pillow_verdict.red_pixel_pct == pytest.approx(array_verdict.red_pixel_pct)


def test_png_path_roundtrip(tmp_path: Path) -> None:
    image = frame(80, 90)
    image[24:31, 24:29] = BLOOD
    path = tmp_path / "start.png"
    Image.fromarray(image, mode="RGB").save(path)
    verdict = validator().validate(path)
    assert verdict.violations == [_safety.CRIMSON_BLOOD_CLUSTER]
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_smaller_than_the_margin_passes() -> None:
    verdict = validator().validate(frame(32, 48, BLOOD))
    assert verdict.passed is True
    assert verdict.red_pixel_pct == 0.0
    assert verdict.skin_pixel_pct == 0.0


def test_combined_failures_keep_a_stable_code_order() -> None:
    image = frame(220, 240)
    image[20:27, 20:25] = BLOOD
    image[20:60, 90:140] = SKIN  # 40 * 50 = 2000 > 3% of the 188 * 208 interior
    image[80:108, 24:50] = SKIN
    image[86:91, 28:33] = (12, 10, 9)
    image[86:91, 40:45] = (12, 10, 9)
    image[98:103, 32:44] = (22, 16, 14)
    _draw(image, (24, 160), "CASE FILE 14")
    verdict = validator().validate(image)
    assert verdict.passed is False
    assert verdict.violations == [
        _safety.CRIMSON_BLOOD_CLUSTER,
        _safety.PHOTOREALISTIC_FACE,
        _safety.SKIN_TONE_CLUSTER,
        _safety.FORBIDDEN_TEXT_BAND,
    ]


def _draw(
    image: np.ndarray,
    xy: tuple[int, int],
    text: str,
    fill: tuple[int, int, int] = INK,
) -> None:
    canvas = Image.fromarray(image, mode="RGB")
    ImageDraw.Draw(canvas).text(xy, text, fill=fill, font=ImageFont.load_default())
    image[...] = np.asarray(canvas, dtype=np.uint8)
