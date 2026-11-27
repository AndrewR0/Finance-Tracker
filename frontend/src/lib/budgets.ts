// Budget status: where spending is against the budget and against the calendar.

export type BudgetStatus = "under" | "ahead" | "over";

/**
 * "over": spent more than the whole budget.
 * "ahead": spending faster than the month is passing (on day 10 of 30, more than a third spent).
 * "under": everything else.
 */
export function budgetStatus(spentCents: number, budgetCents: number, daysElapsed: number, daysInMonth: number): BudgetStatus {
  if (spentCents > budgetCents) return "over";
  if (daysElapsed < daysInMonth && spentCents * daysInMonth > budgetCents * daysElapsed) return "ahead";
  return "under";
}

/** Share of the budget spent, 0 to 100 (capped, for a bar). */
export function barPercent(spentCents: number, budgetCents: number): number {
  if (budgetCents <= 0) return 0;
  return Math.max(0, Math.min(100, (spentCents / budgetCents) * 100));
}

/** Where today falls in the month, 0 to 100, for the "on pace" tick. */
export function pacePercent(daysElapsed: number, daysInMonth: number): number {
  return daysInMonth <= 0 ? 0 : Math.min(100, (daysElapsed / daysInMonth) * 100);
}

/** "2026-11-01" -> "2026-12-01" (n = 1) or "2026-10-01" (n = -1). */
export function shiftMonth(firstOfMonth: string, n: number): string {
  const [year, month] = firstOfMonth.split("-").map(Number);
  const index = year * 12 + (month - 1) + n;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}-01`;
}
