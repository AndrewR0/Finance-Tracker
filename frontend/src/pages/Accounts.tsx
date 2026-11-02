import { useState, type FormEvent } from "react";

import { api, type Account, type AccountType } from "../api/client";
import { useAccounts, useSave } from "../api/hooks";
import { todayISO } from "../lib/dates";
import { formatMoney, formatMoney0, parseMoney } from "../lib/money";

const TYPE_LABELS: Record<AccountType, string> = {
  checking: "Checking",
  savings: "Savings",
  cash: "Cash",
  credit_card: "Credit card",
  brokerage: "Brokerage",
};

const GROUPS: { title: string; types: AccountType[] }[] = [
  { title: "Cash", types: ["checking", "savings", "cash"] },
  { title: "Credit cards", types: ["credit_card"] },
  { title: "Investments", types: ["brokerage"] },
];

export function Accounts() {
  const accounts = useAccounts().data;
  const [adding, setAdding] = useState(false);

  const open = (accounts ?? []).filter((a) => a.closed_at === null);
  const closed = (accounts ?? []).filter((a) => a.closed_at !== null);
  // Assets are what you have, liabilities what you owe. A credit card balance is negative.
  const assets = open.filter((a) => a.balance_cents > 0).reduce((sum, a) => sum + a.balance_cents, 0);
  const liabilities = open.filter((a) => a.balance_cents < 0).reduce((sum, a) => sum + a.balance_cents, 0);

  const groups = [
    ...GROUPS.map((g) => ({ title: g.title, accounts: open.filter((a) => g.types.includes(a.type)) })),
    { title: "Closed", accounts: closed },
  ].filter((g) => g.accounts.length > 0);

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Accounts</h1>
          <div className="sub">Balances add up every transaction in each account</div>
        </div>
        <div className="controls">
          <button className="btn-neon" onClick={() => setAdding(true)}>
            + Add account
          </button>
        </div>
      </div>

      {adding && <AddAccount onDone={() => setAdding(false)} />}

      <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 16 }}>
        <div className="card kpi">
          <div className="lbl">Assets</div>
          <div className="val">{formatMoney0(assets)}</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Liabilities</div>
          <div className="val">{formatMoney0(liabilities)}</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Net worth</div>
          <div className="val">{formatMoney0(assets + liabilities)}</div>
        </div>
      </div>

      <div className="card" style={{ padding: "4px 6px" }}>
        <table>
          <thead>
            <tr>
              <th>Account</th>
              {/* Fixed widths, so the columns don't jump when a row switches to rename mode. */}
              <th style={{ width: 180 }}>Type</th>
              <th className="r" style={{ width: 160 }}>Balance</th>
              <th style={{ width: 190 }} />
            </tr>
          </thead>
          <tbody>
            {accounts === undefined && (
              <tr className="empty-row">
                <td colSpan={4}>Loading…</td>
              </tr>
            )}
            {accounts?.length === 0 && (
              <tr className="empty-row">
                <td colSpan={4}>No accounts yet. Add your checking account to get started.</td>
              </tr>
            )}
            {groups.map((group) => [
              <tr key={group.title} className="dayhead">
                <td colSpan={4}>
                  {group.title} · {formatMoney0(total(group.accounts))}
                </td>
              </tr>,
              ...group.accounts.map((a) => <AccountRow key={a.id} account={a} />),
            ])}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginTop: 12 }}>
        Reconcile: enter the balance from a statement, and the difference is saved as a balance adjustment. It
        changes the balance but doesn't count as income or spending. An account can be closed once its balance is $0.
      </p>
    </div>
  );
}

type AccountChanges = { name?: string; type?: AccountType };

