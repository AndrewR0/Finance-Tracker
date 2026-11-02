import { describe, expect, it } from "vitest";

import type { Account, CategoryTree } from "../api/client";
import type { CsvRow } from "./csv";
import { categoryRefOf, collectNames, defaultChoices, finalCents, guessAccountType, newItems, withTop } from "./sheet";

let line = 2;
function row(account: string, category: string, subcategory: string, amount_cents: number): CsvRow {
  return { line: line++, date: "2023-01-05", amount_cents, payee: null, notes: null, account, category, subcategory };
}

function existingAccount(id: number, name: string, closed = false): Account {
  return {
    id, name, type: "checking", balance_cents: 0,
    created_at: "2026-01-01T00:00:00", closed_at: closed ? "2026-02-01T00:00:00" : null,
  };
}

const TREE: CategoryTree[] = [
  { id: 1, name: "Food", kind: "expense", parent_id: null, subcategories: [{ id: 2, name: "Groceries", kind: "expense", parent_id: 1 }] },
  { id: 3, name: "Salary", kind: "income", parent_id: null, subcategories: [] },
  { id: 4, name: "Moves", kind: "transfer", parent_id: null, subcategories: [] },
];

const ROWS = [
  row("Checking", "Food", "Groceries", -8000),
  row("checking ", "food", "Coffee", -450),
  row("Amex Gold", "Fun", "", -2500),
  row("Checking", "Salary", "", 300000),
  row("Checking", "", "", -100),
  row("Checking", "Moves", "", 500),
];

describe("collectNames", () => {
  it("groups names ignoring case and spaces, keeping the first spelling", () => {
    const names = collectNames(ROWS);

    expect(names.accounts.map((a) => [a.name, a.rows])).toEqual([["Checking", 5], ["Amex Gold", 1]]);
    expect(names.categories.map((c) => [c.name, c.rows, c.subs.map((s) => s.name)])).toEqual([
      ["Food", 2, ["Groceries", "Coffee"]],
      ["Fun", 1, []],
      ["Salary", 1, []],
      ["Moves", 1, []],
    ]);
  });
});

describe("defaultChoices", () => {
  const names = collectNames(ROWS);
  const choices = defaultChoices(names, [existingAccount(10, "Checking"), existingAccount(11, "Amex Gold", true)], TREE, "signed");

  it("uses open accounts with the same name and creates the rest", () => {
    expect(choices.accounts.get("checking")).toEqual({ target: 10, type: "checking" });
    expect(choices.accounts.get("amex gold")?.target).toBe("new"); // the matching one is closed
  });

  it("uses existing categories and subcategories, and creates the rest", () => {
    expect(choices.tops.get("food")).toEqual({ target: 1, kind: "expense" });
    expect(choices.subs.get("food>groceries")).toEqual({ target: 2 });
    expect(choices.subs.get("food>coffee")).toEqual({ target: "new" });
    expect(choices.tops.get("fun")).toEqual({ target: "new", kind: "expense" });
  });

  it("never matches a transfer category, since imported rows can't be transfers", () => {
    expect(choices.tops.get("moves")).toEqual({ target: "new", kind: "income" }); // +$5: more in than out
  });

  it("guesses income from the name when every amount is positive", () => {
    const positive = collectNames([row("A", "Paycheck", "", 100), row("A", "Rent", "", 100)]);
    const guessed = defaultChoices(positive, [], [], "by-category");

    expect(guessed.tops.get("paycheck")?.kind).toBe("income");
    expect(guessed.tops.get("rent")?.kind).toBe("expense");
  });
});

describe("categoryRefOf and newItems", () => {
  const names = collectNames(ROWS);
  const choices = defaultChoices(names, [existingAccount(10, "Checking")], TREE, "signed");

  it("points each row at an id, a new key, or nothing", () => {
    expect(ROWS.map((r) => categoryRefOf(r, choices))).toEqual([
      2, // Food › Groceries exists
      "category:food>coffee", // new subcategory
      "category:fun", // new top-level category
      3,
      null, // no category in the file
      "category:moves",
    ]);
  });

  it("lists what will be created, subcategories under their parent", () => {
    expect(newItems(names, choices)).toEqual({
      accounts: [{ key: "account:amex gold", name: "Amex Gold", type: guessAccountType("Amex Gold") }],
      categories: [
        { key: "category:food>coffee", name: "Coffee", kind: "expense", parent: 1 },
        { key: "category:fun", name: "Fun", kind: "expense", parent: null },
        { key: "category:moves", name: "Moves", kind: "income", parent: null },
      ],
    });
  });

  it("follows the choices: use the parent, or leave uncategorized", () => {
    const changed = { ...choices, tops: new Map(choices.tops), subs: new Map(choices.subs) };
    changed.subs.set("food>coffee", { target: "parent" });
    changed.tops.set("fun", { target: "none", kind: "expense" });

    expect(categoryRefOf(ROWS[1], changed)).toBe(1);
    expect(categoryRefOf(ROWS[2], changed)).toBeNull();
    expect(newItems(names, changed).categories.map((c) => c.key)).toEqual(["category:moves"]);
  });

  it("switching a category to new makes its subcategories new too, under its key", () => {
    const food = names.categories[0];
    const changed = withTop(choices, food, { target: "new", kind: "expense" }, TREE);

    expect(categoryRefOf(ROWS[0], changed)).toBe("category:food>groceries");
    const created = newItems(names, changed).categories;
    expect(created.slice(0, 3)).toEqual([
      { key: "category:food", name: "Food", kind: "expense", parent: null },
      { key: "category:food>groceries", name: "Groceries", kind: "expense", parent: "category:food" },
      { key: "category:food>coffee", name: "Coffee", kind: "expense", parent: "category:food" },
    ]);
  });
});

describe("finalCents", () => {
  const names = collectNames(ROWS);
  const choices = defaultChoices(names, [], TREE, "by-category");

  it("keeps the file's sign normally", () => {
    expect(finalCents(row("A", "Food", "", 500), choices, "signed")).toBe(500);
  });

  it("with by-category, income categories are money in and everything else money out", () => {
    expect(finalCents(row("A", "Salary", "", 300000), choices, "by-category")).toBe(300000);
    expect(finalCents(row("A", "Food", "", 8000), choices, "by-category")).toBe(-8000);
    expect(finalCents(row("A", "", "", 100), choices, "by-category")).toBe(-100);
  });
});

describe("guessAccountType", () => {
  it.each([
    ["Chase Sapphire Visa", "credit_card"],
    ["Amex Gold", "credit_card"],
    ["Discover it", "credit_card"],
    ["Citi Mastercard", "credit_card"],
    ["Ally Savings", "savings"],
    ["Emergency fund", "savings"],
    ["Fidelity Brokerage", "brokerage"],
    ["Roth IRA", "brokerage"],
    ["Vanguard 401k", "brokerage"],
    ["Wallet", "cash"],
    ["Cash", "cash"],
    ["BofA Checking", "checking"],
    ["Everyday", "checking"],
  ])("%s -> %s", (name, type) => {
    expect(guessAccountType(name)).toBe(type);
  });
});
