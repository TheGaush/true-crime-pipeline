"""Tests for contraband pixel purge and CFR/48 kHz ingest command planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent3_gatekeeper.ingest_normalizer import (
    CONTRABAND_TAGS,
    REFUSE_REASON_CONTRABAND,
    audit_staging_folder,
    build_ffmpeg_normalize_command,
    is_contraband_tag,
    plan_cleared_ingest,
    purge_contraband_file,
)


@pytest.mark.parametrize("tag", sorted(CONTRABAND_TAGS))
def test_contraband_tags_are_detected(tag: str) -> None:
    assert is_contraband_tag(tag)


def test_cleared_bodycam_plans_cfr_yuv420p_48k_stereo(tmp_path: Path) -> None:
    src = tmp_path / "officer_bodycam_vfr.mp4"
    dst = tmp_path / "normalized_bodycam.mp4"
    src.write_bytes(b"FAKE_MP4_BYTES")

    result = plan_cleared_ingest(
        src,
        dst,
        provenance_tag="STATE_PUBLIC_RECORD_PERMITTED",
        media_kind="bodycam_mp4",
    )

    assert result.accepted is True
    assert result.normalized_cfr_30fps_48k == 1
    assert result.ffmpeg_command is not None
    cmd = result.ffmpeg_command
    assert cmd[0] == "ffmpeg"
    assert "-vf" in cmd and "fps=30" in cmd
    assert "-fps_mode" in cmd and "cfr" in cmd
    assert "-pix_fmt" in cmd and "yuv420p" in cmd
    assert "-af" in cmd
    assert "aresample=48000:resampler=soxr" in cmd
    assert "-ar" in cmd and "48000" in cmd
    assert "-ac" in cmd and "2" in cmd
    assert "-c:a" in cmd and "pcm_s24le" in cmd


def test_cleared_8khz_mono_911_wav_uses_soxr_dual_mono(tmp_path: Path) -> None:
    src = tmp_path / "dispatch_911_8khz_mono.wav"
    dst = tmp_path / "normalized_911.wav"
    src.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

    result = plan_cleared_ingest(
        src,
        dst,
        provenance_tag="US_FED_EMPLOYEE_17USC105",
        media_kind="call_911_wav",
        source_sample_rate_hz=8000,
        source_channels=1,
    )

    assert result.accepted is True
    assert result.normalized_cfr_30fps_48k == 1
    assert result.ffmpeg_command == build_ffmpeg_normalize_command(
        src,
        dst,
        media_kind="call_911_wav",
        source_sample_rate_hz=8000,
        source_channels=1,
    )

    audio_filter = result.ffmpeg_command[result.ffmpeg_command.index("-af") + 1]
    assert audio_filter == "aresample=48000:resampler=soxr,pan=stereo|c0=c0|c1=c0"
    assert "-ar" in result.ffmpeg_command and "48000" in result.ffmpeg_command
    assert "-ac" in result.ffmpeg_command and "2" in result.ffmpeg_command
    assert "-c:a" in result.ffmpeg_command and "pcm_s24le" in result.ffmpeg_command


@pytest.mark.parametrize("tag", sorted(CONTRABAND_TAGS))
def test_contraband_files_are_purged_and_refused(tmp_path: Path, tag: str) -> None:
    asset = tmp_path / f"{tag.replace(' ', '_')}.mp4"
    asset.write_bytes(b"CONTRABAND_BYTES")

    result = purge_contraband_file(asset, tag)

    assert result.accepted is False
    assert result.normalized_cfr_30fps_48k == 0
    assert result.refuse_reason == REFUSE_REASON_CONTRABAND
    assert result.purged is True
    assert not asset.exists()


def test_plan_cleared_refuses_contraband_without_delete(tmp_path: Path) -> None:
    asset = tmp_path / "news_clip.mp4"
    asset.write_bytes(b"SHOULD_STAY_FOR_PLAN_ONLY")

    result = plan_cleared_ingest(
        asset,
        tmp_path / "out.mp4",
        provenance_tag="news",
        media_kind="bodycam_mp4",
    )

    assert result.accepted is False
    assert result.normalized_cfr_30fps_48k == 0
    assert result.refuse_reason == REFUSE_REASON_CONTRABAND
    assert asset.exists()


def test_audit_staging_folder_purges_contraband_only(tmp_path: Path) -> None:
    ring = tmp_path / "neighbor_ring.mp4"
    bodycam = tmp_path / "officer_bodycam.mp4"
    ring.write_bytes(b"RING")
    bodycam.write_bytes(b"BODYCAM")

    outcomes = audit_staging_folder(
        [
            (ring, "Ring CCTV"),
            (bodycam, "STATE_PUBLIC_RECORD_PERMITTED"),
        ]
    )

    assert len(outcomes) == 2
    assert outcomes[0].purged is True
    assert outcomes[0].normalized_cfr_30fps_48k == 0
    assert not ring.exists()
    assert outcomes[1].accepted is True
    assert outcomes[1].normalized_cfr_30fps_48k == 1
    assert bodycam.exists()