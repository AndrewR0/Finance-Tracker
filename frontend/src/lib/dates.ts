// The API sends dates as "2026-10-22" strings, with no time and no timezone.
// new Date("2026-10-22") would read that as midnight UTC, which is the evening of Oct 21
// in US timezones. So these helpers split the string instead.

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function parts(iso: string): [number, number, number] {
  const [year, month, day] = iso.split("-").map(Number);
  return [year, month, day];
}

/** A local Date for "2026-10-22" (midnight in your timezone). */
export function parseDate(iso: string): Date {
  const [year, month, day] = parts(iso);
  return new Date(year, month - 1, day);
}

export function toISODate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function todayISO(): string {
  return toISODate(new Date());
}

/** "2026-10-22" -> "Wed, Oct 22" */
export function formatDayHeader(iso: string): string {
  const [, month, day] = parts(iso);
  return `${WEEKDAYS[parseDate(iso).getDay()]}, ${MONTHS[month - 1]} ${day}`;
}

/** "2026-10-22" -> "Oct 22" */
export function formatShortDate(iso: string): string {
  const [, month, day] = parts(iso);
  return `${MONTHS[month - 1]} ${day}`;
}

/** "2026-10" (a cash-flow month) -> "Oct" */
export function monthLabel(yearMonth: string): string {
  return MONTHS[Number(yearMonth.split("-")[1]) - 1];
}

/** "2026-10-22" -> "October" */
export function monthName(iso: string): string {
  return MONTHS_LONG[parts(iso)[1] - 1];
}

/** "Oct 1–23", "Sep 28 – Oct 3", or "Dec 30, 2025 – Jan 2, 2026". */
export function formatRange(start: string, end: string): string {
  const [y1, m1, d1] = parts(start);
  const [y2, m2, d2] = parts(end);
  if (y1 !== y2) return `${MONTHS[m1 - 1]} ${d1}, ${y1} – ${MONTHS[m2 - 1]} ${d2}, ${y2}`;
  if (m1 !== m2) return `${MONTHS[m1 - 1]} ${d1} – ${MONTHS[m2 - 1]} ${d2}`;
  if (d1 !== d2) return `${MONTHS[m1 - 1]} ${d1}–${d2}`;
  return `${MONTHS[m1 - 1]} ${d1}`;
}

/** "2026-10" -> first and last day of that month, for list filters. */
export function monthBounds(yearMonth: string): { start: string; end: string } {
  const [year, month] = yearMonth.split("-").map(Number);
  const lastDay = new Date(year, month, 0).getDate(); // day 0 of the next month = last day of this one
  return { start: `${yearMonth}-01`, end: `${yearMonth}-${String(lastDay).padStart(2, "0")}` };
}

type PeriodLike = { kind: "month" | "year" | "all"; start: string; compare_start?: string | null };

/** The page title: "October 2026", "2026", or "All time". */
export function periodTitle(period: PeriodLike): string {
  const [year] = parts(period.start);
  if (period.kind === "month") return `${monthName(period.start)} ${year}`;
  if (period.kind === "year") return String(year);
  return "All time";
}

/** What the period is compared with: "September", "2025", or null for all time. */
export function comparisonName(period: PeriodLike): string | null {
  if (!period.compare_start) return null;
  return period.kind === "month" ? monthName(period.compare_start) : String(parts(period.compare_start)[0]);
}
