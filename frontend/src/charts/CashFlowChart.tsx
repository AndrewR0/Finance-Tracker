import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { CashFlowMonth } from "../api/client";
import { COLORS } from "../lib/colors";
import { monthLabel } from "../lib/dates";
import { formatMoney0, formatMoneyShort, niceTicks } from "../lib/money";

/** Income (blue) and spending (pink) side by side for each month. */
export function CashFlowChart({ months }: { months: CashFlowMonth[] }) {
  const data = months.map((m) => ({ ...m, label: monthLabel(m.month) }));
  // Income can dip below zero (a paycheck correction); then let Recharts pick the axis.
  const lowest = Math.min(0, ...months.map((m) => Math.min(m.income_cents, m.spending_cents)));
  const ticks = lowest < 0 ? undefined : niceTicks(Math.max(...months.map((m) => Math.max(m.income_cents, m.spending_cents))));

  return (
    <div className="cash">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 10, right: 4, bottom: 0, left: 0 }} barGap={2}>
          <CartesianGrid vertical={false} stroke={COLORS.grid} />
          <XAxis dataKey="label" tick={{ fill: COLORS.axis, fontSize: 12 }} axisLine={false} tickLine={false} />
          <YAxis
            ticks={ticks}
            domain={ticks ? [0, ticks[ticks.length - 1]] : undefined}
            tickFormatter={(cents: number) => formatMoneyShort(cents)}
            tick={{ fill: COLORS.axis, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={52}
          />
          <Tooltip
            cursor={{ fill: "rgba(255,255,255,.04)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const m = payload[0].payload as CashFlowMonth & { label: string };
              return (
                <div className="chart-tip">
                  <b>{m.label} {m.month.slice(0, 4)}</b>
                  <br />
                  Income {formatMoney0(m.income_cents)}
                  <br />
                  Spending {formatMoney0(m.spending_cents)}
                  <br />
                  Saved {formatMoney0(m.saved_cents)}
                </div>
              );
            }}
          />
          <Bar dataKey="income_cents" fill={COLORS.blue} radius={[3, 3, 0, 0]} maxBarSize={16} isAnimationActive={false} />
          <Bar dataKey="spending_cents" fill={COLORS.pink} radius={[3, 3, 0, 0]} maxBarSize={16} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
