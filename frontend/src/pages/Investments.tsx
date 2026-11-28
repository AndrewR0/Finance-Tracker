import { useState, type FormEvent } from "react";

import { api, type Account, type AccountHoldings, type Holding, type SecurityKind, type TradeKind } from "../api/client";
import { useAccounts, useComparison, useHoldings, usePriceStatus, useSave, useTrades } from "../api/hooks";
import { BenchmarkChart } from "../charts/BenchmarkChart";
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

      {all.length > 0 && <ComparisonCard accounts={accounts.filter((a) => a.type === "brokerage" || a.type === "retirement")} />}

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

/** You vs the same deposits, on the same days, in the S&P 500 (SPY with dividends reinvested). */
function ComparisonCard({ accounts }: { accounts: Account[] }) {
  const [accountId, setAccountId] = useState<number | null>(null);
  const comparison = useComparison(accountId).data;
  const spy = comparison?.benchmark_cents ?? null;
  const ahead = comparison && spy !== null ? comparison.value_cents - spy : null;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="prices-line">
        <h3 style={{ margin: 0 }}>vs the S&amp;P 500</h3>
        <select
          className="select"
          aria-label="Which accounts"
          style={{ width: "auto" }}
          value={accountId ?? ""}
          onChange={(e) => setAccountId(e.target.value === "" ? null : Number(e.target.value))}
        >
          <option value="">All investment accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
      </div>
      {comparison === undefined ? (
        <p className="muted">Loading…</p>
      ) : comparison.start === null ? (
        <p className="muted">No deposits yet. Transfers into these accounts are what gets compared.</p>
      ) : (
        <>
          <div className="compare-numbers">
            <div>
              <div className="muted">Put in since {formatShortDate(comparison.start)} {comparison.start.slice(0, 4)}</div>
              <b className="num">{formatMoney0(comparison.put_in_cents)}</b>
            </div>
            <div>
              <div className="muted">You now</div>
              <b className="num">{formatMoney0(comparison.value_cents)}</b>
            </div>
            <div>
              <div className="muted">Same deposits in the S&amp;P 500</div>
              <b className="num">{spy === null ? "—" : formatMoney0(spy)}</b>
            </div>
            <div>
              <div className="muted">{ahead === null ? "Difference" : ahead >= 0 ? "You're ahead by" : "You're behind by"}</div>
              <b className={`num ${ahead === null ? "" : ahead >= 0 ? "up" : "down"}`}>
                {ahead === null ? "—" : formatMoney0(Math.abs(ahead))}
              </b>
            </div>
          </div>
          <div className="legend">
            <span><i className="solid" />You</span>
            <span><i className="dash" />Same deposits in the S&amp;P 500</span>
            <span><i className="solid" style={{ borderTop: "1.5px solid var(--ink3)" }} />Put in</span>
          </div>
          <BenchmarkChart comparison={comparison} />
          <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
            Each deposit (transfer in, opening balance, 401k contribution) "buys" SPY at that day's close, dividends
            reinvested.
            {comparison.tracked_since
              ? ` Your line starts ${formatShortDate(comparison.tracked_since)}, when holdings were set up; earlier, only deposits are known.`
              : " Your line appears once these accounts' holdings are set up."}
            {spy === null && " S&P prices arrive with the next price refresh."}
          </p>
        </>
      )}
    </div>
  );
}

