"use client";

// All charts draw ONLY data returned by the backend. There are no hard-coded
// sample values anywhere in this file.

import type { ReactElement } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { compactNumber, correlationColour, formatNumber } from "@/lib/format";
import type { BoxPlot, CategoryCount, CorrelationMatrix, GroupRow, HistogramBin, ScatterPoint, TimePoint } from "@/lib/types";

const ACCENT = "#0f766e";
const ACCENT_2 = "#4338ca";
const AXIS = { fontSize: 12, fill: "#52525b" };

function ChartFrame({ title, summary, children, height = 280 }: { title: string; summary: string; children: ReactElement; height?: number }) {
  return (
    <figure className="w-full">
      <figcaption className="mb-2 text-sm font-medium text-zinc-800">{title}</figcaption>
      {/* The text summary gives screen-reader users the same information as the picture. */}
      <p className="sr-only">{summary}</p>
      <div style={{ height }} className="w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

const tooltipNumber = (v: unknown) => (typeof v === "number" ? formatNumber(v) : String(v));

export function HistogramChart({ column, bins }: { column: string; bins: HistogramBin[] }) {
  const data = bins.map((b) => ({ range: `${compactNumber(b.start)}–${compactNumber(b.end)}`, rows: b.count }));
  const peak = bins.reduce((best, b) => (b.count > best.count ? b : best), bins[0]);
  return (
    <ChartFrame
      title={`Distribution of ${column}`}
      summary={`Histogram of ${column} with ${bins.length} bins. The most common range is ${formatNumber(peak?.start)} to ${formatNumber(peak?.end)} with ${peak?.count} rows.`}
    >
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 32, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="range" tick={AXIS} angle={-30} textAnchor="end" interval="preserveStartEnd" height={50} />
        <YAxis tick={AXIS} allowDecimals={false} width={48} label={{ value: "rows", angle: -90, position: "insideLeft", style: AXIS }} />
        <Tooltip formatter={tooltipNumber} />
        <Legend verticalAlign="top" height={24} />
        <Bar dataKey="rows" name="Number of rows" fill={ACCENT} radius={[3, 3, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

export function CategoryBarChart({ column, rows, otherCount }: { column: string; rows: CategoryCount[]; otherCount: number }) {
  const data = [...rows.map((r) => ({ name: r.value, count: r.count, pct: r.pct }))];
  if (otherCount > 0) data.push({ name: "Other", count: otherCount, pct: Number.NaN });
  return (
    <ChartFrame
      title={`Most common values of ${column}`}
      summary={`Bar chart of ${column}. ${rows.slice(0, 3).map((r) => `${r.value}: ${r.count} rows`).join("; ")}.`}
      height={Math.max(200, data.length * 30 + 60)}
    >
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={AXIS} allowDecimals={false} />
        <YAxis type="category" dataKey="name" tick={AXIS} width={120} />
        <Tooltip formatter={tooltipNumber} />
        <Legend verticalAlign="top" height={24} />
        <Bar dataKey="count" name="Number of rows" fill={ACCENT} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

export function TimeSeriesChart({ points, valueLabel, showCount }: { points: TimePoint[]; valueLabel: string; showCount: boolean }) {
  const data = points.map((p) => ({ label: p.label, value: showCount ? p.count : p.value }));
  return (
    <ChartFrame
      title={`${valueLabel} over time`}
      summary={`Line chart of ${valueLabel} across ${points.length} periods from ${points[0]?.label} to ${points[points.length - 1]?.label}. Periods with no records are shown as gaps.`}
      height={300}
    >
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 32, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="label" tick={AXIS} angle={-30} textAnchor="end" height={56} interval="preserveStartEnd" />
        <YAxis tick={AXIS} tickFormatter={compactNumber} width={56} />
        <Tooltip formatter={tooltipNumber} />
        <Legend verticalAlign="top" height={24} />
        <Line type="monotone" dataKey="value" name={valueLabel} stroke={ACCENT} strokeWidth={2} dot={{ r: 3 }} connectNulls={false} />
      </LineChart>
    </ChartFrame>
  );
}

export function GroupBarChart({ rows, metric, valueColumn, categoryColumn }: {
  rows: GroupRow[];
  metric: "sum" | "mean";
  valueColumn: string;
  categoryColumn: string;
}) {
  const data = rows.map((r) => ({ name: r.group, value: metric === "sum" ? r.sum : r.mean }));
  const label = `${metric === "sum" ? "Total" : "Average"} ${valueColumn}`;
  return (
    <ChartFrame
      title={`${label} by ${categoryColumn}`}
      summary={`Bar chart of ${label} by ${categoryColumn}: ${data.slice(0, 4).map((d) => `${d.name} ${formatNumber(d.value)}`).join(", ")}.`}
      height={Math.max(220, data.length * 30 + 60)}
    >
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" tick={AXIS} tickFormatter={compactNumber} />
        <YAxis type="category" dataKey="name" tick={AXIS} width={120} />
        <Tooltip formatter={tooltipNumber} />
        <Legend verticalAlign="top" height={24} />
        <Bar dataKey="value" name={label} fill={ACCENT_2} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

export function ScatterPlot({ x, y, points, r }: { x: string; y: string; points: ScatterPoint[]; r: number | null }) {
  return (
    <ChartFrame
      title={`${y} against ${x}`}
      summary={`Scatter plot of ${points.length} rows. ${r === null ? "Correlation not calculated." : `Pearson r = ${r.toFixed(2)}.`}`}
      height={320}
    >
      <ScatterChart margin={{ top: 8, right: 16, bottom: 32, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis type="number" dataKey="x" name={x} tick={AXIS} tickFormatter={compactNumber} label={{ value: x, position: "insideBottom", offset: -18, style: AXIS }} />
        <YAxis type="number" dataKey="y" name={y} tick={AXIS} tickFormatter={compactNumber} width={56} label={{ value: y, angle: -90, position: "insideLeft", style: AXIS }} />
        <Tooltip formatter={tooltipNumber} cursor={{ strokeDasharray: "3 3" }} />
        <Legend verticalAlign="top" height={24} />
        <Scatter name={`Rows (${points.length} shown)`} data={points} fill={ACCENT} fillOpacity={0.6} />
      </ScatterChart>
    </ChartFrame>
  );
}

/** Horizontal box plot drawn as plain SVG (Recharts has no box-plot primitive). */
export function BoxPlotChart({ column, box }: { column: string; box: BoxPlot }) {
  const values = [box.lower_whisker, box.upper_whisker, ...box.outliers];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const W = 600;
  const x = (v: number) => 20 + ((v - lo) / span) * (W - 40);
  return (
    <figure className="w-full">
      <figcaption className="mb-2 text-sm font-medium text-zinc-800">Box plot of {column}</figcaption>
      <svg viewBox={`0 0 ${W} 90`} className="w-full" role="img" aria-label={`Box plot of ${column}: median ${formatNumber(box.median)}, middle half from ${formatNumber(box.q1)} to ${formatNumber(box.q3)}, ${box.outlier_count} potential outliers.`}>
        <line x1={x(box.lower_whisker)} x2={x(box.upper_whisker)} y1={40} y2={40} stroke="#71717a" strokeWidth={1.5} />
        <line x1={x(box.lower_whisker)} x2={x(box.lower_whisker)} y1={28} y2={52} stroke="#71717a" strokeWidth={1.5} />
        <line x1={x(box.upper_whisker)} x2={x(box.upper_whisker)} y1={28} y2={52} stroke="#71717a" strokeWidth={1.5} />
        <rect x={x(box.q1)} y={22} width={Math.max(1, x(box.q3) - x(box.q1))} height={36} fill="#ccfbf1" stroke={ACCENT} strokeWidth={1.5} rx={3} />
        <line x1={x(box.median)} x2={x(box.median)} y1={22} y2={58} stroke={ACCENT} strokeWidth={3} />
        {box.outliers.map((v, i) => (
          <circle key={i} cx={x(v)} cy={40} r={3.5} fill="#b45309" fillOpacity={0.7}>
            <title>{`Potential outlier: ${formatNumber(v)}`}</title>
          </circle>
        ))}
        <text x={20} y={82} fontSize={12} fill="#52525b">{formatNumber(lo)}</text>
        <text x={W - 20} y={82} fontSize={12} fill="#52525b" textAnchor="end">{formatNumber(hi)}</text>
        <text x={x(box.median)} y={14} fontSize={12} fill="#0f766e" textAnchor="middle">median {formatNumber(box.median)}</text>
      </svg>
      <p className="mt-1 flex flex-wrap gap-x-4 text-xs text-zinc-600">
        <span><span className="mr-1 inline-block h-2 w-3 rounded-sm border border-teal-700 bg-teal-100 align-middle" />middle 50% (Q1–Q3)</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-700/70 align-middle" />potential outlier (1.5×IQR)</span>
        {box.outlier_count > box.outliers.length && <span>showing {box.outliers.length} of {box.outlier_count} outliers</span>}
      </p>
    </figure>
  );
}

export function CorrelationHeatmap({ matrix }: { matrix: CorrelationMatrix }) {
  return (
    <div className="overflow-x-auto" tabIndex={0} aria-label="Correlation heatmap">
      <table className="border-collapse text-xs">
        <caption className="mb-2 text-left text-sm font-medium text-zinc-800">Correlation between numeric columns (Pearson r)</caption>
        <thead>
          <tr>
            <th scope="col" className="p-1" />
            {matrix.columns.map((c) => (
              <th key={c} scope="col" className="max-w-24 truncate p-1 text-left font-medium text-zinc-600" title={c}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.columns.map((row, i) => (
            <tr key={row}>
              <th scope="row" className="max-w-32 truncate p-1 pr-2 text-right font-medium text-zinc-600" title={row}>
                {row}
              </th>
              {matrix.matrix[i].map((r, j) => (
                <td
                  key={j}
                  className="h-10 w-14 border border-white text-center tabular-nums"
                  style={{ background: correlationColour(r), color: r !== null && Math.abs(r) > 0.55 ? "white" : "#18181b" }}
                  title={r === null ? "Not calculated (fewer than 10 pairs)" : `${row} vs ${matrix.columns[j]}: r = ${r.toFixed(2)}`}
                >
                  {r === null ? "–" : r.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 flex flex-wrap gap-x-4 text-xs text-zinc-600">
        <span><span className="mr-1 inline-block h-2 w-3 rounded-sm align-middle" style={{ background: correlationColour(0.9) }} />move together</span>
        <span><span className="mr-1 inline-block h-2 w-3 rounded-sm align-middle" style={{ background: correlationColour(-0.9) }} />move in opposite directions</span>
        <span>– = fewer than 10 rows with both values</span>
      </p>
    </div>
  );
}
