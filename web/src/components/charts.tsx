"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const AXIS = { fontSize: 12, fill: "var(--muted)" };
const tooltipStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--text)",
};

/** Creditable now vs potential once paperwork is complete, by year. */
export function YearBars({
  data,
  bars,
  height = 240,
  unit = "t",
}: {
  data: Record<string, number | string>[];
  bars: { key: string; label: string; color: string; stack?: string }[];
  height?: number;
  unit?: string;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis dataKey="year" tick={AXIS} axisLine={false} tickLine={false} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={tooltipStyle}
            cursor={{ fill: "var(--surface-2)" }}
            formatter={(v) => `${Number(v).toFixed(2)} ${unit}`}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
          {bars.map((b) => (
            <Bar key={b.key} dataKey={b.key} name={b.label} fill={b.color} stackId={b.stack} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Monthly rainfall the estimate was driven by. */
export function RainBars({ rain }: { rain: number[] }) {
  const months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
  return (
    <div style={{ height: 120 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rain.map((mm, i) => ({ m: months[i], mm }))} margin={{ top: 4, right: 0, bottom: 0, left: -28 }}>
          <XAxis dataKey="m" tick={AXIS} axisLine={false} tickLine={false} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={tooltipStyle} formatter={(v) => `${Number(v).toFixed(0)} mm`} cursor={{ fill: "var(--surface-2)" }} />
          <Bar dataKey="mm" name="Rain" fill="var(--info)" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
