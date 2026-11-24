"""VoiceTrackManifest serializer and chunk cache tests (offline)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from shared_contracts.models import VoiceTrackManifest

from voice_sync.manifest_writer import (
    CachedNarrationChunk,
    ChunkManifestCache,
    FoiaSegmentSpec,
    LocalCuePoint,
    LocalWordStamp,
    NarrationSegmentSpec,
    TwistPadSegmentSpec,
    build_voice_track_manifest,
    manifest_from_cached_chunks,
    narration_text_sha256,
    replace_narration_chunk,
    serialize_manifest_json,
    serialize_manifest_payload,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "voice_sync" / "manifest_writer.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _synth_for_text(
    *,
    ms_per_word: int = 120,
):
    calls: list[tuple[str, str]] = []

    def synthesize(segment_id: str, text: str) -> CachedNarrationChunk:
        calls.append((segment_id, text))
        words = text.split()
        duration_ms = max(400, len(words) * ms_per_word)
        local_words = []
        cursor = 0
        for word in words:
            end = cursor + ms_per_word
            local_words.append(LocalWordStamp(word=word, start_ms=cursor, end_ms=end))
            cursor = end
        text_hash = narration_text_sha256(text)
        return CachedNarrationChunk(
            text_sha256=text_hash,
            duration_ms=duration_ms,
            audio_path=f"audio/{segment_id}_{text_hash[:8]}.wav",
            word_timestamps=tuple(local_words),
            cue_points=(LocalCuePoint(cue_id=f"cue_{segment_id}", at_ms=10, label="bed"),),
            amplitude_envelope=tuple(0.5 for _ in range(max(1, duration_ms // 100))),
        )

    return calls, synthesize


def test_stdlib_only_no_network() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in _BANNED_IMPORTS
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in _BANNED_IMPORTS


def test_build_manifest_matches_vector_shape() -> None:
    calls, synthesize = _synth_for_text()
    cache = ChunkManifestCache()
    specs = [
        NarrationSegmentSpec(segment_id="seg_0_1", text="According to records"),
        TwistPadSegmentSpec(segment_id="seg_0_2", duration_ms=500),
        FoiaSegmentSpec(
            segment_id="seg_0_3", foia_asset_id="foia_0", duration_ms=2000
        ),
    ]
    manifest, stats = build_voice_track_manifest(
        "ep_1", specs, cache=cache, synthesize=synthesize
    )
    assert isinstance(manifest, VoiceTrackManifest)
    assert stats.synthesized == 1
    assert stats.cache_hits == 0
    assert len(calls) == 1
    assert manifest.segments[0].narration_version_sha256 == narration_text_sha256(
        "According to records"
    )
    assert manifest.segments[1].segment_kind == "TWIST_PAD"
    assert manifest.segments[2].foia_asset_id == "foia_0"
    assert manifest.total_master_ms == manifest.segments[-1].end_ms
    assert manifest.word_timestamps[0].start_ms == 0
    assert manifest.cue_points[0].at_ms == 10
    assert all(0.0 <= sample <= 1.0 for sample in manifest.amplitude_envelope)


def test_cache_reuses_unchanged_narration_chunks() -> None:
    calls, synthesize = _synth_for_text()
    cache = ChunkManifestCache()
    text_a = "Alpha chunk one two three"
    text_b = "Bravo chunk four five"
    first_specs = [
        NarrationSegmentSpec(segment_id="n1", text=text_a),
        TwistPadSegmentSpec(segment_id="tw1", duration_ms=600),
        NarrationSegmentSpec(segment_id="n2", text=text_b),
    ]
    build_voice_track_manifest("ep_2", first_specs, cache=cache, synthesize=synthesize)
    assert len(calls) == 2
    assert len(cache) == 2

    second_specs = [
        NarrationSegmentSpec(segment_id="n1b", text=text_a),
        TwistPadSegmentSpec(segment_id="tw1b", duration_ms=600),
        NarrationSegmentSpec(segment_id="n2b", text=text_b),
    ]
    _, stats = build_voice_track_manifest(
        "ep_2", second_specs, cache=cache, synthesize=synthesize
    )
    assert stats.synthesized == 0
    assert stats.cache_hits == 2
    assert len(calls) == 2


def test_replace_chunk_invalidates_only_edited_hash_and_shifts_downstream() -> None:
    calls, synthesize = _synth_for_text(ms_per_word=100)
    cache = ChunkManifestCache()
    text_a = "First narration block"
    text_b = "Second narration tail"
    specs = [
        NarrationSegmentSpec(segment_id="n1", text=text_a),
        TwistPadSegmentSpec(segment_id="tw1", duration_ms=500),
        NarrationSegmentSpec(segment_id="n2", text=text_b),
    ]
    manifest_before, _ = build_voice_track_manifest(
        "ep_3", specs, cache=cache, synthesize=synthesize
    )
    n2_start_before = manifest_before.segments[2].start_ms

    longer = "First narration block with extra proper noun inserted"
    manifest_after, stats = replace_narration_chunk(
        "ep_3",
        specs,
        segment_id="n1",
        new_text=longer,
        cache=cache,
        synthesize=synthesize,
    )
    assert stats.invalidated_sha256 == (narration_text_sha256(text_a),)
    assert stats.synthesized == 1
    assert stats.cache_hits == 1
    assert len(calls) == 3

    assert manifest_after.segments[0].narration_version_sha256 == narration_text_sha256(
        longer
    )
    assert manifest_after.segments[0].end_ms > manifest_before.segments[0].end_ms
    assert manifest_after.segments[2].start_ms > n2_start_before
    assert manifest_after.segments[2].narration_version_sha256 == narration_text_sha256(
        text_b
    )
    assert cache.get(narration_text_sha256(text_a)) is None
    assert cache.get(narration_text_sha256(text_b)) is not None
    assert cache.get(narration_text_sha256(longer)) is not None


def test_word_timestamps_and_cues_shift_with_segment_start() -> None:
    calls, synthesize = _synth_for_text(ms_per_word=80)
    cache = ChunkManifestCache()
    specs = [
        FoiaSegmentSpec(segment_id="f1", foia_asset_id="foia_x", duration_ms=1500),
        NarrationSegmentSpec(segment_id="n1", text="After FOIA slot"),
    ]
    manifest, _ = build_voice_track_manifest(
        "ep_4", specs, cache=cache, synthesize=synthesize
    )
    assert manifest.word_timestamps[0].start_ms == 1500
    assert manifest.cue_points[0].at_ms == 1510


def test_serialize_manifest_roundtrip_json() -> None:
    _, synthesize = _synth_for_text()
    manifest, _ = build_voice_track_manifest(
        "ep_5",
        [NarrationSegmentSpec(segment_id="n1", text="Serialize me")],
        synthesize=synthesize,
    )
    payload = serialize_manifest_payload(manifest)
    restored = VoiceTrackManifest.model_validate(payload)
    assert restored == manifest
    serialized = serialize_manifest_json(manifest)
    assert '"episode_id"' in serialized
    assert "ep_5" in serialized


def test_manifest_from_cached_chunks_requires_warm_cache() -> None:
    calls, synthesize = _synth_for_text()
    cache = ChunkManifestCache()
    text = "Warm cache entry"
    specs = [NarrationSegmentSpec(segment_id="n1", text=text)]
    build_voice_track_manifest("ep_6", specs, cache=cache, synthesize=synthesize)
    assert len(calls) == 1
    rebuilt = manifest_from_cached_chunks("ep_6", specs, cache)
    assert rebuilt.segments[0].narration_version_sha256 == narration_text_sha256(text)


def test_replace_unknown_segment_raises() -> None:
    cache = ChunkManifestCache()
    with pytest.raises(ValueError, match="unknown NARRATION"):
        replace_narration_chunk(
            "ep_x",
            [NarrationSegmentSpec(segment_id="n1", text="hello")],
            segment_id="missing",
            new_text="other",
            cache=cache,
            synthesize=lambda _s, _t: pytest.fail("should not synthesize"),
        )