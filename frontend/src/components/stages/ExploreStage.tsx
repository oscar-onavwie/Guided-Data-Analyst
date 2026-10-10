"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";
import type { Aggregation, AnalysisBundle, Granularity, GroupedSummary, ScatterData, TimeSeries } from "@/lib/types";
import type { Loadable } from "../Workspace";
import { BoxPlotChart, CategoryBarChart, CorrelationHeatmap, GroupBarChart, HistogramChart, ScatterPlot, TimeSeriesChart } from "../charts/Charts";
import { DataTable } from "../DataTable";
import { Alert, Badge, Button, Card, EmptyState, LoadingBlock, Select, Spinner, StatList, Tabs } from "../ui";

type Tab = "distributions" | "categories" | "time" | "groups" | "relationships";

export function ExploreStage({ datasetId, analysis, onContinue }: { datasetId: string; analysis: Loadable<AnalysisBundle>; onContinue: () => void }) {
  const [tab, setTab] = useState<Tab>("distributions");
  if (analysis.status === "idle" || analysis.status === "loading") return <LoadingBlock label="Calculating statistics…" />;
  if (analysis.status === "error") return <Alert tone="error" title="Analysis failed">{analysis.error}</Alert>;
  const a = analysis.data;

  const tabs: { id: Tab; label: string; disabled?: boolean }[] = [
    { id: "distributions", label: `Numeric (${a.numeric.length})`, disabled: a.numeric.length === 0 },
    { id: "categories", label: `Categories (${a.categorical.length})`, disabled: a.categorical.length === 0 },
    { id: "time", label: "Over time", disabled: a.date_columns.length === 0 },
    { id: "groups", label: "Compare groups", disabled: !a.default_grouped },
    { id: "relationships", label: "Relationships", disabled: !a.correlation },
  ];
  const firstEnabled = tabs.find((t) => !t.disabled)?.id;
  const current = tabs.find((t) => t.id === tab)?.disabled ? firstEnabled : tab;

  return (
    <div className="space-y-4">
      <Card
        title="Explore"
        description="Statistics and charts calculated by the backend from your data. Only analyses that suit each column's type are shown."
        actions={<Button onClick={onContinue}>Continue to Discover →</Button>}
      >
        {current ? (
          <>
            <Tabs label="Analysis type" tabs={tabs} active={current} onChange={setTab} />
            <div role="tabpanel" id={`panel-${current}`} aria-labelledby={`tab-${current}`} className="pt-4">
              {current === "distributions" && <Distributions a={a} />}
              {current === "categories" && <Categories a={a} />}
              {current === "time" && <OverTime a={a} datasetId={datasetId} />}
              {current === "groups" && a.default_grouped && <Groups a={a} datasetId={datasetId} initial={a.default_grouped} />}
              {current === "relationships" && <Relationships a={a} datasetId={datasetId} />}
            </div>
          </>
        ) : (
          <EmptyState title="Nothing to explore">This dataset has no numeric, category or date columns that can be analysed.</EmptyState>
        )}
        {tabs.some((t) => t.disabled) && (
          <p className="mt-4 text-xs text-zinc-500">
            Greyed-out tabs are unavailable for this dataset: {tabs.filter((t) => t.disabled).map((t) => t.label.replace(/ \(\d+\)/, "")).join(", ")}.
          </p>
        )}
      </Card>
      {a.skipped.length > 0 && (
        <Alert tone="info" title="Not calculated, and why">
          <ul className="list-disc pl-5">
            {a.skipped.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </Alert>
      )}
    </div>
  );
}

function Distributions({ a }: { a: AnalysisBundle }) {
  const [column, setColumn] = useState(a.numeric[0].column);
  const n = a.numeric.find((x) => x.column === column) ?? a.numeric[0];
  const s = n.summary;
  return (
    <div className="space-y-5">
      <Select id="num-col" label="Numeric column" value={n.column} onChange={setColumn} options={a.numeric.map((x) => ({ value: x.column, label: x.column }))} />
      <StatList
        items={[
          { label: "Values used", value: formatNumber(s.count) },
          { label: "Mean", value: formatNumber(s.mean) },
          { label: "Median", value: formatNumber(s.median) },
          { label: "Std deviation", value: formatNumber(s.std) },
          { label: "Min", value: formatNumber(s.min) },
          { label: "Q1", value: formatNumber(s.q1) },
          { label: "Q3", value: formatNumber(s.q3) },
          { label: "Max", value: formatNumber(s.max) },
        ]}
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <HistogramChart column={n.column} bins={n.histogram} />
        <div className="space-y-3">
          <BoxPlotChart column={n.column} box={n.box} />
          <p className="text-sm text-zinc-600">
            <strong>{s.outliers.count}</strong> potential outlier(s) ({formatPercent(s.outliers.pct)}). Method: {s.outliers.method}.
            {s.outliers.count > 0 && " These values are flagged for review only; they are still included in every calculation."}
          </p>
          {s.mean !== s.median && s.std !== null && (
            <p className="text-sm text-zinc-600">
              The mean is {s.mean > s.median ? "above" : "below"} the median, which suggests the distribution is pulled{" "}
              {s.mean > s.median ? "upwards by larger values" : "downwards by smaller values"}.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Categories({ a }: { a: AnalysisBundle }) {
  const [column, setColumn] = useState(a.categorical[0].column);
  const c = a.categorical.find((x) => x.column === column) ?? a.categorical[0];
  return (
    <div className="space-y-5">
      <Select id="cat-col" label="Category column" value={c.column} onChange={setColumn} options={a.categorical.map((x) => ({ value: x.column, label: x.column }))} />
      <p className="text-sm text-zinc-600">
        {formatNumber(c.unique)} distinct values · {formatNumber(c.non_missing)} rows with a value · {formatNumber(c.missing)} missing. Percentages are of rows with a value.
      </p>
      <div className="grid gap-6 xl:grid-cols-2">
        <CategoryBarChart column={c.column} rows={c.rows} otherCount={c.other_count} />
        <DataTable
          caption={`Frequency table for ${c.column}`}
          columns={["Value", "Rows", "% of non-missing"]}
          numericColumns={[1, 2]}
          rows={[
            ...c.rows.map((r) => [r.value, formatNumber(r.count), formatPercent(r.pct)]),
            ...(c.other_count ? [[`Other (${c.other_categories} values)`, formatNumber(c.other_count), formatPercent((100 * c.other_count) / c.non_missing)]] : []),
          ]}
        />
      </div>
    </div>
  );
}

function OverTime({ a, datasetId }: { a: AnalysisBundle; datasetId: string }) {
  const initial = a.default_timeseries;
  const [dateColumn, setDateColumn] = useState(initial?.date_column ?? a.date_columns[0]);
  const [valueColumn, setValueColumn] = useState(initial?.value_column ?? "");
  const [agg, setAgg] = useState<Aggregation>(initial?.agg ?? "count");
  const [granularity, setGranularity] = useState<Granularity | "auto">("auto");
  const [result, setResult] = useState<Loadable<TimeSeries>>(initial ? { status: "ready", data: initial } : { status: "idle" });

  async function refresh(next: { dateColumn: string; valueColumn: string; agg: Aggregation; granularity: Granularity | "auto" }) {
    setResult({ status: "loading" });
    try {
      const effectiveAgg = next.valueColumn ? (next.agg === "count" ? "sum" : next.agg) : "count";
      const data = await api.timeseries(datasetId, next.dateColumn, next.valueColumn || null, effectiveAgg, next.granularity);
      setResult({ status: "ready", data });
    } catch (e) {
      setResult({ status: "error", error: errorMessage(e) });
    }
  }

  const update = (patch: Partial<{ dateColumn: string; valueColumn: string; agg: Aggregation; granularity: Granularity | "auto" }>) => {
    const next = { dateColumn, valueColumn, agg, granularity, ...patch };
    if (next.valueColumn && next.agg === "count") next.agg = "sum";
    if (!next.valueColumn) next.agg = "count";
    setDateColumn(next.dateColumn);
    setValueColumn(next.valueColumn);
    setAgg(next.agg);
    setGranularity(next.granularity);
    void refresh(next);
  };

  const ts = result.status === "ready" ? result.data : null;
  const valueLabel = ts ? (ts.agg === "count" ? "Number of records" : `${ts.agg === "sum" ? "Total" : "Average"} ${ts.value_column}`) : "";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-3">
        <Select id="ts-date" label="Date column" value={dateColumn} onChange={(v) => update({ dateColumn: v })} options={a.date_columns.map((d) => ({ value: d, label: d }))} />
        <Select
          id="ts-value"
          label="Measure"
          value={valueColumn}
          onChange={(v) => update({ valueColumn: v })}
          options={[{ value: "", label: "Number of records" }, ...a.measures.map((m) => ({ value: m, label: m }))]}
        />
        <Select
          id="ts-agg"
          label="Aggregation"
          value={agg}
          disabled={!valueColumn}
          onChange={(v) => update({ agg: v as Aggregation })}
          options={valueColumn ? [{ value: "sum", label: "Total (sum)" }, { value: "mean", label: "Average (mean)" }] : [{ value: "count", label: "Count" }]}
        />
        <Select
          id="ts-gran"
          label="Period"
          value={granularity}
          onChange={(v) => update({ granularity: v as Granularity | "auto" })}
          options={["auto", "day", "week", "month", "quarter", "year"].map((g) => ({ value: g, label: g === "auto" ? "Automatic" : g[0].toUpperCase() + g.slice(1) }))}
        />
      </div>
      {result.status === "loading" && <Spinner label="Aggregating…" />}
      {result.status === "error" && <Alert tone="error">{result.error}</Alert>}
      {ts && (
        <>
          <TimeSeriesChart points={ts.points} valueLabel={valueLabel} showCount={ts.agg === "count"} />
          <p className="text-sm text-zinc-600">
            Grouped by <strong>{ts.granularity}</strong>. Periods with no records appear as gaps, not zeros.
            {(ts.first_period_partial || ts.last_period_partial) && (
              <>
                {" "}
                <Badge tone="amber">Partial period</Badge> The {[ts.first_period_partial && "first", ts.last_period_partial && "last"].filter(Boolean).join(" and ")} period
                only covers part of the {ts.granularity}, so it may look lower than it really was.
              </>
            )}
          </p>
        </>
      )}
    </div>
  );
}

function Groups({ a, datasetId, initial }: { a: AnalysisBundle; datasetId: string; initial: GroupedSummary }) {
  const [category, setCategory] = useState(initial.category_column);
  const [measure, setMeasure] = useState(initial.value_column);
  const [result, setResult] = useState<Loadable<GroupedSummary>>({ status: "ready", data: initial });

  async function refresh(c: string, m: string) {
    setCategory(c);
    setMeasure(m);
    setResult({ status: "loading" });
    try {
      setResult({ status: "ready", data: await api.grouped(datasetId, c, m) });
    } catch (e) {
      setResult({ status: "error", error: errorMessage(e) });
    }
  }

  const g = result.status === "ready" ? result.data : null;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-3">
        <Select id="g-cat" label="Group by" value={category} onChange={(v) => void refresh(v, measure)} options={a.dimensions.map((d) => ({ value: d, label: d }))} />
        <Select id="g-val" label="Measure" value={measure} onChange={(v) => void refresh(category, v)} options={a.measures.map((m) => ({ value: m, label: m }))} />
      </div>
      {result.status === "loading" && <Spinner label="Comparing groups…" />}
      {result.status === "error" && <Alert tone="error">{result.error}</Alert>}
      {g && (
        <>
          <div className="grid gap-6 xl:grid-cols-2">
            <GroupBarChart rows={g.rows} metric={g.shares_valid ? "sum" : "mean"} valueColumn={g.value_column} categoryColumn={g.category_column} />
            <DataTable
              caption={`${g.value_column} by ${g.category_column}`}
              columns={[g.category_column, "Rows", "Mean", "Median", "Total", "Share of total"]}
              numericColumns={[1, 2, 3, 4, 5]}
              rows={g.rows.map((r) => [r.group, formatNumber(r.count), formatNumber(r.mean), formatNumber(r.median), formatNumber(r.sum), r.share_of_total === null ? "n/a" : formatPercent(r.share_of_total)])}
            />
          </div>
          {g.note && <p className="text-sm text-zinc-600">{g.note}</p>}
        </>
      )}
    </div>
  );
}

function Relationships({ a, datasetId }: { a: AnalysisBundle; datasetId: string }) {
  const corr = a.correlation;
  const initial = a.default_scatter;
  const [x, setX] = useState(initial?.x ?? a.measures[0]);
  const [y, setY] = useState(initial?.y ?? a.measures[1] ?? a.measures[0]);
  const [result, setResult] = useState<Loadable<ScatterData>>(initial ? { status: "ready", data: initial } : { status: "idle" });

  async function refresh(nx: string, ny: string) {
    setX(nx);
    setY(ny);
    setResult({ status: "loading" });
    try {
      setResult({ status: "ready", data: await api.scatter(datasetId, nx, ny) });
    } catch (e) {
      setResult({ status: "error", error: errorMessage(e) });
    }
  }
  if (!corr) return <EmptyState title="Correlation needs at least two numeric columns." />;
  const s = result.status === "ready" ? result.data : null;
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <CorrelationHeatmap matrix={corr} />
        <div>
          <h3 className="mb-2 text-sm font-medium text-zinc-800">Strongest relationships</h3>
          {corr.pairs.length === 0 ? (
            <p className="text-sm text-zinc-500">No pair has at least 10 rows with both values present.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {corr.pairs.slice(0, 6).map((p) => (
                <li key={`${p.x}-${p.y}`}>
                  <button type="button" className="text-left text-teal-800 hover:underline" onClick={() => void refresh(p.x, p.y)}>
                    {p.x} ↔ {p.y}
                  </button>{" "}
                  <span className="tabular-nums text-zinc-600">r = {p.r.toFixed(2)} (n={p.n})</span> <Badge tone={p.strength === "strong" ? "teal" : "neutral"}>{p.strength}</Badge>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-zinc-500">{corr.method}. Correlation shows whether two columns move together; it does not show that one causes the other.</p>
        </div>
      </div>
      <div className="space-y-3">
        <div className="flex flex-wrap gap-3">
          <Select id="sc-x" label="Horizontal axis" value={x} onChange={(v) => void refresh(v, y)} options={a.measures.map((m) => ({ value: m, label: m }))} />
          <Select id="sc-y" label="Vertical axis" value={y} onChange={(v) => void refresh(x, v)} options={a.measures.map((m) => ({ value: m, label: m }))} />
        </div>
        {result.status === "loading" && <Spinner label="Plotting…" />}
        {result.status === "error" && <Alert tone="error">{result.error}</Alert>}
        {s && (
          <>
            <ScatterPlot x={s.x} y={s.y} points={s.points} r={s.r} />
            <p className="text-xs text-zinc-500">
              Showing {formatNumber(s.n_shown)} of {formatNumber(s.n_total)} rows with both values{s.n_shown < s.n_total ? " (a fixed random sample)" : ""}.
              {s.r !== null ? ` Pearson r = ${s.r.toFixed(2)}.` : " Too few rows to calculate a correlation."}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
