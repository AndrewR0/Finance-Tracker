// Reading a bank's CSV export in the browser and turning it into rows the API accepts.
// Every bank's file is a little different, so the user picks which column is which
// (guessMapping makes a first guess from the header names).

/**
 * Split CSV text into rows of cells. Handles quoted cells ("Smith, John"), doubled
 * quotes inside them ("say ""hi"""), commas and line breaks inside quotes, and
 * \r\n or \n line endings. Blank lines are skipped.
 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;

  const endCell = () => {
    row.push(cell);
    cell = "";
  };
  const endRow = () => {
    endCell();
    if (row.some((c) => c.trim() !== "")) rows.push(row);
    row = [];
  };

  const source = text.replace(/^﻿/, ""); // Excel adds a byte-order mark at the start
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    if (quoted) {
      if (ch === '"' && source[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      endCell();
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && source[i + 1] === "\n") i++;
      endRow();
    } else {
      cell += ch;
    }
  }
  if (cell !== "" || row.length > 0) endRow();
  return rows;
}

/**
 * How the file's amounts are signed.
 * signed:      negative = money out (most banks, and this app).
 * flipped:     positive = money out (many credit card files).
 * by-category: every amount is positive, and the category says which way it went:
 *              income categories are money in, everything else is money out (common in
 *              hand-kept spreadsheets). Applied after names are matched, in sheet.ts.
 */
export type SignMode = "signed" | "flipped" | "by-category";

/** Which column (index) holds what. null = this file doesn't have it. */
export type Mapping = {
  date: number | null;
  payee: number | null;
  notes: number | null;
  amount: number | null; // one signed column...
  debit: number | null; // ...or money out and money in in two columns
  credit: number | null;
  // Only for your own spreadsheet. A bank file is all one account, with no categories of yours.
  account: number | null;
  category: number | null;
  subcategory: number | null;
  sign: SignMode;
};

export type Column = Exclude<keyof Mapping, "sign">;

export const EMPTY_MAPPING: Mapping = {
  date: null, payee: null, notes: null, amount: null, debit: null, credit: null,
  account: null, category: null, subcategory: null, sign: "signed",
};

// Checked in this order, and a column is used once, so "Subcategory" is claimed before
// "Category" can match it.
const PATTERNS: [Column, RegExp][] = [
  ["date", /^(transaction |trans\.? |posting |post(ed)? )?date$/i],
  ["payee", /description|payee|merchant|^name$/i],
  ["notes", /memo|notes?$/i],
  ["amount", /^amount/i],
  ["debit", /debit|withdrawal|money out/i],
  ["credit", /credit|deposit|money in/i],
  ["account", /^account( name)?$/i],
  ["subcategory", /^sub[ -]?category$/i],
  ["category", /^category$/i],
];

/** A first guess at the mapping from the header row. The user can change any of it. */
export function guessMapping(header: string[]): Mapping {
  const mapping: Mapping = { ...EMPTY_MAPPING };
  const taken = new Set<number>();
  for (const [field, pattern] of PATTERNS) {
    const index = header.findIndex((name, i) => !taken.has(i) && pattern.test(name.trim()));
    if (index !== -1) {
      mapping[field] = index;
      taken.add(index);
    }
  }
  if (mapping.amount !== null) {
    mapping.debit = null;
    mapping.credit = null;
  }
  return mapping;
}

/**
 * A date as banks write it -> "2026-10-05", or null.
 * Accepts 2026-10-05, 10/05/2026, 10/5/26 and 10-05-2026 (month first, as US banks do).
 */
