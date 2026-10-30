import { describe, expect, it } from "vitest";

import type { Transaction } from "../api/client";
import { indexCategories } from "./categories";
import { changeTone } from "./change";
import { groupByDay, lastCategoryByPayee, matchesSearch, moneyInOut, toRows } from "./transactions";

let nextId = 1;
function tx(fields: Partial<Transaction>): Transaction {
  return {
    id: nextId++,
    account_id: 1,
    date: "2026-10-22",
    amount_cents: -100,
    payee_id: null,
    payee_name: null,
    category_id: null,
    notes: null,
    transfer_id: null,
    transfer_description: null,
    created_at: "2026-10-22T12:00:00",
    ...fields,
  };
}

describe("toRows", () => {
  it("merges the two legs of a transfer into one row", () => {
    const out = tx({ transfer_id: 7, amount_cents: -61200, account_id: 1, transfer_description: "Card payment" });
    const into = tx({ transfer_id: 7, amount_cents: 61200, account_id: 2, transfer_description: "Card payment" });

    const rows = toRows([out, into]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "transfer", transferId: 7, from: out, to: into, description: "Card payment" });
  });

  it("keeps the order, placing a transfer where its first leg was", () => {
    const a = tx({});
    const leg1 = tx({ transfer_id: 3, amount_cents: 500 });
    const b = tx({});
    const leg2 = tx({ transfer_id: 3, amount_cents: -500 });

    expect(toRows([a, leg1, b, leg2]).map((r) => r.key)).toEqual([`t${a.id}`, "x3", `t${b.id}`]);
  });

  it("shows a transfer with only one visible leg", () => {
    const leg = tx({ transfer_id: 9, amount_cents: 2500 });

    const [row] = toRows([leg]);

    expect(row.kind).toBe("transfer");
    expect(row.kind === "transfer" && [row.from, row.to]).toEqual([undefined, leg]);
  });
});

describe("groupByDay", () => {
  it("groups by date in first-seen order", () => {
    const items = [{ date: "2026-10-22", n: 1 }, { date: "2026-10-22", n: 2 }, { date: "2026-10-21", n: 3 }];

    expect(groupByDay(items)).toEqual([
      { date: "2026-10-22", items: [items[0], items[1]] },
      { date: "2026-10-21", items: [items[2]] },
    ]);
  });

  it("handles nothing", () => {
    expect(groupByDay([])).toEqual([]);
  });
});

describe("lastCategoryByPayee", () => {
  it("remembers the newest category per payee, ignoring case", () => {
    const memory = lastCategoryByPayee([
      tx({ payee_name: "Trader Joe's", category_id: 5 }), // newest
      tx({ payee_name: "trader joe's", category_id: 9 }),
      tx({ payee_name: "Shell", category_id: null }),
    ]);

    expect(memory.get("trader joe's")).toBe(5);
    expect(memory.get("shell")).toBeNull();
    expect(memory.has("nobody")).toBe(false);
  });
});

describe("moneyInOut", () => {
  it("adds up by sign and skips transfers", () => {
    const totals = moneyInOut([
      tx({ amount_cents: 270000 }),
      tx({ amount_cents: -8412 }),
      tx({ amount_cents: -588 }),
      tx({ amount_cents: -61200, transfer_id: 1 }),
    ]);

    expect(totals).toEqual({ in: 270000, out: 9000 });
  });
});

describe("matchesSearch", () => {
  it("looks at payee, notes and transfer description", () => {
    expect(matchesSearch(tx({ payee_name: "Blue Bottle" }), "bottle")).toBe(true);
    expect(matchesSearch(tx({ notes: "Bi-weekly" }), "WEEKLY")).toBe(true);
    expect(matchesSearch(tx({ transfer_description: "Card payment" }), "card")).toBe(true);
    expect(matchesSearch(tx({ payee_name: "Shell" }), "bottle")).toBe(false);
    expect(matchesSearch(tx({}), "  ")).toBe(true);
  });
});

describe("indexCategories", () => {
  it("labels subcategories with their parent", () => {
    const index = indexCategories([
      {
        id: 1, name: "Food", kind: "expense", parent_id: null,
        subcategories: [{ id: 5, name: "Groceries", kind: "expense", parent_id: 1 }],
      },
    ]);

    expect(index.get(1)?.label).toBe("Food");
    expect(index.get(5)).toMatchObject({ label: "Food › Groceries", parentId: 1 });
  });
});

describe("changeTone", () => {
  it("more spending is bad, more income is good, cents are the same", () => {
    expect(changeTone(1790, false)).toBe("bad");
    expect(changeTone(-1790, false)).toBe("good");
    expect(changeTone(1790, true)).toBe("good");
    expect(changeTone(49, false)).toBe("same");
  });
});
