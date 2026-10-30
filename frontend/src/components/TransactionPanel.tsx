// The slide-in panel for adding and editing transactions and transfers.
//
// Shape: TransactionPanel (always mounted, slides in and out)
//          -> PanelBody (picks the starting values for what's being edited)
//            -> PanelForm (the form itself; starts from `initial` and owns its state)
// PanelBody gets a new `key` on every open, which makes React throw the old form away
// and start fresh. That's simpler than resetting a dozen fields by hand.

import { useEffect, useMemo, useRef, useState, type FormEvent, type TransitionEvent } from "react";

import { api, type Transaction, type Transfer } from "../api/client";
import { useAccounts, useCategories, useSave, useTransactions, useTransfer } from "../api/hooks";
import { categoryOptions, indexCategories } from "../lib/categories";
import { todayISO } from "../lib/dates";
import { centsToInput, formatMoney, parseMoney } from "../lib/money";
import { lastCategoryByPayee } from "../lib/transactions";
import { usePanelActions, usePanelState, type EntryType, type PanelTarget } from "../state/panel";

type FormValues = {
  type: EntryType;
  amount: string; // what's typed, e.g. "84.12"; becomes cents on save
  date: string;
  accountId: string; // "" = use the default (first open account)
  toAccountId: string;
  payee: string;
  categoryId: string; // "" = uncategorized
  notes: string;
  description: string;
};

type Editing = { kind: "transaction" | "transfer"; id: number } | null;

export function TransactionPanel() {
  const { target, isOpen, openCount } = usePanelState();
  const { close } = usePanelActions();

  const drawerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  // A closed panel is still in the page (off-screen), so make it "inert": Tab skips its
  // fields and screen readers ignore it. (React 18 has no inert prop, so set it directly.)
  useEffect(() => {
    drawerRef.current?.toggleAttribute("inert", !isOpen);
  }, [isOpen]);

  // Focus the amount when the slide has actually finished, not on a guessed timer.
  // Focusing during the slide can make the browser scroll to the field and jerk the panel.
  function onSlideEnd(event: TransitionEvent<HTMLElement>) {
    if (!isOpen || event.target !== event.currentTarget || event.propertyName !== "transform") return;
    event.currentTarget.querySelector<HTMLInputElement>("[data-autofocus]")?.focus({ preventScroll: true });
  }

  return (
    <div className={isOpen ? "open" : ""}>
      <div className="scrim" onClick={close} />
      <aside ref={drawerRef} className="drawer" aria-label="Transaction" onTransitionEnd={onSlideEnd}>
        {target && <PanelBody key={openCount} target={target} />}
      </aside>
    </div>
  );
}

function PanelBody({ target }: { target: PanelTarget }) {
  if (target.mode === "edit-transfer") return <TransferLoader transferId={target.transferId} />;
  if (target.mode === "edit-transaction") {
    return <PanelForm initial={fromTransaction(target.tx)} editing={{ kind: "transaction", id: target.tx.id }} />;
  }
  return <PanelForm initial={blank(target.type)} editing={null} />;
}

/** Editing a transfer needs both legs, which a filtered list may not have, so fetch it. */
function TransferLoader({ transferId }: { transferId: number }) {
  const { data, error } = useTransfer(transferId);
  if (error) return <p className="form-error">{error.message}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  return <PanelForm initial={fromTransfer(data)} editing={{ kind: "transfer", id: transferId }} />;
}

function blank(type: EntryType): FormValues {
  return {
    type,
    amount: "",
    date: todayISO(),
    accountId: "",
    toAccountId: "",
    payee: "",
    categoryId: "",
    notes: "",
    description: "",
  };
}

function fromTransaction(tx: Transaction): FormValues {
  return {
    ...blank(tx.amount_cents < 0 ? "expense" : "income"),
    amount: centsToInput(tx.amount_cents),
    date: tx.date,
    accountId: String(tx.account_id),
    payee: tx.payee_name ?? "",
    categoryId: tx.category_id === null ? "" : String(tx.category_id),
    notes: tx.notes ?? "",
  };
}

function fromTransfer(transfer: Transfer): FormValues {
  return {
    ...blank("transfer"),
    amount: centsToInput(transfer.to_leg.amount_cents),
    date: transfer.to_leg.date,
    accountId: String(transfer.from_leg.account_id),
    toAccountId: String(transfer.to_leg.account_id),
    categoryId: transfer.to_leg.category_id === null ? "" : String(transfer.to_leg.category_id),
    description: transfer.description ?? "",
  };
}

