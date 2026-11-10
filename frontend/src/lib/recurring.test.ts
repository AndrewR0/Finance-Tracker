import { describe, expect, it } from "vitest";

import { daysBetween, dueLabel, formatCharge } from "./recurring";

describe("daysBetween", () => {
  it("counts across a month end", () => {
    expect(daysBetween("2026-10-30", "2026-11-02")).toBe(3);
  });

  it("is not thrown off by daylight saving (Nov 1, 2026 in the US)", () => {
    expect(daysBetween("2026-10-31", "2026-11-01")).toBe(1);
  });
});

describe("dueLabel", () => {
  it.each([
    ["2026-11-09", "Today"],
    ["2026-11-10", "Tomorrow"],
    ["2026-11-15", "In 6 days"],
    ["2026-11-08", "Due yesterday"],
    ["2026-11-06", "Due 3 days ago"],
  ])("%s -> %s", (day, label) => {
    expect(dueLabel("2026-11-09", day)).toBe(label);
  });
});

describe("formatCharge", () => {
  it("marks an estimate", () => {
    expect(formatCharge(5090, true)).toBe("~$50.90");
    expect(formatCharge(1377, false)).toBe("$13.77");
  });
});
