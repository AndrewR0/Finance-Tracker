import { describe, expect, it } from "vitest";

import { suggestPayees } from "./payees";

const names = ["Lone Star Steakhouse", "Amazon", "Starbucks", "Giant", "Star Market"];

describe("suggestPayees", () => {
  it("ignores case and outside spaces", () => {
    expect(suggestPayees(names, "  AMAZ ")).toEqual(["Amazon"]);
  });

  it("puts names that start with the query first", () => {
    expect(suggestPayees(names, "star")).toEqual(["Starbucks", "Star Market", "Lone Star Steakhouse"]);
  });

  it("returns nothing when nothing matches", () => {
    expect(suggestPayees(names, "zzz")).toEqual([]);
  });

  it("never returns more than the limit", () => {
    expect(suggestPayees(names, "", 2)).toHaveLength(2);
  });
});
