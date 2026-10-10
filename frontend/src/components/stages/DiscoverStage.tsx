"use client";

import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { AIExplanation, Finding, FindingsResult } from "@/lib/types";
import type { Loadable } from "../Workspace";
import { Alert, Badge, Button, Card, EmptyState, LoadingBlock, Spinner } from "../ui";

const KIND_LABEL: Record<string, string> = {
  trend: "Trend",
  concentration: "Concentration",
  missing_data: "Missing data",
  group_difference: "Group difference",
  correlation: "Association",
  duplicates: "Duplicates",
  outliers: "Unusual values",
  negative_values: "Negative values",
};

export function DiscoverStage({ datasetId, findings, aiAvailable, ai, onAi, onContinue }: {
  datasetId: string;
  findings: Loadable<FindingsResult>;
  aiAvailable: boolean;
  ai: AIExplanation | null;
  onAi: (a: AIExplanation) => void;
  onContinue: () => void;
}) {
  if (findings.status === "idle" || findings.status === "loading") return <LoadingBlock label="Looking for patterns…" />;
  if (findings.status === "error") return <Alert tone="error" title="Findings could not be generated">{findings.error}</Alert>;
  const f = findings.data;

  return (
    <div className="space-y-4">
      <Card
        title={`Findings (${f.findings.length})`}
        description="Produced by fixed, documented rules — not by AI. Ranked by score; each shows the numbers behind it and its limitations."
        actions={<Button onClick={onContinue}>Continue to Report →</Button>}
      >
        {f.findings.length === 0 ? (
          <EmptyState title="No meaningful patterns found">{f.message}</EmptyState>
        ) : (
          <ol className="space-y-4">
            {f.findings.map((finding) => (
              <li key={finding.id}>
                <FindingCard finding={finding} aiNote={ai?.explanations.find((e) => e.finding_id === finding.id)?.explanation} />
              </li>
            ))}
          </ol>
        )}
        <details className="mt-4 text-sm">
          <summary className="cursor-pointer font-medium text-zinc-700">How findings are ranked</summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-zinc-600">
            {f.ranking_method.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </details>
      </Card>
      <AiPanel datasetId={datasetId} available={aiAvailable} hasFindings={f.findings.length > 0} ai={ai} onAi={onAi} />
    </div>
  );
}

function FindingCard({ finding: f, aiNote }: { finding: Finding; aiNote?: string }) {
  return (
    <article className="rounded-xl border border-zinc-200 p-4" aria-labelledby={`${f.id}-title`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono text-zinc-500">{f.id}</span>
        <Badge tone="indigo">{KIND_LABEL[f.kind] ?? f.kind}</Badge>
        <Badge tone={f.strength === "strong" ? "teal" : f.strength === "moderate" ? "neutral" : "amber"}>{f.strength}</Badge>
        <span className="ml-auto tabular-nums text-zinc-500">score {f.score}</span>
      </div>
      <h3 id={`${f.id}-title`} className="mt-2 font-semibold text-zinc-900">
        {f.title}
      </h3>
      <p className="mt-1 text-sm text-zinc-700">
        <Badge tone="teal" className="mr-1">Descriptive</Badge>
        {f.description}
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="min-w-full text-sm">
          <caption className="sr-only">Evidence for {f.id}</caption>
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-zinc-500">
              <th scope="col" className="py-1 pr-3">Evidence</th>
              <th scope="col" className="py-1 pr-3">Value</th>
              <th scope="col" className="py-1">How it was calculated</th>
            </tr>
          </thead>
          <tbody>
            {f.evidence.map((e) => (
              <tr key={e.label} className="border-t border-zinc-100 align-top">
                <td className="py-1 pr-3">{e.label}</td>
                <td className="py-1 pr-3 font-semibold tabular-nums">{e.value}</td>
                <td className="py-1 text-zinc-600">{e.calculation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        Columns: {f.columns.length ? f.columns.join(", ") : "whole dataset"}
        {f.period ? ` · Period: ${f.period}` : ""}
      </p>
      <p className="mt-3 text-sm text-zinc-700">
        <Badge tone="violet" className="mr-1">Interpretation</Badge>
        {f.why_it_matters}
      </p>
      <p className="mt-2 rounded-md border-l-4 border-amber-500 bg-amber-50 px-3 py-2 text-sm text-amber-950">
        <strong>Caveat:</strong> {f.caveat}
      </p>
      <p className="mt-2 text-sm">
        <strong>Follow-up question:</strong> {f.follow_up}
      </p>
      {aiNote && (
        <p className="mt-3 rounded-md bg-violet-50 px-3 py-2 text-sm text-violet-950">
          <Badge tone="violet" className="mr-1">AI-generated</Badge>
          {aiNote}
        </p>
      )}
    </article>
  );
}

function AiPanel({ datasetId, available, hasFindings, ai, onAi }: {
  datasetId: string;
  available: boolean;
  hasFindings: boolean;
  ai: AIExplanation | null;
  onAi: (a: AIExplanation) => void;
}) {
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<{ kind: "idle" } | { kind: "loading" } | { kind: "error"; message: string }>({ kind: "idle" });

  if (!available) {
    return (
      <Card title="AI explanation (optional)">
        <p className="text-sm text-zinc-600">
          <Badge className="mr-2">Unavailable</Badge>
          AI explanations are switched off on this server. Every finding above was calculated without AI, so nothing is missing from your analysis. See the
          README to enable it with your own API key.
        </p>
      </Card>
    );
  }

  async function run() {
    setState({ kind: "loading" });
    try {
      onAi(await api.aiExplanation(datasetId, consent));
      setState({ kind: "idle" });
    } catch (e) {
      setState({ kind: "error", message: errorMessage(e) });
    }
  }

  return (
    <Card title="AI explanation (optional)" description="A plain-English summary of the findings above, written by an external AI model.">
      {!ai && (
        <div className="space-y-3">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>
              I agree to send the column names, row counts and the findings with their evidence to the external AI service. <strong>Raw rows are not sent.</strong>{" "}
              Do not use this with sensitive data.
            </span>
          </label>
          <Button onClick={() => void run()} disabled={!consent || !hasFindings || state.kind === "loading"}>
            Generate AI explanation
          </Button>
          {!hasFindings && <p className="text-xs text-zinc-500">There are no findings to explain.</p>}
          {state.kind === "loading" && <Spinner label="Waiting for the AI service…" />}
          {state.kind === "error" && <Alert tone="error">{state.message}</Alert>}
        </div>
      )}
      {ai && (
        <div className="space-y-3 text-sm">
          <p className="rounded-md bg-violet-50 px-3 py-2 text-violet-950">
            <Badge tone="violet" className="mr-1">AI-generated</Badge>
            {ai.summary}
          </p>
          {ai.follow_ups.length > 0 && (
            <div>
              <p className="font-medium">Suggested follow-up analyses</p>
              <ul className="list-disc pl-5">
                {ai.follow_ups.map((q) => (
                  <li key={q.question}>
                    {q.question} {q.finding_ids.length > 0 && <span className="text-zinc-500">({q.finding_ids.join(", ")})</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {ai.warnings.length > 0 && (
            <Alert tone="warning" title="Checks on the AI response">
              <ul className="list-disc pl-5">
                {ai.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Alert>
          )}
          <p className="text-xs text-zinc-500">
            {ai.disclaimer} Model: {ai.model}.
          </p>
        </div>
      )}
    </Card>
  );
}
