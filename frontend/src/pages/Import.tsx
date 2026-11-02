import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useAccounts, useCategories, useSave } from "../api/hooks";
import { MatchNames } from "../components/MatchNames";
import { SheetGuide } from "../components/SheetGuide";
import { categoryOptions, indexCategories } from "../lib/categories";
import { EMPTY_MAPPING, guessMapping, parseCsv, toImportRows, type Column, type CsvRow, type Mapping, type SignMode } from "../lib/csv";
import { formatShortDate } from "../lib/dates";
import { formatMoney } from "../lib/money";
import {
  accountRef,
  categoryRefOf,
  collectNames,
  defaultChoices,
  finalCents,
  nameKey,
  newItems,
  type Choices,
  type Ref,
} from "../lib/sheet";

type Source = "bank" | "sheet";
type Stage = "columns" | "names" | "review";

/** A row ready to save: amounts final, account and category resolved to ids or new keys. */
type Pending = {
  line: number;
  date: string;
  amount_cents: number;
  payee: string | null;
  notes: string | null;
  account: Ref;
  category: Ref | null;
};

/** A row on the review table: Pending, plus what the server found and what you chose. */
type Review = Pending & { duplicate: boolean; keep: boolean };

const SHOW_AT_MOST = 300; // rendering 20,000 rows of inputs would freeze the page

/**
 * Import a CSV: a bank statement (every row in one account), or your own spreadsheet
 * (each row names its account and category). Pick the file, match the columns, match the
 * names (spreadsheet only), review. Nothing is saved until the last button, and then
 * everything is saved at once.
 */
