// The add / edit side panel. Any page can open it; it lives once, in App.
//
// Two contexts, on purpose:
//   - actions (open, close) never change, so a component that only opens the panel
//     (the Dashboard, every table row) is NOT re-rendered when the panel opens.
//   - state (what's open) changes on every open, and only the panel itself reads it.
// With one combined context, opening the panel re-rendered the whole Dashboard, charts
// included, in the same frames the slide animation was trying to run. That was the jitter.

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import type { Transaction } from "../api/client";

export type EntryType = "expense" | "income" | "transfer";

export type PanelTarget =
  | { mode: "new"; type: EntryType }
  | { mode: "edit-transaction"; tx: Transaction }
  | { mode: "edit-transfer"; transferId: number };

type PanelActions = {
  open: (target: PanelTarget) => void;
  close: () => void;
};

type PanelState = {
  target: PanelTarget | null;
  isOpen: boolean;
  openCount: number; // changes on every open, so the form starts fresh each time
};

const ActionsContext = createContext<PanelActions | null>(null);
const StateContext = createContext<PanelState | null>(null);

export function PanelProvider({ children }: { children: ReactNode }) {
  // The target stays set after closing, so the panel still has content while it slides away.
  // It starts as a blank expense (hidden), so the form's code has already run once by the
  // first click: the first open is as smooth as the rest.
  const [state, setState] = useState<PanelState>({
    target: { mode: "new", type: "expense" },
    isOpen: false,
    openCount: 0,
  });

  const open = useCallback(
    (target: PanelTarget) => setState((s) => ({ target, isOpen: true, openCount: s.openCount + 1 })),
    [],
  );
  const close = useCallback(() => setState((s) => ({ ...s, isOpen: false })), []);
  const actions = useMemo(() => ({ open, close }), [open, close]);

  return (
    <ActionsContext.Provider value={actions}>
      <StateContext.Provider value={state}>{children}</StateContext.Provider>
    </ActionsContext.Provider>
  );
}

/** open() and close(). Safe to use anywhere: it never causes a re-render. */
export function usePanelActions(): PanelActions {
  const context = useContext(ActionsContext);
  if (!context) throw new Error("usePanelActions needs a <PanelProvider> above it.");
  return context;
}

/** What's open right now. Only the panel itself should need this. */
export function usePanelState(): PanelState {
  const context = useContext(StateContext);
  if (!context) throw new Error("usePanelState needs a <PanelProvider> above it.");
  return context;
}
