"""Content-addressed cache for generated plates and cues.

Writes land in a temporary file, are fsynced, then renamed. A reader that
sees a bad PNG or RIFF header treats the slot as a miss.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

GENERATOR_VERSION = "python_motion.asset_cache.v1"


class CacheStorageError(OSError):
    pass


@dataclass(frozen=True)
class CacheHit:
    key: str
    path: str
    data: bytes
    hit: bool


class AssetCache:
    def __init__(self, root: str, telemetry_path: str | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.telemetry_path = Path(telemetry_path) if telemetry_path else self.root / "telemetry.jsonl"

    def key_for(self, payload: object, case_bible_hash: str, kind: str) -> str:
        body = json.dumps(
            {
                "case_bible_hash": case_bible_hash,
                "generator": GENERATOR_VERSION,
                "kind": kind,
                "payload": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(body.encode("utf8")).hexdigest()

    def put(self, key: str, data: bytes, suffix: str) -> CacheHit:
        path = self._path(key, suffix)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with tmp.open("wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except OSError as error:
            tmp.unlink(missing_ok=True)
            raise CacheStorageError(str(error)) from error
        self._log("store", key, False)
        return CacheHit(key, str(path), data, False)

    def get(self, key: str, suffix: str) -> CacheHit | None:
        path = self._path(key, suffix)
        if not path.is_file():
            self._log("miss", key, False)
            return None
        data = path.read_bytes()
        if not _magic_ok(data, suffix):
            self._log("corrupt", key, False)
            return None
        self._log("hit", key, True)
        return CacheHit(key, str(path), data, True)

    def prune_stale(self, max_age_days: int = 30, now: float | None = None) -> int:
        if max_age_days < 0:
            raise CacheStorageError("max_age_days must be >= 0")
        clock = now if now is not None else __import__("time").time()
        limit = max_age_days * 86400
        removed = 0
        for path in self.root.glob("*"):
            if path.suffix == ".tmp" or path.name == self.telemetry_path.name:
                continue
            if not path.is_file():
                continue
            if clock - path.stat().st_mtime > limit:
                path.unlink()
                removed += 1
        return removed

    def _path(self, key: str, suffix: str) -> Path:
        if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            raise CacheStorageError("cache key must be a sha256 hex digest")
        token = suffix if suffix.startswith(".") else f".{suffix}"
        return self.root / f"{key}{token}"

    def _log(self, event: str, key: str, hit: bool) -> None:
        line = json.dumps({"event": event, "hit": hit, "key": key}, sort_keys=True)
        with self.telemetry_path.open("a", encoding="utf8") as handle:
            handle.write(line + "\n")


def _magic_ok(data: bytes, suffix: str) -> bool:
    token = suffix.lower()
    if token in {".png", "png"}:
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if token in {".wav", "wav"}:
        return data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    return len(data) > 0
