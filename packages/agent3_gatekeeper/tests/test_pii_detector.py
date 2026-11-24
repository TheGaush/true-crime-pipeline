"""Visual + spoken PII detector tests (injected vision, no OpenCV/YOLO/network)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent3_gatekeeper.pii_detector import (
    VISUAL_BYSTANDER_FACE,
    VISUAL_HOUSE_NUMBER,
    VISUAL_LICENSE_PLATE,
    SPOKEN_DOB,
    SPOKEN_JUVENILE,
    SPOKEN_PERSON,
    SPOKEN_PHONE,
    SPOKEN_STREET_ADDRESS,
    BoundingBox,
    CaseRecord,
    FrameVisualDetection,
    WordTimestamp,
    scan_pii,
    scan_spoken_pii,
    smooth_visual_pii_tracks,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "pii_detector.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "cv2"}


def test_module_has_no_network_or_opencv_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_visual_iou_smoothing_merges_overlapping_face_tracks() -> None:
    box_a = BoundingBox(x=100, y=80, w=40, h=50)
    box_b = BoundingBox(x=105, y=82, w=38, h=48)
    box_c = BoundingBox(x=400, y=200, w=60, h=20)
    detections = [
        FrameVisualDetection(0, 0, VISUAL_BYSTANDER_FACE, box_a),
        FrameVisualDetection(1, 33, VISUAL_BYSTANDER_FACE, box_b),
        FrameVisualDetection(2, 66, VISUAL_LICENSE_PLATE, box_c),
        FrameVisualDetection(3, 66, VISUAL_LICENSE_PLATE, box_c),
    ]
    result = smooth_visual_pii_tracks(detections, duration_ms=3_000)
    kinds = {track.kind for track in result.tracks}
    assert kinds == {VISUAL_BYSTANDER_FACE, VISUAL_LICENSE_PLATE}
    face = next(t for t in result.tracks if t.kind == VISUAL_BYSTANDER_FACE)
    plate = next(t for t in result.tracks if t.kind == VISUAL_LICENSE_PLATE)
    assert face.start_ms == 0
    assert face.end_ms == 33
    assert plate.start_ms == 66
    assert plate.end_ms == 66
    assert face.bbox.iou(box_a) >= 0.5


def test_house_number_track_kept_separate_from_plate() -> None:
    plate = BoundingBox(x=10, y=10, w=80, h=30)
    house = BoundingBox(x=12, y=11, w=22, h=18)
    detections = [
        FrameVisualDetection(0, 100, VISUAL_LICENSE_PLATE, plate),
        FrameVisualDetection(1, 133, VISUAL_LICENSE_PLATE, plate),
        FrameVisualDetection(0, 100, VISUAL_HOUSE_NUMBER, house),
        FrameVisualDetection(1, 133, VISUAL_HOUSE_NUMBER, house),
    ]
    result = smooth_visual_pii_tracks(detections, duration_ms=5_000)
    assert len(result.tracks) == 2
    assert {t.kind for t in result.tracks} == {
        VISUAL_LICENSE_PLATE,
        VISUAL_HOUSE_NUMBER,
    }


def test_spoken_phone_555_0194_digit_by_digit_span() -> None:
    words = [
        WordTimestamp("five", 1_000, 1_200),
        WordTimestamp("five", 1_300, 1_500),
        WordTimestamp("five", 1_600, 1_800),
        WordTimestamp("dash", 1_900, 2_100),
        WordTimestamp("zero", 2_200, 2_400),
        WordTimestamp("one", 2_500, 2_700),
        WordTimestamp("nine", 2_800, 3_000),
        WordTimestamp("four", 3_100, 3_300),
    ]
    case = CaseRecord(defendant_name="Marcus Reed")
    result = scan_spoken_pii(words, duration_ms=4_000, case=case)
    phones = [hit for hit in result.intervals if hit.kind == SPOKEN_PHONE]
    assert len(phones) == 1
    assert phones[0].start_ms == 1_000
    assert phones[0].end_ms == 3_300


def test_spoken_address_412_oak_street_across_words() -> None:
    words = [
        WordTimestamp("four", 4_000, 4_150),
        WordTimestamp("one", 4_200, 4_350),
        WordTimestamp("two", 4_400, 4_550),
        WordTimestamp("Oak", 4_600, 4_800),
        WordTimestamp("Street", 4_850, 5_200),
    ]
    case = CaseRecord(defendant_name="Marcus Reed")
    result = scan_spoken_pii(words, duration_ms=6_000, case=case)
    addresses = [hit for hit in result.intervals if hit.kind == SPOKEN_STREET_ADDRESS]
    assert len(addresses) == 1
    assert addresses[0].start_ms == 4_000
    assert addresses[0].end_ms == 5_200
    assert "four one two" in addresses[0].text
    assert "Oak" in addresses[0].text


def test_spoken_dob_month_day_year_span() -> None:
    words = [
        WordTimestamp("date", 6_000, 6_150),
        WordTimestamp("of", 6_160, 6_250),
        WordTimestamp("birth", 6_260, 6_400),
        WordTimestamp("March", 6_500, 6_750),
        WordTimestamp("12", 6_800, 6_950),
        WordTimestamp("2008", 7_000, 7_300),
    ]
    case = CaseRecord(defendant_name="Marcus Reed")
    result = scan_spoken_pii(words, duration_ms=8_000, case=case)
    dobs = [hit for hit in result.intervals if hit.kind == SPOKEN_DOB]
    assert len(dobs) == 1
    assert dobs[0].start_ms == 6_500
    assert dobs[0].end_ms == 7_300


def test_defendant_name_not_flagged_bystander_name_is() -> None:
    words = [
        WordTimestamp("Marcus", 800, 1_000),
        WordTimestamp("Reed", 1_050, 1_250),
        WordTimestamp("Maria", 2_000, 2_200),
        WordTimestamp("Chen", 2_250, 2_500),
    ]
    case = CaseRecord(defendant_name="Marcus Reed")
    result = scan_spoken_pii(words, duration_ms=3_000, case=case)
    people = [hit for hit in result.intervals if hit.kind in {SPOKEN_PERSON, SPOKEN_JUVENILE}]
    assert len(people) == 1
    assert people[0].start_ms == 2_000
    assert people[0].end_ms == 2_500
    assert people[0].kind == SPOKEN_PERSON


def test_juvenile_name_is_spoken_pii() -> None:
    words = [
        WordTimestamp("Tyler", 1_000, 1_200),
        WordTimestamp("Brooks", 1_250, 1_550),
    ]
    case = CaseRecord(
        defendant_name="Marcus Reed",
        juvenile_names=frozenset({"tyler brooks"}),
    )
    result = scan_spoken_pii(words, duration_ms=2_000, case=case)
    assert len(result.intervals) == 1
    assert result.intervals[0].kind == SPOKEN_JUVENILE
    assert result.intervals[0].start_ms == 1_000
    assert result.intervals[0].end_ms == 1_550


def test_scan_pii_combines_visual_and_spoken() -> None:
    words = [
        WordTimestamp("five", 1_000, 1_200),
        WordTimestamp("five", 1_300, 1_500),
        WordTimestamp("five", 1_600, 1_800),
        WordTimestamp("zero", 2_200, 2_400),
        WordTimestamp("one", 2_500, 2_700),
        WordTimestamp("nine", 2_800, 3_000),
        WordTimestamp("four", 3_100, 3_300),
    ]
    visual = [
        FrameVisualDetection(
            0,
            500,
            VISUAL_BYSTANDER_FACE,
            BoundingBox(x=20, y=30, w=50, h=60),
        ),
        FrameVisualDetection(
            1,
            533,
            VISUAL_BYSTANDER_FACE,
            BoundingBox(x=22, y=31, w=48, h=58),
        ),
    ]
    result = scan_pii(
        duration_ms=4_000,
        visual_detections=visual,
        word_timestamps=words,
        case=CaseRecord(defendant_name="Marcus Reed"),
    )
    assert len(result.visual_tracks) == 1
    assert len(result.spoken_intervals) >= 1
    assert result.spoken_intervals[0].kind == SPOKEN_PHONE


def test_literal_phone_token_in_one_word() -> None:
    words = [WordTimestamp("555-0194", 900, 1_100)]
    result = scan_spoken_pii(words, 2_000, CaseRecord(defendant_name="Anyone"))
    assert result.intervals[0].kind == SPOKEN_PHONE
    assert result.intervals[0].start_ms == 900
    assert result.intervals[0].end_ms == 1_100