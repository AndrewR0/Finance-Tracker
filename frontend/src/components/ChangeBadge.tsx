import type { Change } from "../api/client";
import { changeTone } from "../lib/change";
import { formatMoney0 } from "../lib/money";

type Props = {
  change: Change | null | undefined;
  higherIsBetter: boolean;
  show?: "percent" | "dollars";
};

/** "▲ 6%" in red for spending, green for income. "—" when there's nothing to compare. */
export function ChangeBadge({ change, higherIsBetter, show = "percent" }: Props) {
  if (!change) return <span className="chg same">—</span>;

  const tone = changeTone(change.change_cents, higherIsBetter);
  if (tone === "same") return <span className="chg same">no change</span>;

  const arrow = change.change_cents > 0 ? "▲" : "▼";
  const amount =
    show === "dollars" || change.change_percent === null
      ? formatMoney0(Math.abs(change.change_cents))
      : `${Math.abs(Math.round(change.change_percent))}%`;
  return (
    <span className={`chg ${tone}`}>
      {arrow} {amount}
    </span>
  );
}

/** A Change from two plain numbers, for rows that only carry spending and previous_cents. */
export function changeOf(now: number, previous: number | null): Change | null {
  if (previous === null) return null;
  return { previous_cents: previous, change_cents: now - previous, change_percent: null };
}
