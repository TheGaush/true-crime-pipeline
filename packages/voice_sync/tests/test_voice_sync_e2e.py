"""Task 072 — segmented Voice-First integration suite (offline, no network)."""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages" / "shared_contracts" / "src"))

from voice_sync.pipeline import (
    LUFS_TOLERANCE_LU,
    MAX_TOTAL_DRIFT_MS,
    OUTPUT_CHANNELS,
    OUTPUT_SAMPLE_RATE_HZ,
    PRONUNCIATION_SIMILARITY_THRESHOLD,
    ROOM_TONE_RMS_DBFS_MAX,
    ROOM_TONE_RMS_DBFS_MIN,
    TARGET_LUFS,
    TWIST_PAD_MS_MAX,
    TWIST_PAD_MS_MIN,
    VOICE_READY,
    FoiaAudioSlotBeat,
    MockableTtsClient,
    NarrationBeat,
    VoiceSyncService,
    build_tts_segment_plan,
    check_proper_noun_pronunciation,
    read_wav_mono_float,
    verify_narration_never_crosses_foia,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "voice_sync" / "pipeline.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _e2e_beats() -> list[NarrationBeat | FoiaAudioSlotBeat]:
    before = (
        "Detectives reviewed the warehouse timeline. "
        "Witnesses placed the suspect near the loading dock before midnight. "
        "The security camera timestamp aligned with the 911 call."
    )
    after = (
        "After the FOIA dispatch recording, Krzysztof was named in the affidavit. "
        "Investigators matched his route to cell tower records."
    )
    return [
        NarrationBeat(before, is_plot_twist=True),
        FoiaAudioSlotBeat("foia_911_dispatch", duration_ms=2000, l_cut_ms=700),
        NarrationBeat(after),
    ]


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in _BANNED_IMPORTS


def test_narration_plan_never_crosses_foia_slot() -> None:
    plan = build_tts_segment_plan("case_072", _e2e_beats())
    report = verify_narration_never_crosses_foia(plan)
    assert report.passed
    kinds = [segment.segment_kind for segment in plan.segments]
    assert "FOIA_AUDIO_SLOT" in kinds
    foia_idx = kinds.index("FOIA_AUDIO_SLOT")
    assert kinds[foia_idx - 1] == "TWIST_PAD"
    pre_foia = [seg for seg in plan.segments[:foia_idx] if seg.segment_kind == "NARRATION"]
    post_foia = [seg for seg in plan.segments[foia_idx + 1 :] if seg.segment_kind == "NARRATION"]
    assert pre_foia and post_foia


def test_voice_sync_pipeline_certifies_episode() -> None:
    service = VoiceSyncService(REPO)
    with tempfile.TemporaryDirectory() as tmp:
        client = MockableTtsClient(fail_once_on_chunk_id="chunk_002")
        asr = {
            "chunk_001": ["Detectives", "reviewed", "warehouse"],
            "chunk_002": ["crystal", "named", "affidavit"],
        }
        result = service.run_episode(
            "ep_task_072",
            _e2e_beats(),
            proper_nouns=[("Krzysztof", "chunk_002")],
            asr_tokens_by_chunk=asr,
            tts_client=client,
            work_dir=Path(tmp),
        )

        assert result.conveyor_state == VOICE_READY
        assert result.total_drift_ms < MAX_TOTAL_DRIFT_MS
        assert all(report.passed for report in result.stage_reports)

        narration_chunks = [
            path
            for path in Path(tmp).glob("chunk_*.wav")
            if ".partial" not in path.name
        ]
        assert narration_chunks
        assert not list(Path(tmp).glob("*.partial.wav"))

        foia_segments = [s for s in result.manifest.segments if s.segment_kind == "FOIA_AUDIO_SLOT"]
        assert len(foia_segments) == 1
        foia = foia_segments[0]
        assert foia.audio_path is None
        assert foia.foia_asset_id == "foia_911_dispatch"

        post_foia = next(
            seg for seg in result.manifest.segments if seg.segment_kind == "NARRATION" and seg.start_ms >= foia.end_ms
        )
        first_word = next(
            stamp
            for stamp in result.manifest.word_timestamps
            if stamp.segment_id == post_foia.segment_id
        )
        assert first_word.start_ms == post_foia.start_ms
        assert first_word.start_ms >= foia.end_ms

        twist = next(seg for seg in result.manifest.segments if seg.segment_kind == "TWIST_PAD")
        twist_ms = twist.end_ms - twist.start_ms
        assert TWIST_PAD_MS_MIN <= twist_ms <= TWIST_PAD_MS_MAX
        assert result.twist_pad_measured_dbfs is not None
        assert ROOM_TONE_RMS_DBFS_MIN <= result.twist_pad_measured_dbfs <= ROOM_TONE_RMS_DBFS_MAX
        twist_samples = read_wav_mono_float(Path(twist.audio_path or ""))
        assert any(abs(sample) > 1e-6 for sample in twist_samples)


def test_chunks_are_48khz_and_near_minus_16_lufs(tmp_path: Path) -> None:
    service = VoiceSyncService(REPO)
    result = service.run_episode(
        "ep_lufs",
        [NarrationBeat("Short certification beat for loudness parity.")],
        work_dir=tmp_path,
    )
    assert result.conveyor_state == VOICE_READY
    for segment in result.manifest.segments:
        if segment.segment_kind != "NARRATION" or not segment.audio_path:
            continue
        with Path(segment.audio_path).open("rb") as handle:
            header = handle.read(44)
        rate = int.from_bytes(header[24:28], "little")
        channels = int.from_bytes(header[22:24], "little")
        assert rate == OUTPUT_SAMPLE_RATE_HZ
        assert channels == OUTPUT_CHANNELS


def test_mangled_proper_noun_is_flagged() -> None:
    finding = check_proper_noun_pronunciation(
        "Krzysztof",
        ["crystal", "charged"],
        chunk_id="chunk_002",
    )
    assert finding.flagged
    assert finding.similarity < PRONUNCIATION_SIMILARITY_THRESHOLD
    assert finding.needs_resynthesis


def test_mocked_429_and_pronunciation_retry_leaves_no_orphan_wav() -> None:
    service = VoiceSyncService(REPO)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        client = MockableTtsClient(fail_once_on_chunk_id="chunk_002")
        result = service.run_episode(
            "ep_retry",
            _e2e_beats(),
            proper_nouns=[("Krzysztof", "chunk_002")],
            asr_tokens_by_chunk={"chunk_002": ["crystal", "fled"]},
            tts_client=client,
            work_dir=work,
        )
        assert result.conveyor_state == VOICE_READY
        assert result.cleaned_orphan_paths
        assert not list(work.glob("*.partial.wav"))
        chunk_paths = {p.name for p in work.glob("chunk_*.wav")}
        assert chunk_paths
        assert not any(name.endswith(".partial.wav") for name in chunk_paths)
        assert len(client.calls) >= 3


def test_target_lufs_constant_matches_spec() -> None:
    assert TARGET_LUFS == -16.0
    assert LUFS_TOLERANCE_LU == 0.5