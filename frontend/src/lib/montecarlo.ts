// Monte Carlo: run the projection many times with a random return each year, and look at the
// spread of outcomes instead of one straight line.
//
// Each year's return is drawn from a bell curve (normal distribution) centred on the expected
// real return, with the volatility as its standard deviation. A fixed seed makes the "random"
// numbers the same every time, so the page doesn't jitter and tests are repeatable.

import { MAX_YEARS, fiNumber, type Plan } from "./retirement";

export const RUNS = 1000;
const SEED = 20261126;

/** A small, fast, seeded pseudo-random generator ("mulberry32"): numbers in [0, 1). */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A standard normal draw (mean 0, standard deviation 1), from two uniform draws (Box-Muller). */
export function normal(random: () => number): number {
  const u = 1 - random(); // (0, 1]: log(0) would be -Infinity
  const v = random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

export type Band = {
  yearsFromNow: number;
  year: number;
  age: number | null;
  p10: number; // 1 run in 10 ends up below this (a bad stretch of markets)
  p50: number; // the middle run
  p90: number; // 1 run in 10 ends up above this
  reachedShare: number; // share of runs at or above the FI number by this year, 0 to 1
};

export type Simulation = {
  fiNumberCents: number;
  bands: Band[];
  medianFiYearsFromNow: number | null; // when half the runs have reached FI
};

/** The value below which `share` of the sorted numbers fall. */
function percentile(sorted: number[], share: number): number {
  const index = Math.min(sorted.length - 1, Math.max(0, Math.round(share * (sorted.length - 1))));
  return sorted[index];
}

/**
 * Simulate `runs` futures for `years` years. Each year: balance x (1 + random return) + contribution.
 * A return can't go below -90%, so one draw from far in the tail can't wipe a run out entirely.
 */
export function simulate(plan: Plan, volatilityBp: number, runs = RUNS, years = MAX_YEARS, seed = SEED): Simulation {
  const target = fiNumber(plan.yearlySpendingCents, plan.withdrawalRateBp);
  const mean = plan.realReturnBp / 10000;
  const spread = volatilityBp / 10000;
  const random = seededRandom(seed);

  // balances[year][run]
  const balances: number[][] = Array.from({ length: years + 1 }, () => new Array<number>(runs));
  const firstReached: (number | null)[] = new Array(runs).fill(null);
  for (let run = 0; run < runs; run++) {
    let balance = plan.balanceCents;
    balances[0][run] = balance;
    if (balance >= target) firstReached[run] = 0;
    for (let year = 1; year <= years; year++) {
      const yearReturn = Math.max(-0.9, mean + spread * normal(random));
      balance = balance * (1 + yearReturn) + plan.yearlyContributionCents;
      balances[year][run] = balance;
      if (firstReached[run] === null && balance >= target) firstReached[run] = year;
    }
  }

  const bands: Band[] = balances.map((values, yearsFromNow) => {
    const sorted = [...values].sort((a, b) => a - b);
    const reached = firstReached.filter((y) => y !== null && y <= yearsFromNow).length;
    return {
      yearsFromNow,
      year: plan.currentYear + yearsFromNow,
      age: plan.birthYear === null ? null : plan.currentYear + yearsFromNow - plan.birthYear,
      p10: Math.round(percentile(sorted, 0.1)),
      p50: Math.round(percentile(sorted, 0.5)),
      p90: Math.round(percentile(sorted, 0.9)),
      reachedShare: reached / runs,
    };
  });
  const median = bands.find((b) => b.reachedShare >= 0.5);
  return { fiNumberCents: target, bands, medianFiYearsFromNow: median ? median.yearsFromNow : null };
}

/** Chance (0 to 1) of having reached FI by this many years from now. */
export function chanceBy(simulation: Simulation, yearsFromNow: number): number {
  const band = simulation.bands[Math.min(yearsFromNow, simulation.bands.length - 1)];
  return yearsFromNow < 0 ? 0 : band.reachedShare;
}
