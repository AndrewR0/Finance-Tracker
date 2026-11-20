import type { Goal } from "../api/client";
import { monthLabel } from "./dates";
import { formatMoney0 } from "./money";

/** How full the bar is, 0-100. Rounded down, so 99.6% doesn't show "100%" before it's done. */
export function percentOf(savedCents: number, targetCents: number): number {
  if (targetCents <= 0) return 0;
  return Math.max(0, Math.min(100, Math.floor((savedCents * 100) / targetCents)));
}

/** "2027-01-31" -> "Jan 2027" */
export function monthYear(iso: string): string {
  return `${monthLabel(iso.slice(0, 7))} ${iso.slice(0, 4)}`;
}

type Line = { text: string; tone: "good" | "bad" | "" };

/** The small line under a goal's bar: how it's going, in words. */
export function goalLine(goal: Goal): Line {
  const pct = `${percentOf(goal.saved_cents, goal.target_cents)}%`;
  const by = goal.target_date ? ` · by ${monthYear(goal.target_date)}` : "";
  switch (goal.status) {
    case "done":
      return { text: `Fully funded${by}`, tone: "good" };
    case "on_track":
      return { text: `${pct}${by} · on track${goal.eta ? `, around ${monthYear(goal.eta)}` : ""}`, tone: "good" };
    case "behind":
      return {
        text: `${pct}${by} · needs ${formatMoney0(goal.needed_per_month_cents ?? 0)}/mo`,
        tone: "bad",
      };
    case "no_date":
      return {
        text: goal.eta ? `${pct} · around ${monthYear(goal.eta)} at this pace` : `${pct} · no new savings lately`,
        tone: "",
      };
  }
}

/**
 * The new fill order after moving one goal up (-1) or down (+1) past its neighbour
 * on the same account. Goals on other accounts don't compete for money, so they're skipped.
 * Returns every id (the server wants them all), or null if the goal can't move that way.
 */
export function moveGoal(goals: Pick<Goal, "id" | "account_id">[], id: number, direction: -1 | 1): number[] | null {
  const ids = goals.map((g) => g.id);
  const from = ids.indexOf(id);
  if (from === -1) return null;
  const account = goals[from].account_id;
  let to = from + direction;
  while (to >= 0 && to < goals.length && goals[to].account_id !== account) to += direction;
  if (to < 0 || to >= goals.length) return null;
  [ids[from], ids[to]] = [ids[to], ids[from]];
  return ids;
}
