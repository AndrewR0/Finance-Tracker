import { describe, expect, it } from "vitest";

import {
  EMPTY_MAPPING,
  guessMapping,
  parseCsv,
  parseCsvAmount,
  parseCsvDate,
  splitCategory,
  toImportRows,
  type Mapping,
} from "./csv";

describe("parseCsv", () => {
  it("splits rows and cells", () => {
    expect(parseCsv("a,b\n1,2\n")).toEqual([["a", "b"], ["1", "2"]]);
  });

  it("handles quotes, commas and line breaks inside them", () => {
    expect(parseCsv('"Smith, John","say ""hi""","two\nlines"')).toEqual([["Smith, John", 'say "hi"', "two\nlines"]]);
  });

  it("handles Windows line endings, a BOM and blank lines", () => {
    expect(parseCsv("﻿a,b\r\n\r\n1,2\r\n")).toEqual([["a", "b"], ["1", "2"]]);
  });

  it("keeps empty cells", () => {
    expect(parseCsv("1,,3")).toEqual([["1", "", "3"]]);
  });

  it("reads a last line with no line ending", () => {
    expect(parseCsv("a\nb")).toEqual([["a"], ["b"]]);
  });
});

describe("guessMapping", () => {
  it("finds a single amount column", () => {
    expect(guessMapping(["Transaction Date", "Description", "Amount", "Memo"])).toMatchObject({
      date: 0, payee: 1, amount: 2, notes: 3, debit: null, credit: null,
    });
  });

  it("finds debit and credit columns", () => {
    expect(guessMapping(["Date", "Payee", "Debit", "Credit"])).toMatchObject({ date: 0, payee: 1, amount: null, debit: 2, credit: 3 });
  });

  it("prefers the transaction date over the posting date when both exist", () => {
    expect(guessMapping(["Transaction Date", "Post Date", "Description", "Amount"]).date).toBe(0);
  });

  it("leaves unknown columns unmapped", () => {
    expect(guessMapping(["When", "What"])).toMatchObject({ date: null, payee: null, amount: null });
  });
});

describe("guessMapping for your own spreadsheet", () => {
  it("finds account, category and subcategory", () => {
    expect(guessMapping(["Date", "Account", "Category", "Subcategory", "Payee", "Amount", "Notes"])).toMatchObject({
      date: 0, account: 1, category: 2, subcategory: 3, payee: 4, amount: 5, notes: 6,
    });
  });
});

describe("splitCategory", () => {
  it.each([
    ["Food > Coffee", ["Food", "Coffee"]],
    ["Food›Coffee", ["Food", "Coffee"]],
    ["Food: Coffee", ["Food", "Coffee"]],
    [" Food ", ["Food", ""]],
    ["", ["", ""]],
  ])("%j", (text, parts) => {
    expect(splitCategory(text)).toEqual(parts);
  });
});

describe("parseCsvDate", () => {
  it.each([
    ["2026-10-05", "2026-10-05"],
    ["10/05/2026", "2026-10-05"],
    ["10/5/26", "2026-10-05"],
    ["1-31-2026", "2026-01-31"],
    [" 2026-10-05 ", "2026-10-05"],
  ])("%s -> %s", (text, iso) => {
    expect(parseCsvDate(text)).toBe(iso);
  });

  it.each(["", "Oct 5", "02/30/2026", "13/01/2026", "2026/10/05"])("rejects %j", (text) => {
    expect(parseCsvDate(text)).toBeNull();
  });
});

describe("parseCsvAmount", () => {
  it.each([
    ["-12.50", -1250],
    ["12.5", 1250],
    ["$1,234.56", 123456],
    ["(12.50)", -1250],
    ["12.50-", -1250],
    ["−7", -700],
    ["+3.00", 300],
    [".99", 99],
  ])("%s -> %d", (text, cents) => {
    expect(parseCsvAmount(text)).toBe(cents);
  });

  it.each(["", "abc", "1.234", "-", "."])("rejects %j", (text) => {
    expect(parseCsvAmount(text)).toBeNull();
  });
});

describe("toImportRows", () => {
  const single: Mapping = { ...EMPTY_MAPPING, date: 0, payee: 1, amount: 2 };
  const blanks = { account: "", category: "", subcategory: "" };

  it("reads rows with one amount column", () => {
    const { rows, problems } = toImportRows([["10/05/2026", "  BLUE   BOTTLE ", "-4.50"]], single, 2);

    expect(problems).toEqual([]);
    expect(rows).toEqual([{ line: 2, date: "2026-10-05", amount_cents: -450, payee: "BLUE BOTTLE", notes: null, ...blanks }]);
  });

  it("flips signs for files that list purchases as positive", () => {
    const { rows } = toImportRows([["2026-10-05", "Store", "25.00"]], { ...single, sign: "flipped" }, 2);

    expect(rows[0].amount_cents).toBe(-2500);
  });

  it("combines debit and credit columns", () => {
    const mapping: Mapping = { ...EMPTY_MAPPING, date: 0, payee: 1, debit: 2, credit: 3 };
    const { rows } = toImportRows(
      [
        ["2026-10-05", "Store", "25.00", ""],
        ["2026-10-06", "Paycheck", "", "1000.00"],
        ["2026-10-07", "Fee", "-3.00", ""], // some banks already write debits as negative
      ],
      mapping,
      2,
    );

    expect(rows.map((r) => r.amount_cents)).toEqual([-2500, 100000, -300]);
  });

  it("reports rows it can't read, with their line numbers, and skips $0 lines", () => {
    const { rows, problems } = toImportRows(
      [["garbage", "x", "1"], ["2026-10-05", "Hold", "0.00"], ["2026-10-06", "Store", ""], ["2026-10-07", "Ok", "-1"]],
      single,
      2,
    );

    expect(rows.map((r) => r.line)).toEqual([5]);
    expect(problems).toEqual(['Line 2: can\'t read the date "garbage".', "Line 4: no amount."]);
  });

  it("reads account and categories, splitting Food > Coffee when there's no subcategory column", () => {
    const mapping: Mapping = { ...EMPTY_MAPPING, date: 0, account: 1, category: 2, amount: 3 };
    const { rows } = toImportRows([["2023-01-05", " Amex ", "Food > Coffee", "-4"], ["2023-01-06", "Amex", "", "-1"]], mapping, 2);

    expect(rows.map((r) => [r.account, r.category, r.subcategory])).toEqual([["Amex", "Food", "Coffee"], ["Amex", "", ""]]);
  });

  it("uses the subcategory column when there is one", () => {
    const mapping: Mapping = { ...EMPTY_MAPPING, date: 0, category: 1, subcategory: 2, amount: 3 };
    const { rows } = toImportRows([["2023-01-05", "Food", "Coffee", "-4"], ["2023-01-05", "", "Orphan", "-4"]], mapping, 2);

    expect(rows.map((r) => [r.category, r.subcategory])).toEqual([["Food", "Coffee"], ["", ""]]);
  });
});
