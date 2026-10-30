import { useMemo, useRef, useState, type FormEvent } from "react";

import { api, type Account, type CategoryTree, type Transaction } from "../api/client";
import { useAccounts, useCategories, useSave, useTransactions } from "../api/hooks";
import { TransactionTable } from "../components/TransactionTable";
import { categoryOptions, indexCategories, type CategoryInfo } from "../lib/categories";
import { monthBounds, todayISO } from "../lib/dates";
import { formatMoney0, parseMoney } from "../lib/money";
import { lastCategoryByPayee, matchesSearch, moneyInOut, toRows } from "../lib/transactions";
import { usePanelActions } from "../state/panel";

export function Transactions() {
  const { open } = usePanelActions();
  const [search, setSearch] = useState("");
  const [month, setMonth] = useState(todayISO().slice(0, 7)); // "2026-10"; "" = all dates
  const [accountId, setAccountId] = useState(""); // "" = all accounts
  const [categoryFilter, setCategoryFilter] = useState(""); // "", "none", or an id

  const range = month ? monthBounds(month) : {};
  const transactions = useTransactions({ account_id: accountId ? Number(accountId) : undefined, ...range }).data;
  const accounts = useAccounts().data ?? [];
  const tree = useCategories().data ?? [];

  const accountIndex = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);
  const categories = useMemo(() => indexCategories(tree), [tree]);

  // The API filters by account and dates. Search and category are filtered here, in the browser.
  const visible = useMemo(
    () =>
      (transactions ?? []).filter(
        (tx) => matchesSearch(tx, search) && matchesCategory(tx, categoryFilter, categories),
      ),
    [transactions, search, categoryFilter, categories],
  );
  const rows = useMemo(() => toRows(visible), [visible]);
  const totals = moneyInOut(visible);

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Transactions</h1>
          <div className="sub">Click any row to edit it in the side panel</div>
        </div>
        <div className="controls">
          <button className="btn" disabled title="Coming later (feature 8)">
            Import CSV
          </button>
          <button className="btn-neon" onClick={() => open({ mode: "new", type: "expense" })}>
            + Add transaction
          </button>
        </div>
      </div>

      <div className="filters">
        <input
          className="input"
          style={{ width: 240 }}
          placeholder="Search payee or notes"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} title="Clear for all dates" />
        <select className="select" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">All accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
              {a.closed_at ? " (closed)" : ""}
            </option>
          ))}
        </select>
        <select className="select" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="">All categories</option>
          <option value="none">Uncategorized</option>
          {(["expense", "income", "transfer"] as const).map((kind) => (
            <optgroup key={kind} label={kind[0].toUpperCase() + kind.slice(1)}>
              {categoryOptions(tree, kind).map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </optgroup>
          ))}
        </select>
        <span className="totals">
          In <b className="num up">{formatMoney0(totals.in)}</b> · Out <b className="num">{formatMoney0(totals.out)}</b> · Net{" "}
          <b className={`num ${totals.in - totals.out >= 0 ? "up" : "down"}`}>
            {formatMoney0(totals.in - totals.out, { sign: true })}
          </b>
        </span>
      </div>

      <QuickAdd accounts={accounts} tree={tree} categories={categories} />

      <div className="card" style={{ padding: "4px 6px" }}>
        {transactions === undefined ? (
          <p className="muted" style={{ padding: 20 }}>Loading…</p>
        ) : (
          <TransactionTable rows={rows} accounts={accountIndex} categories={categories} variant="full" />
        )}
      </div>
    </div>
  );
}

/** A parent category also matches its subcategories: "Food" shows Groceries and Coffee too. */
function matchesCategory(tx: Transaction, filter: string, categories: Map<number, CategoryInfo>): boolean {
  if (filter === "") return true;
  if (filter === "none") return tx.category_id === null;
  if (tx.category_id === null) return false;
  const id = Number(filter);
  return tx.category_id === id || categories.get(tx.category_id)?.parentId === id;
}

type QuickAddProps = {
  accounts: Account[];
  tree: CategoryTree[];
  categories: Map<number, CategoryInfo>;
};

/** The one-line "add it fast" row. Transfers open the full panel instead. */
function QuickAdd({ accounts, tree, categories }: QuickAddProps) {
  const { open } = usePanelActions();
  const history = useTransactions().data ?? [];
  const payeeMemory = useMemo(() => lastCategoryByPayee(history), [history]);
  const payeeNames = useMemo(() => [...new Set(history.map((t) => t.payee_name).filter(Boolean))], [history]);
  const openAccounts = accounts.filter((a) => a.closed_at === null);

  const [date, setDate] = useState(todayISO());
  const [type, setType] = useState<"expense" | "income">("expense");
  const [payee, setPayee] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const payeeRef = useRef<HTMLInputElement>(null);

  const account = accountId || String(openAccounts[0]?.id ?? "");

  const save = useSave(api.createTransaction);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const cents = parseMoney(amount);
    if (cents === null || cents === 0) return setProblem("Enter an amount, like 84.12.");
    if (!account) return setProblem("Add an account first (Accounts page).");
    setProblem(null);
    save.mutate(
      {
        account_id: Number(account),
        date,
        amount_cents: type === "expense" ? -Math.abs(cents) : Math.abs(cents),
        payee: payee.trim() || null,
        category_id: categoryId ? Number(categoryId) : null,
        notes: null,
      },
      {
        onSuccess: () => {
          setPayee("");
          setCategoryId("");
          setAmount("");
          payeeRef.current?.focus(); // ready for the next one
        },
      },
    );
  }

  function onPayeeChange(name: string) {
    setPayee(name);
    const remembered = payeeMemory.get(name.trim().toLowerCase());
    if (remembered != null && categoryId === "") setCategoryId(String(remembered));
  }

  const error = problem ?? save.error?.message;

  return (
    <>
      <form className="card quick" onSubmit={onSubmit}>
        <input className="input" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        <span className="seg typeseg">
          <button type="button" className={type === "expense" ? "on" : ""} title="Expense" onClick={() => setType("expense")}>
            −
          </button>
          <button type="button" className={type === "income" ? "on" : ""} title="Income" onClick={() => setType("income")}>
            +
          </button>
          <button type="button" title="Transfer" onClick={() => open({ mode: "new", type: "transfer" })}>
            ⇄
          </button>
        </span>
        <input
          ref={payeeRef}
          className="input"
          placeholder="Payee"
          list="quick-payees"
          value={payee}
          onChange={(e) => onPayeeChange(e.target.value)}
        />
        <select className="select" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Uncategorized</option>
          {(type === "expense" ? (["expense", "income"] as const) : (["income", "expense"] as const)).map((kind) => (
            <optgroup key={kind} label={kind === "expense" ? "Expense" : "Income"}>
              {categoryOptions(tree, kind).map((c) => (
                <option key={c.id} value={c.id}>{categories.get(c.id)?.label}</option>
              ))}
            </optgroup>
          ))}
        </select>
        <select className="select" value={account} onChange={(e) => setAccountId(e.target.value)}>
          {openAccounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <input
          className="input"
          placeholder="Amount"
          inputMode="decimal"
          style={{ textAlign: "right" }}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button type="submit" className="btn-neon" disabled={save.isPending}>
          Add
        </button>
      </form>
      <datalist id="quick-payees">
        {payeeNames.map((name) => (
          <option key={name} value={name as string} />
        ))}
      </datalist>
      {error && <p className="form-error" style={{ marginTop: -4 }}>{error}</p>}
    </>
  );
}
