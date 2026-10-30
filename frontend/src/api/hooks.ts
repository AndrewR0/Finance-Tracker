// React Query hooks: each one fetches, caches and refreshes one kind of data.
//
// A query key like ["summary", start, end] names a piece of cached data. Two components
// asking for the same key share one request. After any change (a mutation), useSave
// marks every cached query as stale, so whatever is on screen refetches.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type CategoryKind, type DateRanges, type Period, type PeriodKind } from "./client";

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: api.health, retry: false, refetchInterval: 15000 });
}

export function useAccounts() {
  return useQuery({ queryKey: ["accounts"], queryFn: api.accounts });
}

export function useCategories(kind?: CategoryKind) {
  return useQuery({ queryKey: ["categories", kind ?? "all"], queryFn: () => api.categories(kind) });
}

export function useTransactions(filters: { account_id?: number; start?: string; end?: string } = {}) {
  return useQuery({ queryKey: ["transactions", filters], queryFn: () => api.transactions(filters) });
}

export function useTransfer(id: number | null) {
  return useQuery({
    queryKey: ["transfer", id],
    queryFn: () => api.transfer(id as number),
    enabled: id !== null,
  });
}

export function usePeriodRanges(kind: PeriodKind, date: string | null) {
  return useQuery({
    queryKey: ["period", kind, date],
    queryFn: () => api.period(kind, date),
    placeholderData: (previous) => previous, // keep showing the old period while the new one loads
  });
}

/** The ranges every report takes, from a resolved period. */
export function rangesOf(period: Period): DateRanges {
  return {
    start: period.start,
    end: period.end,
    compare_start: period.compare_start,
    compare_end: period.compare_end,
  };
}

export function useSummary(period: Period | undefined) {
  return useQuery({
    queryKey: ["summary", period && rangesOf(period)],
    queryFn: () => api.summary(rangesOf(period as Period)),
    enabled: period !== undefined,
    placeholderData: (previous) => previous,
  });
}

export function usePace(kind: PeriodKind, date: string | null) {
  return useQuery({
    queryKey: ["pace", kind, date],
    queryFn: () => api.pace(kind, date),
    enabled: kind !== "all",
    placeholderData: (previous) => previous,
  });
}

export function useCashFlow(end: string | undefined) {
  return useQuery({
    queryKey: ["cash-flow", end],
    queryFn: () => api.cashFlow(end as string),
    enabled: end !== undefined,
    placeholderData: (previous) => previous,
  });
}

export function useSpendingByCategory(period: Period | undefined) {
  return useQuery({
    queryKey: ["spending-by-category", period && rangesOf(period)],
    queryFn: () => api.spendingByCategory(rangesOf(period as Period)),
    enabled: period !== undefined,
    placeholderData: (previous) => previous,
  });
}

/** Wrap any API call that changes data. On success, everything on screen refreshes. */
export function useSave<Args, Result>(save: (args: Args) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: save,
    onSuccess: () => queryClient.invalidateQueries(),
  });
}
