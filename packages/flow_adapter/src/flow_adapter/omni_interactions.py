"""Primary interactions backend. The transport is injected so tests stay offline."""

from __future__ import annotations

from dataclasses import dataclass

from .backend import (
    BudgetCapError,
    MissingProviderCredentialsError,
    ProviderConfig,
    mark_unknown,
    release,
    reserve,
)


@dataclass(frozen=True)
class DispatchResult:
    state: str
    operation_id: str | None
    frames_required: int


class InteractionsBackend:
    def __init__(self, config: ProviderConfig, connection, transport, api_key: str | None) -> None:
        self.config = config
        self.connection = connection
        self.transport = transport
        self.api_key = api_key

    def dispatch(self, episode_id: str, scene_id: str, prompt_mode: str, duration_sec: float) -> DispatchResult:
        if not self.api_key:
            raise MissingProviderCredentialsError("provider credentials are missing")
        mode = self.config.prompt_modes[prompt_mode]
        if not mode["min_sec"] <= duration_sec <= mode["max_sec"]:
            raise ValueError("duration is outside the mode window")
        held_clips = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(micro_usd), 0) FROM budget_reservations WHERE episode_id = ? AND status != 'RELEASED'",
            (episode_id,),
        ).fetchone()
        if int(held_clips[0]) >= self.config.max_hero_clips:
            raise BudgetCapError("hero clip count would be exceeded")
        held_sec = float(held_clips[1]) / 1_000_000 / self.config.usd_per_sec
        if held_sec + duration_sec > self.config.max_hero_duration_sec:
            raise BudgetCapError("hero duration would be exceeded")
        micro = int(round(duration_sec * self.config.usd_per_sec * 1_000_000))
        try:
            reserve(self.connection, episode_id, scene_id, micro, self.config.episode_cap_micro_usd)
        except BudgetCapError:
            raise
        try:
            operation = self.transport.create(scene_id, prompt_mode, duration_sec, self.config.model_id)
        except TimeoutError:
            mark_unknown(self.connection, episode_id, scene_id, f"op-{scene_id}")
            return DispatchResult("UNKNOWN_RECONCILE", f"op-{scene_id}", mode["frames"])
        if operation.get("output_tokens", 1) == 0:
            release(self.connection, episode_id, scene_id)
            return DispatchResult("SAFETY_BLOCK", operation.get("id"), mode["frames"])
        self.connection.execute(
            "UPDATE flow_jobs SET state = 'RUNNING', provider_operation_id = ? WHERE episode_id = ? AND scene_id = ?",
            (operation["id"], episode_id, scene_id),
        )
        self.connection.commit()
        return DispatchResult("RUNNING", operation["id"], mode["frames"])

    def reconcile(self) -> list[str]:
        rows = self.connection.execute(
            "SELECT episode_id, scene_id, provider_operation_id FROM flow_jobs WHERE state = 'UNKNOWN_RECONCILE'"
        ).fetchall()
        done = []
        for episode_id, scene_id, operation_id in rows:
            status = self.transport.poll(operation_id)
            self.connection.execute("UPDATE flow_jobs SET state = ? WHERE episode_id = ? AND scene_id = ?", (status, episode_id, scene_id))
            if status == "FAILED":
                release(self.connection, episode_id, scene_id)
            done.append(scene_id)
        self.connection.commit()
        return done
