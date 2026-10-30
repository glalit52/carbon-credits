"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DrySpell, OpticalReading, RadarCall } from "@/lib/engine";

const AXIS = { fontSize: 12, fill: "var(--muted)" };
const tooltipStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
  color: "var(--text)",
};
const t = (day: string) => Date.parse(`${day}T00:00:00Z`);
const shortDate = (ms: number) =>
  new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const monthYear = (ms: number) =>
  new Date(ms).toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
/** Day and month inside one season; month and year once a series spans years. */
const tickFor = (xs: number[]) => (Math.max(...xs) - Math.min(...xs) > 300 * 86_400_000 ? monthYear : shortDate);
const longDate = (ms: number) =>
  new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

// Flooded and drained are the two states the claim rests on; ambiguous is the
// detector declining to call a pass. Shape carries the state as well as colour.
const STATE = {
  flooded: { label: "Flooded", color: "var(--info)", shape: "circle" as const },
  drained: { label: "Drained", color: "var(--accent)", shape: "triangle" as const },
  ambiguous: { label: "Not separable", color: "var(--muted)", shape: "diamond" as const },
};

type RadarPoint = RadarCall & { x: number };

function RadarTip({ active, payload }: { active?: boolean; payload?: { payload: RadarPoint }[] }) {
  const p = active && payload?.[0]?.payload;
  if (!p) return null;
  return (
    <div style={{ ...tooltipStyle, padding: 8, maxWidth: 260 }}>
      <div className="font-medium">{longDate(p.x)} · {p.season}</div>
      <div>
        {STATE[p.state].label}
        {p.inferred ? " (carried across a gap)" : ""} — {Math.round(p.p_flooded * 100)}% flooded
      </div>
      <div className="text-muted">VV {p.vv_db.toFixed(1)} dB · crop stage {p.stage_estimate.toFixed(2)}</div>
      {p.note && <div className="mt-1 text-muted">{p.note}</div>}
    </div>
  );
}

