// Every call to the backend goes through here.
//
// The types come from ./schema.d.ts, which is GENERATED from FastAPI's OpenAPI schema
// (npm run gen:api). Change a Pydantic schema, regenerate, and TypeScript points at
// every place in the frontend that no longer matches.

import type { components } from "./schema";

type Schemas = components["schemas"];

export type Account = Schemas["AccountWithBalance"];
export type AccountType = Schemas["AccountType"];
export type CategoryTree = Schemas["CategoryTree"];
export type CategoryKind = Schemas["CategoryKind"];
export type Transaction = Schemas["TransactionRead"];
export type Transfer = Schemas["TransferRead"];
export type PeriodKind = Schemas["PeriodKind"];
export type Period = Schemas["PeriodRead"];
export type Summary = Schemas["DashboardSummary"];
export type Change = Schemas["Change"];
export type Pace = Schemas["SpendingPace"];
export type CashFlowMonth = Schemas["CashFlowMonth"];
export type CategorySpending = Schemas["CategorySpending"];

/** The backend answered with an error. message is FastAPI's "detail", made readable. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  if (response.status === 204) return undefined as T; // DELETE: no body
  return (await response.json()) as T;
}

/** FastAPI errors are {"detail": "text"} (ours) or {"detail": [{loc, msg}, ...]} (validation). */
async function errorMessage(response: Response): Promise<string> {
  try {
    const data: { detail?: unknown } = await response.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
        .join("; ");
    }
  } catch {
    // not JSON: fall through
  }
  return `${response.status} ${response.statusText}`;
}

type QueryValue = string | number | null | undefined;

/** {start: "2026-10-01", kind: undefined} -> "?start=2026-10-01" (empty values are left out). */
function query(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export type DateRanges = {
  start: string;
  end: string;
  compare_start?: string | null;
  compare_end?: string | null;
};

export const api = {
  health: () => request<{ status: string }>("GET", "/api/health"),

  accounts: () => request<Account[]>("GET", "/api/accounts"),
  createAccount: (body: Schemas["AccountCreate"]) => request<Schemas["AccountRead"]>("POST", "/api/accounts", body),
  updateAccount: (id: number, body: Schemas["AccountUpdate"]) =>
    request<Schemas["AccountRead"]>("PATCH", `/api/accounts/${id}`, body),

  categories: (kind?: CategoryKind) => request<CategoryTree[]>("GET", "/api/categories" + query({ kind })),
  createCategory: (body: Schemas["CategoryCreate"]) =>
    request<Schemas["CategoryRead"]>("POST", "/api/categories", body),

  transactions: (filters: { account_id?: number; start?: string; end?: string } = {}) =>
    request<Transaction[]>("GET", "/api/transactions" + query(filters)),
  createTransaction: (body: Schemas["TransactionCreate"]) =>
    request<Transaction>("POST", "/api/transactions", body),
  updateTransaction: (id: number, body: Schemas["TransactionUpdate"]) =>
    request<Transaction>("PATCH", `/api/transactions/${id}`, body),
  deleteTransaction: (id: number) => request<void>("DELETE", `/api/transactions/${id}`),

  transfer: (id: number) => request<Transfer>("GET", `/api/transfers/${id}`),
  createTransfer: (body: Schemas["TransferCreate"]) => request<Transfer>("POST", "/api/transfers", body),
  updateTransfer: (id: number, body: Schemas["TransferUpdate"]) =>
    request<Transfer>("PATCH", `/api/transfers/${id}`, body),
  deleteTransfer: (id: number) => request<void>("DELETE", `/api/transfers/${id}`),

  period: (kind: PeriodKind, date: string | null) =>
    request<Period>("GET", "/api/dashboard/period" + query({ kind, date })),
  summary: (ranges: DateRanges) => request<Summary>("GET", "/api/dashboard/summary" + query(ranges)),
  pace: (kind: PeriodKind, date: string | null) =>
    request<Pace>("GET", "/api/dashboard/spending-pace" + query({ kind, date })),
  cashFlow: (end: string, months = 12) =>
    request<CashFlowMonth[]>("GET", "/api/dashboard/cash-flow" + query({ end, months })),
  spendingByCategory: (ranges: DateRanges) =>
    request<CategorySpending[]>("GET", "/api/dashboard/spending-by-category" + query(ranges)),
};
