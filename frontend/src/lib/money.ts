// Money arrives from the API as integer cents. These helpers are the only place it becomes
// text, and parseMoney is the only place text becomes cents. No floats in between.

const MINUS = "−"; // typographic minus "−", like the mockup

/** 123456 -> "$1,234.56", -8412 -> "−$84.12". With sign: true, positives get a "+". */
export function formatMoney(cents: number, { sign = false } = {}): string {
  const abs = Math.abs(cents);
  const dollars = Math.floor(abs / 100).toLocaleString("en-US");
  const rest = String(abs % 100).padStart(2, "0");
  return `${prefix(cents, sign)}$${dollars}.${rest}`;
}

/** Whole dollars for big numbers on cards: 4821049 -> "$48,210". */
export function formatMoney0(cents: number, { sign = false } = {}): string {
  const dollars = Math.round(Math.abs(cents) / 100);
  // Round first, so -40 cents shows as "$0", not "−$0".
  return `${prefix(dollars === 0 ? 0 : cents, sign)}$${dollars.toLocaleString("en-US")}`;
}

/** Short axis labels: 80000 -> "$800", 150000 -> "$1.5k", 2500000 -> "$25k". */
export function formatMoneyShort(cents: number): string {
  const dollars = Math.round(Math.abs(cents) / 100);
  const sign = cents < 0 && dollars > 0 ? MINUS : "";
  if (dollars < 1000) return `${sign}$${dollars}`;
  const thousands = dollars / 1000;
  const text = thousands < 10 ? thousands.toFixed(1).replace(/\.0$/, "") : String(Math.round(thousands));
  return `${sign}$${text}k`;
}

/**
 * Round axis ticks for a chart whose values go from 0 to maxCents: about `target` steps,
 * each 1, 2, 2.5 or 5 times a power of ten. 249100 -> [0, 100000, 200000, 300000] ($0 to $3k).
 */
export function niceTicks(maxCents: number, target = 4): number[] {
  if (maxCents <= 0) return [0, 100];
  const rough = maxCents / target;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough) as number;
  const steps = Math.ceil(maxCents / step);
  return Array.from({ length: steps + 1 }, (_, i) => i * step);
}

function prefix(value: number, sign: boolean): string {
  if (value < 0) return MINUS;
  return sign && value > 0 ? "+" : "";
}

/** Cents as an editable input value: -8412 -> "84.12" (no sign, no "$", no commas). */
export function centsToInput(cents: number): string {
  const abs = Math.abs(cents);
  return `${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}

/**
 * What someone typed -> cents, or null if it isn't an amount.
 * "84.12" -> 8412, "$1,234.5" -> 123450, "12" -> 1200, "-5" -> -500, "1.234" -> null.
 */
export function parseMoney(text: string): number | null {
  const cleaned = text.replace(/[$,\s]/g, "").replace(MINUS, "-");
  const match = /^(-)?(\d*)(?:\.(\d{0,2}))?$/.exec(cleaned);
  if (!match) return null;
  const [, minus, whole, fraction] = match;
  if (whole === "" && !fraction) return null; // "", "-", "." are not amounts
  const cents = Number(whole || "0") * 100 + Number((fraction ?? "").padEnd(2, "0"));
  return minus ? -cents : cents;
}
