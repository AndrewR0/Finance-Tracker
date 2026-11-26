import { describe, expect, it } from "vitest";

import { MAX_YEARS, YEARS_AFTER_FI, bpToPercent, fiNumber, percentToBp, project, type Plan } from "./retirement";

const PLAN: Plan = {
  balanceCents: 10_000_000, // $100,000
  yearlyContributionCents: 2_000_000, // $20,000
  yearlySpendingCents: 4_000_000, // $40,000
  withdrawalRateBp: 400,
  realReturnBp: 700,
  currentYear: 2026,
  birthYear: 1996,
};

describe("fiNumber", () => {
  it("is spending divided by the withdrawal rate", () => {
    expect(fiNumber(4_000_000, 400)).toBe(100_000_000); // $40k at 4% -> $1M
    expect(fiNumber(4_000_000, 350)).toBe(114_285_714);
  });
});

describe("project", () => {
  it("grows by return plus contributions each year", () => {
    const { points } = project(PLAN);
    expect(points[0]).toEqual({ yearsFromNow: 0, year: 2026, age: 30, balanceCents: 10_000_000 });
    expect(points[1].balanceCents).toBe(12_700_000); // 100k x 1.07 + 20k
    expect(points[2].balanceCents).toBe(15_589_000); // 127k x 1.07 + 20k
  });

  it("finds the first year at or above the FI number", () => {
    const result = project(PLAN);
    const fi = result.fiYearsFromNow as number;
    expect(result.points[fi].balanceCents).toBeGreaterThanOrEqual(result.fiNumberCents);
    expect(result.points[fi - 1].balanceCents).toBeLessThan(result.fiNumberCents);
    expect(fi).toBe(18); // 100k x 1.07^18 + 20k a year ~ $1.02M; year 17 is ~ $933k
    expect(result.points.length).toBe(fi + YEARS_AFTER_FI + 1); // a few years past FI, then stop
  });

  it("already there", () => {
    expect(project({ ...PLAN, balanceCents: 200_000_000 }).fiYearsFromNow).toBe(0);
  });

  it("never gets there within the horizon", () => {
    const result = project({ ...PLAN, yearlyContributionCents: 0, realReturnBp: 0 });
    expect(result.fiYearsFromNow).toBeNull();
    expect(result.points.length).toBe(MAX_YEARS + 1);
  });

  it("shows years from now when there's no birth year", () => {
    expect(project({ ...PLAN, birthYear: null }).points[3].age).toBeNull();
  });
});

describe("percentToBp / bpToPercent", () => {
  it.each([
    ["4", 400],
    ["3.5", 350],
    ["6.25", 625],
    ["7%", 700],
    ["-1", -100],
  ])("%s -> %i", (text, bp) => {
    expect(percentToBp(text)).toBe(bp);
    expect(percentToBp(bpToPercent(bp))).toBe(bp);
  });

  it.each(["", "abc", "4.123", "1.2.3"])("refuses %j", (text) => {
    expect(percentToBp(text)).toBeNull();
  });

  it("formats without trailing zeros", () => {
    expect([bpToPercent(400), bpToPercent(350), bpToPercent(625), bpToPercent(-100)]).toEqual(["4", "3.5", "6.25", "-1"]);
  });
});
