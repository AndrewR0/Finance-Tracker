import { describe, expect, it } from "vitest";

import { formatWhen, parseWhen, whenOfPeriod, whenRange } from "./when";

const TODAY = "2026-10-23";

describe("parseWhen", () => {
  it("defaults to this month", () => {
    expect(parseWhen(null, TODAY)).toEqual({ mode: "month", month: "2026-10", start: "2026-10-01", end: "2026-10-31" });
  });

  it("reads a month, a year, all and a range", () => {
    expect(parseWhen("2026-02", TODAY)).toMatchObject({ mode: "month", start: "2026-02-01", end: "2026-02-28" });
    expect(parseWhen("2025", TODAY)).toMatchObject({ mode: "year", start: "2025-01-01", end: "2025-12-31" });
    expect(parseWhen("all", TODAY)).toEqual({ mode: "all" });
    expect(parseWhen("2026-10-01..2026-10-15", TODAY)).toEqual({ mode: "range", start: "2026-10-01", end: "2026-10-15" });
  });

  it("puts a backwards range in order", () => {
    expect(parseWhen("2026-10-15..2026-10-01", TODAY)).toEqual({ mode: "range", start: "2026-10-01", end: "2026-10-15" });
  });

  it("falls back to this month for anything else", () => {
    for (const junk of ["", "2026-13", "yesterday", "2026-10-01..", "2026-10-01..soon"]) {
      expect(parseWhen(junk, TODAY)).toMatchObject({ mode: "month", month: "2026-10" });
    }
  });

  it("round-trips through formatWhen", () => {
    for (const value of ["2026-02", "2025", "all", "2026-10-01..2026-10-15"]) {
      expect(formatWhen(parseWhen(value, TODAY))).toBe(value);
    }
  });
});

describe("whenRange", () => {
  it("is empty for all dates", () => {
    expect(whenRange({ mode: "all" })).toEqual({});
    expect(whenRange(parseWhen("2025", TODAY))).toEqual({ start: "2025-01-01", end: "2025-12-31" });
  });
});

describe("whenOfPeriod", () => {
  it("covers the whole month or year", () => {
    expect(whenOfPeriod({ kind: "month", start: "2026-10-01" })).toBe("2026-10");
    expect(whenOfPeriod({ kind: "year", start: "2026-01-01" })).toBe("2026");
    expect(whenOfPeriod({ kind: "all", start: "2024-03-02" })).toBe("all");
  });
});
