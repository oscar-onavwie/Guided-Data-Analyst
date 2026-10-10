"use client";

import { useState } from "react";
import { formatDate, formatNumber, formatPercent, titleCase } from "@/lib/format";
import type { ColumnProfile, DataIssue, DatasetProfile } from "@/lib/types";
import type { Loadable } from "../Workspace";
import { Alert, Badge, Button, Card, EmptyState, Kpi, LoadingBlock, StatList, cx } from "../ui";

const TYPE_TONE: Record<string, "teal" | "indigo" | "violet" | "neutral" | "amber"> = {
  numeric: "teal",
  datetime: "indigo",
  categorical: "violet",
  boolean: "violet",
  text: "neutral",
  empty: "amber",
};

export function ProfileStage({ profile, onContinue }: { profile: Loadable<DatasetProfile>; onContinue: () => void }) {
  if (profile.status === "idle" || profile.status === "loading") return <LoadingBlock label="Profiling the dataset…" />;
  if (profile.status === "error") return <Alert tone="error" title="Profiling failed">{profile.error}</Alert>;
  const p = profile.data;
  const confirmed = p.issues.filter((i) => i.severity === "confirmed");
  const potential = p.issues.filter((i) => i.severity === "potential");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Kpi label="Rows" value={formatNumber(p.rows)} />
        <Kpi label="Columns" value={p.columns} hint={Object.entries(p.type_counts).map(([t, n]) => `${n} ${t}`).join(", ")} />
        <Kpi label="Missing cells" value={formatPercent(p.missing_cells_pct)} hint={`${formatNumber(p.missing_cells)} cells`} tone={p.missing_cells_pct > 5 ? "warn" : "neutral"} />
        <Kpi label="Duplicate rows" value={formatNumber(p.duplicate_rows)} hint="counted, not removed" tone={p.duplicate_rows ? "warn" : "neutral"} />
        <Kpi label="Confirmed issues" value={confirmed.length} tone={confirmed.length ? "bad" : "neutral"} />
        <Kpi label="Potential issues" value={potential.length} tone={potential.length ? "warn" : "neutral"} />
      </div>

      <Card
        title="Data-quality assessment"
        description="Confirmed issues are objectively present in the file. Potential issues are worth checking but may be legitimate. Nothing has been changed or removed."
        actions={<Button onClick={onContinue}>Continue to Explore →</Button>}
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <IssueList title="Confirmed issues" tone="red" issues={confirmed} empty="No confirmed issues found." />
          <IssueList title="Potential issues — investigate" tone="amber" issues={potential} empty="No potential issues found." />
        </div>
        {p.parse_notes.length > 0 && (
          <details className="mt-4 text-sm">
            <summary className="cursor-pointer font-medium text-zinc-700">Changes made while reading the file ({p.parse_notes.length})</summary>
            <ul className="mt-2 list-disc pl-5 text-zinc-600">
              {p.parse_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </details>
        )}
      </Card>

      <Card title="Columns" description="Select a column to see its details.">
        <ColumnTable columns={p.column_profiles} />
      </Card>
    </div>
  );
}

