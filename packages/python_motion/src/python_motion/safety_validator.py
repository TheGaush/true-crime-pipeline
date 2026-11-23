"""Law 12 pre-flight check for Start/End keyframe images.

``InputImageSafetyValidator`` inspects a raster before it is uploaded.
It reports violation codes and never crops, blurs, or rewrites a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

MARGIN_PX = 16
MIN_RED_CLUSTER = 35
MAX_SKIN_CONTIGUOUS_PCT = 3.0

CRIMSON_BLOOD_CLUSTER = "CRIMSON_BLOOD_CLUSTER"
PHOTOREALISTIC_FACE = "PHOTOREALISTIC_FACE"
SKIN_TONE_CLUSTER = "SKIN_TONE_CLUSTER"
FORBIDDEN_TEXT_BAND = "FORBIDDEN_TEXT_BAND"

_GLYPH_MIN_RUNS = 6
_GLYPH_MAX_MEDIAN_RUN = 6
_GLYPH_MIN_SPAN = 20
_GLYPH_MIN_ROWS = 5
_GLYPH_MIN_VARIATION = 0.01
_INK_DELTA = 40


@dataclass(frozen=True)
class ImageSafetyVerdict:
    """Result of one keyframe inspection.

    ``passed`` is true only when ``violations`` is empty.
    ``red_pixel_pct`` is the share of the inspected interior that matches
    the crimson predicate, whether or not those pixels form one cluster.
    ``skin_pixel_pct`` is the share taken by the largest 8-connected skin
    cluster. Skin rejection uses that contiguous ratio, not a scattered total.
    Percentages are computed after the outer 16px margin is ignored.
    """

    passed: bool
    violations: list[str]
    red_pixel_pct: float
    skin_pixel_pct: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "violations", list(self.violations))
        if self.passed != (len(self.violations) == 0):
            raise ValueError("passed must be true only when violations is empty")


class InputImageSafetyValidator:
    """Reject crimson clusters, photorealistic faces, skin fields, and text bands."""

    def validate(self, image: object) -> ImageSafetyVerdict:
        """Inspect ``image`` and return a verdict.

        ``image`` may be a uint8 ``HxWx3`` or ``HxWx4`` array (RGB, alpha
        ignored), a Pillow image, or a filesystem path. The input buffer is
        not modified. A failed image is not cropped or blurred.
        """
        rgb = _as_rgb(image)
        interior = _interior(rgb)
        height, width = interior.shape[:2]
        if height == 0 or width == 0:
            return ImageSafetyVerdict(True, [], 0.0, 0.0)

        pixels = height * width
        red = _crimson_mask(interior)
        skin = _skin_mask(interior)
        labels, count = _label(skin)
        skin_largest = _largest_from_labels(labels, count)
        red_largest = _largest_component(red)
        violations: list[str] = []
        if red_largest >= MIN_RED_CLUSTER:
            violations.append(CRIMSON_BLOOD_CLUSTER)
        if _haar_face(interior) or _face_structure(interior, labels, count):
            violations.append(PHOTOREALISTIC_FACE)
        if (100.0 * skin_largest / pixels) > MAX_SKIN_CONTIGUOUS_PCT:
            violations.append(SKIN_TONE_CLUSTER)
        if _text_band(interior):
            violations.append(FORBIDDEN_TEXT_BAND)
        return ImageSafetyVerdict(
            not violations,
            violations,
            100.0 * float(red.sum()) / pixels,
            100.0 * float(skin_largest) / pixels,
        )


def _as_rgb(image: object) -> np.ndarray:
    if isinstance(image, np.ndarray):
        array = np.array(image, copy=True)
        if array.dtype != np.uint8:
            raise TypeError("expected a uint8 RGB image")
        if array.ndim != 3 or array.shape[2] not in (3, 4):
            raise ValueError("expected an HxWx3 or HxWx4 uint8 image")
        return np.ascontiguousarray(array[..., :3])
    if isinstance(image, (str, Path)):
        return _rgb_from_path(Path(image))
    convert = getattr(image, "convert", None)
    if callable(convert):
        rgb = convert("RGB")
        array = np.array(rgb, dtype=np.uint8, copy=True)
        if array.ndim != 3 or array.shape[2] != 3:
            raise ValueError("expected an RGB image")
        return np.ascontiguousarray(array)
    raise TypeError("expected an ndarray, image path, or Pillow image")


def _rgb_from_path(path: Path) -> np.ndarray:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError("reading an image path requires Pillow") from exc
    with Image.open(path) as handle:
        rgb = handle.convert("RGB")
        return np.ascontiguousarray(np.array(rgb, dtype=np.uint8, copy=True))


def _interior(rgb: np.ndarray) -> np.ndarray:
    margin = MARGIN_PX
    height, width = rgb.shape[:2]
    if height <= margin * 2 or width <= margin * 2:
        return rgb[0:0, 0:0]
    return rgb[margin : height - margin, margin : width - margin]


def _crimson_mask(rgb: np.ndarray) -> np.ndarray:
    """Blood red, with the amber lamp ``#B8860B`` left out.

    A pixel is crimson when ``R > 140``, ``R - max(G, B) > 55``,
    ``R - G > 55``, and ``G < 100``. Amber is ``R=184, G=134, B=11``
    (``R - G == 50`` and ``G >= 100``), so a warm lamp stays eligible.
    """
    red = rgb[..., 0].astype(np.int16)
    green = rgb[..., 1].astype(np.int16)
    blue = rgb[..., 2].astype(np.int16)
    return (
        (red > 140)
        & ((red - np.maximum(green, blue)) > 55)
        & ((red - green) > 55)
        & (green < 100)
    )


def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    """Saturated mid peach/tan. Parchment ``#E9E2D2`` has ``S < 35`` and is excluded."""
    hue, sat, val = _opencv_hsv(rgb)
    return (
        (hue >= 2)
        & (hue <= 22)
        & (sat >= 45)
        & (sat <= 175)
        & (val >= 80)
        & (val <= 230)
        & (sat >= 35)
    )


