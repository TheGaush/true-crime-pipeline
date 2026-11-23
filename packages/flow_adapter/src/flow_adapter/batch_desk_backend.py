"""Optional human batch desk: rolling lock, three-slot queue, sunk-cost stop.

Credits stay reserved until a clip or a safety failure is confirmed.
Each account keeps its own reset clock.
"""

from __future__ import annotations

from dataclasses import dataclass

DAILY_LOCK_MS = 86_400_000 + 300_000
TOS_NOTICE = (
    "human_batch_desk rotates consumer accounts and may conflict with the consumer terms; "
    "a billed API account is the commercial path"
)


class AccountLockedError(RuntimeError):
    pass


@dataclass
class Account:
    account_id: str
    first_spend_ms: int | None = None
    reserved_credits: int = 0
    committed_credits: int = 0


@dataclass(frozen=True)
class EpisodeCard:
    episode_id: str
    created_ms: int
    status: str = "AWAITING_FLOW_BATCH"


def tos_notice(adapter: str) -> str | None:
    if adapter == "human_batch_desk":
        return TOS_NOTICE
    return None


def next_reset_ms(first_spend_ms: int) -> int:
    return first_spend_ms + DAILY_LOCK_MS


def checkout(account: Account, now_ms: int) -> str:
    if account.first_spend_ms is not None and now_ms < next_reset_ms(account.first_spend_ms):
        raise AccountLockedError(account.account_id)
    return account.account_id


def reserve_credit(account: Account, now_ms: int) -> None:
    checkout(account, now_ms)
    if account.first_spend_ms is None:
        account.first_spend_ms = now_ms
    account.reserved_credits += 1


def commit_credit(account: Account) -> None:
    if account.reserved_credits < 1:
        raise RuntimeError("nothing is reserved")
    account.reserved_credits -= 1
    account.committed_credits += 1


def refund_credit(account: Account) -> None:
    if account.reserved_credits < 1:
        raise RuntimeError("nothing is reserved")
    account.reserved_credits -= 1


def next_slots(cards: list[EpisodeCard], limit: int = 3) -> list[EpisodeCard]:
    waiting = [card for card in cards if card.status == "AWAITING_FLOW_BATCH"]
    return sorted(waiting, key=lambda card: (card.created_ms, card.episode_id))[:limit]


def saturation_decision(spent_fraction: float, wave: int) -> str:
    if wave > 3 and spent_fraction < 0.5:
        return "ABORT"
    if spent_fraction > 0.5 and wave <= 5:
        return "FINISH"
    return "CONTINUE"
