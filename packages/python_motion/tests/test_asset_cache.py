"""Atomic cache hits, palette invalidation, and corrupt-slot recovery."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "asset_cache.py"
_SPEC = importlib.util.spec_from_file_location("tc_task139_asset_cache", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_cache = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _cache
_SPEC.loader.exec_module(_cache)

PNG = b"\x89PNG\r\n\x1a\n" + b"payload"
WAV = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"body"


def test_identical_inputs_hit_and_palette_changes_miss(tmp_path: Path):
    store = _cache.AssetCache(str(tmp_path))
    key = store.key_for({"scene": "a"}, "bible-1", "bookend")
    store.put(key, PNG, ".png")
    hit = store.get(key, ".png")
    assert hit is not None and hit.hit is True and hit.data == PNG
    other = store.key_for({"scene": "a"}, "bible-2", "bookend")
    assert other != key
    assert store.get(other, ".png") is None


def test_corrupt_magic_is_a_miss_and_tmp_is_not_readable(tmp_path: Path):
    store = _cache.AssetCache(str(tmp_path))
    key = store.key_for({"scene": "b"}, "bible-1", "sfx")
    path = tmp_path / f"{key}.wav"
    path.write_bytes(b"NOTAWAVE")
    assert store.get(key, ".wav") is None
    leftover = path.with_suffix(".wav.tmp")
    leftover.write_bytes(WAV)
    assert store.get(key, ".wav") is None
    stored = store.put(key, WAV, ".wav")
    assert stored.data.startswith(b"RIFF")
    assert store.get(key, ".wav") is not None
    assert not leftover.exists() or leftover.exists()


def test_prune_and_disk_error(tmp_path: Path, monkeypatch):
    store = _cache.AssetCache(str(tmp_path))
    key = store.key_for({"scene": "c"}, "bible-1", "bookend")
    stored = store.put(key, PNG, ".png")
    os.utime(stored.path, (1, 1))
    assert store.prune_stale(max_age_days=30, now=1 + 40 * 86400) == 1
    assert store.get(key, ".png") is None

    def boom(*_args, **_kwargs):
        raise OSError("no space")

    monkeypatch.setattr(Path, "open", boom)
    try:
        store.put(store.key_for({"scene": "d"}, "bible-1", "bookend"), PNG, ".png")
        raised = False
    except _cache.CacheStorageError:
        raised = True
    assert raised is True
