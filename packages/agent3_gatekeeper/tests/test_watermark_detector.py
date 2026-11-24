"""Tests for corner watermark temporal persistence gate."""

from __future__ import annotations

import pytest

from agent3_gatekeeper.watermark_detector import (
    CORNER_FRACTION,
    CornerWatermarkScanner,
    VideoFrame,
    corner_safe_zones,
    is_agency_osd_label,
    is_broadcaster_reject_label,
)


def _frame(index: int, *, w: int = 1920, h: int = 1080) -> VideoFrame:
    return VideoFrame(frame_index=index, width=w, height=h, payload=b"\x00")


def test_corner_safe_zones_use_outer_fifteen_percent() -> None:
    zones = corner_safe_zones(1000, 800)
    assert len(zones) == 4
    tl = zones[0]
    assert tl.name == "top_left"
    assert (tl.x0, tl.y0, tl.x1, tl.y1) == (0, 0, 150, 120)
    br = zones[3]
    assert br.name == "bottom_right"
    assert (br.x0, br.y0, br.x1, br.y1) == (850, 680, 1000, 800)


@pytest.mark.parametrize(
    "label",
    ["AXON BODY", "axon body cam", "WatchGuard HUD", "WATCHGUARD timestamp OSD"],
)
def test_agency_osd_labels_pass_classification(label: str) -> None:
    assert is_agency_osd_label(label)
    assert not is_broadcaster_reject_label(label)


@pytest.mark.parametrize(
    "label",
    ["CourtTV", "FOX NEWS", "YouTube logo", "youtube.com corner bug"],
)
def test_broadcaster_labels_reject_classification(label: str) -> None:
    assert is_broadcaster_reject_label(label)
    assert not is_agency_osd_label(label)


def test_axon_osd_across_frames_passes() -> None:
    def vision(frame: VideoFrame, zone) -> str:
        if zone.name == "bottom_right":
            return "AXON BODY"
        if frame.frame_index == 3 and zone.name == "top_left":
            return "WatchGuard HUD"
        return "clean"

    scanner = CornerWatermarkScanner(vision)
    frames = [_frame(i) for i in range(4)]
    result = scanner.scan_frames(frames)

    assert result.passed is True
    assert result.watermark_clean == 1
    assert len(result.agency_osd_hits) >= 2


@pytest.mark.parametrize(
    "logo_label,canon",
    [
        ("CourtTV", "courttv"),
        ("FOX", "fox"),
        ("YouTube logo", "youtube"),
    ],
)
def test_persistent_broadcaster_logo_rejects(logo_label: str, canon: str) -> None:
    call_log: list[int] = []

    def vision(frame: VideoFrame, zone) -> str:
        call_log.append(frame.frame_index)
        if zone.name == "top_right":
            return logo_label
        return "clean"

    scanner = CornerWatermarkScanner(vision)
    frames = [_frame(i) for i in range(3)]
    result = scanner.scan_frames(frames)

    assert result.passed is False
    assert result.watermark_clean == 0
    assert result.rejected_label == canon
    assert result.persistence_frames >= 2
    assert len(call_log) == len(frames) * 4


def test_one_frame_fox_noise_passes() -> None:
    def vision(frame: VideoFrame, zone) -> str:
        if frame.frame_index == 1 and zone.name == "bottom_left":
            return "FOX NEWS"
        if zone.name == "bottom_right":
            return "AXON BODY"
        return "clean"

    scanner = CornerWatermarkScanner(vision)
    frames = [_frame(i) for i in range(4)]
    result = scanner.scan_frames(frames)

    assert result.passed is True
    assert result.watermark_clean == 1
    assert result.corner_hits and all(h.frame_index == 1 for h in result.corner_hits)


def test_watchguard_hud_only_passes() -> None:
    def vision(_frame: VideoFrame, _zone) -> str:
        return "WatchGuard HUD"

    scanner = CornerWatermarkScanner(vision)
    result = scanner.scan_frames([_frame(0), _frame(5)])

    assert result.passed is True
    assert result.watermark_clean == 1


def test_empty_clip_passes() -> None:
    scanner = CornerWatermarkScanner(lambda _f, _z: "CourtTV")
    result = scanner.scan_frames([])
    assert result.passed is True
    assert result.watermark_clean == 1


def test_corner_fraction_constant_matches_spec() -> None:
    assert CORNER_FRACTION == 0.15