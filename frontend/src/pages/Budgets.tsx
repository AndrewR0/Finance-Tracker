import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api, type BudgetRow, type MonthBudgets } from "../api/client";
import { useBudgets, useSave } from "../api/hooks";
import { barPercent, budgetStatus, pacePercent, shiftMonth } from "../lib/budgets";
import { monthName, todayISO } from "../lib/dates";
import { centsToInput, formatMoney0, parseMoney } from "../lib/money";

/** Optional monthly budgets per category. A parent's budget covers its subcategories. */
export function Budgets() {
  const thisMonth = `${todayISO().slice(0, 7)}-01`;
  const [month, setMonth] = useState(thisMonth);
  const [editing, setEditing] = useState(false);
  const data = useBudgets(month).data;
  const title = `${monthName(month)} ${month.slice(0, 4)}`;

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Budgets</h1>
          <div className="sub">Optional monthly limits. A category's budget covers its subcategories.</div>
        </div>
        <div className="controls">
          <span className="seg">
            <button aria-label="Previous month" onClick={() => setMonth(shiftMonth(month, -1))}>‹</button>
            <button className="on" style={{ minWidth: 120 }}>{title}</button>
            <button aria-label="Next month" onClick={() => setMonth(shiftMonth(month, 1))}>›</button>
          </span>
          <button className={editing ? "btn" : "btn-neon"} onClick={() => setEditing((on) => !on)}>
            {editing ? "Done editing" : "Edit budgets"}
          </button>
        </div>
      </div>

      {data === undefined ? (
        <div className="empty">Loading…</div>
      ) : editing ? (
        <EditBudgets data={data} title={title} />
      ) : (
        <BudgetView data={data} onEdit={() => setEditing(true)} />
      )}
    </div>
  );
}

function BudgetView({ data, onEdit }: { data: MonthBudgets; onEdit: () => void }) {
  const budgeted = data.rows.filter((r) => r.budget_cents !== null);
  const budgetedIds = new Set(budgeted.map((r) => r.category_id));
  // Show a parent whenever it or one of its subcategories has a budget.
  const shown = data.rows.filter(
    (r) => r.budget_cents !== null || (r.parent_id === null && data.rows.some((s) => s.parent_id === r.category_id && budgetedIds.has(s.category_id))),
  );
  const left = data.budgeted_cents - data.spent_budgeted_cents;

  if (budgeted.length === 0) {
    return (
      <div className="card">
        <p className="muted">No budgets for this month yet.</p>
        <button className="btn-neon" onClick={onEdit}>
          Set some budgets
        </button>
        <p className="muted" style={{ fontSize: 12.5 }}>
          Budgets are optional: set them only where you want a limit. Each one suggests your average monthly spending from
          the last 6 months.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))", marginBottom: 16 }}>
        <div className="card kpi">
          <div className="lbl">Budgeted</div>
          <div className="val">{formatMoney0(data.budgeted_cents)}</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Spent in budgets</div>
          <div className="val">{formatMoney0(data.spent_budgeted_cents)}</div>
          <div className="delta">
            day {data.days_elapsed} of {data.days_in_month}
          </div>
        </div>
        <div className="card kpi">
          <div className="lbl">{left >= 0 ? "Left" : "Over"}</div>
          <div className={`val ${left >= 0 ? "up" : "down"}`}>{formatMoney0(Math.abs(left))}</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Not budgeted</div>
          <div className="val">{formatMoney0(data.unbudgeted_cents)}</div>
          <div className="delta">
            <Link className="link" to="/categories">by category →</Link>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: "4px 6px" }}>
        <table className="accttable budgettable">
          <thead>
            <tr>
              <th>Category</th>
              <th className="r">Budget</th>
              <th className="r">Spent</th>
              <th className="r">Left</th>
              <th style={{ width: "34%" }} />
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <BudgetLine key={r.category_id} row={r} data={data} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 12 }}>
        The tick on each bar is where you'd be if you spent evenly through the month. Green: on or under pace. Pink:
        spending faster than the month. Red: over the budget. Refunds lower spending; Savings and transfers don't count.
      </p>
    </>
  );
}

