"""Offline hero-scene orchestrator.

A timed-out dispatch is reconciled before any new create. A second failure
leaves the scene on its fallback clip. Frame counts follow round(duration * 30).
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path


class OrchestratorError(RuntimeError):
    pass


@dataclass(frozen=True)
class SceneResult:
    scene_id: str
    state: str
    engine: str
    nb_frames: int
    path: str


class FlowOrchestrator:
    def __init__(self, db_path: str, out_dir: str, transport) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.transport = transport
        self.connection = sqlite3.connect(db_path)
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS flow_jobs (
              episode_id TEXT NOT NULL,
              scene_id TEXT NOT NULL,
              state TEXT NOT NULL,
              strikes INTEGER NOT NULL DEFAULT 0,
              provider_operation_id TEXT,
              idempotency_key TEXT NOT NULL,
              UNIQUE(episode_id, scene_id)
            );
            CREATE TABLE IF NOT EXISTS budget_reservations (
              episode_id TEXT NOT NULL,
              scene_id TEXT NOT NULL,
              micro_usd INTEGER NOT NULL,
              status TEXT NOT NULL
            );
            """
        )

    def run(self, manifest: dict) -> dict:
        self.reconcile()
        rows = []
        heroes = [scene for scene in manifest["scenes"] if scene.get("visual_engine") == "FLOW_HERO_VIDEO"]
        if len(heroes) > 10:
            raise OrchestratorError("hero clip cap")
        for scene in heroes:
            rows.append(self._fulfill(manifest["episode_id"], scene))
        expected = sum(_frames(float(scene["duration_sec"])) for scene in heroes)
        actual = sum(row.nb_frames for row in rows)
        if actual != expected:
            raise OrchestratorError(f"frame drift {actual} != {expected}")
        report = {"episode_id": manifest["episode_id"], "scenes": [row.__dict__ for row in rows], "nb_frames": actual}
        (self.out_dir / "hero_fulfillment_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
        return report

    def reconcile(self) -> list[str]:
        done = []
        pending = self.connection.execute(
            "SELECT episode_id, scene_id, provider_operation_id FROM flow_jobs WHERE state = 'UNKNOWN_RECONCILE'"
        ).fetchall()
        for episode_id, scene_id, operation_id in pending:
            status = self.transport.poll(operation_id)
            self.connection.execute(
                "UPDATE flow_jobs SET state = ? WHERE episode_id = ? AND scene_id = ?",
                (status, episode_id, scene_id),
            )
            done.append(scene_id)
        self.connection.commit()
        return done

    def _fulfill(self, episode_id: str, scene: dict) -> SceneResult:
        existing = self.connection.execute(
            "SELECT state FROM flow_jobs WHERE episode_id = ? AND scene_id = ?",
            (episode_id, scene["scene_id"]),
        ).fetchone()
        if existing and existing[0] in {"SUCCEEDED", "FALLBACK"}:
            path = self.out_dir / f"{scene['scene_id']}.mp4"
            return SceneResult(scene["scene_id"], existing[0], scene["visual_engine"], _frames(float(scene["duration_sec"])), path.as_posix())
        try:
            operation = self.transport.create(scene["scene_id"], scene.get("prompt_mode", "TEXT_TO_VIDEO"), float(scene["duration_sec"]))
        except TimeoutError:
            self._upsert(episode_id, scene["scene_id"], "UNKNOWN_RECONCILE", f"op-{scene['scene_id']}")
            path = self._plate(scene, "hold")
            return SceneResult(scene["scene_id"], "UNKNOWN_RECONCILE", scene["visual_engine"], _frames(float(scene["duration_sec"])), path)
        if int(operation.get("output_tokens", 1)) == 0:
            strikes = self._strike(episode_id, scene["scene_id"])
            if strikes >= 2:
                path = self._plate(scene, "fallback")
                self._upsert(episode_id, scene["scene_id"], "FALLBACK", operation["id"])
                return SceneResult(scene["scene_id"], "FALLBACK", scene.get("fallback_engine", "STILL_2K_PANZOOM"), _frames(float(scene["duration_sec"])), path)
            self._upsert(episode_id, scene["scene_id"], "STRIKE_1", operation["id"])
            path = self._plate(scene, "retry")
            return SceneResult(scene["scene_id"], "STRIKE_1", scene["visual_engine"], _frames(float(scene["duration_sec"])), path)
        self._upsert(episode_id, scene["scene_id"], "SUCCEEDED", operation["id"])
        path = self._plate(scene, "hero")
        return SceneResult(scene["scene_id"], "SUCCEEDED", scene["visual_engine"], _frames(float(scene["duration_sec"])), path)

    def _strike(self, episode_id: str, scene_id: str) -> int:
        row = self.connection.execute(
            "SELECT strikes FROM flow_jobs WHERE episode_id = ? AND scene_id = ?",
            (episode_id, scene_id),
        ).fetchone()
        strikes = 1 if row is None else int(row[0]) + 1
        self.connection.execute(
            "INSERT INTO flow_jobs (episode_id, scene_id, state, strikes, idempotency_key) VALUES (?, ?, 'STRIKE_1', ?, ?) "
            "ON CONFLICT(episode_id, scene_id) DO UPDATE SET strikes = ?, state = 'STRIKE_1'",
            (episode_id, scene_id, strikes, f"{episode_id}:{scene_id}", strikes),
        )
        self.connection.execute(
            "INSERT INTO budget_reservations (episode_id, scene_id, micro_usd, status) VALUES (?, ?, 0, 'RELEASED')",
            (episode_id, scene_id),
        )
        self.connection.commit()
        return strikes

    def _upsert(self, episode_id: str, scene_id: str, state: str, operation_id: str) -> None:
        self.connection.execute(
            "INSERT INTO flow_jobs (episode_id, scene_id, state, provider_operation_id, idempotency_key) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(episode_id, scene_id) DO UPDATE SET state = excluded.state, provider_operation_id = excluded.provider_operation_id",
            (episode_id, scene_id, state, operation_id, f"{episode_id}:{scene_id}"),
        )
        self.connection.commit()

    def _plate(self, scene: dict, label: str) -> str:
        frames = _frames(float(scene["duration_sec"]))
        path = self.out_dir / f"{scene['scene_id']}.mp4"
        color = "0x3A4F66" if label == "fallback" else "0xE9E2D2"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=30:d={frames / 30:.3f}",
                "-frames:v", str(frames), "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                str(path),
            ],
            check=True, capture_output=True,
        )
        return path.as_posix()


def _frames(duration_sec: float) -> int:
    return max(1, int(round(duration_sec * 30)))