def _opencv_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """8-bit HSV in the same scale as ``COLOR_RGB2HSV`` (H 0-179, S/V 0-255)."""
    red = rgb[..., 0].astype(np.int32)
    green = rgb[..., 1].astype(np.int32)
    blue = rgb[..., 2].astype(np.int32)
    vmax = np.maximum(np.maximum(red, green), blue)
    vmin = np.minimum(np.minimum(red, green), blue)
    diff = vmax - vmin
    sat = np.zeros(red.shape, dtype=np.int32)
    nonzero = vmax > 0
    sat[nonzero] = (diff[nonzero] * 255) // vmax[nonzero]
    hue = np.zeros(red.shape, dtype=np.int32)
    active = diff > 0
    safe = np.maximum(diff, 1)
    red_peak = active & (vmax == red)
    green_peak = active & ~red_peak & (vmax == green)
    blue_peak = active & ~red_peak & ~green_peak
    red_hue = _trunc_div((green - blue) * 60, safe)
    red_hue = np.where(red_hue < 0, red_hue + 360, red_hue)
    hue[red_peak] = red_hue[red_peak] // 2
    hue[green_peak] = (_trunc_div((blue - red) * 60, safe) + 120)[green_peak] // 2
    hue[blue_peak] = (_trunc_div((red - green) * 60, safe) + 240)[blue_peak] // 2
    return hue, sat, vmax


def _trunc_div(numer: np.ndarray, denom: np.ndarray) -> np.ndarray:
    """Toward-zero integer division, matching the C++ HSV conversion."""
    numer_i = numer.astype(np.int32, copy=False)
    denom_i = denom.astype(np.int32, copy=False)
    sign = np.sign(numer_i).astype(np.int32)
    return sign * (np.abs(numer_i) // denom_i)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (
        rgb[..., 0].astype(np.int16) * 54
        + rgb[..., 1].astype(np.int16) * 183
        + rgb[..., 2].astype(np.int16) * 19
    ) >> 8


def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """8-connected component labels. Background is 0."""
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    count = 0
    ys, xs = np.nonzero(mask)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if labels[y0, x0] != 0:
            continue
        count += 1
        stack = [(int(y0), int(x0))]
        labels[y0, x0] = count
        while stack:
            y, x = stack.pop()
            y_lo = y - 1 if y else 0
            y_hi = y + 2 if y + 1 < height else height
            x_lo = x - 1 if x else 0
            x_hi = x + 2 if x + 1 < width else width
            window = mask[y_lo:y_hi, x_lo:x_hi]
            labeled = labels[y_lo:y_hi, x_lo:x_hi]
            fresh = window & (labeled == 0)
            if not fresh.any():
                continue
            local_y, local_x = np.nonzero(fresh)
            labeled[fresh] = count
            for ny, nx in zip(local_y.tolist(), local_x.tolist()):
                stack.append((y_lo + ny, x_lo + nx))
    return labels, count


def _largest_from_labels(labels: np.ndarray, count: int) -> int:
    if count == 0:
        return 0
    sizes = np.bincount(labels.ravel())
    return int(sizes[1:].max())


def _largest_component(mask: np.ndarray) -> int:
    if mask.size == 0 or not bool(mask.any()):
        return 0
    labels, count = _label(mask)
    return _largest_from_labels(labels, count)


