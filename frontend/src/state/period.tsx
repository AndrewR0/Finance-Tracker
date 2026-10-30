// The Month / Year / All choice, shared by every page (pick "Year" on the dashboard and the
// Categories page shows the year too). React context passes it down without threading
// props through every component.

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { Period, PeriodKind } from "../api/client";
import { usePeriodRanges } from "../api/hooks";

type Choice = { kind: PeriodKind; date: string | null }; // date null = "the period containing today"

type PeriodContextValue = {
  choice: Choice;
  setKind: (kind: PeriodKind) => void;
  setDate: (date: string | null) => void;
};

const PeriodContext = createContext<PeriodContextValue | null>(null);

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [choice, setChoice] = useState<Choice>({ kind: "month", date: null });
  const value = useMemo(
    () => ({
      choice,
      setKind: (kind: PeriodKind) => setChoice((c) => ({ ...c, kind })),
      setDate: (date: string | null) => setChoice((c) => ({ ...c, date })),
    }),
    [choice],
  );
  return <PeriodContext.Provider value={value}>{children}</PeriodContext.Provider>;
}

/** The chosen period, plus its date ranges from the API (undefined until they load). */
export function usePeriod(): PeriodContextValue & { period: Period | undefined } {
  const context = useContext(PeriodContext);
  if (!context) throw new Error("usePeriod needs a <PeriodProvider> above it.");
  const { data } = usePeriodRanges(context.choice.kind, context.choice.date);
  return { ...context, period: data };
}
