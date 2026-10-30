import { useMemo, useRef, useState, type FormEvent, type RefObject } from "react";

import { api, type CategoryKind, type CategorySpending, type CategoryTree } from "../api/client";
import { useCategories, useSave, useSpendingByCategory } from "../api/hooks";
import { ChangeBadge, changeOf } from "../components/ChangeBadge";
import { PeriodPicker } from "../components/PeriodPicker";
import { comparisonName, periodTitle } from "../lib/dates";
import { formatMoney0 } from "../lib/money";
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
              </tr>
            </thead>
            <tbody>
              {tree.length === 0 && (
                <tr className="empty-row">
                  <td colSpan={3}>No {kind} categories yet. Add one on the right.</td>
                </tr>
              )}
              {tree.map((top) => [
                <CategoryRow key={top.id} category={top} spending={spending} showSpending={showSpending} parent />,
                ...top.subcategories.map((sub) => (
                  <CategoryRow key={sub.id} category={sub} spending={spending} showSpending={showSpending} />
                )),
                <tr key={`add-${top.id}`} className="add" onClick={() => addUnder(top.id)}>
                  <td colSpan={3}>+ Add subcategory</td>
                </tr>,
              ])}
              {showSpending && spending.has("none") && (
                <CategoryRow
                  category={{ id: -1, name: "Uncategorized" }}
                  spending={spending}
                  showSpending
                  parent
                  spendingKey="none"
                />
              )}
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

type RowProps = {
  category: { id: number; name: string };
  spending: Map<number | "none", Spending>;
  showSpending: boolean;
  parent?: boolean;
  spendingKey?: number | "none";
};

function CategoryRow({ category, spending, showSpending, parent = false, spendingKey }: RowProps) {
  const numbers = spending.get(spendingKey ?? category.id) ?? { now: 0, previous: null };
  return (
    <tr className={parent ? "parent" : "child"}>
      <td>{category.name}</td>
      {showSpending && (
        <td className="r num" style={numbers.now ? undefined : { color: "var(--ink3)" }}>
          {formatMoney0(numbers.now)}
        </td>
      )}
      {showSpending && (
        <td className="r">
          <ChangeBadge change={changeOf(numbers.now, numbers.previous)} higherIsBetter={false} show="dollars" />
        </td>
      )}
    </tr>
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
        Renaming, merging and deleting categories need backend endpoints that don't exist yet.
      </p>
    </form>
  );
}
