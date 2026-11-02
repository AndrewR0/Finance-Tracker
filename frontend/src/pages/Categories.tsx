import { useMemo, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link } from "react-router-dom";

import { api, type CategoryKind, type CategorySpending, type CategoryTree } from "../api/client";
import { useCategories, useSave, useSpendingByCategory } from "../api/hooks";
import { ChangeBadge, changeOf } from "../components/ChangeBadge";
import { PeriodPicker } from "../components/PeriodPicker";
import { comparisonName, periodTitle } from "../lib/dates";
import { formatMoney0 } from "../lib/money";
import { whenOfPeriod } from "../lib/when";
import { usePeriod } from "../state/period";

const KINDS: { kind: CategoryKind; label: string }[] = [
  { kind: "expense", label: "Expense" },
  { kind: "income", label: "Income" },
  { kind: "transfer", label: "Transfer" },
];

type Spending = { now: number; previous: number | null };

export function Categories() {
  const { period } = usePeriod();
  const [kind, setKind] = useState<CategoryKind>("expense");
  const [parentId, setParentId] = useState(""); // which parent the "new category" form adds under
  const nameRef = useRef<HTMLInputElement>(null);

  const tree = (useCategories().data ?? []).filter((c) => c.kind === kind);
  const report = useSpendingByCategory(period).data;
  const spending = useMemo(() => spendingById(report ?? []), [report]);
  const showSpending = kind === "expense"; // the API reports spending only, so far
  const vs = period && comparisonName(period);
  const shared: Shared = {
    spending,
    showSpending,
    tree,
    when: period ? whenOfPeriod(period) : "all",
    columns: showSpending ? 4 : 2,
  };

  function addUnder(id: number) {
    setParentId(String(id));
    nameRef.current?.focus();
  }

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Categories</h1>
          <div className="sub">{period ? periodTitle(period) : "…"}</div>
        </div>
        <div className="controls">
          {showSpending && <PeriodPicker />}
          <span className="seg">
            {KINDS.map((k) => (
              <button
                key={k.kind}
                className={kind === k.kind ? "on" : ""}
                onClick={() => {
                  setKind(k.kind);
                  setParentId("");
                }}
              >
                {k.label}
              </button>
            ))}
          </span>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.5fr) minmax(0, 1fr)", alignItems: "start" }}>
        <div className="card" style={{ padding: "4px 6px" }}>
          <table className="cattable">
            <thead>
              <tr>
                <th>Category</th>
                {showSpending && <th className="r">Spent</th>}
                {showSpending && <th className="r">{vs ? `vs ${vs}` : "Change"}</th>}
                <th style={{ width: 70 }} />
              </tr>
            </thead>
            <tbody>
              {tree.length === 0 && (
                <tr className="empty-row">
                  <td colSpan={shared.columns}>No {kind} categories yet. Add one on the right.</td>
                </tr>
              )}
              {tree.map((top) => [
                <CategoryRow key={top.id} category={top} hasSubcategories={top.subcategories.length > 0} {...shared} />,
                ...top.subcategories.map((sub) => <CategoryRow key={sub.id} category={sub} {...shared} />),
                <tr key={`add-${top.id}`} className="add" onClick={() => addUnder(top.id)}>
                  <td colSpan={shared.columns}>+ Add subcategory</td>
                </tr>,
              ])}
              {showSpending && spending.has("none") && <UncategorizedRow {...shared} />}
            </tbody>
          </table>
        </div>

        <AddCategory kind={kind} tree={tree} parentId={parentId} setParentId={setParentId} nameRef={nameRef} />
      </div>
    </div>
  );
}

/** {id or "none": {now, previous}} for parents (rolled up) and subcategories alike. */
function spendingById(rows: CategorySpending[]): Map<number | "none", Spending> {
  const result = new Map<number | "none", Spending>();
  for (const row of rows) {
    result.set(row.category_id ?? "none", { now: row.spending_cents, previous: row.previous_cents });
    for (const sub of row.subcategories) {
      if (sub.category_id !== null) result.set(sub.category_id, { now: sub.spending_cents, previous: sub.previous_cents });
    }
  }
  return result;
}

type Category = { id: number; name: string; kind: CategoryKind; parent_id: number | null };

type Shared = {
  spending: Map<number | "none", Spending>;
  showSpending: boolean;
  tree: CategoryTree[]; // this kind's categories, for the move and merge pickers
  when: string; // the period, for links to the Transactions page
  columns: number;
};

/** Spent and change cells, shared by real categories and the Uncategorized row. */
function SpendingCells({ numbers }: { numbers: Spending }) {
  return (
    <>
      <td className="r num" style={numbers.now ? undefined : { color: "var(--ink3)" }}>
        {formatMoney0(numbers.now)}
      </td>
      <td className="r">
        <ChangeBadge change={changeOf(numbers.now, numbers.previous)} higherIsBetter={false} show="dollars" />
      </td>
    </>
  );
}

function UncategorizedRow({ spending, when }: Shared) {
  return (
    <tr className="parent">
      <td>
        <Link className="plain-link" to={`/transactions?category=none&when=${when}`}>
          Uncategorized
        </Link>
      </td>
      <SpendingCells numbers={spending.get("none") ?? { now: 0, previous: null }} />
      <td />
    </tr>
  );
}

type RowProps = Shared & { category: Category; hasSubcategories?: boolean };