export function parseCsvDate(text: string): string | null {
  const value = text.trim();
  let year: number, month: number, day: number;
  let match = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(value);
  if (match) {
    [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  } else {
    match = /^(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})$/.exec(value);
    if (!match) return null;
    [month, day, year] = [Number(match[1]), Number(match[2]), Number(match[3])];
    if (year < 100) year += 2000;
  }
  const check = new Date(year, month - 1, day);
  if (check.getFullYear() !== year || check.getMonth() !== month - 1 || check.getDate() !== day) return null; // 02/30
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/**
 * An amount as banks write it -> cents, or null. "" -> null.
 * "-12.50", "$1,234.56", "(12.50)" (accountants' negative), "12.50-", "−12.5".
 */
export function parseCsvAmount(text: string): number | null {
  let value = text.trim().replace(/[$,\s]/g, "").replace("−", "-");
  if (value === "") return null;
  let negative = false;
  if (/^\(.*\)$/.test(value)) {
    negative = true;
    value = value.slice(1, -1);
  }
  if (value.endsWith("-")) {
    negative = !negative;
    value = value.slice(0, -1);
  }
  if (value.startsWith("-")) {
    negative = !negative;
    value = value.slice(1);
  } else if (value.startsWith("+")) {
    value = value.slice(1);
  }
  const match = /^(\d*)(?:\.(\d{1,2}))?$/.exec(value);
  if (!match || (match[1] === "" && match[2] === undefined)) return null;
  const cents = Number(match[1] || "0") * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return negative ? -cents : cents;
}

export type CsvRow = {
  line: number; // 1-based line in the file, for messages
  date: string;
  amount_cents: number; // with sign: "by-category", the sign isn't final yet
  payee: string | null;
  notes: string | null;
  account: string; // "" when the file has no account column
  category: string; // "" = uncategorized
  subcategory: string;
};

/** "Food > Coffee" or "Food: Coffee" in one cell -> ["Food", "Coffee"]. Plain "Food" -> ["Food", ""]. */
export function splitCategory(text: string): [string, string] {
  const match = /^(.+?)\s*(?:>|›|:)\s*(.+)$/.exec(text.trim());
  return match ? [match[1].trim(), match[2].trim()] : [text.trim(), ""];
}

/** Turn data rows into CsvRows. Rows that can't be read become problems instead of guesses. */
export function toImportRows(
  rows: string[][],
  mapping: Mapping,
  firstLine: number,
): { rows: CsvRow[]; problems: string[] } {
  const result: CsvRow[] = [];
  const problems: string[] = [];
  const cell = (row: string[], index: number | null) => (index === null ? "" : (row[index] ?? "").trim());

  rows.forEach((row, i) => {
    const line = firstLine + i;
    const date = parseCsvDate(cell(row, mapping.date));
    if (date === null) return problems.push(`Line ${line}: can't read the date "${cell(row, mapping.date)}".`);

    let cents: number | null;
    if (mapping.amount !== null) {
      cents = parseCsvAmount(cell(row, mapping.amount));
    } else {
      // Debit is money out, credit is money in. Banks write both as positive numbers.
      const debit = parseCsvAmount(cell(row, mapping.debit));
      const credit = parseCsvAmount(cell(row, mapping.credit));
      cents = debit === null && credit === null ? null : (credit ?? 0) - Math.abs(debit ?? 0);
    }
    if (cents === null) return problems.push(`Line ${line}: no amount.`);
    if (cents === 0) return; // a $0.00 line (an authorization hold, a note): nothing to import
    if (mapping.sign === "flipped") cents = -cents;

    const payee = cell(row, mapping.payee).replace(/\s+/g, " ").slice(0, 100);
    const notes = cell(row, mapping.notes).slice(0, 500);
    // Without a subcategory column, "Food > Coffee" in the category column is split in two.
    const [category, subFromCategory] =
      mapping.subcategory === null ? splitCategory(cell(row, mapping.category)) : [cell(row, mapping.category), ""];
    const subcategory = mapping.subcategory === null ? subFromCategory : cell(row, mapping.subcategory);
    result.push({
      line,
      date,
      amount_cents: cents,
      payee: payee || null,
      notes: notes || null,
      account: cell(row, mapping.account).slice(0, 100),
      category: category.slice(0, 100),
      subcategory: category ? subcategory.slice(0, 100) : "", // a subcategory needs a category
    });
  });
  return { rows: result, problems };
}
