import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type RetirementInputs } from "../api/client";
import { useRetirement, useSave } from "../api/hooks";
import { COLORS } from "../lib/colors";
import { formatShortDate } from "../lib/dates";
import { centsToInput, formatMoney0, formatMoneyShort, parseMoney } from "../lib/money";
import { RUNS, chanceBy, simulate, type Simulation } from "../lib/montecarlo";
import { bpToPercent, percentToBp, project, type Projection } from "../lib/retirement";

/** The form as typed. Empty override boxes mean "use what my data says". */
type Form = {
  birthYear: string;
  retireAge: string;
  withdrawal: string;
  realReturn: string;
  volatility: string;
  spending: string;
  contribution: string;
  k401: string;
};

function formFrom(inputs: RetirementInputs): Form {
  const s = inputs.settings;
  return {
    birthYear: s.birth_year === null || s.birth_year === undefined ? "" : String(s.birth_year),
    retireAge: s.retire_age === null || s.retire_age === undefined ? "" : String(s.retire_age),
    withdrawal: bpToPercent(s.withdrawal_rate_bp ?? 400),
    realReturn: bpToPercent(s.real_return_bp ?? 700),
    volatility: bpToPercent(s.volatility_bp ?? 1500),
    spending: s.spending_override_cents == null ? "" : centsToInput(s.spending_override_cents),
    contribution: s.contribution_override_cents == null ? "" : centsToInput(s.contribution_override_cents),
    k401: s.k401_yearly_cents ? centsToInput(s.k401_yearly_cents) : "",
  };
}

/** What the form means, or the first problem with it. */
function readForm(form: Form, thisYear: number) {
  const whole = (text: string) => (/^\s*\d+\s*$/.test(text) ? Number(text) : null);
  const birthYear = form.birthYear.trim() === "" ? null : whole(form.birthYear);
  if (form.birthYear.trim() !== "" && (birthYear === null || birthYear < 1900 || birthYear > thisYear))
    return { problem: "Birth year should look like 1995." } as const;
  const retireAge = form.retireAge.trim() === "" ? null : whole(form.retireAge);
  if (form.retireAge.trim() !== "" && (retireAge === null || retireAge < 18 || retireAge > 100))
    return { problem: "Retirement age should be between 18 and 100." } as const;
  const withdrawal = percentToBp(form.withdrawal);
  if (withdrawal === null || withdrawal < 50 || withdrawal > 2000)
    return { problem: "Withdrawal rate should be between 0.5% and 20%." } as const;
  const realReturn = percentToBp(form.realReturn);
  if (realReturn === null || realReturn < -500 || realReturn > 2000)
    return { problem: "Return should be between -5% and 20%." } as const;
  const volatility = percentToBp(form.volatility);
  if (volatility === null || volatility < 0 || volatility > 5000)
    return { problem: "Volatility should be between 0% and 50%." } as const;
  const money = (text: string) => (text.trim() === "" ? null : parseMoney(text));
  const spending = money(form.spending);
  const contribution = money(form.contribution);
  const k401 = money(form.k401) ?? 0;
  for (const [value, text] of [[spending, form.spending], [contribution, form.contribution], [k401, form.k401]] as const) {
    if (text.trim() !== "" && (value === null || value < 0)) return { problem: "Amounts should be dollars, like 40000." } as const;
  }
  return {
    settings: {
      birth_year: birthYear,
      retire_age: retireAge,
      withdrawal_rate_bp: withdrawal,
      real_return_bp: realReturn,
      volatility_bp: volatility,
      spending_override_cents: spending,
      contribution_override_cents: contribution,
      k401_yearly_cents: k401,
    },
  } as const;
}

