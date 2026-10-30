import { useMemo } from "react";
import { Link } from "react-router-dom";

import type { CategorySpending, Pace, Period, Summary } from "../api/client";
import { useAccounts, useCashFlow, useCategories, usePace, useSpendingByCategory, useSummary, useTransactions } from "../api/hooks";
import { CashFlowChart } from "../charts/CashFlowChart";
import { PaceChart } from "../charts/PaceChart";
import { ChangeBadge, changeOf } from "../components/ChangeBadge";
import { PeriodPicker } from "../components/PeriodPicker";
import { TransactionTable } from "../components/TransactionTable";
import { indexCategories } from "../lib/categories";
import { comparisonName, formatRange, formatShortDate, monthName, periodTitle } from "../lib/dates";
import { formatMoney0 } from "../lib/money";
import { toRows } from "../lib/transactions";
import { usePanelActions } from "../state/panel";
import { usePeriod } from "../state/period";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

/** "this month" / "in September" / "this year" / "since Jan 4" */
function periodPhrase(period: Period): string {
  const current = period.next_date === null; // the next period hasn't started, so this one is ongoing
  if (period.kind === "month") return current ? "this month" : `in ${monthName(period.start)}`;
  if (period.kind === "year") return current ? "this year" : `in ${period.start.slice(0, 4)}`;
  return `since ${formatShortDate(period.start)}, ${period.start.slice(0, 4)}`;
}

/** "vs this point in September" for an ongoing period, "vs September" for a finished one. */
function versus(period: Period): string {
  const name = comparisonName(period);
  if (!name) return "";
  return period.next_date === null ? `vs this point in ${name}` : `vs ${name}`;
}

export function Dashboard() {
  const { choice, period } = usePeriod();
  const { open } = usePanelActions();
  const summary = useSummary(period).data;
  const pace = usePace(choice.kind, choice.date).data;
  const cashFlow = useCashFlow(period?.end).data;
  const spending = useSpendingByCategory(period).data;

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>{period ? periodTitle(period) : "…"}</h1>
          <div className="sub">{greeting()}</div>
        </div>
        <div className="controls">
          <PeriodPicker />
          <button className="btn-neon" onClick={() => open({ mode: "new", type: "expense" })}>
            + Add transaction
          </button>
        </div>
      </div>

      <div className="grid">
        <KpiCards summary={summary} period={period} />
        <PaceCard pace={choice.kind === "all" ? undefined : pace} period={period} spentAllTime={summary?.spending_cents} />

        <div className="card span2">
          <h3>
            Cash flow <small>12 months to {period ? formatShortDate(period.end) : "…"}</small>
          </h3>
          <div className="legend">
            <span><i style={{ background: "var(--s1)" }} />Income</span>
            <span><i style={{ background: "var(--s2)" }} />Spending</span>
          </div>
          {cashFlow ? <CashFlowChart months={cashFlow} /> : <div style={{ height: 200 }} />}
        </div>

        <SpendingCard rows={spending} period={period} />
        <RecentCard />
      </div>
    </div>
  );
}

function KpiCards({ summary, period }: { summary: Summary | undefined; period: Period | undefined }) {
  if (!summary || !period) {
    return (
      <>
        {["Net worth", "Income", "Spending", "Saved"].map((label) => (
          <div key={label} className="card kpi">
            <div className="lbl">{label}</div>
            <div className="val">…</div>
          </div>
        ))}
      </>
    );
  }

  const vs = versus(period);
  const savedRate = summary.income_cents > 0 ? Math.round((summary.saved_cents / summary.income_cents) * 100) : null;
  const netChange = summary.net_worth_change_cents;

  return (
    <>
      <div className="card kpi">
        <div className="lbl">Net worth</div>
        <div className="val">{formatMoney0(summary.net_worth_cents)}</div>
        <div className="delta">
          <span className={netChange > 0 ? "up" : netChange < 0 ? "down" : ""}>
            {netChange > 0 ? "▲" : netChange < 0 ? "▼" : ""} {formatMoney0(Math.abs(netChange))}
          </span>{" "}
          {periodPhrase(period)}
        </div>
      </div>
      <div className="card kpi">
        <div className="lbl">Income</div>
        <div className="val">{formatMoney0(summary.income_cents)}</div>
        <div className="delta">
          {summary.income_change ? (
            <>
              <ChangeBadge change={summary.income_change} higherIsBetter /> {vs}
            </>
          ) : (
            periodPhrase(period)
          )}
        </div>
      </div>
      <div className="card kpi">
        <div className="lbl">Spending</div>
        <div className="val">{formatMoney0(summary.spending_cents)}</div>
        <div className="delta">
          {summary.spending_change ? (
            <>
              <ChangeBadge change={summary.spending_change} higherIsBetter={false} /> {vs}
            </>
          ) : (
            periodPhrase(period)
          )}
        </div>
      </div>
      <div className="card kpi">
        <div className="lbl">Saved</div>
        <div className={`val ${summary.saved_cents < 0 ? "down" : ""}`}>{formatMoney0(summary.saved_cents)}</div>
        <div className="delta">{savedRate === null ? "No income yet" : `${savedRate}% of income`}</div>
      </div>
    </>
  );
}