/** Each Sentinel-1 pass: normalised VV backscatter, coloured by the detector's call. */
export function RadarSeries({ calls, spells }: { calls: RadarCall[]; spells: DrySpell[] }) {
  const points = calls.map((c) => ({ ...c, x: t(c.day) }));
  const xs = points.map((p) => p.x);
  return (
    <div style={{ height: 260 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          {spells.map((s) => (
            <ReferenceArea
              key={s.start}
              x1={t(s.start)}
              x2={t(s.end)}
              fill={s.terminal ? "var(--surface-2)" : "var(--accent-soft)"}
              fillOpacity={1}
              ifOverflow="extendDomain"
            />
          ))}
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={[Math.min(...xs), Math.max(...xs)]}
            tickFormatter={shortDate}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
          />
          <YAxis dataKey="vv_db" type="number" unit=" dB" tick={AXIS} axisLine={false} tickLine={false} width={64} />
          <Tooltip content={<RadarTip />} cursor={{ stroke: "var(--border)" }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {(Object.keys(STATE) as (keyof typeof STATE)[]).map((k) => (
            <Scatter
              key={k}
              name={STATE[k].label}
              data={points.filter((p) => p.state === k)}
              fill={STATE[k].color}
              shape={STATE[k].shape}
              legendType={STATE[k].shape}
              stroke="var(--surface)"
              strokeWidth={1.5}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Optical greenness, with passes lost to cloud left as gaps rather than joined over. */
export function NdviSeries({ readings, water }: { readings: OpticalReading[]; water: boolean }) {
  const data = readings.map((r) => ({ x: t(r.day), ndvi: r.ndvi, water: r.water ?? null, rain: r.rain_mm }));
  const tick = tickFor(data.map((d) => d.x));
  return (
    <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={tick}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
          />
          <YAxis domain={[0, 1]} tick={AXIS} axisLine={false} tickLine={false} width={44} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(x) => longDate(Number(x))}
            formatter={(v, name) => (v == null ? ["lost to cloud", name] : [Number(v).toFixed(2), name])}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line dataKey="ndvi" name="NDVI (greenness)" stroke="var(--brand)" strokeWidth={2} dot={false} connectNulls={false} />
          {water && (
            <Line dataKey="water" name="Surface water fraction" stroke="var(--info)" strokeWidth={2} dot={false} strokeDasharray="4 3" />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Canopy height with its retrieval error as a band. */
export function CanopySeries({ readings }: { readings: OpticalReading[] }) {
  const data = readings
    .filter((r) => r.canopy_m != null)
    .map((r) => ({
      x: t(r.day),
      h: r.canopy_m,
      band: [Math.max(0, (r.canopy_m ?? 0) - (r.canopy_sd_m ?? 0)), (r.canopy_m ?? 0) + (r.canopy_sd_m ?? 0)],
    }));
  const tick = tickFor(data.map((d) => d.x));
  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={tick}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
          />
          <YAxis unit=" m" tick={AXIS} axisLine={false} tickLine={false} width={52} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(x) => longDate(Number(x))}
            formatter={(v, name) =>
              Array.isArray(v) ? [`${Number(v[0]).toFixed(1)}–${Number(v[1]).toFixed(1)} m`, name] : [`${Number(v).toFixed(2)} m`, name]
            }
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            dataKey="band"
            name="± one standard error"
            stroke="none"
            fill="var(--brand-soft)"
            fillOpacity={1}
            legendType="square"
          />
          <Line dataKey="h" name="Canopy height" stroke="var(--brand)" strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** A logger's daily mean water level, against the thresholds the engine classifies with. */
export function LoggerLevels({
  days,
  thresholds,
  calls,
}: {
  days: { day: string; mean_cm: number; min_cm: number }[];
  thresholds: { flooded_above_cm: number; drained_below_cm: number; safe_awd_cm: number };
  calls?: RadarCall[];
}) {
  const data = days.map((d) => ({ x: t(d.day), mean: d.mean_cm, min: d.min_cm }));
  const lo = data[0]?.x ?? 0;
  const hi = data[data.length - 1]?.x ?? 0;
  const passes = (calls ?? []).filter((c) => t(c.day) >= lo && t(c.day) <= hi);
  return (
    <div style={{ height: 260 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={[lo, hi]}
            tickFormatter={shortDate}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
          />
          <YAxis unit=" cm" tick={AXIS} axisLine={false} tickLine={false} width={56} />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={(x) => longDate(Number(x))}
            formatter={(v, name) => [`${Number(v).toFixed(1)} cm`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={0} stroke="var(--border)" />
          <ReferenceLine
            y={thresholds.safe_awd_cm}
            stroke="var(--accent)"
            strokeDasharray="4 3"
            label={{ value: "safe-AWD depth", position: "insideBottomLeft", fontSize: 11, fill: "var(--muted)" }}
          />
          {passes.map((c) => (
            <ReferenceLine key={c.day} x={t(c.day)} stroke="var(--border)" strokeDasharray="2 3" />
          ))}
          <Line dataKey="mean" name="Daily mean level" stroke="var(--info)" strokeWidth={2} dot={false} />
          <Line dataKey="min" name="Daily lowest" stroke="var(--muted)" strokeWidth={1} dot={false} strokeDasharray="3 3" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Scenes over a farm on a timeline; a gap longer than a dry-down is a blind spot. */
export function SceneTimeline({
  scenes,
}: {
  scenes: { day: string; usable: boolean; cloud_cover: number | null; platform: string }[];
}) {
  const data = scenes.map((s) => ({ x: t(s.day), y: s.usable ? 1 : 0, ...s }));
  return (
    <div style={{ height: 120 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <XAxis
            dataKey="x"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={shortDate}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            dataKey="y"
            type="number"
            domain={[-0.5, 1.5]}
            ticks={[0, 1]}
            tickFormatter={(v) => (v ? "usable" : "cloudy")}
            tick={AXIS}
            axisLine={false}
            tickLine={false}
            width={64}
          />
          <Tooltip
            contentStyle={tooltipStyle}
            labelFormatter={() => ""}
            formatter={(_v, _n, item) => {
              const s = (item as { payload: (typeof data)[number] }).payload;
              return [`${s.platform}${s.cloud_cover != null ? `, ${Math.round(s.cloud_cover)}% cloud` : ""}`, longDate(s.x)];
            }}
          />
          <Scatter data={data.filter((d) => d.usable)} fill="var(--brand)" shape="circle" name="Usable" />
          <Scatter data={data.filter((d) => !d.usable)} fill="var(--muted)" shape="cross" name="Cloudy" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