export function Retirement() {
  const inputs = useRetirement().data;
  const [form, setForm] = useState<Form | null>(null);
  const save = useSave(api.saveRetirementSettings);
  const thisYear = new Date().getFullYear();

  // Fill the form once the saved settings arrive (and again after a save).
  useEffect(() => {
    if (inputs) setForm(formFrom(inputs));
  }, [inputs]);

  const read = form ? readForm(form, thisYear) : null;
  const settings = read && "settings" in read ? read.settings : null;

  const plan = useMemo(() => {
    if (!inputs || !settings) return null;
    const k401 = settings.k401_yearly_cents || inputs.k401_12m_cents;
    const actualContribution = inputs.invested_12m_cents + k401;
    const spending = settings.spending_override_cents ?? inputs.spending_12m_cents;
    const contribution = settings.contribution_override_cents ?? actualContribution;
    const base = {
      balanceCents: inputs.balance_cents,
      yearlyContributionCents: contribution,
      yearlySpendingCents: spending,
      withdrawalRateBp: settings.withdrawal_rate_bp,
      realReturnBp: settings.real_return_bp,
      currentYear: thisYear,
      birthYear: settings.birth_year,
    };
    return {
      actualContribution,
      spending,
      contribution,
      projection: project(base),
      simulation: simulate(base, settings.volatility_bp),
    };
  }, [inputs, settings, thisYear]);

  if (!inputs || !form) {
    return (
      <div className="page on">
        <div className="empty">Loading…</div>
      </div>
    );
  }

  const set = (changes: Partial<Form>) => setForm({ ...form, ...changes });
  const dirty = JSON.stringify(form) !== JSON.stringify(formFrom(inputs));

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (settings) save.mutate(settings);
  }

  return (
    <div className="page on">
      <div className="head">
        <div>
          <h1>Retirement</h1>
          <div className="sub">How much you need, and when you get there, in today's dollars</div>
        </div>
      </div>

      {plan && <Results plan={plan} inputs={inputs} birthYear={settings?.birth_year ?? null} retireAge={settings?.retire_age ?? null} />}

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", alignItems: "start" }}>
        <form className="card retire-form" onSubmit={onSubmit}>
          <h3>Assumptions</h3>
          <div className="retire-fields">
            <label className="field">
              Birth year
              <input className="input" inputMode="numeric" placeholder="e.g. 1995" value={form.birthYear} onChange={(e) => set({ birthYear: e.target.value })} />
            </label>
            <label className="field">
              Retire at age <span className="muted">(optional)</span>
              <input className="input" inputMode="numeric" placeholder="e.g. 55" value={form.retireAge} onChange={(e) => set({ retireAge: e.target.value })} />
            </label>
            <label className="field" title="The share of your balance you'd take out each year. 4% is the classic rule of thumb.">
              Withdrawal rate %
              <input className="input" inputMode="decimal" value={form.withdrawal} onChange={(e) => set({ withdrawal: e.target.value })} />
            </label>
            <label className="field" title="Yearly growth after inflation. 7% is a common long-run stock-market guess; 5% is more cautious.">
              Return after inflation %
              <input className="input" inputMode="decimal" value={form.realReturn} onChange={(e) => set({ realReturn: e.target.value })} />
            </label>
            <label className="field" title="How much a year's return swings around the average (one standard deviation). Stocks have historically been 15-20%; a mix with bonds is lower.">
              Volatility %
              <input className="input" inputMode="decimal" value={form.volatility} onChange={(e) => set({ volatility: e.target.value })} />
            </label>
            <label className="field">
              Yearly spending in retirement
              <input
                className="input"
                inputMode="decimal"
                placeholder={`${formatMoney0(inputs.spending_12m_cents)} (your last 12 months)`}
                value={form.spending}
                onChange={(e) => set({ spending: e.target.value })}
              />
            </label>
            <label className="field">
              401k per year (payroll + match)
              <input
                className="input"
                inputMode="decimal"
                placeholder={inputs.k401_12m_cents ? `${formatMoney0(inputs.k401_12m_cents)} (recorded)` : "$0"}
                value={form.k401}
                onChange={(e) => set({ k401: e.target.value })}
              />
            </label>
            <label className="field">
              Yearly contributions, all accounts
              <input
                className="input"
                inputMode="decimal"
                placeholder={`${formatMoney0(plan?.actualContribution ?? 0)} (from your data)`}
                value={form.contribution}
                onChange={(e) => set({ contribution: e.target.value })}
              />
            </label>
          </div>
          <p className="muted" style={{ fontSize: 12.5 }}>
            Leave spending or contributions empty to use your data: {formatShortDate(inputs.period_start)}{" "}
            {inputs.period_start.slice(0, 4)} to today. Contributions = transfers into investment accounts (
            {formatMoney0(inputs.invested_12m_cents)}) + 401k.
          </p>
          {read && "problem" in read && <p className="form-error">{read.problem}</p>}
          {save.error && <p className="form-error">{save.error.message}</p>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn" disabled={!dirty} onClick={() => setForm(formFrom(inputs))}>
              Reset
            </button>
            <button type="submit" className="btn-neon" disabled={!dirty || !settings || save.isPending}>
              {dirty ? "Save" : "Saved"}
            </button>
          </div>
        </form>

        <div className="card">
          <h3>What's counted today</h3>
          <table className="accttable kvtable">
            <tbody>
              {inputs.accounts.map((a) => (
                <tr key={a.account_id}>
                  <td>
                    {a.name}
                    {!a.in_net_worth && <span className="muted"> · retirement</span>}
                  </td>
                  <td className="r num">{formatMoney0(a.value_cents)}</td>
                </tr>
              ))}
              <tr className="total">
                <td>Invested today</td>
                <td className="r num">{formatMoney0(inputs.balance_cents)}</td>
              </tr>
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: 12.5 }}>
            All Brokerage and Retirement accounts at market value. Both views assume the same spending and
            contributions every year, in today's dollars. Pre-tax 401k money is counted in full here, though
            withdrawals from it will be taxed.
          </p>
        </div>
      </div>
    </div>
  );
}

