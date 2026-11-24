"""Segmented voice timeline drift validator (Task 070).

Confirms ``sum(segment durations) == total_master_ms`` using integer
millisecond arithmetic only, and checks each ``NARRATION`` WAV against its
segment interval via caller-supplied declared durations (no FFprobe).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Mapping, Sequence

MAX_NARRATION_WAV_DRIFT_MS: Final[int] = 20


@dataclass(frozen=True, slots=True)
class TimelineSegment:
    segment_id: str
    segment_kind: str
    start_ms: int
    end_ms: int
    audio_path: str | None = None


@dataclass(frozen=True, slots=True)
class DriftFinding:
    code: str
    detail: str
    segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class DriftValidationResult:
    ok: bool
    total_master_ms: int
    segment_duration_sum_ms: int
    findings: tuple[DriftFinding, ...]


class DriftValidationError(Exception):
    def __init__(self, result: DriftValidationResult) -> None:
        self.result = result
        parts = "; ".join(finding.detail for finding in result.findings)
        super().__init__(parts or "voice timeline drift validation failed")


def _require_nonneg_int_ms(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be a non-negative int millisecond value")
    if value < 0:
        raise ValueError(f"{field} must be >= 0")
    return value


def segment_duration_ms(segment: TimelineSegment) -> int:
    """Return ``end_ms - start_ms`` for a timeline segment."""
    start_ms = _require_nonneg_int_ms(segment.start_ms, field="start_ms")
    if isinstance(segment.end_ms, bool) or not isinstance(segment.end_ms, int):
        raise TypeError("end_ms must be a non-negative int millisecond value")
    if segment.end_ms <= start_ms:
        raise ValueError("segment end_ms must be greater than start_ms")
    return segment.end_ms - start_ms


def validate_voice_timeline_drift(
    *,
    total_master_ms: int,
    segments: Sequence[TimelineSegment],
    declared_narration_wav_ms: Mapping[str, int],
) -> DriftValidationResult:
    """Validate cumulative segment closure and per-NARRATION WAV drift."""
    master_ms = _require_nonneg_int_ms(total_master_ms, field="total_master_ms")
    if not segments:
        finding = DriftFinding(
            code="empty_timeline",
            detail="voice timeline must contain at least one segment",
        )
        return DriftValidationResult(
            ok=False,
            total_master_ms=master_ms,
            segment_duration_sum_ms=0,
            findings=(finding,),
        )

    findings: list[DriftFinding] = []
    duration_sum = 0

    for segment in segments:
        duration = segment_duration_ms(segment)
        duration_sum += duration

        if segment.segment_kind != "NARRATION":
            continue
        if segment.audio_path is None:
            findings.append(
                DriftFinding(
                    code="narration_missing_audio",
                    detail=f"NARRATION segment {segment.segment_id} requires audio_path",
                    segment_id=segment.segment_id,
                )
            )
            continue

        declared = declared_narration_wav_ms.get(segment.audio_path)
        if declared is None:
            findings.append(
                DriftFinding(
                    code="narration_wav_undeclared",
                    detail=(
                        f"NARRATION segment {segment.segment_id} missing declared "
                        f"WAV duration for {segment.audio_path}"
                    ),
                    segment_id=segment.segment_id,
                )
            )
            continue

        if isinstance(declared, bool) or not isinstance(declared, int):
            findings.append(
                DriftFinding(
                    code="narration_wav_non_integer",
                    detail=f"declared WAV duration for {segment.audio_path} must be int ms",
                    segment_id=segment.segment_id,
                )
            )
            continue

        drift = abs(declared - duration)
        if drift >= MAX_NARRATION_WAV_DRIFT_MS:
            findings.append(
                DriftFinding(
                    code="narration_wav_drift",
                    detail=(
                        f"NARRATION segment {segment.segment_id} WAV drift {drift} ms "
                        f"(declared {declared} ms, segment {duration} ms)"
                    ),
                    segment_id=segment.segment_id,
                )
            )

    if duration_sum != master_ms:
        findings.append(
            DriftFinding(
                code="timeline_sum_mismatch",
                detail=(
                    f"segment durations sum to {duration_sum} ms but "
                    f"total_master_ms is {master_ms} ms"
                ),
            )
        )

    return DriftValidationResult(
        ok=not findings,
        total_master_ms=master_ms,
        segment_duration_sum_ms=duration_sum,
        findings=tuple(findings),
    )


def assert_voice_timeline_drift(
    *,
    total_master_ms: int,
    segments: Sequence[TimelineSegment],
    declared_narration_wav_ms: Mapping[str, int],
) -> DriftValidationResult:
    """Return the validation result or raise ``DriftValidationError``."""
    result = validate_voice_timeline_drift(
        total_master_ms=total_master_ms,
        segments=segments,
        declared_narration_wav_ms=declared_narration_wav_ms,
    )
    if not result.ok:
        raise DriftValidationError(result)
    return result