function AccountCard({ account }: { account: AccountHoldings }) {
  const undo = useSave(() => api.undoHoldings(account.account_id));
  const [confirming, setConfirming] = useState(false);
  const [panel, setPanel] = useState<"none" | "trade" | "history">("none");
  const toggle = (which: "trade" | "history") => setPanel((open) => (open === which ? "none" : which));

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
            <td className="r num" data-label="Cost">{formatMoney(account.cost_basis_cents)}</td>
            <td className="r num">{formatMoney(account.value_cents)}</td>
            <td className="r">
              <Gain cents={account.gain_cents} cost={account.cost_basis_cents} />
            </td>
          </tr>
        </tbody>
      </table>
      {(account.realized_cents !== 0 || account.dividends_cents !== 0) && (
        <div className="muted realized-line">
          Realized from sales <Gain cents={account.realized_cents} cost={0} /> · Dividends{" "}
          <span className="num">{formatMoney(account.dividends_cents)}</span>
        </div>
      )}
      <div className="card-actions">
        <button className="btn small" onClick={() => toggle("trade")}>
          + Trade
        </button>
        <button className="btn small" onClick={() => toggle("history")}>
          {panel === "history" ? "Hide history" : "History"}
        </button>
      </div>
      {panel === "trade" && <TradeForm account={account} onDone={() => setPanel("none")} />}
      {panel === "history" && <TradeHistory accountId={account.account_id} />}
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

const TRADE_KINDS: { kind: Exclude<TradeKind, "opening">; label: string; help: string }[] = [
  { kind: "buy", label: "Buy", help: "Paid from the account's cash. Add the transfer in first, as usual." },
  { kind: "sell", label: "Sell", help: "What you got after fees goes to the account's cash. Oldest shares sell first (FIFO)." },
  { kind: "dividend", label: "Dividend", help: "Counts as gain inside the account, not income. Tick reinvested if it bought shares." },
  {
    kind: "contribution",
    label: "401k contribution",
    help: "Shares bought with payroll money that never went through your bank: no cash leaves the account.",
  },
];

const KIND_NAMES: Record<TradeKind, string> = {
  opening: "Opening lot",
  buy: "Buy",
  sell: "Sell",
  dividend: "Dividend",
  contribution: "401k contribution",
};

/** Add a buy, sell, dividend or 401k contribution to one account. */
function TradeForm({ account, onDone }: { account: AccountHoldings; onDone: () => void }) {
  const [kind, setKind] = useState<Exclude<TradeKind, "opening">>("buy");
  const [date, setDate] = useState(todayISO());
  const [security, setSecurity] = useState(account.holdings[0] ? String(account.holdings[0].security_id) : "new");
  const [newTicker, setNewTicker] = useState("");
  const [newName, setNewName] = useState("");
  const [newKind, setNewKind] = useState<SecurityKind>("fund");
  const [newManual, setNewManual] = useState(false);
  const [shares, setShares] = useState("");
  const [amount, setAmount] = useState("");
  const [reinvested, setReinvested] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const save = useSave((body: Parameters<typeof api.addTrade>[1]) => api.addTrade(account.account_id, body));

  const needsShares = kind !== "dividend" || reinvested;
  const isNew = security === "new" && kind !== "sell" && kind !== "dividend";

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const cents = parseMoney(amount);
    if (cents === null || cents <= 0) return setProblem("Enter the amount in dollars (more than $0).");
    const parsedShares = needsShares ? parseDecimal(shares, SHARE_DECIMALS) : null;
    if (needsShares && parsedShares === null) return setProblem(`Enter shares (more than 0, up to ${SHARE_DECIMALS} decimals).`);
    if (isNew && (!newTicker.trim() || !newName.trim())) return setProblem("A new holding needs a ticker and a name.");
    if (!isNew && security === "new") return setProblem("Pick the holding.");
    setProblem(null);
    save.mutate(
      {
        date,
        kind,
        amount_cents: cents,
        ...(isNew
          ? { new_security: { ticker: newTicker.trim(), name: newName.trim(), kind: newKind, price_source: newManual ? "manual" : "yfinance" } }
          : { security_id: Number(security) }),
        ...(kind === "dividend"
          ? reinvested
            ? { reinvested_shares: parsedShares as string }
            : {}
          : { shares: parsedShares as string }),
      },
      { onSuccess: onDone },
    );
  }

  const amountLabel = kind === "sell" ? "Proceeds (after fees)" : kind === "dividend" ? "Dividend paid" : "Cost (with fees)";

  return (
    <form className="trade-form" onSubmit={onSubmit}>
      <div className="row">
        <label className="field">
          Type
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
            {TRADE_KINDS.map((k) => (
              <option key={k.kind} value={k.kind}>{k.label}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Date
          <input className="input" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="field">
          Holding
          <select className="select" value={security} onChange={(e) => setSecurity(e.target.value)}>
            {account.holdings.map((h) => (
              <option key={h.security_id} value={h.security_id}>{h.ticker} · {h.name}</option>
            ))}
            {kind !== "sell" && kind !== "dividend" && <option value="new">New holding…</option>}
          </select>
        </label>
        {needsShares && (
          <label className="field">
            {kind === "dividend" ? "Shares it bought" : "Shares"}
            <input className="input" inputMode="decimal" placeholder="0.00" value={shares} onChange={(e) => setShares(e.target.value)} />
          </label>
        )}
        <label className="field">
          {amountLabel}
          <input className="input" inputMode="decimal" placeholder="$" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
      </div>
      {isNew && (
        <div className="row">
          <label className="field">
            Ticker
            <input className="input" value={newTicker} maxLength={20} placeholder="VTI" onChange={(e) => setNewTicker(e.target.value.toUpperCase())} />
          </label>
          <label className="field">
            Name
            <input className="input" value={newName} maxLength={100} onChange={(e) => setNewName(e.target.value)} />
          </label>
          <label className="field">
            Kind
            <select className="select" value={newKind} onChange={(e) => setNewKind(e.target.value as SecurityKind)}>
              {Object.entries(KIND_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="check" title="No public ticker: you'll type its price in">
            <input type="checkbox" checked={newManual} onChange={(e) => setNewManual(e.target.checked)} /> Manual price
          </label>
        </div>
      )}
      <div className="row">
        {kind === "dividend" && (
          <label className="check">
            <input type="checkbox" checked={reinvested} onChange={(e) => setReinvested(e.target.checked)} /> Reinvested (it bought
            shares)
          </label>
        )}
        <span className="muted" style={{ fontSize: 12.5, flex: 1 }}>
          {TRADE_KINDS.find((k) => k.kind === kind)?.help}
        </span>
        <button type="button" className="btn" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn-neon" disabled={save.isPending}>
          Save
        </button>
      </div>
      {(problem ?? save.error?.message) && <p className="form-error">{problem ?? save.error?.message}</p>}
    </form>
  );
}

/** Every trade in one account, newest first. ✕ deletes one (re-add it to change it). */
function TradeHistory({ accountId }: { accountId: number }) {
  const trades = useTrades(accountId).data;
  const remove = useSave((tradeId: number) => api.deleteTrade(tradeId));
  const [confirmId, setConfirmId] = useState<number | null>(null);

  if (trades === undefined) return <div className="muted trade-history">Loading…</div>;
  return (
    <div className="trade-history">
      <table className="accttable tradetable">
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td className="muted">{formatShortDate(t.date)} {t.date.slice(0, 4)}</td>
              <td>{KIND_NAMES[t.kind]}</td>
              <td>
                <b>{t.ticker}</b>
              </td>
              <td className="r num" data-label={t.shares ? "Shares" : undefined}>{t.shares ? formatShares(t.shares) : ""}</td>
              <td className="r num">{formatMoney(t.amount_cents)}</td>
              <td className="r">
                {t.kind !== "opening" &&
                  (confirmId === t.id ? (
                    <>
                      <button className="btn small" disabled={remove.isPending} onClick={() => remove.mutate(t.id, { onSuccess: () => setConfirmId(null) })}>
                        Delete
                      </button>{" "}
                      <button className="btn small" onClick={() => setConfirmId(null)}>
                        Keep
                      </button>
                    </>
                  ) : (
                    <button className="icon-btn" aria-label={`Delete this ${KIND_NAMES[t.kind]}`} onClick={() => setConfirmId(t.id)}>
                      ✕
                    </button>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {remove.error && <p className="form-error">{remove.error.message}</p>}
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
        <td className="r num" data-label="Shares">{formatShares(h.shares)}</td>
        <td className="r num" data-label="Price" title={h.price_date ? `Price from ${formatShortDate(h.price_date)}` : "No price yet"}>
          {h.price === null ? "—" : formatPrice(h.price)}
          {h.price_source === "manual" && (
            <button className="icon-btn" title={`Update ${h.ticker}'s price`} onClick={() => setEditing((open) => !open)}>
              ✎
            </button>
          )}
        </td>
        <td className="r num" data-label="Cost">{formatMoney(h.cost_basis_cents)}</td>
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
      <table className="setup-table">
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
