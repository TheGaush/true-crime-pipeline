import React from "react";
import { DAILY_LOCK_MS } from "./useCountdownLock";

export type DeskAccount = { accountId: string; firstSpendMs: number | null };

export function AccountTabs({
  accounts,
  serverNowMs,
}: {
  accounts: DeskAccount[];
  serverNowMs: number;
}) {
  return React.createElement(
    "div",
    { role: "tablist" },
    ...accounts.map((account) => {
      const remainingMs =
        account.firstSpendMs == null
          ? 0
          : Math.max(0, DAILY_LOCK_MS - (serverNowMs - account.firstSpendMs));
      const lock = { locked: remainingMs > 0, remainingMs };
      return React.createElement(
        "button",
        {
          key: account.accountId,
          role: "tab",
          disabled: lock.locked,
          "data-remaining": String(lock.remainingMs),
        },
        lock.locked ? `${account.accountId} locked` : account.accountId,
      );
    }),
  );
}