function IssueList({ title, tone, issues, empty }: { title: string; tone: "red" | "amber"; issues: DataIssue[]; empty: string }) {
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-zinc-800">
        <Badge tone={tone}>{issues.length}</Badge> {title}
      </h3>
      {issues.length === 0 ? (
        <p className="text-sm text-zinc-500">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {issues.map((i) => (
            <li key={i.id} className={cx("rounded-lg border-l-4 bg-zinc-50 px-3 py-2 text-sm", tone === "red" ? "border-red-600" : "border-amber-500")}>
              <span className="mr-2 font-mono text-xs text-zinc-500">{i.id}</span>
              {i.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ColumnTable({ columns }: { columns: ColumnProfile[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (columns.length === 0) return <EmptyState title="No columns" />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <caption className="sr-only">Column profile</caption>
        <thead>
          <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500">
            <th scope="col" className="py-2 pr-3">Column</th>
            <th scope="col" className="py-2 pr-3">Type</th>
            <th scope="col" className="py-2 pr-3">Role</th>
            <th scope="col" className="py-2 pr-3 text-right">Missing</th>
            <th scope="col" className="py-2 pr-3 text-right">Invalid</th>
            <th scope="col" className="py-2 pr-3 text-right">Unique</th>
            <th scope="col" className="py-2">Flags</th>
          </tr>
        </thead>
        <tbody>
          {columns.map((c) => {
            const isOpen = open === c.name;
            return (
              <ColumnRow key={c.name} column={c} isOpen={isOpen} onToggle={() => setOpen(isOpen ? null : c.name)} />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ColumnRow({ column: c, isOpen, onToggle }: { column: ColumnProfile; isOpen: boolean; onToggle: () => void }) {
  const detailId = `col-detail-${c.name.replace(/\W+/g, "-")}`;
  return (
    <>
      <tr className="border-b border-zinc-100 align-top">
        <th scope="row" className="py-2 pr-3 text-left font-medium">
          <button type="button" onClick={onToggle} aria-expanded={isOpen} aria-controls={detailId} className="flex items-center gap-1 text-left text-teal-800 hover:underline">
            <span aria-hidden="true" className="inline-block w-3 text-zinc-400">{isOpen ? "▾" : "▸"}</span>
            {c.name}
          </button>
        </th>
        <td className="py-2 pr-3"><Badge tone={TYPE_TONE[c.inferred_type] ?? "neutral"}>{c.inferred_type}</Badge></td>
        <td className="py-2 pr-3 text-zinc-600">{c.role}</td>
        <td className="py-2 pr-3 text-right tabular-nums">{c.missing ? `${formatNumber(c.missing)} (${formatPercent(c.missing_pct)})` : "0"}</td>
        <td className={cx("py-2 pr-3 text-right tabular-nums", c.invalid > 0 && "font-semibold text-red-700")}>{formatNumber(c.invalid)}</td>
        <td className="py-2 pr-3 text-right tabular-nums">{formatNumber(c.unique)}</td>
        <td className="space-x-1 py-2">
          {c.is_constant && <Badge tone="amber">constant</Badge>}
          {c.likely_identifier && <Badge>identifier</Badge>}
          {c.candidate_date && <Badge tone="indigo">date</Badge>}
        </td>
      </tr>
      {isOpen && (
        <tr id={detailId} className="border-b border-zinc-100 bg-zinc-50/70">
          <td colSpan={7} className="px-3 py-4">
            <ColumnDetail column={c} />
          </td>
        </tr>
      )}
    </>
  );
}

function ColumnDetail({ column: c }: { column: ColumnProfile }) {
  return (
    <div className="space-y-3">
      {c.numeric && (
        <StatList
          items={[
            { label: "Count", value: formatNumber(c.numeric.count) },
            { label: "Mean", value: formatNumber(c.numeric.mean) },
            { label: "Median", value: formatNumber(c.numeric.median) },
            { label: "Std deviation", value: formatNumber(c.numeric.std) },
            { label: "Min", value: formatNumber(c.numeric.min) },
            { label: "Max", value: formatNumber(c.numeric.max) },
            { label: "Q1 / Q3", value: `${formatNumber(c.numeric.q1)} / ${formatNumber(c.numeric.q3)}` },
            { label: "Sum", value: formatNumber(c.numeric.sum) },
            { label: "Negative values", value: formatNumber(c.numeric.negatives) },
            { label: "Zeros", value: formatNumber(c.numeric.zeros) },
            { label: "Potential outliers", value: formatNumber(c.numeric.outliers.count) },
          ]}
        />
      )}
      {c.date_range && (
        <StatList
          items={[
            { label: "Earliest", value: formatDate(c.date_range.min) },
            { label: "Latest", value: formatDate(c.date_range.max) },
            { label: "Span", value: `${formatNumber(c.date_range.span_days)} days` },
            { label: "Future dates", value: formatNumber(c.date_range.future_count) },
          ]}
        />
      )}
      {c.top_categories && c.top_categories.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-medium text-zinc-500">Most common values</p>
          <ul className="flex flex-wrap gap-2">
            {c.top_categories.map((t) => (
              <li key={t.value} className="rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs">
                <span className="font-medium">{t.value}</span> <span className="text-zinc-500">{formatNumber(t.count)} ({formatPercent(t.pct)})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {c.invalid > 0 && (
        <p className="text-sm text-red-800">
          {c.invalid} value(s) could not be read as {titleCase(c.inferred_type).toLowerCase()} and were excluded, e.g. {c.invalid_examples.map((e) => `“${e}”`).join(", ")}.
        </p>
      )}
      {c.notes.length > 0 && (
        <ul className="list-disc pl-5 text-sm text-zinc-600">
          {c.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
      <p className="text-xs text-zinc-500">Sample values: {c.sample_values.length ? c.sample_values.join(" · ") : "none"}</p>
    </div>
  );
}
