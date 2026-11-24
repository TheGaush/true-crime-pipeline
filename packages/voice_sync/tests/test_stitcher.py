"""Tests for segmented voice timeline stitcher (Task 065)."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from voice_sync.stitcher import (
    L_CUT_MS_MAX,
    L_CUT_MS_MIN,
    ROOM_TONE_RMS_DBFS_MAX,
    ROOM_TONE_RMS_DBFS_MIN,
    TWIST_PAD_MS_MAX,
    TWIST_PAD_MS_MIN,
    FoiaBeat,
    NarrationBeat,
    StitcherError,
    read_wav_mono_float,
    rms_dbfs,
    stitch_timeline,
    write_room_tone_wav,
)


def _minimal_voice_db(episode_id: str = "ep_065") -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        CREATE TABLE episodes (
          episode_id TEXT PRIMARY KEY,
          total_master_ms INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE voice_segments (
          segment_id TEXT PRIMARY KEY,
          episode_id TEXT NOT NULL,
          seq_index INTEGER NOT NULL,
          segment_kind TEXT NOT NULL,
          start_ms INTEGER NOT NULL,
          end_ms INTEGER NOT NULL,
          audio_path TEXT,
          foia_asset_id TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO episodes (episode_id, total_master_ms) VALUES (?, 0)",
        (episode_id,),
    )
    conn.commit()
    return conn


def test_twist_pad_room_tone_dbfs_and_nonzero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "pad.wav"
        measured = write_room_tone_wav(wav_path, 600, seed=42)
        assert ROOM_TONE_RMS_DBFS_MIN <= measured <= ROOM_TONE_RMS_DBFS_MAX
        samples, _rate = read_wav_mono_float(wav_path)
        assert any(abs(s) > 0 for s in samples)
        assert ROOM_TONE_RMS_DBFS_MIN <= rms_dbfs(samples) <= ROOM_TONE_RMS_DBFS_MAX


def test_twist_pad_duration_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "bad.wav"
        with pytest.raises(StitcherError, match="TWIST_PAD duration"):
            write_room_tone_wav(wav_path, 400, seed=1)
        with pytest.raises(StitcherError, match="TWIST_PAD duration"):
            write_room_tone_wav(wav_path, 800, seed=1)


def test_stitch_timeline_bounds_and_total() -> None:
    beats = [
        NarrationBeat("seg_n1", "audio/n1.wav", 5000, "sha_n1", plot_twist=True),
        FoiaBeat("seg_f1", "foia_1", clip_duration_ms=8000, l_cut_ms=700),
        NarrationBeat("seg_n2", "audio/n2.wav", 3000, "sha_n2", plot_twist=False),
    ]
    twist_ms = 520
    with tempfile.TemporaryDirectory() as tmp:
        result = stitch_timeline(
            "ep_065",
            beats,
            twist_pad_ms=twist_ms,
            output_dir=tmp,
            twist_pad_seed=7,
        )
        assert result.total_master_ms == 5000 + twist_ms + 8000 + 700 + 3000
        kinds = [s.segment_kind for s in result.segments]
        assert kinds == ["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT", "NARRATION"]
        assert result.segments[0].start_ms == 0
        for prev, nxt in zip(result.segments, result.segments[1:]):
            assert prev.end_ms == nxt.start_ms
        twist = result.segments[1]
        assert TWIST_PAD_MS_MIN <= twist.end_ms - twist.start_ms <= TWIST_PAD_MS_MAX
        foia = result.segments[2]
        assert foia.end_ms - foia.start_ms == 8000 + 700
        assert foia.audio_path is None
        assert foia.foia_asset_id == "foia_1"
        assert twist.twist_pad_wav_path is not None
        samples, _ = read_wav_mono_float(twist.twist_pad_wav_path)
        assert ROOM_TONE_RMS_DBFS_MIN <= rms_dbfs(samples) <= ROOM_TONE_RMS_DBFS_MAX


def test_l_cut_bounds() -> None:
    with pytest.raises(StitcherError, match="l_cut_ms"):
        stitch_timeline(
            "ep_x",
            [FoiaBeat("f", "foia_x", 1000, l_cut_ms=500)],
        )
    with pytest.raises(StitcherError, match="l_cut_ms"):
        stitch_timeline(
            "ep_x",
            [FoiaBeat("f", "foia_x", 1000, l_cut_ms=1200)],
        )
    result = stitch_timeline(
        "ep_ok",
        [FoiaBeat("f", "foia_x", 2000, l_cut_ms=L_CUT_MS_MIN)],
    )
    assert result.total_master_ms == 2000 + L_CUT_MS_MIN
    result2 = stitch_timeline(
        "ep_ok2",
        [FoiaBeat("f2", "foia_x", 1000, l_cut_ms=L_CUT_MS_MAX)],
    )
    assert result2.total_master_ms == 1000 + L_CUT_MS_MAX


def test_sqlite_persistence() -> None:
    conn = _minimal_voice_db()
    beats = [
        NarrationBeat("vs_1", "s1.wav", 10000, "abc123", plot_twist=True),
        FoiaBeat("vs_2", "foia_9", 5000, l_cut_ms=800),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        result = stitch_timeline(
            "ep_065",
            beats,
            twist_pad_ms=600,
            output_dir=tmp,
            connection=conn,
        )
    row = conn.execute(
        "SELECT total_master_ms FROM episodes WHERE episode_id = ?", ("ep_065",)
    ).fetchone()
    assert row[0] == result.total_master_ms
    rows = conn.execute(
        "SELECT segment_kind, start_ms, end_ms, audio_path, foia_asset_id "
        "FROM voice_segments ORDER BY seq_index"
    ).fetchall()
    assert len(rows) == 3
    assert rows[0][0] == "NARRATION" and rows[0][3] == "s1.wav"
    assert rows[1][0] == "TWIST_PAD" and rows[1][3] is None
    assert rows[2][0] == "FOIA_AUDIO_SLOT" and rows[2][4] == "foia_9"
    conn.close()


def test_sum_equals_total_master_ms() -> None:
    beats = [
        NarrationBeat("a", "audio/a.wav", 1200, "sha_a"),
        NarrationBeat("b", "audio/b.wav", 2400, "sha_b", plot_twist=True),
        FoiaBeat("c", "foia_c", 15000, l_cut_ms=900),
        NarrationBeat("d", "audio/d.wav", 800, "sha_d"),
    ]
    result = stitch_timeline("ep_sum", beats, twist_pad_ms=750)
    segment_sum = sum(s.end_ms - s.start_ms for s in result.segments)
    assert segment_sum == result.total_master_ms
    assert result.segments[-1].end_ms == result.total_master_ms