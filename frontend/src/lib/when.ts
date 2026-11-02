// The Transactions page's date filter, stored in the URL as one "when" value so a link
// can open the page already filtered (the dashboard's click-throughs do this).
//
//   "2026-10"                 a month
//   "2026"                    a year
//   "all"                     every date
//   "2026-10-01..2026-10-15"  a custom range
//   missing                   this month (the page's default)

import { monthBounds } from "./dates";

export type When =
  | { mode: "month"; month: string; start: string; end: string }
  | { mode: "year"; year: string; start: string; end: string }
  | { mode: "all" }
  | { mode: "range"; start: string; end: string };

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/** Read a "when" value. Anything unreadable falls back to the month of `today`. */
export function parseWhen(value: string | null, today: string): When {
  if (value === "all") return { mode: "all" };
  if (value && /^\d{4}$/.test(value)) return { mode: "year", year: value, start: `${value}-01-01`, end: `${value}-12-31` };
  if (value && /^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return { mode: "month", month: value, ...monthBounds(value) };
  if (value) {
    const [start, end] = value.split("..");
    if (ISO.test(start ?? "") && ISO.test(end ?? "")) {
      return start <= end ? { mode: "range", start, end } : { mode: "range", start: end, end: start };
    }
  }
  const month = today.slice(0, 7);
  return { mode: "month", month, ...monthBounds(month) };
}

/** The opposite of parseWhen. */
export function formatWhen(when: When): string {
  switch (when.mode) {
    case "month":
      return when.month;
    case "year":
      return when.year;
    case "all":
      return "all";
    case "range":
      return `${when.start}..${when.end}`;
  }
}

/** The dates to ask the API for. All dates = no filter. */
export function whenRange(when: When): { start?: string; end?: string } {
  return when.mode === "all" ? {} : { start: when.start, end: when.end };
}

/** A dashboard period as a "when": the whole month or year it belongs to. */
export function whenOfPeriod(period: { kind: "month" | "year" | "all"; start: string }): string {
  if (period.kind === "month") return period.start.slice(0, 7);
  if (period.kind === "year") return period.start.slice(0, 4);
  return "all";
}
