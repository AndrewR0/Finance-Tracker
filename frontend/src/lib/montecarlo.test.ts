import { describe, expect, it } from "vitest";

import { chanceBy, normal, seededRandom, simulate } from "./montecarlo";
import { project, type Plan } from "./retirement";

const PLAN: Plan = {
  balanceCents: 10_000_000, // $100,000 (made-up)
  yearlyContributionCents: 2_000_000,
  yearlySpendingCents: 4_000_000,
  withdrawalRateBp: 400,
  realReturnBp: 700,
  currentYear: 2026,
  birthYear: 1996,
};

describe("seededRandom", () => {
  it("gives the same numbers for the same seed, in [0, 1)", () => {
    const a = seededRandom(42);
    const b = seededRandom(42);
    const draws = Array.from({ length: 1000 }, () => a());
    expect(draws.slice(0, 5)).toEqual(Array.from({ length: 5 }, () => b()));
    expect(Math.min(...draws)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...draws)).toBeLessThan(1);
  });
});

describe("normal", () => {
  it("averages about 0 with a spread of about 1", () => {
    const random = seededRandom(7);
    const draws = Array.from({ length: 20000 }, () => normal(random));
    const mean = draws.reduce((s, x) => s + x, 0) / draws.length;
    const sd = Math.sqrt(draws.reduce((s, x) => s + (x - mean) ** 2, 0) / draws.length);
    expect(Math.abs(mean)).toBeLessThan(0.03);
    expect(Math.abs(sd - 1)).toBeLessThan(0.03);
  });
});

describe("simulate", () => {
  it("with no volatility, every run is the straight-line projection", () => {
    const sim = simulate(PLAN, 0, 50, 20);
    const straight = project(PLAN);
    for (const band of sim.bands.slice(0, 19)) {
      const expected = straight.points[band.yearsFromNow].balanceCents;
      expect(band.p10).toBe(expected);
      expect(band.p90).toBe(expected);
    }
    expect(sim.medianFiYearsFromNow).toBe(straight.fiYearsFromNow);
  });

  it("with volatility, outcomes spread out around the middle", () => {
    const sim = simulate(PLAN, 1500, 1000, 30);
    const year20 = sim.bands[20];
    expect(year20.p10).toBeLessThan(year20.p50);
    expect(year20.p50).toBeLessThan(year20.p90);
  });

  it("the chance of having reached FI only goes up over time", () => {
    const sim = simulate(PLAN, 1500, 1000, 40);
    const shares = sim.bands.map((b) => b.reachedShare);
    shares.slice(1).forEach((share, i) => expect(share).toBeGreaterThanOrEqual(shares[i]));
    expect(chanceBy(sim, 0)).toBe(0);
    expect(chanceBy(sim, 40)).toBeGreaterThan(0.9);
  });

  it("is repeatable", () => {
    expect(simulate(PLAN, 1500, 200, 30)).toEqual(simulate(PLAN, 1500, 200, 30));
  });

  it("starting at or above FI counts as reached right away", () => {
    expect(chanceBy(simulate({ ...PLAN, balanceCents: 200_000_000 }, 1500, 100, 10), 0)).toBe(1);
  });
});
