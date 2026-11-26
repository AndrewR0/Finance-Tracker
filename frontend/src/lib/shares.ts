// Shares and prices arrive from the API as integers, like money:
//   shares: units of 1/100,000,000 of a share (bitcoin has 8 decimal places)
//   prices: units of 1/1,000,000 of a dollar
// These helpers turn them into text, and typed text into what the API accepts. No floats.

export const SHARE_DECIMALS = 8;
export const PRICE_DECIMALS = 6;

/** Integer units with `decimals` implied decimal places -> "1234.5" (trailing zeros dropped). */
function unitsToText(units: number, decimals: number, minDecimals = 0): string {
  const negative = units < 0;
  const digits = String(Math.abs(units)).padStart(decimals + 1, "0");
  const whole = digits.slice(0, -decimals);
  let fraction = digits.slice(-decimals).replace(/0+$/, "");
  fraction = fraction.padEnd(minDecimals, "0");
  const wholeText = Number(whole).toLocaleString("en-US");
  return `${negative ? "−" : ""}${wholeText}${fraction ? `.${fraction}` : ""}`;
}

/** 3841207 -> "0.03841207", 30050000000 -> "300.5". */
export function formatShares(units: number): string {
  return unitsToText(units, SHARE_DECIMALS);
}

/**
 * 123456700 -> "$123.4567", 1000000 -> "$1.00": at least 2 decimals, like money, and at most 4.
 * A price worked out from a value (142794415 -> "$142.7944") would otherwise show all 6.
 */
export function formatPrice(units: number): string {
  const rounded = Math.round(units / 100) * 100; // to 4 decimal places
  return `$${unitsToText(rounded, PRICE_DECIMALS, 2)}`;
}

/**
 * What someone typed -> a decimal string the API accepts, or null if it isn't one.
 * "1,234.5" -> "1234.5", ".5" -> "0.5", "0" -> null (must be more than 0), too many decimals -> null.
 */
export function parseDecimal(text: string, maxDecimals: number): string | null {
  const cleaned = text.replace(/[$,\s]/g, "");
  const match = /^(\d*)(?:\.(\d*))?$/.exec(cleaned);
  if (!match) return null;
  const [, whole, fraction = ""] = match;
  if (whole === "" && fraction === "") return null;
  if (fraction.length > maxDecimals) return null;
  if (/^0*$/.test(whole + fraction)) return null;
  const normalizedWhole = whole.replace(/^0+(?=\d)/, "") || "0";
  const trimmedFraction = fraction.replace(/0+$/, "");
  return trimmedFraction ? `${normalizedWhole}.${trimmedFraction}` : normalizedWhole;
}

/** Gain as a percent of cost, one decimal: (150, 1000) -> "+15.0%". Null when cost is 0. */
export function gainPercent(gainCents: number, costCents: number): string | null {
  if (costCents <= 0) return null;
  const tenths = Math.round((gainCents * 1000) / costCents);
  const sign = tenths > 0 ? "+" : tenths < 0 ? "−" : "";
  return `${sign}${(Math.abs(tenths) / 10).toFixed(1)}%`;
}
