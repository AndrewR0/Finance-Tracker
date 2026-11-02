import type { Account, AccountType, CategoryTree } from "../api/client";
import { formatMoney0 } from "../lib/money";
import { withTop, type Choices, type TopGroup, type collectNames } from "../lib/sheet";

const TYPE_LABELS: Record<AccountType, string> = {
  checking: "Checking",
  savings: "Savings",
  cash: "Cash",
  credit_card: "Credit card",
  brokerage: "Brokerage",
};

type Props = {
  names: ReturnType<typeof collectNames>;
  choices: Choices;
  setChoices: (choices: Choices) => void;
  accounts: Account[]; // open accounts
  tree: CategoryTree[]; // income and expense categories (rows can't go into transfer ones)
  bySign: boolean; // amounts are signed, so the money column means something
};

/** Step 3 of a spreadsheet import: what each account and category name in the file becomes. */
export function MatchNames({ names, choices, setChoices, accounts, tree, bySign }: Props) {
  return (
    <>
      <table className="names">
        <thead>
          <tr>
            <th>Account in your file</th>
            <th className="r" style={{ width: 70 }}>Rows</th>
            <th style={{ width: 260 }}>Goes into</th>
            <th style={{ width: 170 }}>Type</th>
          </tr>
        </thead>
        <tbody>
          {names.accounts.map((a) => {
            const choice = choices.accounts.get(a.key)!;
            const blank = a.key === "";
            const set = (next: typeof choice) => setChoices({ ...choices, accounts: new Map(choices.accounts).set(a.key, next) });
            return (
              <tr key={a.key}>
                <td>{blank ? <span className="muted">No account in the file</span> : a.name}</td>
                <td className="r muted">{a.rows}</td>
                <td>
                  <select
                    className="select slim"
                    aria-label={`Account for ${a.name || "rows with no account"}`}
                    value={String(choice.target)}
                    onChange={(e) => {
                      const target = e.target.value === "new" ? "new" : Number(e.target.value);
                      const existing = accounts.find((x) => x.id === target);
                      set({ target, type: existing?.type ?? choice.type });
                    }}
                  >
                    {!blank && <option value="new">Create “{a.name}”</option>}
                    {blank && choice.target === "new" && <option value="new">Pick an account…</option>}
                    {accounts.map((x) => (
                      <option key={x.id} value={x.id}>{x.name}</option>
                    ))}
                  </select>
                </td>
                <td>
                  {choice.target === "new" && !blank ? (
                    <select
                      className="select slim"
                      aria-label={`Type for ${a.name}`}
                      value={choice.type}
                      onChange={(e) => set({ ...choice, type: e.target.value as AccountType })}
                    >
                      {Object.entries(TYPE_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="muted">{choice.target === "new" ? "" : TYPE_LABELS[choice.type]}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {names.categories.length > 0 && (
        <table className="names" style={{ marginTop: 18 }}>
          <thead>
            <tr>
              <th>Category in your file</th>
              <th className="r" style={{ width: 70 }}>Rows</th>
              {bySign && <th className="r" style={{ width: 110 }}>Net</th>}
              <th style={{ width: 260 }}>Goes into</th>
              <th style={{ width: 170 }}>Kind</th>
            </tr>
          </thead>
          <tbody>
            {names.categories.map((group) => (
              <CategoryRows key={group.key} group={group} {...{ choices, setChoices, tree, bySign }} />
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

type RowsProps = Pick<Props, "choices" | "setChoices" | "tree" | "bySign"> & { group: TopGroup };

/** A top-level category from the file, then its subcategories. */
function CategoryRows({ group, choices, setChoices, tree, bySign }: RowsProps) {
  const choice = choices.tops.get(group.key)!;
  const parent = typeof choice.target === "number" ? tree.find((t) => t.id === choice.target) : undefined;
  const parentName = parent?.name ?? group.name;

  function pickTop(value: string) {
    const target = value === "new" || value === "none" ? value : Number(value);
    const existing = tree.find((t) => t.id === target);
    const kind = existing ? (existing.kind as "income" | "expense") : choice.kind;
    setChoices(withTop(choices, group, { target, kind }, tree));
  }

  return (
    <>
      <tr className="parent">
        <td>{group.name}</td>
        <td className="r muted">{group.rows}</td>
        {bySign && <td className={`r num ${group.cents > 0 ? "up" : ""}`}>{formatMoney0(group.cents, { sign: true })}</td>}
        <td>
          <select className="select slim" aria-label={`Category for ${group.name}`} value={String(choice.target)} onChange={(e) => pickTop(e.target.value)}>
            <option value="new">Create “{group.name}”</option>
            {(["expense", "income"] as const).map((kind) => (
              <optgroup key={kind} label={kind === "expense" ? "Expense categories" : "Income categories"}>
                {tree
                  .filter((t) => t.kind === kind)
                  .map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
              </optgroup>
            ))}
            <option value="none">Leave uncategorized</option>
          </select>
        </td>
        <td>
          {choice.target === "new" ? (
            <select
              className="select slim"
              aria-label={`Kind for ${group.name}`}
              value={choice.kind}
              onChange={(e) => setChoices({ ...choices, tops: new Map(choices.tops).set(group.key, { ...choice, kind: e.target.value as "income" | "expense" }) })}
            >
              <option value="expense">Expense</option>
              <option value="income">Income</option>
            </select>
          ) : (
            <span className="muted">{choice.target === "none" ? "" : choice.kind === "income" ? "Income" : "Expense"}</span>
          )}
        </td>
      </tr>
      {choice.target !== "none" &&
        group.subs.map((sub) => {
          const subChoice = choices.subs.get(sub.key)!;
          return (
            <tr key={sub.key} className="child">
              <td>{sub.name}</td>
              <td className="r muted">{sub.rows}</td>
              {bySign && <td className={`r num ${sub.cents > 0 ? "up" : ""}`}>{formatMoney0(sub.cents, { sign: true })}</td>}
              <td>
                <select
                  className="select slim"
                  aria-label={`Subcategory for ${group.name} › ${sub.name}`}
                  value={String(subChoice.target)}
                  onChange={(e) => {
                    const value = e.target.value;
                    const target = value === "new" || value === "parent" ? value : Number(value);
                    setChoices({ ...choices, subs: new Map(choices.subs).set(sub.key, { target }) });
                  }}
                >
                  <option value="new">Create “{parentName} › {sub.name}”</option>
                  {parent?.subcategories.map((s) => (
                    <option key={s.id} value={s.id}>{parentName} › {s.name}</option>
                  ))}
                  <option value="parent">Just “{parentName}”</option>
                </select>
              </td>
              <td />
            </tr>
          );
        })}
    </>
  );
}
