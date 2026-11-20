import { describe, expect, it } from "vitest";

import type { Goal } from "../api/client";
import { goalLine, monthYear, moveGoal, percentOf } from "./goals";

function goal(overrides: Partial<Goal>): Goal {
  return {
    id: 1,
    name: "Laptop",
    account_id: 1,
    target_cents: 200_000,
    target_date: "2027-01-31",
    position: 1,
    archived_at: null,
    created_at: "2026-10-01T00:00:00",
    saved_cents: 115_000,
    status: "on_track",
    eta: "2026-12-20",
    needed_per_month_cents: 28_334,
    account_pace_cents: 50_000,
    ...overrides,
  };
}

describe("percentOf", () => {
  it("rounds down and stays within 0-100", () => {
    expect(percentOf(115_000, 200_000)).toBe(57);
    expect(percentOf(199_999, 200_000)).toBe(99);
    expect(percentOf(300_000, 200_000)).toBe(100);
    expect(percentOf(-5, 200_000)).toBe(0);
    expect(percentOf(5, 0)).toBe(0);
  });
});

describe("monthYear", () => {
  it("formats a date", () => {
    expect(monthYear("2027-01-31")).toBe("Jan 2027");
  });
});

describe("goalLine", () => {
  it("describes each status", () => {
    expect(goalLine(goal({}))).toEqual({ text: "57% · by Jan 2027 · on track, around Dec 2026", tone: "good" });
    expect(goalLine(goal({ status: "behind" })).text).toBe("57% · by Jan 2027 · needs $283/mo");
    expect(goalLine(goal({ status: "done", saved_cents: 200_000 })).text).toBe("Fully funded · by Jan 2027");
    expect(goalLine(goal({ status: "no_date", target_date: null })).text).toBe("57% · around Dec 2026 at this pace");
    expect(goalLine(goal({ status: "no_date", target_date: null, eta: null })).text).toBe("57% · no new savings lately");
  });
});

describe("moveGoal", () => {
  const goals = [
    { id: 1, account_id: 1 },
    { id: 2, account_id: 2 },
    { id: 3, account_id: 1 },
  ];

  it("swaps with the next goal on the same account, skipping others", () => {
    expect(moveGoal(goals, 1, 1)).toEqual([3, 2, 1]);
    expect(moveGoal(goals, 3, -1)).toEqual([3, 2, 1]);
  });

  it("returns null at either end", () => {
    expect(moveGoal(goals, 1, -1)).toBeNull();
    expect(moveGoal(goals, 2, 1)).toBeNull();
    expect(moveGoal(goals, 99, 1)).toBeNull();
  });
});
