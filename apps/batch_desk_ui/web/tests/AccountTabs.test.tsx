import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccountTabs } from "../src/components/AccountTabs";
import { DAILY_LOCK_MS, useCountdownLock } from "../src/components/useCountdownLock";

describe("account lock", () => {
  it("locks only the account that has spent inside the window", () => {
    const now = 1_000_000;
    render(
      React.createElement(AccountTabs, {
        serverNowMs: now,
        accounts: [
          { accountId: "account-1", firstSpendMs: now - 1_000 },
          { accountId: "account-2", firstSpendMs: null },
        ],
      }),
    );
    expect(screen.getByRole("tab", { name: "account-1 locked" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("tab", { name: "account-2" }).hasAttribute("disabled")).toBe(false);
    expect(useCountdownLock(now - 1_000, now).remainingMs).toBe(DAILY_LOCK_MS - 1_000);
    expect(useCountdownLock(now - DAILY_LOCK_MS, now).locked).toBe(false);
  });
});
