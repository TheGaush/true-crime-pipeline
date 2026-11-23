"""Two-strike breaker that refuses a code streak longer than 50 seconds."""

from __future__ import annotations

from dataclasses import dataclass

MAX_ATTEMPTS = 2
MAX_CODE_STREAK_SEC = 50.0
VERBS = {"runs", "grabs", "chases", "stabs", "shoots", "flees", "screams"}


@dataclass
class Neighbor:
    engine: str
    duration_sec: float


@dataclass
class SceneTicket:
    scene_id: str
    prompt: str
    duration_sec: float
    fallback_engine: str = "CODE_STICKMAN"
    attempt_count: int = 0
    status: str = "PENDING"
    alert: str = ""


class CircuitBreaker:
    def __init__(self, escrow_usd: float) -> None:
        self.escrow_usd = escrow_usd

    def fail(self, scene: SceneTicket, previous: Neighbor | None, nxt: Neighbor | None) -> str:
        if scene.status == "fallback_triggered" or scene.attempt_count >= MAX_ATTEMPTS:
            scene.status = "fallback_triggered"
            return scene.status
        if self.escrow_usd <= 0:
            return self._fallback(scene, previous, nxt)
        scene.attempt_count += 1
        if scene.attempt_count == 1:
            scene.prompt = simplify(scene.prompt)
            self.escrow_usd = max(0.0, self.escrow_usd - 0.4)
            scene.status = "RETRY"
            scene.alert = "Strike 1: Simplified motion prompt loaded"
            return scene.status
        return self._fallback(scene, previous, nxt)

    def _fallback(self, scene: SceneTicket, previous: Neighbor | None, nxt: Neighbor | None) -> str:
        engine = scene.fallback_engine
        if engine == "CODE_STICKMAN" and _streak(scene, previous, nxt) > MAX_CODE_STREAK_SEC:
            engine = "STILL_2K_PANZOOM"
        scene.fallback_engine = engine
        scene.attempt_count = min(MAX_ATTEMPTS, max(scene.attempt_count, 1))
        scene.status = "fallback_triggered"
        return scene.status


def simplify(prompt: str) -> str:
    words = [word for word in prompt.replace(",", " ").split() if word.lower() not in VERBS]
    return " ".join(words[:10]) or "neutral documentary motion"


def _streak(scene: SceneTicket, previous: Neighbor | None, nxt: Neighbor | None) -> float:
    total = scene.duration_sec
    if previous and previous.engine == "CODE_STICKMAN":
        total += previous.duration_sec
    if nxt and nxt.engine == "CODE_STICKMAN":
        total += nxt.duration_sec
    return total
