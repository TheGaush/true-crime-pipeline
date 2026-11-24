export const DAILY_LOCK_MS = 86_700_000;

export function useCountdownLock(firstSpendMs: number | null, serverNowMs: number) {
  if (firstSpendMs == null) return { locked: false, remainingMs: 0 };
  const remainingMs = Math.max(0, DAILY_LOCK_MS - (serverNowMs - firstSpendMs));
  return { locked: remainingMs > 0, remainingMs };
}