function BudgetLine({ row, data }: { row: BudgetRow; data: MonthBudgets }) {
  const isSub = row.parent_id !== null;
  if (row.budget_cents === null) {
    // A parent shown only because a subcategory has a budget.
    return (
      <tr className="parent">
        <td colSpan={5}>{row.name}</td>
      </tr>
    );
  }
  const budget = row.budget_cents;
  const left = budget - row.spent_cents;
  const status = budgetStatus(row.spent_cents, budget, data.days_elapsed, data.days_in_month);
  return (
    <tr className={isSub ? "child" : "parent"}>
      <td>{row.name}</td>
      <td className="r num" data-label="Budget">{formatMoney0(budget)}</td>
      <td className="r num" data-label="Spent">{formatMoney0(row.spent_cents)}</td>
      <td className={`r num ${left < 0 ? "down" : ""}`} data-label="Left">{formatMoney0(left)}</td>
      <td>
        <div className={`budget-bar ${status}`} title={`${Math.round((row.spent_cents / budget) * 100)}% of the budget spent`}>
          <i style={{ width: `${barPercent(row.spent_cents, budget)}%` }} />
          {data.days_elapsed > 0 && data.days_elapsed < data.days_in_month && (
            <b style={{ left: `${pacePercent(data.days_elapsed, data.days_in_month)}%` }} />
          )}
        </div>
      </td>
    </tr>
  );
}

/** Every spending category with a box for its budget. Saving a box sets it from this month on. */
function EditBudgets({ data, title }: { data: MonthBudgets; title: string }) {
  return (
    <div className="card" style={{ padding: "4px 6px" }}>
      <p className="muted" style={{ fontSize: 12.5, margin: "8px 10px" }}>
        Changes apply from {title} on; earlier months keep the budgets they had. Leave a box empty for no budget.
      </p>
      <table className="accttable budgettable">
        <thead>
          <tr>
            <th>Category</th>
            <th className="r">Avg / month (last 6)</th>
            <th className="r">Spent this month</th>
            <th className="r" style={{ width: 230 }}>
              Budget
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <EditLine key={`${data.month}:${r.category_id}`} row={r} month={data.month} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EditLine({ row, month }: { row: BudgetRow; month: string }) {
  const saved = row.budget_cents === null ? "" : centsToInput(row.budget_cents);
  const [text, setText] = useState(saved);
  const save = useSave((amount: number | null) => api.setBudget(row.category_id, { month, amount_cents: amount }));
  const cents = text.trim() === "" ? null : parseMoney(text);
  const valid = text.trim() === "" || (cents !== null && cents >= 0);
  const changed = text !== saved;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (valid && changed) save.mutate(cents === 0 ? null : cents);
  }

  return (
    <tr className={row.parent_id === null ? "parent" : "child"}>
      <td>{row.name}</td>
      <td className="r num muted" data-label="Avg">{row.suggested_cents ? formatMoney0(row.suggested_cents) : "—"}</td>
      <td className="r num muted" data-label="This month">{formatMoney0(row.spent_cents)}</td>
      <td className="r">
        <form className="budget-edit" onSubmit={onSubmit}>
          {row.suggested_cents > 0 && text === "" && (
            <button
              type="button"
              className="btn small"
              title="Use your 6-month average"
              onClick={() => {
                // Saved right away: the button is the whole action, there's no box to leave afterwards.
                const average = Math.round(row.suggested_cents / 100) * 100; // whole dollars
                setText(centsToInput(average));
                save.mutate(average);
              }}
            >
              Use avg
            </button>
          )}
          <input
            className="input r"
            inputMode="decimal"
            aria-label={`${row.name} budget`}
            placeholder="No budget"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => valid && changed && save.mutate(cents === 0 ? null : cents)}
            style={{ width: 110, borderColor: valid ? undefined : "var(--bad)" }}
          />
          {save.isPending && <span className="muted">…</span>}
          {save.error && <span className="form-error">{save.error.message}</span>}
        </form>
      </td>
    </tr>
  );
}
