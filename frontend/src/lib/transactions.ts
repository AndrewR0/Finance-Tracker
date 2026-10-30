// Turning the API's flat transaction list into what the Transactions page shows.

import type { Transaction } from "../api/client";

/**
 * One line in the list. A transfer is two transactions in the API (money out of one
 * account, into another) but one line on screen, so its legs are merged.
 * If a filter hides one leg (for example "Visa only"), the transfer has just the leg that's visible.
 */
export type Row =
  | { kind: "transaction"; key: string; date: string; tx: Transaction }
  | {
      kind: "transfer";
      key: string;
      date: string;
      transferId: number;
      from?: Transaction; // the negative leg
      to?: Transaction; // the positive leg
      description: string | null;
    };

/** Merge transfer legs into one row each. Keeps the API's order (newest first). */
export function toRows(transactions: Transaction[]): Row[] {
  const rows: Row[] = [];
  const transfers = new Map<number, Extract<Row, { kind: "transfer" }>>();

  for (const tx of transactions) {
    if (tx.transfer_id === null) {
      rows.push({ kind: "transaction", key: `t${tx.id}`, date: tx.date, tx });
      continue;
    }
    let row = transfers.get(tx.transfer_id);
    if (!row) {
      row = {
        kind: "transfer",
        key: `x${tx.transfer_id}`,
        date: tx.date,
        transferId: tx.transfer_id,
        description: tx.transfer_description,
      };
      transfers.set(tx.transfer_id, row);
      rows.push(row); // placed where its first leg appears
    }
    if (tx.amount_cents < 0) row.from = tx;
    else row.to = tx;
  }
  return rows;
}

/** [{date, items}] in the order dates first appear. */
export function groupByDay<T extends { date: string }>(items: T[]): { date: string; items: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const group = groups.get(item.date);
    if (group) group.push(item);
    else groups.set(item.date, [item]);
  }
  return [...groups].map(([date, grouped]) => ({ date, items: grouped }));
}

/**
 * For quick-add: the category last used with each payee (lowercased name -> category id).
 * transactions must be newest first, so the first one seen per payee wins.
 */
export function lastCategoryByPayee(transactions: Transaction[]): Map<string, number | null> {
  const result = new Map<string, number | null>();
  for (const tx of transactions) {
    if (tx.payee_name && tx.transfer_id === null) {
      const key = tx.payee_name.toLowerCase();
      if (!result.has(key)) result.set(key, tx.category_id);
    }
  }
  return result;
}

/** Money in and out of the listed transactions, by sign. Transfers are left out. */
export function moneyInOut(transactions: Transaction[]): { in: number; out: number } {
  let moneyIn = 0;
  let moneyOut = 0;
  for (const tx of transactions) {
    if (tx.transfer_id !== null) continue;
    if (tx.amount_cents > 0) moneyIn += tx.amount_cents;
    else moneyOut -= tx.amount_cents;
  }
  return { in: moneyIn, out: moneyOut };
}

/** Case-insensitive search over payee, notes and transfer description. */
export function matchesSearch(tx: Transaction, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  return [tx.payee_name, tx.notes, tx.transfer_description].some((text) => text?.toLowerCase().includes(needle));
}
