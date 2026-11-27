import { useState } from "react";
import { Link } from "react-router-dom";

import type { Change, YearInReview } from "../api/client";
import { useReview } from "../api/hooks";
import { CashFlowChart } from "../charts/CashFlowChart";
import { ChangeBadge } from "../components/ChangeBadge";
import { formatShortDate, monthLabel } from "../lib/dates";
import { formatMoney0 } from "../lib/money";

/** A Change with its percent filled in, for ChangeBadge. Null when there's nothing to compare with. */
function versus(now: number, previous: number | undefined | null): Change | null {
  if (previous === undefined || previous === null) return null;
  const percent = previous === 0 ? null : Math.round(((now - previous) / Math.abs(previous)) * 1000) / 10;
  return { previous_cents: previous, change_cents: now - previous, change_percent: percent };
}

const percentOf = (part: number, whole: number) => (whole > 0 ? Math.round((part / whole) * 100) : 0);

/** One year's story: totals vs last year, months, top categories and payees, and how things grew. */
export function Review() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const data = useReview(year).data;

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>{year} in review</h1>
          <div className="sub">
            {data
              ? `${formatShortDate(data.start)} – ${formatShortDate(data.end)}${data.partial ? " (so far), compared with the same days last year" : ", compared with the year before"}`
              : "…"}
          </div>
        </div>
        <div className="controls">
          <select className="select" aria-label="Year" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: "auto" }}>
            {(data?.years ?? [thisYear]).slice().reverse().map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>
      {data === undefined ? <div className="empty">Loading…</div> : <ReviewBody data={data} />}
    </div>
  );
}

function ReviewBody({ data }: { data: YearInReview }) {
  const t = data.totals;
  const p = data.previous;
  const rate = percentOf(t.saved_cents, t.income_cents);
  const lastRate = p ? percentOf(p.saved_cents, p.income_cents) : null;
  const vs = p ? (data.partial ? "vs same days last year" : `vs ${data.year - 1}`) : "";
  const spendingMonths = data.months.filter((m) => m.spending_cents > 0);
  const biggest = spendingMonths.reduce<(typeof data.months)[number] | null>((a, m) => (!a || m.spending_cents > a.spending_cents ? m : a), null);
  const bestSaving = data.months.reduce<(typeof data.months)[number] | null>((a, m) => (!a || m.saved_cents > a.saved_cents ? m : a), null);
  const netChange = data.net_worth_end_cents - data.net_worth_start_cents;
  const investChange = data.investments_end_cents - data.investments_start_cents;
  const topTotal = data.top_categories.reduce((s, c) => s + c.cents, 0);

  return (
    <>
      <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))", marginBottom: 16 }}>
        <div className="card kpi">
          <div className="lbl">Income</div>
          <div className="val">{formatMoney0(t.income_cents)}</div>
          <div className="delta">
            <ChangeBadge change={versus(t.income_cents, p?.income_cents)} higherIsBetter /> {vs}
          </div>
        </div>
        <div className="card kpi">
          <div className="lbl">Spending</div>
          <div className="val">{formatMoney0(t.spending_cents)}</div>
          <div className="delta">
            <ChangeBadge change={versus(t.spending_cents, p?.spending_cents)} higherIsBetter={false} /> {vs}
          </div>
        </div>
        <div className="card kpi">
          <div className="lbl">Saved</div>
          <div className={`val ${t.saved_cents < 0 ? "down" : ""}`}>{formatMoney0(t.saved_cents)}</div>
          <div className="delta">
            {rate}% of income{lastRate !== null && ` (last year ${lastRate}%)`}
          </div>
        </div>
        <div className="card kpi">
          <div className="lbl">Invested</div>
          <div className="val">{formatMoney0(t.invested_cents)}</div>
          <div className="delta">
            <ChangeBadge change={versus(t.invested_cents, p?.invested_cents)} higherIsBetter /> {vs}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>Month by month</h3>
        <div className="legend">
          <span><i style={{ background: "var(--s1)" }} />Income</span>
          <span><i style={{ background: "var(--s2)" }} />Spending</span>
        </div>
        <CashFlowChart months={data.months} />
      </div>

      <div className="grid review-grid" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3>Highlights</h3>
          <ul className="review-facts">
            {biggest && (
              <li>
                <b>Biggest spending month:</b> {monthLabel(biggest.month)}, {formatMoney0(biggest.spending_cents)}
              </li>
            )}
            {bestSaving && bestSaving.saved_cents > 0 && (
              <li>
                <b>Best saving month:</b> {monthLabel(bestSaving.month)}, {formatMoney0(bestSaving.saved_cents)} saved
              </li>
            )}
            <li>
              <b>Transactions:</b> {data.transactions.toLocaleString("en-US")}
              {data.top_payees[0] && (
                <>
                  , most money to <b>{data.top_payees[0].name}</b>
                </>
              )}
            </li>
            <li>
              <b>Net worth:</b> {formatMoney0(data.net_worth_start_cents)} → {formatMoney0(data.net_worth_end_cents)}{" "}
              <span className={netChange >= 0 ? "up" : "down"}>({formatMoney0(netChange, { sign: true })})</span>
            </li>
            <li>
              <b>Investments:</b> {formatMoney0(data.investments_start_cents)} → {formatMoney0(data.investments_end_cents)}{" "}
              <span className={investChange >= 0 ? "up" : "down"}>({formatMoney0(investChange, { sign: true })}, including deposits and accounts first added this year)</span>
            </li>
            {data.sp500_return_bp !== null && (
              <li>
                <b>S&amp;P 500{data.partial ? " so far" : ""}:</b>{" "}
                <span className={data.sp500_return_bp >= 0 ? "up" : "down"}>
                  {data.sp500_return_bp >= 0 ? "+" : "−"}
                  {(Math.abs(data.sp500_return_bp) / 100).toFixed(1)}%
                </span>{" "}
                with dividends. <Link className="link" to="/investments">Your comparison →</Link>
              </li>
            )}
            {data.budget_months_total > 0 && (
              <li>
                <b>Budgets:</b> on track {data.budget_months_on_track} of {data.budget_months_total} budget-months (
                {percentOf(data.budget_months_on_track, data.budget_months_total)}%)
              </li>
            )}
          </ul>
        </div>

        <div className="card">
          <h3>Where the money went</h3>
          <table className="review-list">
            <tbody>
              {data.top_categories.map((c) => (
                <tr key={c.id ?? "none"}>
                  <td>
                    {c.name}
                    <div className="review-bar">
                      <i style={{ width: `${percentOf(c.cents, topTotal)}%` }} />
                    </div>
                  </td>
                  <td className="r num">{formatMoney0(c.cents)}</td>
                  <td className="r">{p && <ChangeBadge change={versus(c.cents, c.previous_cents)} higherIsBetter={false} show="dollars" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3>Top payees</h3>
          <table className="review-list">
            <tbody>
              {data.top_payees.map((payee) => (
                <tr key={payee.id ?? payee.name}>
                  <td>
                    {payee.name}
                    <div className="muted" style={{ fontSize: 12 }}>
                      {payee.count} {payee.count === 1 ? "payment" : "payments"}
                    </div>
                  </td>
                  <td className="r num">{formatMoney0(payee.cents)}</td>
                  <td className="r">{p && <ChangeBadge change={versus(payee.cents, payee.previous_cents)} higherIsBetter={false} show="dollars" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
