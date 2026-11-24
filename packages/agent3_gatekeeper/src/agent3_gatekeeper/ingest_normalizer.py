"""Pixel purge for contraband provenance tags and CFR/48 kHz ingest command planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

CONTRABAND_TAGS: frozenset[str] = frozenset({"news", "CC BY-NC", "Ring CCTV"})
REFUSE_REASON_CONTRABAND = "CONTRABAND_PIXEL_PURGE"

_VIDEO_MEDIA_KINDS = frozenset(
    {"bodycam_mp4", "dashcam_mp4", "court_mp4"},
)
_AUDIO_MEDIA_KINDS = frozenset(
    {"call_911_wav", "interrogation_wav"},
)


@dataclass(frozen=True, slots=True)
class IngestNormalizeResult:
    accepted: bool
    normalized_cfr_30fps_48k: int
    ffmpeg_command: tuple[str, ...] | None = None
    refuse_reason: str | None = None
    purged: bool = False


def is_contraband_tag(provenance_tag: str) -> bool:
    """Return whether ``provenance_tag`` blocks pixel retention."""
    return provenance_tag in CONTRABAND_TAGS


def _audio_filter_chain(*, source_sample_rate_hz: int, source_channels: int) -> str:
    resample = "aresample=48000:resampler=soxr"
    if source_sample_rate_hz == 8000 and source_channels == 1:
        return f"{resample},pan=stereo|c0=c0|c1=c0"
    if source_channels == 1:
        return f"{resample},pan=stereo|c0=c0|c1=c0"
    return resample


def build_ffmpeg_normalize_command(
    input_path: Path | str,
    output_path: Path | str,
    *,
    media_kind: str,
    source_sample_rate_hz: int = 48000,
    source_channels: int = 2,
) -> tuple[str, ...]:
    """Build the ffmpeg argv that would conform cleared FOIA media at ingest."""
    src = str(input_path)
    dst = str(output_path)
    audio_filter = _audio_filter_chain(
        source_sample_rate_hz=source_sample_rate_hz,
        source_channels=source_channels,
    )
    base_audio = (
        "-af",
        audio_filter,
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s24le",
    )

    if media_kind in _VIDEO_MEDIA_KINDS:
        return (
            "ffmpeg",
            "-y",
            "-i",
            src,
            "-vf",
            "fps=30",
            "-fps_mode",
            "cfr",
            "-pix_fmt",
            "yuv420p",
            *base_audio,
            "-c:v",
            "libx264",
            dst,
        )

    if media_kind in _AUDIO_MEDIA_KINDS or media_kind == "photo_cc0":
        if media_kind == "photo_cc0":
            raise ValueError("photo_cc0 has no CFR/48 kHz transcode target")
        return ("ffmpeg", "-y", "-i", src, *base_audio, dst)

    raise ValueError(f"unsupported media_kind for ingest normalization: {media_kind}")


def purge_contraband_file(
    asset_path: Path | str,
    provenance_tag: str,
) -> IngestNormalizeResult:
    """Delete on-disk bytes for contraband-tagged assets and refuse ingest."""
    path = Path(asset_path)
    if not is_contraband_tag(provenance_tag):
        raise ValueError(f"provenance_tag is not contraband: {provenance_tag!r}")

    purged = False
    if path.exists():
        path.unlink()
        purged = True

    return IngestNormalizeResult(
        accepted=False,
        normalized_cfr_30fps_48k=0,
        ffmpeg_command=None,
        refuse_reason=REFUSE_REASON_CONTRABAND,
        purged=purged,
    )


def plan_cleared_ingest(
    input_path: Path | str,
    output_path: Path | str,
    *,
    provenance_tag: str,
    media_kind: str,
    source_sample_rate_hz: int = 48000,
    source_channels: int = 2,
) -> IngestNormalizeResult:
    """Return the ffmpeg command and metadata flags for a cleared staging asset."""
    if is_contraband_tag(provenance_tag):
        return IngestNormalizeResult(
            accepted=False,
            normalized_cfr_30fps_48k=0,
            ffmpeg_command=None,
            refuse_reason=REFUSE_REASON_CONTRABAND,
            purged=False,
        )

    command = build_ffmpeg_normalize_command(
        input_path,
        output_path,
        media_kind=media_kind,
        source_sample_rate_hz=source_sample_rate_hz,
        source_channels=source_channels,
    )
    return IngestNormalizeResult(
        accepted=True,
        normalized_cfr_30fps_48k=1,
        ffmpeg_command=command,
        refuse_reason=None,
        purged=False,
    )


def audit_staging_folder(
    entries: Iterable[tuple[Path | str, str]],
) -> list[IngestNormalizeResult]:
    """Purge contraband files from a staging manifest of ``(path, provenance_tag)``."""
    outcomes: list[IngestNormalizeResult] = []
    for asset_path, provenance_tag in entries:
        if is_contraband_tag(provenance_tag):
            outcomes.append(purge_contraband_file(asset_path, provenance_tag))
        else:
            outcomes.append(
                IngestNormalizeResult(
                    accepted=True,
                    normalized_cfr_30fps_48k=1,
                    ffmpeg_command=None,
                    refuse_reason=None,
                    purged=False,
                )
            )
    return outcomes


def ffmpeg_command_as_str(command: Sequence[str]) -> str:
    """Render argv as a single shell-ready ffmpeg command string."""
    return " ".join(command)