"use client";

import { api } from "@/lib/api";
import type { AnalysisBundle, DatasetProfile, DatasetSummary, FindingsResult } from "@/lib/types";
import type { Loadable } from "../Workspace";
import { Alert, Badge, Card, LinkButton, LoadingBlock } from "../ui";

const SECTIONS = [
  "Dataset overview",
  "Data-quality assessment (confirmed vs potential issues)",
  "Analytical methodology",
  "Key statistics",
  "Charts",
  "Prioritised findings with evidence and caveats",
  "Limitations and assumptions",
  "Suggested next steps",
];

export function ReportStage({ dataset, profile, analysis, findings, aiIncluded }: {
  dataset: DatasetSummary;
  profile: Loadable<DatasetProfile>;
  analysis: Loadable<AnalysisBundle>;
  findings: Loadable<FindingsResult>;
  aiIncluded: boolean;
}) {
  const loading = [profile, analysis, findings].some((x) => x.status === "loading" || x.status === "idle");
  const failed = [profile, analysis, findings].find((x) => x.status === "error");
  if (failed && failed.status === "error") return <Alert tone="error" title="The report could not be prepared">{failed.error}</Alert>;
  if (loading) return <LoadingBlock label="Preparing the report…" />;
  const p = profile.status === "ready" ? profile.data : null;
  const a = analysis.status === "ready" ? analysis.data : null;
  const f = findings.status === "ready" ? findings.data : null;
  if (!p || !a || !f) return null;

  const exports: { table: string; label: string; available: boolean; reason?: string }[] = [
    { table: "column_profile", label: "Column profile", available: true },
    { table: "data_issues", label: "Data-quality issues", available: true },
    { table: "findings", label: "Findings with evidence", available: true },
    { table: "numeric_summary", label: "Numeric summary statistics", available: a.numeric.length > 0, reason: "no numeric columns" },
    { table: "category_frequencies", label: "Category frequency tables", available: a.categorical.length > 0, reason: "no category columns" },
    { table: "grouped_summary", label: "Group comparison", available: !!a.default_grouped, reason: "no category + measure pair" },
    { table: "time_series", label: "Time series", available: !!a.default_timeseries, reason: "no date column" },
    { table: "correlations", label: "Correlations", available: !!a.correlation, reason: "fewer than two numeric columns" },
  ];

  return (
    <div className="space-y-4">
      <Card
        title="Analysis report"
        description={`Built from the same results you have seen in the app for ${dataset.filename}. It includes the dataset name, the date it was loaded and the date the report was generated.`}
      >
        {dataset.is_demo && (
          <div className="mb-4">
            <Alert tone="warning">This report is based on a built-in DEMO dataset and will be labelled as such.</Alert>
          </div>
        )}
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-zinc-800">What the report contains</h3>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-zinc-700">
              {SECTIONS.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            <p className="mt-3 text-sm text-zinc-600">
              This dataset: {p.rows.toLocaleString("en-GB")} rows, {p.issues.length} data-quality issue(s), {f.findings.length} finding(s)
              {aiIncluded ? ", plus the AI explanation you generated (clearly labelled)" : ""}.
            </p>
          </div>
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-zinc-800">Download</h3>
            <div className="flex flex-wrap gap-2">
              <LinkButton variant="primary" href={api.reportUrl(dataset.dataset_id)} download>
                Download HTML report
              </LinkButton>
              <LinkButton href={api.reportUrl(dataset.dataset_id, false)} target="_blank" rel="noopener noreferrer">
                Open printable view
              </LinkButton>
            </div>
            <p className="text-xs text-zinc-500">
              For a PDF, open the printable view and use your browser&apos;s <strong>Print → Save as PDF</strong>. The HTML file is self-contained and works offline.
            </p>
          </div>
        </div>
      </Card>

      <Card title="Export tables as CSV" description="Opens cleanly in Excel. Cells that start with =, +, - or @ are prefixed with an apostrophe to prevent formula injection.">
        <ul className="grid gap-2 sm:grid-cols-2">
          {exports.map((e) => (
            <li key={e.table} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 px-3 py-2 text-sm">
              <span>{e.label}</span>
              {e.available ? (
                <a className="font-medium text-teal-800 hover:underline" href={api.exportUrl(dataset.dataset_id, e.table)} download>
                  Download CSV
                </a>
              ) : (
                <Badge>Unavailable: {e.reason}</Badge>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
