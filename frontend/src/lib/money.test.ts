import { describe, expect, it } from "vitest";

import { centsToInput, formatMoney, formatMoney0, formatMoneyShort, niceTicks, parseMoney } from "./money";

describe("formatMoney", () => {
  it.each([
    [123456, "$1,234.56"],
    [-8412, "−$84.12"],
    [5, "$0.05"],
    [0, "$0.00"],
    [100000000, "$1,000,000.00"],
  ])("%i -> %s", (cents, text) => {
    expect(formatMoney(cents)).toBe(text);
  });

  it("adds a + only when asked", () => {
    expect(formatMoney(270000, { sign: true })).toBe("+$2,700.00");
    expect(formatMoney(0, { sign: true })).toBe("$0.00");
  });
});

describe("formatMoney0", () => {
  it("rounds to whole dollars", () => {
    expect(formatMoney0(4821049)).toBe("$48,210");
    expect(formatMoney0(150)).toBe("$2");
    expect(formatMoney0(-182040)).toBe("−$1,820");
  });

  it("never shows minus zero", () => {
    expect(formatMoney0(-40)).toBe("$0");
  });
});

describe("formatMoneyShort", () => {
  it.each([
    [0, "$0"],
    [80000, "$800"],
    [100000, "$1k"],
    [150000, "$1.5k"],
    [2500000, "$25k"],
    [-150000, "−$1.5k"],
  ])("%i -> %s", (cents, text) => {
    expect(formatMoneyShort(cents)).toBe(text);
  });
});

describe("niceTicks", () => {
  it.each([
    [249100, [0, 100000, 200000, 300000]], // $2,491 -> $0 $1k $2k $3k
    [1500000, [0, 500000, 1000000, 1500000]], // exactly on a step: no extra tick
    [1620000, [0, 500000, 1000000, 1500000, 2000000]],
    [9000, [0, 2500, 5000, 7500, 10000]], // $90 -> steps of $25
    [0, [0, 100]], // nothing yet: still a usable axis
  ])("%i -> %j", (max, ticks) => {
    expect(niceTicks(max)).toEqual(ticks);
  });
});

describe("centsToInput", () => {
  it("drops the sign and formatting", () => {
    expect(centsToInput(-8412)).toBe("84.12");
    expect(centsToInput(123400)).toBe("1234.00");
    expect(centsToInput(5)).toBe("0.05");
  });
});

describe("parseMoney", () => {
  it.each([
    ["84.12", 8412],
    ["$1,234.5", 123450],
    ["12", 1200],
    [".5", 50],
    ["-5", -500],
    ["−5.25", -525],
    [" 7.00 ", 700],
    ["0", 0],
  ])("%s -> %i", (text, cents) => {
    expect(parseMoney(text)).toBe(cents);
  });

  it.each(["", "-", ".", "abc", "1.234", "1.2.3", "12a"])("%j is not an amount", (text) => {
    expect(parseMoney(text)).toBeNull();
  });

  it("round-trips with centsToInput", () => {
    for (const cents of [1, 99, 100, 8412, 123456]) {
      expect(parseMoney(centsToInput(cents))).toBe(cents);
    }
  });
});
