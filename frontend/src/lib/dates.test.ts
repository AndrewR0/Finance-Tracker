import { describe, expect, it } from "vitest";

import {
  comparisonName,
  formatDayHeader,
  formatRange,
  formatShortDate,
  monthBounds,
  parseDate,
  periodTitle,
  toISODate,
} from "./dates";

describe("parsing and printing", () => {
  it("reads a date as local midnight, not UTC", () => {
    const date = parseDate("2026-10-22");
    expect([date.getFullYear(), date.getMonth(), date.getDate()]).toEqual([2026, 9, 22]);
  });

  it("round-trips", () => {
    expect(toISODate(parseDate("2026-01-05"))).toBe("2026-01-05");
  });

  it("formats day headers and short dates", () => {
    expect(formatDayHeader("2026-10-22")).toBe("Thu, Oct 22");
    expect(formatShortDate("2026-03-01")).toBe("Mar 1");
  });
});

describe("formatRange", () => {
  it.each([
    ["2026-10-01", "2026-10-23", "Oct 1–23"],
    ["2026-09-28", "2026-10-03", "Sep 28 – Oct 3"],
    ["2025-12-30", "2026-01-02", "Dec 30, 2025 – Jan 2, 2026"],
    ["2026-10-05", "2026-10-05", "Oct 5"],
  ])("%s to %s -> %s", (start, end, text) => {
    expect(formatRange(start, end)).toBe(text);
  });
});

describe("monthBounds", () => {
  it.each([
    ["2026-10", "2026-10-31"],
    ["2026-02", "2026-02-28"],
    ["2028-02", "2028-02-29"],
    ["2026-04", "2026-04-30"],
  ])("%s ends on %s", (month, end) => {
    expect(monthBounds(month)).toEqual({ start: `${month}-01`, end });
  });
});

describe("period names", () => {
  const october = { kind: "month", start: "2026-10-01", compare_start: "2026-09-01" } as const;
  const year = { kind: "year", start: "2026-01-01", compare_start: "2025-01-01" } as const;
  const all = { kind: "all", start: "2025-01-04", compare_start: null } as const;

  it("titles", () => {
    expect(periodTitle(october)).toBe("October 2026");
    expect(periodTitle(year)).toBe("2026");
    expect(periodTitle(all)).toBe("All time");
  });

  it("comparison names", () => {
    expect(comparisonName(october)).toBe("September");
    expect(comparisonName(year)).toBe("2025");
    expect(comparisonName(all)).toBeNull();
  });
});
