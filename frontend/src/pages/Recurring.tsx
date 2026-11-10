// Recurring spending: payees you pay on a steady schedule, found from your transactions.
// Nothing to set up. The server re-detects series on every load (see backend/app/recurring.py).

import { useMemo, useState } from "react";

import { api, type Recurring as Series } from "../api/client";
import { useCategories, useRecurring, useSave, useUpcoming } from "../api/hooks";
import { indexCategories, type CategoryInfo } from "../lib/categories";
import { formatShortDate, todayISO } from "../lib/dates";
import { formatMoney, formatMoney0 } from "../lib/money";
import { CADENCE_LABELS, dueLabel, formatCharge } from "../lib/recurring";

export function Recurring() {
  const series = useRecurring().data;
  const next30 = useUpcoming(30).data;
  const tree = useCategories().data;
  const categories = useMemo(() => indexCategories(tree ?? []), [tree]);
  const [showIgnored, setShowIgnored] = useState(false);

  const active = (series ?? []).filter((s) => !s.ignored);
  const ignored = (series ?? []).filter((s) => s.ignored);
  const perMonth = active.reduce((sum, s) => sum + s.monthly_cents, 0);
  const due30 = (next30 ?? []).reduce((sum, c) => sum + c.amount_cents, 0);

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Recurring</h1>
          <div className="sub">Found automatically: payees you pay on a steady schedule, for about the same amount</div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 16 }}>
        <div className="card kpi">
          <div className="lbl">Per month</div>
          <div className="val">{series ? formatMoney0(perMonth) : "…"}</div>
          <div className="delta">{active.length} recurring {active.length === 1 ? "charge" : "charges"}</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Per year</div>
          <div className="val">{series ? formatMoney0(perMonth * 12) : "…"}</div>
          <div className="delta">at today's amounts</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Next 30 days</div>
          <div className="val">{next30 ? formatMoney0(due30) : "…"}</div>
          <div className="delta">{next30?.length ?? 0} expected {next30?.length === 1 ? "charge" : "charges"}</div>
        </div>
      </div>

      <div className="card" style={{ padding: "4px 6px" }}>
        <SeriesTable rows={active} categories={categories} loading={series === undefined} />
      </div>

      {ignored.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <button className="btn" onClick={() => setShowIgnored((v) => !v)}>
            {showIgnored ? "Hide" : "Show"} ignored ({ignored.length})
          </button>
          {showIgnored && (
            <div className="card" style={{ padding: "4px 6px", marginTop: 10 }}>
              <SeriesTable rows={ignored} categories={categories} loading={false} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type TableProps = { rows: Series[]; categories: Map<number, CategoryInfo>; loading: boolean };

function SeriesTable({ rows, categories, loading }: TableProps) {
  const today = todayISO();
  const save = useSave(api.setRecurringIgnored);

  if (loading) return <p className="muted" style={{ padding: 12 }}>Looking for recurring charges…</p>;
  if (rows.length === 0) {
    return (
      <p className="muted" style={{ padding: 12 }}>
        Nothing recurring yet. A payee shows up here after about 3 charges on a steady schedule (2 for yearly ones).
      </p>
    );
  }

  return (
    <table className="rectable">
      <thead>
        <tr>
          <th>Payee</th>
          <th>Category</th>
          <th>How often</th>
          <th>Next</th>
          <th className="r">Amount</th>
          <th className="r">Per month</th>
          <th style={{ width: 90 }} />
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => {
          const due = dueLabel(today, s.next_date);
          return (
            <tr key={`${s.payee_id}:${s.matched_amount_cents ?? ""}`} className={s.ignored ? "off" : undefined}>
              <td>
                {s.payee_name}
                {s.matched_amount_cents !== null && (
                  <span className="muted" title="This payee has other payments too; only this amount repeats.">
                    {" "}· {formatMoney(s.matched_amount_cents)} only
                  </span>
                )}
              </td>
              <td>
                {s.category_id !== null ? (
                  <span className="cat">{categories.get(s.category_id)?.label}</span>
                ) : (
                  <span className="muted">Uncategorized</span>
                )}
              </td>
              <td className="muted" title={`Based on ${s.charges} charges, last on ${formatShortDate(s.last_date)}`}>
                {CADENCE_LABELS[s.cadence]}
              </td>
              <td className="nowrap">
                {formatShortDate(s.next_date)}{" "}
                <span className={due.startsWith("Due") ? "due late" : "due"}>{due}</span>
              </td>
              <td className="r num" title={s.amount_varies ? "An estimate: this amount changes from charge to charge" : undefined}>
                {formatCharge(s.amount_cents, s.amount_varies)}
              </td>
              <td className="r num muted">{formatMoney(s.monthly_cents)}</td>
              <td className="r">
                <button
                  className="btn slim"
                  disabled={save.isPending}
                  title={s.ignored ? "Count it as recurring again" : "Not a bill: hide it here and on the dashboard"}
                  onClick={() =>
                    save.mutate({ payee_id: s.payee_id, matched_amount_cents: s.matched_amount_cents, ignored: !s.ignored })
                  }
                >
                  {s.ignored ? "Restore" : "Ignore"}
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