function PanelForm({ initial, editing }: { initial: FormValues; editing: Editing }) {
  const { close } = usePanelActions();
  const [form, setForm] = useState(initial);
  const [problem, setProblem] = useState<string | null>(null);
  const amountRef = useRef<HTMLInputElement>(null);

  const accounts = useAccounts().data ?? [];
  const tree = useCategories().data ?? [];
  const history = useTransactions().data ?? [];

  const openAccounts = accounts.filter((a) => a.closed_at === null || String(a.id) === initial.accountId);
  const categories = useMemo(() => indexCategories(tree), [tree]);
  const payeeMemory = useMemo(() => lastCategoryByPayee(history), [history]);
  const payeeNames = useMemo(() => [...new Set(history.map((t) => t.payee_name).filter(Boolean))], [history]);

  // Defaults that depend on loaded data, worked out on every render instead of stored.
  const fromId = form.accountId || String(openAccounts[0]?.id ?? "");
  const toId = form.toAccountId || String(openAccounts.find((a) => String(a.id) !== fromId)?.id ?? "");

  const isTransfer = form.type === "transfer";
  const update = (changes: Partial<FormValues>) => setForm((f) => ({ ...f, ...changes }));

  const save = useSave(async (cents: number) => {
    const categoryId = form.categoryId === "" ? null : Number(form.categoryId);
    if (isTransfer) {
      if (editing) {
        return api.updateTransfer(editing.id, {
          date: form.date,
          amount_cents: cents,
          description: form.description.trim() || null,
          category_id: categoryId,
        });
      }
      return api.createTransfer({
        from_account_id: Number(fromId),
        to_account_id: Number(toId),
        date: form.date,
        amount_cents: cents,
        description: form.description.trim() || null,
        category_id: categoryId,
      });
    }
    const body = {
      account_id: Number(fromId),
      date: form.date,
      amount_cents: form.type === "expense" ? -cents : cents,
      payee: form.payee.trim() || null,
      category_id: categoryId,
      notes: form.notes.trim() || null,
    };
    return editing ? api.updateTransaction(editing.id, body) : api.createTransaction(body);
  });

  const remove = useSave(async () => {
    if (!editing) return;
    if (editing.kind === "transfer") await api.deleteTransfer(editing.id);
    else await api.deleteTransaction(editing.id);
  });

  function submit(addAnother: boolean) {
    const cents = parseMoney(form.amount);
    if (cents === null || cents === 0) return setProblem("Enter an amount, like 84.12.");
    if (!fromId) return setProblem("Add an account first (Accounts page).");
    if (isTransfer && (!toId || toId === fromId)) return setProblem("A transfer needs two different accounts.");
    setProblem(null);

    save.mutate(Math.abs(cents), {
      onSuccess: () => {
        if (!addAnother) return close();
        update({ amount: "", payee: "", notes: "", description: "", categoryId: "" });
        amountRef.current?.focus();
      },
    });
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit(false);
  }

  function onPayeeChange(name: string) {
    const remembered = payeeMemory.get(name.trim().toLowerCase());
    setForm((f) => ({
      ...f,
      payee: name,
      // Fill in the category this payee had last time, but never overwrite one you picked.
      categoryId: f.categoryId === "" && remembered != null ? String(remembered) : f.categoryId,
    }));
  }

  function onDelete() {
    if (!window.confirm(isTransfer ? "Delete this transfer (both sides)?" : "Delete this transaction?")) return;
    remove.mutate(undefined, { onSuccess: close });
  }

  const title = editing
    ? isTransfer ? "Edit transfer" : "Edit transaction"
    : isTransfer ? "Add transfer" : "Add transaction";
  const remembered = payeeMemory.get(form.payee.trim().toLowerCase());
  const error = problem ?? save.error?.message ?? remove.error?.message ?? null;
  const cents = parseMoney(form.amount) ?? 0;
  const busy = save.isPending || remove.isPending;

  return (
    <form className="drawer-form" onSubmit={onSubmit}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>{title}</h2>
        <button type="button" className="x" onClick={close} aria-label="Close">
          ✕
        </button>
      </div>

      <span className="seg" style={{ alignSelf: "flex-start" }}>
        {(["expense", "income", "transfer"] as const).map((type) => (
          <button
            key={type}
            type="button"
            className={form.type === type ? "on" : ""}
            // A transaction can't turn into a transfer (or back): that's a different record.
            disabled={editing !== null && (type === "transfer") !== isTransfer}
            onClick={() => update({ type, categoryId: (type === "transfer") === isTransfer ? form.categoryId : "" })}
          >
            {type[0].toUpperCase() + type.slice(1)}
          </button>
        ))}
      </span>

      <label className="field">
        Amount
        <input
          ref={amountRef}
          data-autofocus
          className="input amount"
          inputMode="decimal"
          placeholder="$ 0.00"
          value={form.amount}
          onChange={(e) => update({ amount: e.target.value })}
        />
      </label>

      {isTransfer ? (
        <>
          <label className="field">
            Date
            <input className="input" type="date" required value={form.date} onChange={(e) => update({ date: e.target.value })} />
          </label>
          <div className="two arrow">
            <label className="field">
              From
              <select className="select" value={fromId} disabled={editing !== null} onChange={(e) => update({ accountId: e.target.value })}>
                {openAccounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              {!editing && <BalanceHint accounts={accounts} id={fromId} delta={-cents} />}
            </label>
            <span style={{ color: "var(--pink-soft)", paddingBottom: 28, textShadow: "0 0 8px var(--pink)" }}>→</span>
            <label className="field">
              To
              <select className="select" value={toId} disabled={editing !== null} onChange={(e) => update({ toAccountId: e.target.value })}>
                {openAccounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              {!editing && <BalanceHint accounts={accounts} id={toId} delta={cents} />}
            </label>
          </div>
          {editing && <span className="hint">The accounts can't be changed. Delete the transfer and add it again instead.</span>}
          <label className="field">
            Description
            <input className="input" placeholder="Credit card payment" value={form.description} onChange={(e) => update({ description: e.target.value })} />
          </label>
          <label className="field">
            Category
            <select className="select" value={form.categoryId} onChange={(e) => update({ categoryId: e.target.value })}>
              <option value="">No category</option>
              {categoryOptions(tree, "transfer").map((c) => (
                <option key={c.id} value={c.id}>{c.label}</option>
              ))}
            </select>
          </label>
        </>
      ) : (
        <>
          <div className="two">
            <label className="field">
              Date
              <input className="input" type="date" required value={form.date} onChange={(e) => update({ date: e.target.value })} />
            </label>
            <label className="field">
              Account
              <select className="select" value={fromId} onChange={(e) => update({ accountId: e.target.value })}>
                {openAccounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="field">
            Payee
            <input className="input" list="payee-names" value={form.payee} onChange={(e) => onPayeeChange(e.target.value)} />
            {remembered != null && String(remembered) !== form.categoryId && (
              <span className="hint">
                Last time: <b>{categories.get(remembered)?.label}</b>
              </span>
            )}
          </label>
          <datalist id="payee-names">
            {payeeNames.map((name) => (
              <option key={name} value={name as string} />
            ))}
          </datalist>
          <label className="field">
            Category
            <select className="select" value={form.categoryId} onChange={(e) => update({ categoryId: e.target.value })}>
              <option value="">Uncategorized</option>
              {/* Your own kind first. The other kind is there for refunds: Income + Food = a refund. */}
              {(form.type === "expense" ? (["expense", "income"] as const) : (["income", "expense"] as const)).map((kind) => (
                <optgroup key={kind} label={kind === "expense" ? "Expense" : "Income"}>
                  {categoryOptions(tree, kind).map((c) => (
                    <option key={c.id} value={c.id}>{c.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="field">
            Notes
            <input className="input" placeholder="Optional" value={form.notes} onChange={(e) => update({ notes: e.target.value })} />
          </label>
        </>
      )}

      {error && <div className="form-error">{error}</div>}

      <div className="actions">
        {editing && (
          <button type="button" className="btn danger spacer" onClick={onDelete} disabled={busy}>
            Delete
          </button>
        )}
        <button type="button" className="btn" onClick={close}>
          Cancel
        </button>
        {!editing && (
          <button type="button" className="btn" onClick={() => submit(true)} disabled={busy}>
            Save &amp; add another
          </button>
        )}
        <button type="submit" className="btn-neon" disabled={busy}>
          Save
        </button>
      </div>
    </form>
  );
}

function BalanceHint({ accounts, id, delta }: { accounts: { id: number; balance_cents: number }[]; id: string; delta: number }) {
  const account = accounts.find((a) => String(a.id) === id);
  if (!account || delta === 0) return null;
  return (
    <span className="hint">
      {formatMoney(account.balance_cents)} → <b>{formatMoney(account.balance_cents + delta)}</b>
    </span>
  );
}
