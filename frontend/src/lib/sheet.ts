// Importing your own spreadsheet: matching the account and category names in the file to
// the app's, and building the request that creates whatever is new.
//
// Names are grouped ignoring case and outer spaces, so "Food" and "food " are one category.

import type { Account, AccountType, CategoryTree } from "../api/client";
import type { CsvRow, SignMode } from "./csv";

/** An existing id, or a key for a row this import will create (see Ref in the backend). */
export type Ref = number | string;

export type AccountChoice = { target: number | "new"; type: AccountType };
export type TopChoice = { target: number | "new" | "none"; kind: "income" | "expense" };
export type SubChoice = { target: number | "new" | "parent" };

export type Choices = {
  accounts: Map<string, AccountChoice>; // by account name key
  tops: Map<string, TopChoice>; // by category name key
  subs: Map<string, SubChoice>; // by "category>subcategory" key
};

export type NameCount = { key: string; name: string; rows: number; cents: number };
export type TopGroup = NameCount & { subs: NameCount[] };

export const nameKey = (name: string) => name.trim().toLowerCase();
export const subKey = (top: string, sub: string) => `${nameKey(top)}>${nameKey(sub)}`;

/** Each distinct account and category in the file, with how many rows use it, in order of first use. */
export function collectNames(rows: CsvRow[]): { accounts: NameCount[]; categories: TopGroup[] } {
  const accounts = new Map<string, NameCount>();
  const tops = new Map<string, TopGroup>();
  const count = <T extends NameCount>(map: Map<string, T>, key: string, make: () => T, cents: number) => {
    const item = map.get(key) ?? map.set(key, make()).get(key)!;
    item.rows += 1;
    item.cents += cents;
    return item;
  };

  for (const row of rows) {
    count(accounts, nameKey(row.account), () => ({ key: nameKey(row.account), name: row.account.trim(), rows: 0, cents: 0 }), row.amount_cents);
    if (!row.category) continue;
    const top = count(tops, nameKey(row.category), () => ({ key: nameKey(row.category), name: row.category.trim(), rows: 0, cents: 0, subs: [] }), row.amount_cents);
    if (!row.subcategory) continue;
    const key = subKey(row.category, row.subcategory);
    let sub = top.subs.find((s) => s.key === key);
    if (!sub) top.subs.push((sub = { key, name: row.subcategory.trim(), rows: 0, cents: 0 }));
    sub.rows += 1;
    sub.cents += row.amount_cents;
  }
  return { accounts: [...accounts.values()], categories: [...tops.values()] };
}

/**
 * A first guess at an account's type from its name, for accounts the import will create.
 * The user can change it on the Match names step.
 *
 * guessAccountType("Chase Sapphire Visa") -> "credit_card"
 * guessAccountType("Ally Savings")        -> "savings"
 * guessAccountType("Everyday")            -> "checking" (when nothing matches)
 */
export function guessAccountType(name: string): AccountType {
  // First match wins, so the order matters: "Cash Rewards Visa" is a card, not cash.
  for (const [type, words] of ACCOUNT_TYPE_WORDS) {
    if (words.test(name)) return type;
  }
  return "checking";
}

// \b keeps short words from matching inside others ("ira" in "Mirage", "cash" in "Cashmere").
const ACCOUNT_TYPE_WORDS: [AccountType, RegExp][] = [
  ["credit_card", /\b(credit|card|visa|mastercard|amex|american express|discover|sapphire)\b/i],
  ["savings", /\b(savings?|emergency|fund|reserve|hysa|money market)\b/i],
  ["brokerage", /\b(brokerage|invest(ment|ing)?s?|ira|roth|401k|403b|hsa|stocks?|fidelity|vanguard|schwab|robinhood)\b/i],
  ["cash", /\b(cash|wallet)\b/i],
];

const INCOME_WORDS = /income|salary|paycheck|payroll|wage|bonus|interest|dividend|refund|reimburse/i;

/**
 * The starting choices: names that match an existing account or category (ignoring case) use
 * it; anything else will be created. A new category's kind is guessed from its money: more in
 * than out is income. With "by-category" signs every amount is positive, so the name decides.
 */
