import type { PeriodKind } from "../api/client";
import { usePeriod } from "../state/period";

const KINDS: { kind: PeriodKind; label: string }[] = [
  { kind: "month", label: "Month" },
  { kind: "year", label: "Year" },
  { kind: "all", label: "All" },
];

/** ‹ Month Year All ›. The arrows step through periods using the dates the API hands back. */
export function PeriodPicker({ arrows = true }: { arrows?: boolean }) {
  const { choice, setKind, setDate, period } = usePeriod();
  const isAll = choice.kind === "all";

  return (
    <span className="seg">
      {arrows && (
        <button
          title="Previous"
          disabled={isAll || !period?.previous_date}
          onClick={() => setDate(period?.previous_date ?? null)}
        >
          ‹
        </button>
      )}
      {KINDS.map(({ kind, label }) => (
        <button key={kind} className={choice.kind === kind ? "on" : ""} onClick={() => setKind(kind)}>
          {label}
        </button>
      ))}
      {arrows && (
        <button title="Next" disabled={isAll || !period?.next_date} onClick={() => setDate(period?.next_date ?? null)}>
          ›
        </button>
      )}
    </span>
  );
}
