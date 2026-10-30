import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Pace } from "../api/client";
import { COLORS } from "../lib/colors";
import { formatMoney0, formatMoneyShort, niceTicks } from "../lib/money";

type Point = { label: string; current: number | null; previous: number | null };

type Props = {
  pace: Pace;
  currentName: string; // "October"
  previousName: string; // "September"
};

/** Running spending this period (pink, filled) vs the previous one (dashed). */
export function PaceChart({ pace, currentName, previousName }: Props) {
  const data: Point[] = pace.points.map((p) => ({
    label: p.label,
    current: p.current_cents,
    previous: p.previous_cents,
  }));
  const isMonth = pace.kind === "month";
  const ticks = niceTicks(Math.max(0, ...data.map((p) => Math.max(p.current ?? 0, p.previous ?? 0))));

  return (
    <div className="pace">
      <ResponsiveContainer width="100%" height={190}>
        <ComposedChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke={COLORS.grid} />
          <XAxis
            dataKey="label"
            tick={{ fill: COLORS.axis, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={18}
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
              const point = payload[0].payload as Point;
              return (
                <div className="chart-tip">
                  <b>{isMonth ? `Day ${point.label}` : point.label}</b>
                  <br />
                  {currentName}: {point.current === null ? "not yet" : formatMoney0(point.current)}
                  <br />
                  {previousName}: {point.previous === null ? "—" : formatMoney0(point.previous)}
                </div>
              );
            }}
          />
          <Line
            type="linear"
            dataKey="previous"
            stroke={COLORS.bench}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            activeDot={{ r: 4, fill: COLORS.bench, stroke: "#161126", strokeWidth: 2 }}
            isAnimationActive={false}
          />
          <Area
            type="linear"
            dataKey="current"
            stroke={COLORS.pink}
            strokeWidth={2.5}
            fill={COLORS.pink}
            fillOpacity={0.12}
            dot={false}
            activeDot={{ r: 5, fill: COLORS.pink, stroke: "#161126", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
