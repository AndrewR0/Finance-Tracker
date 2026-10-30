import type { ReactNode } from "react";

import type { Account } from "../api/client";
import type { CategoryInfo } from "../lib/categories";
import { formatDayHeader, formatShortDate } from "../lib/dates";
import { formatMoney } from "../lib/money";
import { groupByDay, type Row } from "../lib/transactions";
import { usePanelActions } from "../state/panel";

type Props = {
  rows: Row[];
  accounts: Map<number, Account>;
  categories: Map<number, CategoryInfo>;
  variant: "full" | "recent"; // full: grouped by day with notes; recent: a short list for the dashboard
};

/** The cells every row shows, worked out once for both kinds of row. */
function describe(row: Row, accounts: Props["accounts"], categories: Props["categories"]) {
  const accountName = (id: number) => accounts.get(id)?.name ?? `Account ${id}`;

  if (row.kind === "transaction") {
    const { tx } = row;
    const category = tx.category_id === null ? null : categories.get(tx.category_id);
    return {
      payee: tx.payee_name ?? <span className="muted">No payee</span>,
      category: category ? <span className="cat">{category.label}</span> : <span className="muted">Uncategorized</span>,
      account: accountName(tx.account_id),
      notes: tx.notes ?? "",
      amount: <span className={`num ${tx.amount_cents > 0 ? "up" : ""}`}>{formatMoney(tx.amount_cents, { sign: true })}</span>,
    };
  }

  const leg = row.to ?? row.from;
  const category = leg?.category_id == null ? null : categories.get(leg.category_id);
  let account: string;
  let amount: ReactNode;
  if (row.from && row.to) {
    account = `${accountName(row.from.account_id)} → ${accountName(row.to.account_id)}`;
    // Money moved between your own accounts: no sign, no color.
    amount = <span className="num" style={{ color: "var(--ink2)" }}>{formatMoney(row.to.amount_cents)}</span>;
  } else {
    // A filter hid the other side: show this side as it affects this account.
    const only = (row.from ?? row.to)!;
    account = row.from ? `From ${accountName(only.account_id)}` : `Into ${accountName(only.account_id)}`;
    amount = <span className="num" style={{ color: "var(--ink2)" }}>{formatMoney(only.amount_cents, { sign: true })}</span>;
  }
  return {
    payee: row.description ?? "Transfer",
    category: <span className="cat xfer">{category?.label ?? "Transfer"}</span>,
    account,
    notes: "",
    amount,
  };
}

export function TransactionTable({ rows, accounts, categories, variant }: Props) {
  const { open } = usePanelActions();
  const edit = (row: Row) =>
    row.kind === "transaction"
      ? open({ mode: "edit-transaction", tx: row.tx })
      : open({ mode: "edit-transfer", transferId: row.transferId });

  if (variant === "recent") {
    return (
      <table style={{ marginTop: 6 }}>
        <tbody>
          {rows.length === 0 && (
            <tr className="empty-row">
              <td colSpan={5}>No transactions yet.</td>
            </tr>
          )}
          {rows.map((row) => {
            const cells = describe(row, accounts, categories);
            return (
              <tr key={row.key} className="tx" onClick={() => edit(row)} style={{ cursor: "pointer" }}>
                <td className="d">{formatShortDate(row.date)}</td>
                <td>{cells.payee}</td>
                <td>{cells.category}</td>
                <td className="muted">{cells.account}</td>
                <td className="r">{cells.amount}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Payee</th>
          <th>Category</th>
          <th>Account</th>
          <th>Notes</th>
          <th className="r">Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr className="empty-row">
            <td colSpan={5}>No transactions match.</td>
          </tr>
        )}
        {groupByDay(rows).map((day) => [
          <tr key={day.date} className="dayhead">
            <td colSpan={5}>{formatDayHeader(day.date)}</td>
          </tr>,
          ...day.items.map((row) => {
            const cells = describe(row, accounts, categories);
            return (
              <tr key={row.key} className="tx" onClick={() => edit(row)}>
                <td>{cells.payee}</td>
                <td>{cells.category}</td>
                <td className="muted">{cells.account}</td>
                <td className="muted">{cells.notes}</td>
                <td className="r">{cells.amount}</td>
              </tr>
            );
          }),
        ])}
      </tbody>
    </table>
  );
}