type PlanResult = { spending: number; contribution: number; projection: Projection; simulation: Simulation };

/** "age 43" or "in 17 years", for a number of years from now. */
function whenText(plan: PlanResult, yearsFromNow: number): string {
  const band = plan.simulation.bands[Math.min(yearsFromNow, plan.simulation.bands.length - 1)];
  return band.age !== null ? `age ${band.age}` : `in ${yearsFromNow} years`;
}

function Results({ plan, inputs, birthYear, retireAge }: { plan: PlanResult; inputs: RetirementInputs; birthYear: number | null; retireAge: number | null }) {
  const { projection, simulation } = plan;
  const fi = projection.fiYearsFromNow;
  const fiPoint = fi === null ? null : projection.points[fi];
  const progress = projection.fiNumberCents > 0 ? Math.min(100, Math.round((inputs.balance_cents / projection.fiNumberCents) * 100)) : 100;
  const when =
    fiPoint === null
      ? "Not within 60 years"
      : fi === 0
        ? "You're there"
        : fiPoint.age !== null
          ? `Age ${fiPoint.age} (${fiPoint.year})`
          : `In ${fi} years (${fiPoint.year})`;
  const retireYears = retireAge !== null && birthYear !== null ? retireAge - (projection.points[0].year - birthYear) : null;
  const atRetireAge = retireYears !== null && retireYears >= 0 ? projection.points.find((p) => p.yearsFromNow === retireYears) : undefined;

  // Monte Carlo answers
  const percent = (share: number) => `${Math.round(share * 100)}%`;
  const ninety = simulation.bands.find((b) => b.reachedShare >= 0.9);
  const chanceAtStraightLine = fi === null ? null : chanceBy(simulation, fi);
  const chanceAtRetire = retireYears !== null && retireYears >= 0 ? chanceBy(simulation, retireYears) : null;
  const chartYears = Math.min(simulation.bands.length - 1, Math.max(projection.points.length - 1, (ninety?.yearsFromNow ?? 40) + 3));

  return (
    <>
      <div className="grid" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))", marginBottom: 16 }}>
        <div className="card kpi">
          <div className="lbl">FI number</div>
          <div className="val">{formatMoney0(projection.fiNumberCents)}</div>
          <div className="delta">{formatMoney0(plan.spending)} a year ÷ withdrawal rate</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Invested today</div>
          <div className="val">{formatMoney0(inputs.balance_cents)}</div>
          <div className="delta">{progress}% of the way</div>
        </div>
        <div className="card kpi">
          <div className="lbl">Adding each year</div>
          <div className="val">{formatMoney0(plan.contribution)}</div>
          <div className="delta">contributions</div>
        </div>
        <div className="card kpi">
          <div className="lbl">You reach it (steady returns)</div>
          <div className={`val ${fiPoint ? "up" : "down"}`} style={{ fontSize: 22 }}>{when}</div>
          <div className="delta">
            {atRetireAge
              ? `At ${retireAge}: ${formatMoney0(atRetireAge.balanceCents)} (${Math.round((atRetireAge.balanceCents / projection.fiNumberCents) * 100)}% of FI)`
              : "if every year returns exactly the average"}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>With ups and downs ({RUNS.toLocaleString("en-US")} simulated markets)</h3>
        <div className="compare-numbers">
          {chanceAtRetire !== null && (
            <div>
              <div className="muted">Chance of FI by your target, {retireAge}</div>
              <b className={`num ${chanceAtRetire >= 0.8 ? "up" : chanceAtRetire < 0.5 ? "down" : ""}`}>{percent(chanceAtRetire)}</b>
            </div>
          )}
          {chanceAtStraightLine !== null && fi !== null && fi > 0 && (
            <div>
              <div className="muted">Chance by {whenText(plan, fi)} (the steady-return date)</div>
              <b className="num">{percent(chanceAtStraightLine)}</b>
            </div>
          )}
          <div>
            <div className="muted">Half of the runs get there by</div>
            <b className="num">{simulation.medianFiYearsFromNow === null ? "—" : whenText(plan, simulation.medianFiYearsFromNow)}</b>
          </div>
          <div>
            <div className="muted">9 in 10 runs get there by</div>
            <b className="num">{ninety ? whenText(plan, ninety.yearsFromNow) : "not within 60 years"}</b>
          </div>
        </div>
        <ProjectionChart projection={projection} simulation={simulation} years={chartYears} retireYears={atRetireAge ? retireYears : null} />
        <p className="muted" style={{ fontSize: 12.5, marginBottom: 0 }}>
          The band covers the middle 80% of runs (from the 10th to the 90th percentile); the solid line is the middle
          run, the dashed one steady returns. Each run draws every year's return at random around your average, with
          the volatility as its spread. Even the same average can arrive years apart, depending on when the bad years
          land.
        </p>
      </div>
    </>
  );
}