def _haar_face(rgb: np.ndarray) -> bool:
    """Frontal or profile Haar hit, when OpenCV and its cascades are installed.

    Cascade weights are never downloaded. A missing install is not a pass by
    itself: ``_face_structure`` still rejects a skin-toned face with eyes and
    a mouth.
    """
    try:
        import cv2
    except ImportError:
        return False
    cascades = getattr(getattr(cv2, "data", None), "haarcascades", None)
    if not cascades:
        return False
    gray = np.ascontiguousarray(_luma(rgb).astype(np.uint8))
    if gray.shape[0] < 30 or gray.shape[1] < 30:
        return False
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        xml = Path(cascades) / name
        if not xml.is_file():
            continue
        classifier = cv2.CascadeClassifier(str(xml))
        if classifier.empty():
            continue
        found = classifier.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=6,
            minSize=(30, 30),
        )
        if len(found) > 0:
            return True
    return False


def _face_structure(rgb: np.ndarray, labels: np.ndarray, count: int) -> bool:
    """Skin region with two upper dark features and a lower dark feature."""
    if count == 0:
        return False
    luma = _luma(rgb)
    for index in range(1, count + 1):
        ys, xs = np.nonzero(labels == index)
        if ys.size < 160:
            continue
        y0 = int(ys.min())
        y1 = int(ys.max())
        x0 = int(xs.min())
        x1 = int(xs.max())
        box_h = y1 - y0 + 1
        box_w = x1 - x0 + 1
        if box_h < 22 or box_w < 18:
            continue
        ratio = box_h / box_w
        if ratio < 0.75 or ratio > 2.4:
            continue
        if ys.size / (box_h * box_w) < 0.5:
            continue
        roi_luma = luma[y0 : y1 + 1, x0 : x1 + 1]
        roi_skin = labels[y0 : y1 + 1, x0 : x1 + 1] == index
        dark = (roi_luma < 55) & ~roi_skin
        if dark.shape[0] < 3 or dark.shape[1] < 3:
            continue
        dark = dark.copy()
        dark[0, :] = False
        dark[-1, :] = False
        dark[:, 0] = False
        dark[:, -1] = False
        upper_h = max(1, int(round(box_h * 0.62)))
        upper_blobs = _blob_stats(dark[:upper_h])
        lower = dark[box_h // 2 :]
        if not _separated_eyes(upper_blobs, box_w, box_h):
            continue
        if not any(area >= 4 for _cy, _cx, area in _blob_stats(lower)):
            continue
        return True
    return False


def _blob_stats(mask: np.ndarray) -> list[tuple[float, float, int]]:
    labels, count = _label(mask)
    blobs: list[tuple[float, float, int]] = []
    for index in range(1, count + 1):
        ys, xs = np.nonzero(labels == index)
        area = int(ys.size)
        if area < 4:
            continue
        blobs.append((float(ys.mean()), float(xs.mean()), area))
    return blobs


def _separated_eyes(
    blobs: list[tuple[float, float, int]],
    box_w: int,
    box_h: int,
) -> bool:
    for i, (y1, x1, _area1) in enumerate(blobs):
        for y2, x2, _area2 in blobs[i + 1 :]:
            if abs(x1 - x2) >= 0.15 * box_w and abs(y1 - y2) <= 0.35 * box_h:
                return True
    return False


def _text_band(rgb: np.ndarray) -> bool:
    """High-frequency horizontal glyph band.

    A caption produces several rows of many short ink runs whose shape changes
    from row to row. A solid limb, lamp, or railing is one long run, or the
    same run repeated without row-to-row change, and stays eligible.
    """
    height, width = rgb.shape[:2]
    if height < _GLYPH_MIN_ROWS or width < _GLYPH_MIN_SPAN:
        return False
    luma = _luma(rgb)
    median = np.median(luma, axis=1)
    ink = np.abs(luma.astype(np.float32) - median[:, None]) >= _INK_DELTA
    glyph = np.fromiter((_glyph_row(ink[y]) for y in range(height)), dtype=bool, count=height)
    y = 0
    while y < height:
        if not glyph[y]:
            y += 1
            continue
        start = y
        while y < height and glyph[y]:
            y += 1
        if y - start >= _GLYPH_MIN_ROWS and _band_varies(ink[start:y]):
            return True
    return False


def _glyph_row(row: np.ndarray) -> bool:
    if not bool(row.any()):
        return False
    padded = np.concatenate((np.array([False]), row, np.array([False])))
    starts = np.flatnonzero(~padded[:-1] & padded[1:])
    ends = np.flatnonzero(padded[:-1] & ~padded[1:])
    lengths = ends - starts
    if lengths.size < _GLYPH_MIN_RUNS:
        return False
    if float(np.median(lengths)) > _GLYPH_MAX_MEDIAN_RUN:
        return False
    idx = np.flatnonzero(row)
    span = int(idx[-1] - idx[0] + 1)
    if span < _GLYPH_MIN_SPAN:
        return False
    return int(row.sum()) < row.size * 0.45


def _band_varies(rows: np.ndarray) -> bool:
    if rows.shape[0] < 2:
        return False
    changes = [(rows[i] != rows[i + 1]).mean() for i in range(rows.shape[0] - 1)]
    return float(np.mean(changes)) > _GLYPH_MIN_VARIATION
