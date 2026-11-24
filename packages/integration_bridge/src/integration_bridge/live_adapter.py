"""Live and stub render adapters. Both stay on the same method names."""

from __future__ import annotations

import importlib
import sqlite3
import sys
from pathlib import Path

from .mvp_slice import REPO, connect

MOTIF_REGISTRY_V1 = (
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
    "TimelineScrubber",
    "SmsPhoneThread",
    "MapRouteTrace",
    "CaseBoardSpine",
    "AlibiSplitScreen",
    "EvidenceMatchCard",
    "HeroVideoBridge",
    "CustomDiagramScene",
)


def _motion(stem: str):
    root = str(REPO / "packages" / "python_motion" / "src")
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(f"python_motion.{stem}")


class StubPart2RenderAdapter:
    def render_scene(self, scene: dict) -> dict:
        return {"adapter": "stub", "scene_id": scene["scene_id"], "spend_usd": 0.0, "motif": scene.get("motif_component")}


class LivePart2RenderAdapter:
    def supported_motifs(self) -> tuple[str, ...]:
        return MOTIF_REGISTRY_V1

    def render_scene(self, scene: dict, out_dir: str) -> dict:
        book = _motion("bookend_generator")
        sfx = _motion("sfx_synth")
        pair = book.BookendGenerator().generate(
            book.BookendRequest(scene["scene_id"], "TEXT_TO_VIDEO", 4, out_dir)
        )
        cue = sfx.SfxSynthesizer().synthesize(sfx.SfxRequest("paper_slide", duration_ms=20, seed=1))
        return {
            "adapter": "live",
            "scene_id": scene["scene_id"],
            "motif": scene.get("motif_component"),
            "spend_usd": 0.0,
            "safety_passed": pair.safety_passed,
            "start_frame": pair.start_frame,
            "sfx_hz": cue.sample_rate_hz,
        }


def acquire_lease(connection: sqlite3.Connection, episode_id: str, holder: str) -> bool:
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute(
        "SELECT holder FROM episode_lock_lease WHERE episode_id = ?",
        (episode_id,),
    ).fetchone()
    if row is not None:
        connection.execute("COMMIT")
        return False
    connection.execute(
        "INSERT INTO episode_lock_lease (episode_id, holder, acquired_at) VALUES (?,?,?)",
        (episode_id, holder, 1),
    )
    connection.execute("COMMIT")
    return True


def open_locked(path: str) -> sqlite3.Connection:
    return connect(path)
