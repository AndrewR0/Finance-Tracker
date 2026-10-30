export type Tone = "good" | "bad" | "same";

/**
 * Color for a change: more spending is bad, more income or savings is good.
 * Changes under half a dollar count as "same", so a few cents don't paint a card red.
 */
export function changeTone(changeCents: number, higherIsBetter: boolean): Tone {
  if (Math.abs(changeCents) < 50) return "same";
  return changeCents > 0 === higherIsBetter ? "good" : "bad";
}
