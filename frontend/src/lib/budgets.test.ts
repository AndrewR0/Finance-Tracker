import { describe, expect, it } from "vitest";

import { barPercent, budgetStatus, pacePercent, shiftMonth } from "./budgets";

describe("budgetStatus", () => {
  it("is over once spending passes the budget", () => {
    expect(budgetStatus(50001, 50000, 10, 30)).toBe("over");
  });

  it("is ahead when spending outruns the calendar", () => {
    expect(budgetStatus(20000, 50000, 10, 30)).toBe("ahead"); // 40% spent, a third of the month gone
    expect(budgetStatus(15000, 50000, 10, 30)).toBe("under"); // 30% spent
  });

  it("at month end, anything up to the budget is fine", () => {
    expect(budgetStatus(50000, 50000, 30, 30)).toBe("under");
  });

  it("a month that hasn't started is ahead with any spending", () => {
    expect(budgetStatus(100, 50000, 0, 30)).toBe("ahead");
    expect(budgetStatus(0, 50000, 0, 30)).toBe("under");
  });
});

describe("bars", () => {
  it("caps the bar between 0 and 100", () => {
    expect(barPercent(25000, 50000)).toBe(50);
    expect(barPercent(90000, 50000)).toBe(100);
    expect(barPercent(-100, 50000)).toBe(0);
    expect(pacePercent(15, 30)).toBe(50);
  });
});

describe("shiftMonth", () => {
  it("moves across year ends", () => {
    expect(shiftMonth("2026-12-01", 1)).toBe("2027-01-01");
    expect(shiftMonth("2026-01-01", -1)).toBe("2025-12-01");
    expect(shiftMonth("2026-11-01", -1)).toBe("2026-10-01");
  });
});
