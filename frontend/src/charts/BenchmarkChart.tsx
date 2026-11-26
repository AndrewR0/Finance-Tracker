import { CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Comparison } from "../api/client";
import { COLORS } from "../lib/colors";
import { formatShortDate } from "../lib/dates";
import { formatMoney0, formatMoneyShort, niceTicks } from "../lib/money";

type Point = { date: string; putIn: number; spy: number | null; you: number | null };

/** Your value (blue) vs the same deposits in the S&P 500 (dashed), over what you put in (thin). */
export function BenchmarkChart({ comparison }: { comparison: Comparison }) {
  const data: Point[] = comparison.points.map((p) => ({
    date: p.date,
    putIn: p.put_in_cents,
    spy: p.benchmark_cents,
    you: p.value_cents,
  }));
  const ticks = niceTicks(Math.max(0, ...data.map((p) => Math.max(p.putIn, p.spy ?? 0, p.you ?? 0))));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={COLORS.grid} />
        <XAxis
          dataKey="date"
          tickFormatter={(iso: string) => `${formatShortDate(iso)} '${iso.slice(2, 4)}`}
          tick={{ fill: COLORS.axis, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          interval="preserveStartEnd"
          minTickGap={40}
        />
        <YAxis
          ticks={ticks}
          domain={[0, ticks[ticks.length - 1]]}
          tickFormatter={(cents: number) => formatMoneyShort(cents)}
          tick={{ fill: COLORS.axis, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={52}
        />
        <Tooltip
          cursor={{ stroke: COLORS.axis, strokeDasharray: "2 3" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as Point;
            return (
              <div className="chart-tip">
                <b>Week of {formatShortDate(p.date)} {p.date.slice(0, 4)}</b>
                <br />
                Put in: {formatMoney0(p.putIn)}
                <br />
                S&amp;P 500: {p.spy === null ? "—" : formatMoney0(p.spy)}
                <br />
                You: {p.you === null ? "not tracked yet" : formatMoney0(p.you)}
              </div>
            );
          }}
        />
        <Line type="stepAfter" dataKey="putIn" stroke={COLORS.axis} strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Line
          type="linear"
          dataKey="spy"
          stroke={COLORS.bench}
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
          connectNulls
          isAnimationActive={false}
        />
        <Line
          type="linear"
          dataKey="you"
          stroke={COLORS.blue}
          strokeWidth={2.5}
          dot={{ r: 3, fill: COLORS.blue }}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
