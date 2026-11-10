/**
 * Which payee names to suggest for what's typed so far, best match first.
 *
 * `names` holds every payee you've used (no duplicates), in the order they appear in your
 * history. Returns at most `limit` names.
 */
export function suggestPayees(names: string[], query: string, limit = 8): string[] {
  const q = query.trim().toLowerCase();
  if (q === "") return names.slice(0, limit);

  // Names that start with the query beat names that only contain it ("Star" -> Starbucks
  // before Lone Star Steakhouse). Within each group, history order is kept.
  const starts: string[] = [];
  const contains: string[] = [];
  for (const name of names) {
    const lower = name.toLowerCase();
    if (lower.startsWith(q)) starts.push(name);
    else if (lower.includes(q)) contains.push(name);
  }
  return [...starts, ...contains].slice(0, limit);
}
