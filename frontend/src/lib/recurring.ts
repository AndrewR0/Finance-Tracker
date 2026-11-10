import type { Cadence } from "../api/client";
import { parseDate } from "./dates";
import { formatMoney } from "./money";

export const CADENCE_LABELS: Record<Cadence, string> = {
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  monthly: "Monthly",
  quarterly: "Every 3 months",
  yearly: "Yearly",
};

/** Whole days from `today` to `day` (both "YYYY-MM-DD"). Negative when `day` has passed. */
export function daysBetween(today: string, day: string): number {
  // Math.round, not floor: a daylight-saving change makes one "day" 23 or 25 hours long.
  return Math.round((parseDate(day).getTime() - parseDate(today).getTime()) / 86_400_000);
}

/** "Today", "Tomorrow", "In 6 days", or "Due 2 days ago" for a charge that hasn't posted yet. */
export function dueLabel(today: string, day: string): string {
  const days = daysBetween(today, day);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days > 1) return `In ${days} days`;
  return days === -1 ? "Due yesterday" : `Due ${-days} days ago`;
}

/** "$50.90", or "~$50.90" when the bill changes from month to month. */
export function formatCharge(cents: number, varies: boolean): string {
  return (varies ? "~" : "") + formatMoney(cents);
}
