// Savings goals. Each one is funded by an account's balance; goals sharing an account
// fill top to bottom (see backend/app/goals.py). Progress is worked out on the server.

import { useState, type FormEvent } from "react";

import { api, type Account, type Goal } from "../api/client";
import { useAccounts, useGoals, useSave } from "../api/hooks";
import { formatShortDate } from "../lib/dates";
import { goalLine, moveGoal, percentOf } from "../lib/goals";
import { amountInput, centsToInput, formatMoney0, parseMoney } from "../lib/money";

export function Goals() {
  const goals = useGoals().data;
  const accounts = useAccounts().data;
  const [adding, setAdding] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const active = (goals ?? []).filter((g) => g.archived_at === null);
  const archived = (goals ?? []).filter((g) => g.archived_at !== null);
  const saved = active.reduce((sum, g) => sum + g.saved_cents, 0);
  const toGo = active.reduce((sum, g) => sum + g.target_cents - g.saved_cents, 0);
  const perMonth = active.reduce((sum, g) => sum + (g.needed_per_month_cents ?? 0), 0);

  // One card per funding account, in the order its first goal fills.
  const accountIds = [...new Set(active.map((g) => g.account_id))];
  const accountById = new Map((accounts ?? []).map((a) => [a.id, a]));

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Goals</h1>
          <div className="sub">Funded by an account's balance. Goals on the same account fill top to bottom.</div>
        </div>
        <div className="controls">
          <button className="btn-neon" onClick={() => setAdding(true)}>
            + Add goal
          </button>
        </div>
      </div>

      {adding && <GoalForm accounts={accounts ?? []} onDone={() => setAdding(false)} />}

      <div className="grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))", marginBottom: 16 }}>
        <div className="card kpi">
          <div className="lbl">Saved toward goals</div>
          <div className="val">{goals ? formatMoney0(saved) : "…"}</div>
          <div className="delta">
            {active.length} active {active.length === 1 ? "goal" : "goals"}
          </div>
        </div>
        <div className="card kpi">
          <div className="lbl">Still to save</div>
          <div className="val">{goals ? formatMoney0(toGo) : "…"}</div>
          <div className="delta">{percentOf(saved, saved + toGo)}% of the way there</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Needed per month</div>
          <div className="val">{goals ? formatMoney0(perMonth) : "…"}</div>
          <div className="delta">to hit every target date</div>
        </div>
      </div>

      {goals?.length === 0 && !adding && (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            No goals yet. Add one, like "New laptop, $2,000 by January", and link it to your savings account.
          </p>
        </div>
      )}

      <div className="goal-cards">
        {accountIds.map((accountId) => (
          <AccountGoals
            key={accountId}
            account={accountById.get(accountId)}
            goals={active.filter((g) => g.account_id === accountId)}
            allGoals={goals ?? []}
            accounts={accounts ?? []}
          />
        ))}
      </div>

      {archived.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <button className="btn" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? "Hide" : "Show"} bought ({archived.length})
          </button>
          {showArchived && (
            <div className="card" style={{ marginTop: 10 }}>
              {archived.map((g) => (
                <ArchivedGoal key={g.id} goal={g} account={accountById.get(g.account_id)} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type AccountGoalsProps = { account: Account | undefined; goals: Goal[]; allGoals: Goal[]; accounts: Account[] };

function AccountGoals({ account, goals, allGoals, accounts }: AccountGoalsProps) {
  const pace = goals[0].account_pace_cents;
  const target = goals.reduce((sum, g) => sum + g.target_cents, 0);
  const balance = account?.balance_cents ?? 0;

  return (
    <div className="card">
      <h3>
        {account?.name ?? "Account"}
        <small>
          <span className="num">{formatMoney0(balance)}</span> of {formatMoney0(target)} ·{" "}
          {pace > 0 ? (
            <span className="up">+{formatMoney0(pace)}/mo lately</span>
          ) : (
            <span className="down">not growing lately</span>
          )}
        </small>
      </h3>
      {goals.map((g, i) => (
        <GoalItem key={g.id} goal={g} first={i === 0} last={i === goals.length - 1} allGoals={allGoals} accounts={accounts} />
      ))}
    </div>
  );
}

type GoalItemProps = { goal: Goal; first: boolean; last: boolean; allGoals: Goal[]; accounts: Account[] };

function GoalItem({ goal, first, last, allGoals, accounts }: GoalItemProps) {
  const [editing, setEditing] = useState(false);
  const reorder = useSave(api.reorderGoals);
  const archive = useSave(() => api.updateGoal(goal.id, { archived: true }));
  const remove = useSave(() => api.deleteGoal(goal.id));
  const line = goalLine(goal);
  const error = reorder.error ?? archive.error ?? remove.error;

  if (editing) return <GoalForm goal={goal} accounts={accounts} onDone={() => setEditing(false)} />;

  function move(direction: -1 | 1) {
    const active = allGoals.filter((g) => g.archived_at === null);
    const order = moveGoal(active, goal.id, direction);
    // Archived goals keep their place at the end; the server wants every id.
    if (order) reorder.mutate([...order, ...allGoals.filter((g) => g.archived_at !== null).map((g) => g.id)]);
  }

  return (
    <div className={`goal ${goal.status === "done" ? "done" : ""}`}>
      <div className="top">
        {goal.name}
        <span className="num">
          {formatMoney0(goal.saved_cents)} / {formatMoney0(goal.target_cents)}
        </span>
      </div>
      <div className="t">
        <i style={{ width: `${percentOf(goal.saved_cents, goal.target_cents)}%` }} />
      </div>
      <div className="goal-foot">
        <small className={line.tone === "good" ? "up" : line.tone === "bad" ? "down" : ""}>{line.text}</small>
        <span className="goal-acts">
          <button className="btn slim" disabled={first || reorder.isPending} title="Fill this one sooner" onClick={() => move(-1)}>
            ↑
          </button>
          <button className="btn slim" disabled={last || reorder.isPending} title="Fill this one later" onClick={() => move(1)}>
            ↓
          </button>
          <button className="btn slim" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button
            className="btn slim"
            disabled={archive.isPending}
            title="You bought it: stop saving for it and free its money for the next goal"
            onClick={() => archive.mutate(undefined)}
          >
            Bought ✓
          </button>
          <button
            className="btn slim danger"
            disabled={remove.isPending}
            onClick={() => window.confirm(`Delete "${goal.name}"? Your money isn't touched.`) && remove.mutate(undefined)}
          >
            Delete
          </button>
        </span>
      </div>
      {error && <div className="form-error">{error.message}</div>}
    </div>
  );
}

function ArchivedGoal({ goal, account }: { goal: Goal; account: Account | undefined }) {
  const restore = useSave(() => api.updateGoal(goal.id, { archived: false }));
  const remove = useSave(() => api.deleteGoal(goal.id));
  return (
    <div className="goal archived">
      <div className="top">
        {goal.name}
        <span className="num">{formatMoney0(goal.target_cents)}</span>
      </div>
      <div className="goal-foot">
        <small>
          Bought {goal.archived_at ? formatShortDate(goal.archived_at.slice(0, 10)) : ""} · {account?.name}
        </small>
        <span className="goal-acts">
          <button className="btn slim" disabled={restore.isPending} title="Start saving for it again, last in line" onClick={() => restore.mutate(undefined)}>
            Restore
          </button>
          <button
            className="btn slim danger"
            disabled={remove.isPending}
            onClick={() => window.confirm(`Delete "${goal.name}" for good?`) && remove.mutate(undefined)}
          >
            Delete
          </button>
        </span>
      </div>
    </div>
  );
}

/** Add a goal (no `goal`) or edit one. Edits send only the fields that changed. */
function GoalForm({ goal, accounts, onDone }: { goal?: Goal; accounts: Account[]; onDone: () => void }) {
  const open = accounts.filter((a) => a.closed_at === null);
  const firstSavings = open.find((a) => a.type === "savings") ?? open[0];
  const [name, setName] = useState(goal?.name ?? "");
  const [accountId, setAccountId] = useState<number | undefined>(goal?.account_id ?? firstSavings?.id);
  const [amount, setAmount] = useState(goal ? centsToInput(goal.target_cents) : "");
  const [date, setDate] = useState(goal?.target_date ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const create = useSave(api.createGoal);
  const update = useSave((changes: Parameters<typeof api.updateGoal>[1]) => api.updateGoal(goal!.id, changes));
  const save = goal ? update : create;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const cents = parseMoney(amount);
    if (cents === null || cents <= 0) return setProblem("Enter how much it costs, like 2000.");
    if (accountId === undefined) return setProblem("Add a savings account first, on the Accounts page.");
    setProblem(null);
    const targetDate = date === "" ? null : date;

    if (!goal) {
      create.mutate({ name, account_id: accountId, target_cents: cents, target_date: targetDate }, { onSuccess: onDone });
      return;
    }
    const changes: Parameters<typeof api.updateGoal>[1] = {};
    if (name.trim() !== goal.name) changes.name = name;
    if (accountId !== goal.account_id) changes.account_id = accountId;
    if (cents !== goal.target_cents) changes.target_cents = cents;
    if (targetDate !== goal.target_date) changes.target_date = targetDate;
    if (Object.keys(changes).length === 0) return onDone();
    update.mutate(changes, { onSuccess: onDone });
  }

  return (
    <form className={goal ? "goal-edit" : "card form-card"} onSubmit={onSubmit}>
      {!goal && <h3>New goal</h3>}
      <div className="row">
        <label className="field">
          Saving for
          <input className="input" autoFocus required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="New laptop" />
        </label>
        <label className="field">
          Costs
          <input
            className="input"
            required
            inputMode="decimal"
            placeholder="2000"
            value={amount}
            onChange={(e) => setAmount(amountInput(e.target.value, { negative: false }))}
          />
        </label>
      </div>
      <div className="row">
        <label className="field">
          Funded by
          <select className="select" value={accountId ?? ""} onChange={(e) => setAccountId(Number(e.target.value))}>
            {open.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          By (optional)
          <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      </div>
      <div className="row" style={{ justifyContent: "flex-end" }}>
        <button type="button" className="btn" onClick={onDone}>
          Cancel
        </button>
        <button type="submit" className="btn-neon" disabled={save.isPending}>
          {goal ? "Save" : "Add"}
        </button>
      </div>
      {(problem ?? save.error?.message) && <p className="form-error">{problem ?? save.error?.message}</p>}
    </form>
  );
}