function PaceCard({ pace, period, spentAllTime }: { pace: Pace | undefined; period: Period | undefined; spentAllTime: number | undefined }) {
  if (period?.kind === "all") {
    return (
      <div className="card full">
        <h3>
          Spending vs previous period <small>All time</small>
        </h3>
        <div className="pace-head">
          <div>
            <div className="lbl">Spent all time</div>
            <div className="big">{spentAllTime === undefined ? "…" : formatMoney0(spentAllTime)}</div>
          </div>
          <div className="cmp">All time has no earlier period to compare. Pick Month or Year.</div>
        </div>
      </div>
    );
  }
  if (!pace || !period) return <div className="card full" style={{ minHeight: 300 }} />;

  const isMonth = pace.kind === "month";
  const nowName = isMonth ? monthName(pace.start) : pace.start.slice(0, 4);
  const thenName = isMonth ? monthName(pace.compare_start) : pace.compare_start.slice(0, 4);
  const elapsed = pace.points.filter((p) => p.current_cents !== null).length;
  const previousLength = pace.points.filter((p) => p.previous_cents !== null).length;
  const unit = isMonth ? "Daily" : "Monthly";
  const ongoing = period.next_date === null;
  const sameEnd = pace.previous_same_point_cents;

  return (
    <div className="card full">
      <h3>
        Spending vs last {isMonth ? "month" : "year"}{" "}
        <small>
          {formatRange(pace.start, pace.end)} compared with {formatRange(pace.compare_start, pace.compare_end)}
        </small>
      </h3>
      <div className="pace-wrap">
        <div>
          <div className="pace-head">
            <div>
              <div className="lbl">Spent {ongoing ? "so far " : ""}in {nowName}</div>
              <div className="big">{formatMoney0(pace.spent_cents)}</div>
            </div>
            <div className="cmp">
              <ChangeBadge change={changeOf(pace.spent_cents, sameEnd)} higherIsBetter={false} show="dollars" />{" "}
              {ongoing ? `vs the same point in ${thenName}` : `vs ${thenName}`} ({formatMoney0(sameEnd)})
            </div>
          </div>
          <div className="legend">
            <span><i className="solid" style={{ borderTopColor: "var(--s2)" }} />{nowName}</span>
            <span><i className="dash" />{thenName}</span>
          </div>
          <PaceChart pace={pace} currentName={nowName} previousName={thenName} />
        </div>
        <div className="pace-side">
          <div>{thenName} total<b>{formatMoney0(pace.previous_total_cents)}</b></div>
          <div>{unit} average now<b>{formatMoney0(Math.round(pace.spent_cents / Math.max(elapsed, 1)))}</b></div>
          <div>{unit} average then<b>{formatMoney0(Math.round(pace.previous_total_cents / Math.max(previousLength, 1)))}</b></div>
          {ongoing && <div>On pace for<b>{formatMoney0(pace.projected_cents)}</b></div>}
        </div>
      </div>
    </div>
  );
}

function SpendingCard({ rows, period }: { rows: CategorySpending[] | undefined; period: Period | undefined }) {
  const top = (rows ?? []).filter((r) => r.spending_cents > 0).slice(0, 7);
  const biggest = Math.max(1, ...top.map((r) => r.spending_cents));
  const name = period && comparisonName(period);

  return (
    <div className="card span2">
      <h3>
        Spending by category{" "}
        <small>
          <Link className="link" to="/categories">{name ? `change vs ${name}` : "details"} →</Link>
        </small>
      </h3>
      <div className="bars">
        {top.length === 0 && <p className="muted">No spending in this period.</p>}
        {top.map((row) => (
          <div className="row" key={row.category_id ?? "none"}>
            <span className="name">{row.name}</span>
            <span className="t">
              <i style={{ width: `${(row.spending_cents / biggest) * 100}%` }} />
            </span>
            <span className="v num">{formatMoney0(row.spending_cents)}</span>
            <span className="c">
              <ChangeBadge change={changeOf(row.spending_cents, row.previous_cents)} higherIsBetter={false} show="dollars" />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecentCard() {
  const transactions = useTransactions().data;
  const accounts = useAccounts().data;
  const tree = useCategories().data;

  const accountIndex = useMemo(() => new Map((accounts ?? []).map((a) => [a.id, a])), [accounts]);
  const categories = useMemo(() => indexCategories(tree ?? []), [tree]);
  const rows = useMemo(() => toRows(transactions ?? []).slice(0, 6), [transactions]);

  return (
    <div className="card full">
      <h3>
        Recent transactions{" "}
        <small>
          <Link className="link" to="/transactions">View all →</Link>
        </small>
      </h3>
      <TransactionTable rows={rows} accounts={accountIndex} categories={categories} variant="recent" />
    </div>
  );
}
