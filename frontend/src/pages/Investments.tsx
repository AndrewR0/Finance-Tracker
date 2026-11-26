import { useState, type FormEvent } from "react";

import { api, type Account, type AccountHoldings, type Holding, type SecurityKind } from "../api/client";
import { useAccounts, useHoldings, usePriceStatus, useSave } from "../api/hooks";
import { formatShortDate, todayISO } from "../lib/dates";
import { formatMoney, formatMoney0, parseMoney } from "../lib/money";
import { PRICE_DECIMALS, SHARE_DECIMALS, formatPrice, formatShares, gainPercent, parseDecimal } from "../lib/shares";

const KIND_LABELS: Record<SecurityKind, string> = { fund: "Fund", stock: "Stock", crypto: "Crypto", other: "Other" };

/** Investments: holdings per account, derived from opening lots (and, later, trades). */
export function Investments() {
  const holdings = useHoldings().data;
  const accounts = useAccounts().data ?? [];
  const [settingUp, setSettingUp] = useState<number | null>(null);

  const withHoldings = new Set((holdings ?? []).map((h) => h.account_id));
  const notSetUp = accounts.filter(
    (a) => (a.type === "brokerage" || a.type === "retirement") && a.closed_at === null && !withHoldings.has(a.id),
  );
  const all = holdings ?? [];
  const value = all.reduce((sum, a) => sum + a.value_cents, 0);
  const cost = all.reduce((sum, a) => sum + a.cost_basis_cents, 0);
  const gain = all.reduce((sum, a) => sum + a.gain_cents, 0);
  const setupAccount = accounts.find((a) => a.id === settingUp);

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Investments</h1>
          <div className="sub">Holdings come from opening lots; values use each holding's latest market price</div>
        </div>
      </div>

      {setupAccount && <SetUpHoldings account={setupAccount} onDone={() => setSettingUp(null)} />}

      {all.length > 0 && <PricesBar holdings={all} />}

      {all.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 16 }}>
          <div className="card kpi">
            <div className="lbl">Value</div>
            <div className="val">{formatMoney0(value)}</div>
            <div className="delta">All investment accounts, retirement included</div>
          </div>
          <div className="card kpi">
            <div className="lbl">Cost basis</div>
            <div className="val">{formatMoney0(cost)}</div>
            <div className="delta">What the shares you hold cost</div>
          </div>
          <div className="card kpi">
            <div className="lbl">Gain</div>
            <div className={`val ${gain > 0 ? "up" : gain < 0 ? "down" : ""}`}>{formatMoney0(gain, { sign: true })}</div>
            <div className="delta">{gainPercent(gain, cost) ?? "—"} unrealized</div>
          </div>
        </div>
      )}

      {holdings === undefined && <div className="empty">Loading…</div>}
      {all.map((account) => (
        <AccountCard key={account.account_id} account={account} />
      ))}

      {notSetUp.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Set up holdings</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            Copy each holding from your provider's cost basis page: ticker, shares, cost basis and today's value. Past
            balance updates stay in your history; one adjustment makes the account's cash match.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {notSetUp.map((a) => (
              <button key={a.id} className="btn" onClick={() => setSettingUp(a.id)}>
                {a.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * "Prices as of Nov 25 · Refresh prices", plus a warning per ticker the last refresh couldn't use.
 * The server refreshes by itself every 6 hours; the button is for "right now".
 */
function PricesBar({ holdings }: { holdings: AccountHoldings[] }) {
  const status = usePriceStatus().data;
  const refresh = useSave(() => api.refreshPrices());
  const switchToManual = useSave((securityId: number) => api.updateSecurity(securityId, { price_source: "manual" }));
  const idOf = new Map(holdings.flatMap((a) => a.holdings.map((h) => [h.ticker, h.security_id] as const)));
  const failed = Object.entries(status?.failed ?? {});

  return (
    <div className="card prices-bar" style={{ marginBottom: 16 }}>
      <div className="prices-line">
        <span className="muted">
          {status?.prices_as_of ? `Market prices as of ${formatShortDate(status.prices_as_of)}` : "No market prices yet"}
          {status?.refreshed_at && ` · checked ${new Date(status.refreshed_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`}
        </span>
        <button className="btn small" disabled={refresh.isPending} onClick={() => refresh.mutate(undefined)}>
          {refresh.isPending ? "Refreshing…" : "Refresh prices"}
        </button>
      </div>
      {refresh.error && <div className="form-error">{refresh.error.message}</div>}
      {failed.map(([ticker, problem]) => (
        <div key={ticker} className="price-warning">
          <b>{ticker}:</b> {problem}{" "}
          {idOf.has(ticker) && (
            <button
              className="btn small"
              disabled={switchToManual.isPending}
              onClick={() => switchToManual.mutate(idOf.get(ticker) as number)}
            >
              Use manual prices
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function AccountCard({ account }: { account: AccountHoldings }) {
  const undo = useSave(() => api.undoHoldings(account.account_id));
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="card" style={{ padding: "4px 6px", marginBottom: 16 }}>
      <table className="accttable holdtable">
        <thead>
          <tr className="dayhead">
            <td colSpan={6}>
              {account.account_name} · {formatMoney0(account.value_cents)}
              {!account.in_net_worth && <span className="muted"> · not in net worth</span>}
            </td>
          </tr>
          <tr>
            <th>Holding</th>
            <th className="r">Shares</th>
            <th className="r">Price</th>
            <th className="r">Cost basis</th>
            <th className="r">Value</th>
            <th className="r">Gain</th>
          </tr>
        </thead>
        <tbody>
          {account.holdings.map((h) => (
            <HoldingRow key={h.security_id} holding={h} />
          ))}
          {account.cash_cents !== 0 && (
            <tr>
              <td className="muted">Cash</td>
              <td />
              <td />
              <td />
              <td className="r num">{formatMoney(account.cash_cents)}</td>
              <td />
            </tr>
          )}
          <tr className="total">
            <td>Total</td>
            <td />
            <td />
            <td className="r num">{formatMoney(account.cost_basis_cents)}</td>
            <td className="r num">{formatMoney(account.value_cents)}</td>
            <td className="r">
              <Gain cents={account.gain_cents} cost={account.cost_basis_cents} />
            </td>
          </tr>
        </tbody>
      </table>
      {account.can_undo && (
        <div style={{ padding: "6px 10px 10px", fontSize: 12.5 }} className="muted">
          {confirming ? (
            <>
              Remove these opening lots and the setup adjustment?{" "}
              <button className="btn small" disabled={undo.isPending} onClick={() => undo.mutate(undefined)}>
                Undo setup
              </button>{" "}
              <button className="btn small" onClick={() => setConfirming(false)}>
                Keep
              </button>
            </>
          ) : (
            <button className="btn small" onClick={() => setConfirming(true)}>
              Undo setup…
            </button>
          )}
          {undo.error && <span className="form-error"> {undo.error.message}</span>}
        </div>
      )}
    </div>
  );
}

function Gain({ cents, cost }: { cents: number; cost: number }) {
  const percent = gainPercent(cents, cost);
  return (
    <span className={`num ${cents > 0 ? "up" : cents < 0 ? "down" : ""}`}>
      {formatMoney(cents, { sign: true })}
      {percent && <span className="muted"> {percent}</span>}
    </span>
  );
}

/** One holding. A manual-price holding (no public ticker) gets an "Update price" form. */
function HoldingRow({ holding: h }: { holding: Holding }) {
  const [editing, setEditing] = useState(false);
  const [price, setPrice] = useState("");
  const [date, setDate] = useState(todayISO());
  const save = useSave(() => api.addPrice(h.security_id, { date, price: parseDecimal(price, PRICE_DECIMALS) ?? "" }));

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (parseDecimal(price, PRICE_DECIMALS) === null) return;
    save.mutate(undefined, { onSuccess: () => setEditing(false) });
  }

  return (
    <>
      <tr>
        <td>
          <b>{h.ticker}</b> <span className="muted">{h.name}</span>
        </td>
        <td className="r num">{formatShares(h.shares)}</td>
        <td className="r num" title={h.price_date ? `Price from ${formatShortDate(h.price_date)}` : "No price yet"}>
          {h.price === null ? "—" : formatPrice(h.price)}
          {h.price_source === "manual" && (
            <button className="icon-btn" title={`Update ${h.ticker}'s price`} onClick={() => setEditing((open) => !open)}>
              ✎
            </button>
          )}
        </td>
        <td className="r num">{formatMoney(h.cost_basis_cents)}</td>
        <td className="r num">{formatMoney(h.value_cents)}</td>
        <td className="r">
          <Gain cents={h.gain_cents} cost={h.cost_basis_cents} />
        </td>
      </tr>
      {editing && (
        <tr className="reconcile">
          <td colSpan={6}>
            <form className="rename" onSubmit={onSubmit}>
              <span className="muted">{h.ticker} price on</span>
              <input className="input" type="date" required value={date} style={{ width: 150 }} onChange={(e) => setDate(e.target.value)} />
              <input
                className="input"
                autoFocus
                required
                inputMode="decimal"
                placeholder="Price per share"
                aria-label="Price per share"
                value={price}
                style={{ width: 140 }}
                onChange={(e) => setPrice(e.target.value)}
              />
              <button type="submit" className="btn-neon" disabled={save.isPending || parseDecimal(price, PRICE_DECIMALS) === null}>
                Save
              </button>
              <button type="button" className="btn" onClick={() => setEditing(false)}>
                Cancel
              </button>
              {save.error && <div className="form-error">{save.error.message}</div>}
            </form>
          </td>
        </tr>
      )}
    </>
  );
}

type Row = {
  ticker: string;
  name: string;
  kind: SecurityKind;
  manual: boolean; // no public ticker: prices are typed in
  shares: string;
  cost: string;
  value: string;
};

const EMPTY_ROW: Row = { ticker: "", name: "", kind: "fund", manual: false, shares: "", cost: "", value: "" };

/** A row's problem in words, or null when it's ready to send. */
function rowProblem(row: Row): string | null {
  if (!row.ticker.trim()) return "a ticker";
  if (!row.name.trim()) return "a name";
  if (parseDecimal(row.shares, SHARE_DECIMALS) === null) return `shares (more than 0, up to ${SHARE_DECIMALS} decimals)`;
  const cost = parseMoney(row.cost);
  if (cost === null || cost < 0) return "a cost basis";
  const value = parseMoney(row.value);
  if (value === null || value < 0) return "today's value";
  return null;
}

/** The one-time setup: every holding in the account, as of one day. */
function SetUpHoldings({ account, onDone }: { account: Account; onDone: () => void }) {
  const [rows, setRows] = useState<Row[]>([{ ...EMPTY_ROW }]);
  const [cash, setCash] = useState("0");
  const [date, setDate] = useState(todayISO());
  const [problem, setProblem] = useState<string | null>(null);
  const save = useSave(api.setUpHoldings.bind(null, account.id));

  const update = (i: number, changes: Partial<Row>) => setRows((all) => all.map((r, j) => (j === i ? { ...r, ...changes } : r)));
  const totalValue = rows.reduce((sum, r) => sum + (parseMoney(r.value) ?? 0), 0) + (parseMoney(cash) ?? 0);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const bad = rows.findIndex((r) => rowProblem(r) !== null);
    if (bad >= 0) return setProblem(`Row ${bad + 1} needs ${rowProblem(rows[bad])}.`);
    const cashCents = parseMoney(cash);
    if (cashCents === null) return setProblem("Cash needs an amount (0 is fine).");
    setProblem(null);
    save.mutate(
      {
        date,
        cash_cents: cashCents,
        holdings: rows.map((r) => ({
          ticker: r.ticker.trim(),
          name: r.name.trim(),
          kind: r.kind,
          price_source: r.manual ? "manual" : "yfinance",
          shares: parseDecimal(r.shares, SHARE_DECIMALS) as string,
          cost_basis_cents: parseMoney(r.cost) as number,
          market_value_cents: parseMoney(r.value) as number,
        })),
      },
      { onSuccess: onDone },
    );
  }

  return (
    <form className="card form-card setup-card" onSubmit={onSubmit}>
      <h3>Set up {account.name}</h3>
      <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
        Today the app has {account.name} at {formatMoney(account.balance_cents)}. Enter what you hold now; the total
        below should come out close to your provider's.
      </p>
      <table className="accttable setup-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Name</th>
            <th>Kind</th>
            <th title="No public ticker (some 401k funds): you'll type its price in">Manual price</th>
            <th className="r">Shares</th>
            <th className="r">Cost basis</th>
            <th className="r">Value today</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              <td>
                <input className="input" aria-label="Ticker" placeholder="VTSAX" value={row.ticker} maxLength={20}
                  onChange={(e) => update(i, { ticker: e.target.value.toUpperCase() })} />
              </td>
              <td>
                <input className="input" aria-label="Name" placeholder="Total Stock Market" value={row.name} maxLength={100}
                  onChange={(e) => update(i, { name: e.target.value })} />
              </td>
              <td>
                <select className="select" aria-label="Kind" value={row.kind} onChange={(e) => update(i, { kind: e.target.value as SecurityKind })}>
                  {Object.entries(KIND_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </td>
              <td>
                <input type="checkbox" aria-label="Manual price" checked={row.manual} onChange={(e) => update(i, { manual: e.target.checked })} />
              </td>
              <td>
                <input className="input r" aria-label="Shares" inputMode="decimal" placeholder="0.00" value={row.shares}
                  onChange={(e) => update(i, { shares: e.target.value })} />
              </td>
              <td>
                <input className="input r" aria-label="Cost basis" inputMode="decimal" placeholder="$" value={row.cost}
                  onChange={(e) => update(i, { cost: e.target.value })} />
              </td>
              <td>
                <input className="input r" aria-label="Value today" inputMode="decimal" placeholder="$" value={row.value}
                  onChange={(e) => update(i, { value: e.target.value })} />
              </td>
              <td>
                {rows.length > 1 && (
                  <button type="button" className="icon-btn" aria-label={`Remove row ${i + 1}`} onClick={() => setRows((all) => all.filter((_, j) => j !== i))}>
                    ✕
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="row" style={{ marginTop: 10 }}>
        <button type="button" className="btn" onClick={() => setRows((all) => [...all, { ...EMPTY_ROW }])}>
          + Add holding
        </button>
        <label className="field">
          Uninvested cash
          <input className="input" inputMode="decimal" value={cash} onChange={(e) => setCash(e.target.value)} style={{ width: 120 }} />
        </label>
        <label className="field">
          As of
          <input className="input" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <span className="muted" style={{ alignSelf: "end", paddingBottom: 8 }}>
          Total {formatMoney(totalValue)}
        </span>
        <button type="button" className="btn" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn-neon" disabled={save.isPending}>
          Save holdings
        </button>
      </div>
      {(problem ?? save.error?.message) && <p className="form-error">{problem ?? save.error?.message}</p>}
    </form>
  );
}