function ProjectionChart({ projection, simulation, years, retireYears }: { projection: Projection; simulation: Simulation; years: number; retireYears: number | null }) {
  const byAge = simulation.bands[0].age !== null;
  const data = simulation.bands.slice(0, years + 1).map((b) => ({
    x: byAge ? (b.age as number) : b.yearsFromNow,
    year: b.year,
    band: [b.p10, b.p90] as [number, number],
    p10: b.p10,
    p90: b.p90,
    median: b.p50,
    steady: projection.points[b.yearsFromNow]?.balanceCents ?? null,
    reached: b.reachedShare,
  }));
  const retireX = retireYears === null ? null : byAge ? data[0].x + retireYears : retireYears;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={COLORS.grid} />
        <XAxis
          dataKey="x"
          tick={{ fill: COLORS.axis, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(x: number) => (byAge ? `${x}` : x === 0 ? "now" : `+${x}y`)}
          minTickGap={24}
        />
        <YAxis tickFormatter={(c: number) => formatMoneyShort(c)} tick={{ fill: COLORS.axis, fontSize: 12 }} axisLine={false} tickLine={false} width={56} />
        <Tooltip
          cursor={{ stroke: COLORS.axis, strokeDasharray: "2 3" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as (typeof data)[number];
            return (
              <div className="chart-tip">
                <b>{byAge ? `Age ${p.x}` : `In ${p.x} years`} · {p.year}</b>
                <br />
                Bad markets (10th pct): {formatMoney0(p.p10)}
                <br />
                Middle run: {formatMoney0(p.median)}
                <br />
                Good markets (90th pct): {formatMoney0(p.p90)}
                {p.steady !== null && (
                  <>
                    <br />
                    Steady returns: {formatMoney0(p.steady)}
                  </>
                )}
                <br />
                Reached FI: {Math.round(p.reached * 100)}% of runs
              </div>
            );
          }}
        />
        <Area type="monotone" dataKey="band" stroke="none" fill={COLORS.blue} fillOpacity={0.15} isAnimationActive={false} />
        <ReferenceLine y={projection.fiNumberCents} stroke={COLORS.pink} strokeDasharray="5 4" label={{ value: "FI number", fill: COLORS.pink, fontSize: 12, position: "insideTopLeft" }} />
        {retireX !== null && <ReferenceLine x={retireX} stroke={COLORS.bench} strokeDasharray="3 3" />}
        <Line type="monotone" dataKey="steady" stroke={COLORS.axis} strokeWidth={1.5} strokeDasharray="4 4" dot={false} isAnimationActive={false} connectNulls={false} />
        <Line type="monotone" dataKey="median" stroke={COLORS.blue} strokeWidth={2.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
