import { describe, expect, it } from "vitest";

import { formatPrice, formatShares, gainPercent, parseDecimal } from "./shares";

describe("formatShares", () => {
  it.each([
    [3841207, "0.03841207"],
    [30050000000, "300.5"],
    [100000000, "1"],
    [123456700000000, "1,234,567"],
  ])("%i -> %s", (units, text) => {
    expect(formatShares(units)).toBe(text);
  });
});

describe("formatPrice", () => {
  it.each([
    [123456700, "$123.4567"],
    [1000000, "$1.00"],
    [91234500000, "$91,234.50"],
    [0, "$0.00"],
    [142794415, "$142.7944"],
    [142794450, "$142.7945"],
  ])("%i -> %s", (units, text) => {
    expect(formatPrice(units)).toBe(text);
  });
});

describe("parseDecimal", () => {
  it.each([
    ["1,234.5", "1234.5"],
    [".5", "0.5"],
    ["0.03841207", "0.03841207"],
    ["007.10", "7.1"],
    ["$130.50", "130.5"],
  ])("%s -> %s", (text, parsed) => {
    expect(parseDecimal(text, 8)).toBe(parsed);
  });

  it.each(["", ".", "0", "0.000", "-1", "1.2.3", "abc", "0.123456789"])("refuses %j", (text) => {
    expect(parseDecimal(text, 8)).toBeNull();
  });
});

describe("gainPercent", () => {
  it("rounds to one decimal with a sign", () => {
    expect(gainPercent(150, 1000)).toBe("+15.0%");
    expect(gainPercent(-150000, 500000)).toBe("−30.0%");
    expect(gainPercent(0, 1000)).toBe("0.0%");
    expect(gainPercent(5, 0)).toBeNull();
  });
});