export function Import() {
  const allAccounts = useAccounts().data ?? [];
  const accounts = allAccounts.filter((a) => a.closed_at === null);
  const fullTree = useCategories().data ?? [];
  const tree = fullTree.filter((c) => c.kind !== "transfer");
  const categoryIndex = useMemo(() => indexCategories(fullTree), [fullTree]);

  const [source, setSource] = useState<Source>("bank");
  const [accountId, setAccountId] = useState("");
  const [fileName, setFileName] = useState("");
  const [table, setTable] = useState<string[][]>([]);
  const [hasHeader, setHasHeader] = useState(true);
  const [mapping, setMapping] = useState<Mapping>(EMPTY_MAPPING);
  const [stage, setStage] = useState<Stage>("columns");
  const [parsed, setParsed] = useState<CsvRow[]>([]);
  const [choices, setChoices] = useState<Choices | null>(null);
  const [review, setReview] = useState<Review[] | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [filter, setFilter] = useState<"all" | "duplicates" | "uncategorized">("all");
  const [done, setDone] = useState<{ text: string; link: string } | null>(null);

  const account = accountId || String(accounts[0]?.id ?? "");
  const header = hasHeader ? (table[0] ?? []) : (table[0] ?? []).map((_, i) => `Column ${i + 1}`);
  const dataRows = useMemo(() => (hasHeader ? table.slice(1) : table), [table, hasHeader]);
  const firstLine = hasHeader ? 2 : 1;
  const sample = useMemo(() => toImportRows(dataRows.slice(0, 3), mapping, firstLine), [dataRows, mapping, firstLine]);
  const names = useMemo(() => collectNames(parsed), [parsed]);
  const created = choices ? newItems(names, choices) : { accounts: [], categories: [] };

  const preview = useMutation({ mutationFn: api.importPreview });
  const commit = useSave(api.importCommit);

  // ---- step 1: file ----

  async function onFile(file: File | undefined) {
    if (!file) return;
    const rows = parseCsv(await file.text());
    setFileName(file.name);
    setTable(rows);
    setMapping(hasHeader && rows[0] ? guessMapping(rows[0]) : EMPTY_MAPPING);
    setStage("columns");
    setReview(null);
    setDone(null);
  }

  function switchSource(next: Source) {
    setSource(next);
    setStage("columns");
    setReview(null);
    if (next === "bank" && mapping.sign === "by-category") setMapping((m) => ({ ...m, sign: "signed" }));
  }

  // ---- step 2: columns ----

  function readRows(): CsvRow[] {
    const { rows, problems: unreadable } = toImportRows(dataRows, mapping, firstLine);
    setProblems(unreadable);
    return rows;
  }

  function toNames() {
    const rows = readRows();
    setParsed(rows);
    setChoices(defaultChoices(collectNames(rows), allAccounts, tree, mapping.sign));
    setStage("names");
  }

  // ---- review ----

  function check(pending: Pending[], suggest: boolean) {
    if (pending.length === 0) {
      setReview([]);
      setStage("review");
      return;
    }
    preview.mutate(
      {
        rows: pending.map((r) => ({
          date: r.date,
          amount_cents: r.amount_cents,
          payee: r.payee,
          notes: r.notes,
          account_id: typeof r.account === "number" ? r.account : null, // a new account has nothing to compare with
        })),
      },
      {
        // The server returns rows in the order they were sent, so index i is pending[i].
        onSuccess: (checked) => {
          setReview(
            checked.map((result, i) => ({
              ...pending[i],
              // A bank statement has no categories of yours: start from the payee's last category.
              category: suggest && pending[i].category === null ? result.suggested_category_id : pending[i].category,
              duplicate: result.duplicate,
              keep: !result.duplicate, // likely duplicates start unticked
            })),
          );
          setFilter("all");
          setStage("review");
        },
      },
    );
  }

  function checkBank() {
    const rows = readRows();
    check(rows.map((r) => ({ ...r, account: Number(account), category: null })), true);
  }

  function checkSheet() {
    if (!choices) return;
    check(
      parsed.map((r) => {
        const choice = choices.accounts.get(nameKey(r.account))!;
        return {
          line: r.line,
          date: r.date,
          amount_cents: finalCents(r, choices, mapping.sign),
          payee: r.payee,
          notes: r.notes,
          account: choice.target === "new" ? accountRef(r.account) : choice.target,
          category: categoryRefOf(r, choices),
        };
      }),
      false,
    );
  }

  function update(line: number, changes: Partial<Review>) {
    setReview((rows) => rows && rows.map((row) => (row.line === line ? { ...row, ...changes } : row)));
  }

  function save() {
    const kept = (review ?? []).filter((r) => r.keep);
    const isSheet = source === "sheet";
    // Only create what the kept rows use: skipping every row of a new account means no empty account.
    const usedAccounts = new Set(kept.map((r) => r.account));
    const usedCategories = new Set(kept.map((r) => r.category));
    const newAccounts = isSheet ? created.accounts.filter((a) => usedAccounts.has(a.key)) : [];
    // A new category is needed if a row uses it, or if it's the parent of a new one a row uses.
    const newCategories = isSheet
      ? created.categories.filter(
          (c) => usedCategories.has(c.key) || created.categories.some((sub) => sub.parent === c.key && usedCategories.has(sub.key)),
        )
      : [];
    commit.mutate(
      {
        new_accounts: newAccounts,
        new_categories: newCategories,
        rows: kept.map((r) => ({
          date: r.date,
          amount_cents: r.amount_cents,
          payee: r.payee?.trim() || null,
          notes: r.notes,
          account: r.account,
          category: r.category,
        })),
      },
      {
        onSuccess: (result) => {
          const dates = kept.map((r) => r.date).sort();
          const extras = [
            result.created_accounts && `${result.created_accounts} new account${result.created_accounts === 1 ? "" : "s"}`,
            result.created_categories && `${result.created_categories} new categor${result.created_categories === 1 ? "y" : "ies"}`,
          ].filter(Boolean);
          setDone({
            text: `Imported ${result.created} transaction${result.created === 1 ? "" : "s"}${extras.length ? `, with ${extras.join(" and ")}` : ""}.`,
            link: `/transactions?${isSheet ? "" : `account=${account}&`}when=${dates[0]}..${dates[dates.length - 1]}`,
          });
          setReview(null);
          setTable([]);
          setFileName("");
          setStage("columns");
        },
      },
    );
  }

  // ---- labels for the review table ----

  const accountName = (ref: Ref) =>
    typeof ref === "number" ? (allAccounts.find((a) => a.id === ref)?.name ?? `Account ${ref}`) : `${created.accounts.find((a) => a.key === ref)?.name ?? ref} (new)`;

  const newCategoryLabels = useMemo(() => {
    const labels = new Map<string, string>();
    for (const c of created.categories) {
      const parent = c.parent === null ? null : typeof c.parent === "number" ? categoryIndex.get(c.parent)?.name : created.categories.find((p) => p.key === c.parent)?.name;
      labels.set(c.key, `${parent ? `${parent} › ` : ""}${c.name} (new)`);
    }
    return labels;
  }, [created.categories, categoryIndex]);

  const categoryName = (ref: Ref | null) =>
    ref === null ? "Uncategorized" : typeof ref === "number" ? (categoryIndex.get(ref)?.label ?? `Category ${ref}`) : (newCategoryLabels.get(ref) ?? ref);

  // ---- render ----

  const set = (field: Column) => (value: string) => setMapping((m) => ({ ...m, [field]: value === "" ? null : Number(value) }));
  const twoColumns = mapping.amount === null && (mapping.debit !== null || mapping.credit !== null);
  const kept = review?.filter((r) => r.keep).length ?? 0;
  const duplicates = review?.filter((r) => r.duplicate).length ?? 0;
  const visible = (review ?? []).filter(
    (r) => filter === "all" || (filter === "duplicates" ? r.duplicate : r.category === null),
  );
  const blankAccountUnpicked = choices?.accounts.get("")?.target === "new";

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Import CSV</h1>
          <div className="sub">A bank statement, or your own spreadsheet saved as CSV</div>
        </div>
        <div className="controls">
          <Link className="btn" to="/transactions">
            Back to transactions
          </Link>
        </div>
      </div>

      {done && (
        <div className="card import-done">
          {done.text}{" "}
          <Link className="link" to={done.link}>
            See them →
          </Link>
        </div>
      )}

      <div className="card import-step">
        <h3>1. Choose what you're importing</h3>
        <span className="seg" style={{ marginTop: 12, display: "inline-flex" }}>
          <button className={source === "bank" ? "on" : ""} onClick={() => switchSource("bank")}>
            Bank statement
          </button>
          <button className={source === "sheet" ? "on" : ""} onClick={() => switchSource("sheet")}>
            My own spreadsheet
          </button>
        </span>
        <p className="muted" style={{ fontSize: 12.5, margin: "10px 0 0" }}>
          {source === "bank"
            ? "A CSV downloaded from your bank or card's website. Every row goes into one account; you pick categories while reviewing."
            : "Your own tracking sheet, with an account and category on each row. Accounts and categories you don't have yet can be created."}
        </p>
        {source === "sheet" && <SheetGuide />}
        <div className="import-row">
          {source === "bank" && (
            <label className="field">
              Account
              <select className="select" value={account} onChange={(e) => setAccountId(e.target.value)}>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </label>
          )}
          <label className="field">
            CSV file
            <input className="input" type="file" accept=".csv,text/csv" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={hasHeader}
              onChange={(e) => {
                setHasHeader(e.target.checked);
                setMapping(e.target.checked && table[0] ? guessMapping(table[0]) : EMPTY_MAPPING);
              }}
            />
            First row is column names
          </label>
        </div>
        {source === "bank" && accounts.length === 0 && <p className="form-error">Add an account first (Accounts page).</p>}
      </div>

      {table.length > 0 && (
        <div className="card import-step">
          <h3>
            2. Match the columns <small>{fileName} · {dataRows.length.toLocaleString()} rows</small>
          </h3>
          <div className="import-row">
            <ColumnPick label="Date" header={header} value={mapping.date} onChange={set("date")} />
            {source === "sheet" && (
              <>
                <ColumnPick label="Account" header={header} value={mapping.account} onChange={set("account")} />
                <ColumnPick label="Category" header={header} value={mapping.category} onChange={set("category")} />
                <ColumnPick label="Subcategory (optional)" header={header} value={mapping.subcategory} onChange={set("subcategory")} />
              </>
            )}
            <ColumnPick label="Payee / description" header={header} value={mapping.payee} onChange={set("payee")} />
            {!twoColumns && <ColumnPick label="Amount" header={header} value={mapping.amount} onChange={set("amount")} />}
            {mapping.amount === null && (
              <>
                <ColumnPick label="Money out (debit)" header={header} value={mapping.debit} onChange={set("debit")} />
                <ColumnPick label="Money in (credit)" header={header} value={mapping.credit} onChange={set("credit")} />
              </>
            )}
            <ColumnPick label="Notes (optional)" header={header} value={mapping.notes} onChange={set("notes")} />
            <label className="field">
              Amounts
              <select
                className="select"
                value={mapping.sign}
                onChange={(e) => setMapping((m) => ({ ...m, sign: e.target.value as SignMode }))}
              >
                <option value="signed">Negative = money out</option>
                <option value="flipped">Positive = money out (some card files)</option>
                {source === "sheet" && mapping.category !== null && (
                  <option value="by-category">All positive: the category decides</option>
                )}
              </select>
            </label>
          </div>

          <div className="import-sample">
            <div className="muted">The first rows will be read as:</div>
            {sample.rows.map((r) => (
              <div key={r.line}>
                {formatShortDate(r.date)} ·{" "}
                {source === "sheet" && (
                  <>
                    {r.account || <span className="muted">no account</span>} ·{" "}
                    {r.category ? `${r.category}${r.subcategory ? ` › ${r.subcategory}` : ""}` : <span className="muted">uncategorized</span>} ·{" "}
                  </>
                )}
                {r.payee ?? <span className="muted">no payee</span>} ·{" "}
                {mapping.sign === "by-category" ? (
                  <span className="num">{formatMoney(Math.abs(r.amount_cents))}</span>
                ) : (
                  <>
                    <span className={`num ${r.amount_cents > 0 ? "up" : ""}`}>{formatMoney(r.amount_cents, { sign: true })}</span>
                    <span className="muted">{r.amount_cents > 0 ? " (money in)" : " (money out)"}</span>
                  </>
                )}
              </div>
            ))}
            {sample.problems.map((p) => (
              <div key={p} className="form-error">{p}</div>
            ))}
          </div>

          {stage === "columns" && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
              {source === "bank" ? (
                <button className="btn-neon" disabled={!account || mapping.date === null || preview.isPending} onClick={checkBank}>
                  {preview.isPending ? "Checking…" : "Check for duplicates"}
                </button>
              ) : (
                <button className="btn-neon" disabled={mapping.date === null} onClick={toNames}>
                  Next: match names
                </button>
              )}
            </div>
          )}
          {stage !== "columns" && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
              <button className="btn" onClick={() => { setStage("columns"); setReview(null); }}>
                Change columns
              </button>
            </div>
          )}
          {preview.error && <p className="form-error">{preview.error.message}</p>}
        </div>
      )}

      {source === "sheet" && stage !== "columns" && choices && (
        <div className="card import-step">
          <h3>
            3. Match names <small>{parsed.length.toLocaleString()} rows read</small>
          </h3>
          <p className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
            Names that match yours (ignoring capitals) are already picked. Anything else will be created.
          </p>
          <MatchNames names={names} choices={choices} setChoices={setChoices} accounts={accounts} tree={tree} bySign={mapping.sign !== "by-category"} />
          {stage === "names" && (
            <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 12, marginTop: 12 }}>
              {blankAccountUnpicked && <span className="form-error">Pick an account for rows with no account.</span>}
              <span className="muted" style={{ fontSize: 12.5 }}>
                Will create {created.accounts.length} account{created.accounts.length === 1 ? "" : "s"} and{" "}
                {created.categories.length} categor{created.categories.length === 1 ? "y" : "ies"}
              </span>
              <button className="btn-neon" disabled={preview.isPending || blankAccountUnpicked} onClick={checkSheet}>
                {preview.isPending ? "Checking…" : "Check for duplicates"}
              </button>
            </div>
          )}
          {stage === "review" && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 12 }}>
              <button className="btn" onClick={() => { setStage("names"); setReview(null); }}>
                Change names
              </button>
            </div>
          )}
        </div>
      )}

      {stage === "review" && review && (
        <div className="card import-step">
          <h3>
            {source === "sheet" ? "4" : "3"}. Review{" "}
            <small>
              {review.length.toLocaleString()} rows · {duplicates.toLocaleString()} look already entered (unticked) ·{" "}
              {kept.toLocaleString()} will be imported
            </small>
          </h3>
          {problems.length > 0 && (
            <details className="import-problems">
              <summary className="form-error">
                {problems.length === 1 ? "1 row couldn't be read and will be" : `${problems.length} rows couldn't be read and will be`} skipped
              </summary>
              {problems.map((p) => (
                <div key={p} className="muted">{p}</div>
              ))}
            </details>
          )}
          <div className="filters" style={{ marginTop: 10 }}>
            <select className="select" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
              <option value="all">All rows</option>
              <option value="duplicates">Only “already entered?”</option>
              <option value="uncategorized">Only uncategorized</option>
            </select>
            {duplicates > 0 && (
              <>
                <button className="btn small" onClick={() => setReview((rows) => rows && rows.map((r) => (r.duplicate ? { ...r, keep: true } : r)))}>
                  Import duplicates too
                </button>
                <button className="btn small" onClick={() => setReview((rows) => rows && rows.map((r) => (r.duplicate ? { ...r, keep: false } : r)))}>
                  Skip duplicates
                </button>
              </>
            )}
            {visible.length > SHOW_AT_MOST && (
              <span className="muted" style={{ fontSize: 12.5 }}>
                Showing the first {SHOW_AT_MOST} of {visible.length.toLocaleString()}. All of them are imported.
              </span>
            )}
          </div>
          <table>
            <thead>
              <tr>
                <th style={{ width: 36 }} />
                <th style={{ width: 100 }}>Date</th>
                {source === "sheet" && <th style={{ width: 150 }}>Account</th>}
                <th>Payee</th>
                <th style={{ width: 230 }}>Category</th>
                <th className="r" style={{ width: 120 }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {visible.slice(0, SHOW_AT_MOST).map((row) => (
                <tr key={row.line} className={row.keep ? "" : "skipped"}>
                  <td>
                    <input type="checkbox" aria-label={`Import line ${row.line}`} checked={row.keep} onChange={(e) => update(row.line, { keep: e.target.checked })} />
                  </td>
                  <td className="d">
                    {formatShortDate(row.date)} <span className="muted">{row.date.slice(0, 4)}</span>
                  </td>
                  {source === "sheet" && <td className="muted">{accountName(row.account)}</td>}
                  <td>
                    <input
                      className="input slim"
                      value={row.payee ?? ""}
                      maxLength={100}
                      aria-label={`Payee, line ${row.line}`}
                      onChange={(e) => update(row.line, { payee: e.target.value })}
                    />
                    {row.duplicate && <span className="dup">already entered?</span>}
                  </td>
                  <td>
                    {source === "bank" ? (
                      <CategoryPick value={row.category} amount={row.amount_cents} tree={tree} onChange={(category) => update(row.line, { category })} />
                    ) : (
                      <span className={row.category === null ? "muted" : ""}>{categoryName(row.category)}</span>
                    )}
                  </td>
                  <td className={`r num ${row.amount_cents > 0 ? "up" : ""}`}>{formatMoney(row.amount_cents, { sign: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
            <button className="btn-neon" disabled={kept === 0 || commit.isPending} onClick={save}>
              {commit.isPending ? "Importing…" : `Import ${kept.toLocaleString()} transaction${kept === 1 ? "" : "s"}`}
            </button>
          </div>
          {commit.error && <p className="form-error">{commit.error.message}</p>}
        </div>
      )}
    </div>
  );
}

type PickProps = { label: string; header: string[]; value: number | null; onChange: (value: string) => void };

function ColumnPick({ label, header, value, onChange }: PickProps) {
  return (
    <label className="field">
      {label}
      <select className="select" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {header.map((name, i) => (
          <option key={i} value={i}>{name || `Column ${i + 1}`}</option>
        ))}
      </select>
    </label>
  );
}

type CategoryPickProps = { value: Ref | null; amount: number; tree: Parameters<typeof categoryOptions>[0]; onChange: (id: number | null) => void };

/** A bank row's category: money out lists expense categories first, money in lists income first. */
function CategoryPick({ value, amount, tree, onChange }: CategoryPickProps) {
  return (
    <select
      className="select slim"
      aria-label="Category"
      value={value === null ? "" : String(value)}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">Uncategorized</option>
      {(amount < 0 ? (["expense", "income"] as const) : (["income", "expense"] as const)).map((kind) => (
        <optgroup key={kind} label={kind === "expense" ? "Expense" : "Income"}>
          {categoryOptions(tree, kind).map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}
