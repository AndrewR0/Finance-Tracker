// Retirement math: the FI number and a year-by-year projection, in today's dollars.
//
// Everything here is "what if": it runs in the browser on every keystroke and is never stored,
// so plain numbers are fine. Results are rounded to whole cents before they leave this file.

export type Plan = {
  balanceCents: number; // invested today
  yearlyContributionCents: number; // added every year
  yearlySpendingCents: number; // what retirement has to pay for, per year
  withdrawalRateBp: number; // 400 = 4.00%
  realReturnBp: number; // yearly growth after inflation; 700 = 7.00%
  currentYear: number;
  birthYear: number | null;
};

export type YearPoint = {
  yearsFromNow: number;
  year: number;
  age: number | null;
  balanceCents: number;
};

export type Projection = {
  fiNumberCents: number;
  points: YearPoint[];
  fiYearsFromNow: number | null; // null: not within MAX_YEARS
};

/** Years the projection looks ahead before giving up. */
export const MAX_YEARS = 60;
/** Years of chart shown after reaching FI, so the line doesn't just stop at the target. */
export const YEARS_AFTER_FI = 5;

/**
 * The FI ("financial independence") number: the balance whose withdrawal rate covers a year of
 * spending. $40,000 a year at 4% -> $1,000,000. (The "4% rule": withdraw 4% of the starting
 * balance each year, adjusted for inflation, and historically it lasted 30+ years.)
 */
export function fiNumber(yearlySpendingCents: number, withdrawalRateBp: number): number {
  if (withdrawalRateBp <= 0) return Infinity;
  return Math.round((yearlySpendingCents * 10000) / withdrawalRateBp);
}

/**
 * Grow the balance one year at a time: balance x (1 + return) + contribution. Contributions land
 * at the end of each year (a slightly cautious simplification).
 */
export function project(plan: Plan): Projection {
  const target = fiNumber(plan.yearlySpendingCents, plan.withdrawalRateBp);
  const growth = 1 + plan.realReturnBp / 10000;
  const point = (yearsFromNow: number, balance: number): YearPoint => ({
    yearsFromNow,
    year: plan.currentYear + yearsFromNow,
    age: plan.birthYear === null ? null : plan.currentYear + yearsFromNow - plan.birthYear,
    balanceCents: Math.round(balance),
  });

  let balance = plan.balanceCents;
  const points = [point(0, balance)];
  let fiYearsFromNow: number | null = balance >= target ? 0 : null;
  for (let years = 1; years <= MAX_YEARS; years++) {
    if (fiYearsFromNow !== null && years > fiYearsFromNow + YEARS_AFTER_FI) break;
    balance = balance * growth + plan.yearlyContributionCents;
    points.push(point(years, balance));
    if (fiYearsFromNow === null && balance >= target) fiYearsFromNow = years;
  }
  return { fiNumberCents: target, points, fiYearsFromNow };
}

/**
 * A percent as typed -> basis points, or null: "4" -> 400, "3.5" -> 350, "6.25" -> 625, "-1" -> -100.
 * At most 2 decimals, so it maps exactly onto whole basis points.
 */
export function percentToBp(text: string): number | null {
  const match = /^\s*(-)?(\d{1,3})(?:\.(\d{1,2}))?\s*%?\s*$/.exec(text);
  if (!match) return null;
  const [, minus, whole, fraction = ""] = match;
  const bp = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return minus ? -bp : bp;
}

/** Basis points as an editable percent: 400 -> "4", 350 -> "3.5", 625 -> "6.25". */
export function bpToPercent(bp: number): string {
  const sign = bp < 0 ? "-" : "";
  const abs = Math.abs(bp);
  const fraction = String(abs % 100).padStart(2, "0").replace(/0+$/, "");
  return `${sign}${Math.floor(abs / 100)}${fraction ? `.${fraction}` : ""}`;
}