/** One account. Click ✎ to edit its name and type in place: Enter saves, Esc cancels. */
function AccountRow({ account }: { account: Account }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(account.name);
  const [type, setType] = useState<AccountType>(account.type);
  const [reconciling, setReconciling] = useState(false);
  const save = useSave((changes: AccountChanges) => api.updateAccount(account.id, changes));
  const close = useSave(() => api.closeAccount(account.id));
  const reopen = useSave(() => api.reopenAccount(account.id));
  const formId = `account-${account.id}`; // the type <select> sits in another cell and joins the form by id
  const isClosed = account.closed_at !== null;
  const actionError = close.error?.message ?? reopen.error?.message;

  function startEditing() {
    setName(account.name);
    setType(account.type);
    save.reset(); // forget an error from a previous attempt
    setEditing(true);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    // Send only what changed, the way PATCH is meant to be used.
    const changes: AccountChanges = {};
    if (name.trim() !== account.name) changes.name = name;
    if (type !== account.type) changes.type = type;
    if (Object.keys(changes).length === 0) return setEditing(false); // nothing changed: skip the request
    save.mutate(changes, { onSuccess: () => setEditing(false) });
  }

  return (
    <>
      <tr className="acct" style={isClosed ? { opacity: 0.55 } : undefined}>
        <td>
          {editing ? (
            <form id={formId} className="rename" onSubmit={onSubmit}>
              <input
                className="input"
                autoFocus
                required
                maxLength={100}
                aria-label="Account name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
              />
              <button type="submit" className="btn-neon" disabled={save.isPending}>
                Save
              </button>
              <button type="button" className="btn" onClick={() => setEditing(false)}>
                Cancel
              </button>
              {save.error && <div className="form-error">{save.error.message}</div>}
            </form>
          ) : (
            <>
              {account.name}
              <button className="icon-btn" title={`Edit ${account.name}`} aria-label={`Edit ${account.name}`} onClick={startEditing}>
                ✎
              </button>
            </>
          )}
        </td>
        <td className="muted">
          {editing ? (
            <select
              form={formId}
              className="select"
              aria-label="Account type"
              value={type}
              onChange={(e) => setType(e.target.value as AccountType)}
              onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
            >
              {Object.entries(TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          ) : (
            TYPE_LABELS[account.type]
          )}
        </td>
        <td className={`r num ${account.balance_cents < 0 ? "down" : ""}`}>{formatMoney(account.balance_cents)}</td>
        <td className="r acct-actions">
          {isClosed ? (
            <button className="btn small" disabled={reopen.isPending} onClick={() => reopen.mutate(undefined)}>
              Reopen
            </button>
          ) : (
            <>
              <button className="btn small" onClick={() => setReconciling((open) => !open)}>
                Reconcile
              </button>
              <button
                className="btn small"
                disabled={close.isPending || account.balance_cents !== 0}
                title={account.balance_cents !== 0 ? "Bring the balance to $0 first (a transfer, or reconcile to 0)" : "Close this account"}
                onClick={() => close.mutate(undefined)}
              >
                Close
              </button>
            </>
          )}
        </td>
      </tr>
      {actionError && (
        <tr>
          <td colSpan={4} className="form-error">{actionError}</td>
        </tr>
      )}
      {reconciling && !isClosed && <ReconcileRow account={account} onDone={() => setReconciling(false)} />}
    </>
  );
}

/**
 * Enter what the statement says; the server adds the difference as an adjustment.
 * For a credit card you type what you owe as a positive number, the way statements show it.
 */
function ReconcileRow({ account, onDone }: { account: Account; onDone: () => void }) {
  const owes = account.type === "credit_card";
  const [date, setDate] = useState(todayISO());
  const [amount, setAmount] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const reconcile = useSave((balance_cents: number) => api.reconcileAccount(account.id, { date, balance_cents }));

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const cents = parseMoney(amount);
    if (cents === null) return setProblem("Enter the statement balance, like 1250.00.");
    setProblem(null);
    reconcile.mutate(owes ? -cents : cents, {
      onSuccess: (r) =>
        setResult(
          r.adjustment
            ? `Added an adjustment of ${formatMoney(r.adjustment.amount_cents, { sign: true })}. ` +
                `The balance was ${formatMoney(r.previous_balance_cents)}.`
            : "Already matches. Nothing to change.",
        ),
    });
  }

  return (
    <tr className="reconcile">
      <td colSpan={4}>
        <form className="rename" onSubmit={onSubmit}>
          <span className="muted">Statement balance at the end of</span>
          <input className="input" type="date" required value={date} style={{ width: 150 }} onChange={(e) => setDate(e.target.value)} />
          <input
            className="input"
            autoFocus
            inputMode="decimal"
            placeholder={owes ? "Amount owed" : "Balance"}
            aria-label={owes ? "Amount owed" : "Balance"}
            style={{ width: 140, textAlign: "right" }}
            value={amount}
            onChange={(e) => {
              setAmount(e.target.value);
              setResult(null);
            }}
            onKeyDown={(e) => e.key === "Escape" && onDone()}
          />
          <button type="submit" className="btn-neon" disabled={reconcile.isPending}>
            Reconcile
          </button>
          <button type="button" className="btn" onClick={onDone}>
            Done
          </button>
          {result && <span className="muted" style={{ flexBasis: "100%" }}>{result}</span>}
          {(problem ?? reconcile.error?.message) && <div className="form-error">{problem ?? reconcile.error?.message}</div>}
        </form>
      </td>
    </tr>
  );
}

function total(accounts: Account[]): number {
  return accounts.reduce((sum, a) => sum + a.balance_cents, 0);
}

function AddAccount({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AccountType>("checking");
  const save = useSave(api.createAccount);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ name, type }, { onSuccess: onDone });
  }

  return (
    <form className="card form-card" onSubmit={onSubmit}>
      <h3>New account</h3>
      <div className="row">
        <label className="field">
          Name
          <input className="input" autoFocus required value={name} onChange={(e) => setName(e.target.value)} placeholder="Checking" />
        </label>
        <label className="field">
          Type
          <select className="select" value={type} onChange={(e) => setType(e.target.value as AccountType)}>
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <button type="button" className="btn" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn-neon" disabled={save.isPending}>
          Add
        </button>
      </div>
      {save.error && <p className="form-error">{save.error.message}</p>}
    </form>
  );
}