/** One category: its name links to its transactions; ✎ edits it and ✕ deletes it, in a row underneath. */
function CategoryRow({ category, hasSubcategories = false, spending, showSpending, tree, when, columns }: RowProps) {
  const [mode, setMode] = useState<"view" | "edit" | "delete">("view");
  const numbers = spending.get(category.id) ?? { now: 0, previous: null };
  const done = () => setMode("view");
  const form = { category, hasSubcategories, tree, onDone: done };

  return (
    <>
      <tr className={`${category.parent_id === null ? "parent" : "child"} catrow`}>
        <td>
          <Link className="plain-link" to={`/transactions?category=${category.id}&when=${when}`} title="See these transactions">
            {category.name}
          </Link>
        </td>
        {showSpending && <SpendingCells numbers={numbers} />}
        <td className="r acct-actions">
          <button className="icon-btn" title={`Edit ${category.name}`} aria-label={`Edit ${category.name}`} onClick={() => setMode("edit")}>
            ✎
          </button>
          <button
            className="icon-btn"
            title={`Delete ${category.name}`}
            aria-label={`Delete ${category.name}`}
            onClick={() => setMode("delete")}
          >
            ✕
          </button>
        </td>
      </tr>
      {mode !== "view" && (
        <tr className="reconcile">
          <td colSpan={columns}>{mode === "edit" ? <EditCategory {...form} /> : <DeleteCategory {...form} />}</td>
        </tr>
      )}
    </>
  );
}

type FormProps = { category: Category; hasSubcategories: boolean; tree: CategoryTree[]; onDone: () => void };

/** Rename, and move: under another parent, or up to the top level. */
function EditCategory({ category, hasSubcategories, tree, onDone }: FormProps) {
  const [name, setName] = useState(category.name);
  const [parent, setParent] = useState(category.parent_id === null ? "" : String(category.parent_id));
  const save = useSave(() => api.updateCategory(category.id, { name, parent_id: parent === "" ? null : Number(parent) }));

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate(undefined, { onSuccess: onDone });
  }

  return (
    <form className="rename" onSubmit={onSubmit}>
      <input
        className="input"
        autoFocus
        required
        maxLength={100}
        aria-label="Category name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onDone()}
      />
      {hasSubcategories ? (
        <span className="muted" style={{ fontSize: 12.5 }}>
          Has subcategories, so it stays top-level
        </span>
      ) : (
        <select className="select" aria-label="Goes under" value={parent} onChange={(e) => setParent(e.target.value)}>
          <option value="">Top level</option>
          {tree
            .filter((top) => top.id !== category.id)
            .map((top) => (
              <option key={top.id} value={top.id}>Under {top.name}</option>
            ))}
        </select>
      )}
      <button type="submit" className="btn-neon" disabled={save.isPending}>
        Save
      </button>
      <button type="button" className="btn" onClick={onDone}>
        Cancel
      </button>
      {save.error && <div className="form-error">{save.error.message}</div>}
    </form>
  );
}

/** Delete, moving its transactions to another category (a merge) or to Uncategorized. */
function DeleteCategory({ category, hasSubcategories, tree, onDone }: FormProps) {
  const [moveTo, setMoveTo] = useState("");
  const remove = useSave(() => api.deleteCategory(category.id, moveTo === "" ? null : Number(moveTo)));

  // Every category of this kind except the ones being deleted (this one and its subcategories).
  const doomed = new Set([category.id, ...(tree.find((t) => t.id === category.id)?.subcategories.map((s) => s.id) ?? [])]);
  const targets = tree
    .flatMap((top) => [
      { id: top.id, label: top.name },
      ...top.subcategories.map((sub) => ({ id: sub.id, label: `${top.name} › ${sub.name}` })),
    ])
    .filter((t) => !doomed.has(t.id));

  return (
    <div className="rename">
      <span>
        Delete <b>{category.name}</b>
        {hasSubcategories ? " and its subcategories" : ""}? Move its transactions to
      </span>
      <select className="select" aria-label="Move transactions to" value={moveTo} onChange={(e) => setMoveTo(e.target.value)}>
        <option value="">Uncategorized</option>
        {targets.map((t) => (
          <option key={t.id} value={t.id}>{t.label}</option>
        ))}
      </select>
      <button className="btn danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
        Delete
      </button>
      <button className="btn" onClick={onDone}>
        Cancel
      </button>
      {remove.error && <div className="form-error">{remove.error.message}</div>}
    </div>
  );
}

type AddProps = {
  kind: CategoryKind;
  tree: CategoryTree[];
  parentId: string;
  setParentId: (id: string) => void;
  nameRef: RefObject<HTMLInputElement>;
};

function AddCategory({ kind, tree, parentId, setParentId, nameRef }: AddProps) {
  const [name, setName] = useState("");
  const save = useSave(api.createCategory);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    save.mutate(
      { name, kind, parent_id: parentId ? Number(parentId) : null },
      { onSuccess: () => setName("") }, // keep the parent, so adding several subcategories is quick
    );
  }

  return (
    <form className="card" onSubmit={onSubmit}>
      <h3>New {kind} category</h3>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
        <label className="field">
          Name
          <input ref={nameRef} className="input" required value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          Goes under
          <select className="select" value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">Nothing (a top-level category)</option>
            {tree.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </label>
        {save.error && <p className="form-error">{save.error.message}</p>}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button type="submit" className="btn-neon" disabled={save.isPending}>
            Add category
          </button>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
        ✎ renames or moves a category. ✕ deletes it and moves its transactions to the category you pick, which is
        also how you merge two categories.
      </p>
    </form>
  );
}