export function defaultChoices(
  names: ReturnType<typeof collectNames>,
  accounts: Account[],
  tree: CategoryTree[],
  sign: SignMode,
): Choices {
  const choices: Choices = { accounts: new Map(), tops: new Map(), subs: new Map() };

  const open = accounts.filter((existing) => existing.closed_at === null);
  for (const a of names.accounts) {
    if (a.key === "") {
      // Rows with no account name can't create one, so they go into an existing account
      // ("new" here means "not picked yet", and the page asks for a choice).
      choices.accounts.set("", open[0] ? { target: open[0].id, type: open[0].type } : { target: "new", type: "checking" });
      continue;
    }
    const match = open.find((existing) => nameKey(existing.name) === a.key);
    choices.accounts.set(a.key, match ? { target: match.id, type: match.type } : { target: "new", type: guessAccountType(a.name) });
  }

  const usable = tree.filter((t) => t.kind !== "transfer"); // imported rows can't be transfers
  for (const top of names.categories) {
    const match = usable.find((t) => nameKey(t.name) === top.key);
    const guessedKind = (sign === "by-category" ? INCOME_WORDS.test(top.name) : top.cents > 0) ? "income" : "expense";
    choices.tops.set(top.key, match ? { target: match.id, kind: match.kind as "income" | "expense" } : { target: "new", kind: guessedKind });
    for (const sub of top.subs) {
      const subMatch = match?.subcategories.find((s) => nameKey(s.name) === nameKey(sub.name));
      choices.subs.set(sub.key, { target: subMatch ? subMatch.id : "new" });
    }
  }
  return choices;
}

/**
 * Change one top-level category's choice. Its subcategories follow: under an existing parent
 * they use that parent's subcategory with the same name (or a new one), under a new parent
 * they're all new. Returns new Choices (React state is never changed in place).
 */
export function withTop(choices: Choices, group: TopGroup, choice: TopChoice, tree: CategoryTree[]): Choices {
  const tops = new Map(choices.tops).set(group.key, choice);
  const subs = new Map(choices.subs);
  const parent = typeof choice.target === "number" ? tree.find((t) => t.id === choice.target) : undefined;
  for (const sub of group.subs) {
    const match = parent?.subcategories.find((s) => nameKey(s.name) === nameKey(sub.name));
    subs.set(sub.key, { target: match ? match.id : "new" });
  }
  return { ...choices, tops, subs };
}

export const accountRef = (name: string) => `account:${nameKey(name)}`;
const topRef = (name: string) => `category:${nameKey(name)}`;
const subRef = (top: string, sub: string) => `category:${subKey(top, sub)}`;

/** Where one row's category goes: an existing id, a new category's key, or null (uncategorized). */
export function categoryRefOf(row: Pick<CsvRow, "category" | "subcategory">, choices: Choices): Ref | null {
  if (!row.category) return null;
  const top = choices.tops.get(nameKey(row.category));
  if (!top || top.target === "none") return null;
  const parent = top.target === "new" ? topRef(row.category) : top.target;
  if (!row.subcategory) return parent;
  const sub = choices.subs.get(subKey(row.category, row.subcategory));
  if (!sub || sub.target === "parent") return parent;
  return sub.target === "new" ? subRef(row.category, row.subcategory) : sub.target;
}

/** Is this row's category income? Uncategorized counts as spending. */
function isIncome(row: CsvRow, choices: Choices): boolean {
  const top = row.category ? choices.tops.get(nameKey(row.category)) : undefined;
  return top !== undefined && top.target !== "none" && top.kind === "income";
}

/** The amount to save: as read, or with sign "by-category", money in for income and out for the rest. */
export function finalCents(row: CsvRow, choices: Choices, sign: SignMode): number {
  if (sign !== "by-category") return row.amount_cents;
  return isIncome(row, choices) ? Math.abs(row.amount_cents) : -Math.abs(row.amount_cents);
}

export type NewAccount = { key: string; name: string; type: AccountType };
export type NewCategory = { key: string; name: string; kind: "income" | "expense"; parent: Ref | null };

/** The accounts and categories the import will create, from the choices. */
export function newItems(names: ReturnType<typeof collectNames>, choices: Choices): { accounts: NewAccount[]; categories: NewCategory[] } {
  const accounts = names.accounts
    .filter((a) => a.key !== "" && choices.accounts.get(a.key)?.target === "new")
    .map((a) => ({ key: accountRef(a.name), name: a.name, type: choices.accounts.get(a.key)!.type }));

  const categories: NewCategory[] = [];
  for (const top of names.categories) {
    const choice = choices.tops.get(top.key);
    if (!choice || choice.target === "none") continue;
    if (choice.target === "new") categories.push({ key: topRef(top.name), name: top.name, kind: choice.kind, parent: null });
    const parent = choice.target === "new" ? topRef(top.name) : choice.target;
    for (const sub of top.subs) {
      if (choices.subs.get(sub.key)?.target === "new") {
        categories.push({ key: subRef(top.name, sub.name), name: sub.name, kind: choice.kind, parent });
      }
    }
  }
  return { accounts, categories };
}
