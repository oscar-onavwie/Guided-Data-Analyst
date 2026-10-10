"use client";

import { useRef, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { checkFile, formatBytes, formatDate, formatNumber } from "@/lib/format";
import type { AppConfig, DatasetSummary, DemoDataset } from "@/lib/types";
import { DataTable } from "../DataTable";
import { Alert, Badge, Button, Card, Select, Spinner, cx } from "../ui";

type Phase =
  | { kind: "idle" }
  | { kind: "busy"; message: string }
  | { kind: "choose-sheet"; file: File; sheets: string[]; selected: string }
  | { kind: "error"; message: string };

export function UploadStage({ config, demos, dataset, onLoaded, onContinue }: {
  config: AppConfig | null;
  demos: DemoDataset[];
  dataset: DatasetSummary | null;
  onLoaded: (d: DatasetSummary) => void;
  onContinue: () => void;
}) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const maxMb = config?.max_upload_mb ?? 20;
  const busy = phase.kind === "busy";

  async function upload(file: File, sheet?: string) {
    setPhase({ kind: "busy", message: `Reading and parsing ${file.name}…` });
    try {
      const summary = await api.upload(file, sheet);
      onLoaded(summary);
      setPhase({ kind: "idle" });
    } catch (e) {
      setPhase({ kind: "error", message: errorMessage(e) });
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return;
    const check = checkFile(file.name, file.size, maxMb);
    if (!check.ok) {
      setPhase({ kind: "error", message: check.message });
      return;
    }
    if (check.extension === ".xlsx") {
      setPhase({ kind: "busy", message: "Reading worksheet names…" });
      try {
        const { sheets } = await api.sheets(file);
        if (sheets.length > 1) {
          setPhase({ kind: "choose-sheet", file, sheets, selected: sheets[0] });
          return;
        }
        await upload(file, sheets[0]);
      } catch (e) {
        setPhase({ kind: "error", message: errorMessage(e) });
      }
      return;
    }
    await upload(file);
  }

  async function loadDemo(key: string) {
    setPhase({ kind: "busy", message: "Loading demo dataset…" });
    try {
      onLoaded(await api.loadDemo(key));
      setPhase({ kind: "idle" });
    } catch (e) {
      setPhase({ kind: "error", message: errorMessage(e) });
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Upload a dataset" description="CSV or Excel (.xlsx). The first row should contain column names.">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (!busy) void handleFile(e.dataTransfer.files?.[0]);
          }}
          className={cx(
            "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
            dragging ? "border-teal-600 bg-teal-50" : "border-zinc-300 bg-zinc-50",
          )}
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-8 w-8 text-teal-700" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <p className="text-sm text-zinc-700">Drag a file here, or</p>
          <Button onClick={() => inputRef.current?.click()} disabled={busy}>
            Choose a file
          </Button>
          <input
            ref={inputRef}
            id="file-input"
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="sr-only"
            aria-label="Choose a CSV or Excel file"
            onChange={(e) => {
              void handleFile(e.target.files?.[0]);
              e.target.value = ""; // allow re-selecting the same file
            }}
          />
          <p className="text-xs text-zinc-500">
            Up to {maxMb} MB
            {config ? `, ${formatNumber(config.max_rows)} rows and ${config.max_columns} columns` : ""}. Macros and formulas are never run.
          </p>
        </div>

        <div className="mt-4 space-y-3" aria-live="polite">
          {phase.kind === "busy" && <Spinner label={phase.message} />}
          {phase.kind === "error" && (
            <Alert tone="error" title="The file could not be loaded">
              {phase.message}
            </Alert>
          )}
          {phase.kind === "choose-sheet" && (
            <div className="rounded-lg border border-zinc-200 p-4">
              <p className="mb-3 text-sm">
                <strong>{phase.file.name}</strong> ({formatBytes(phase.file.size)}) has {phase.sheets.length} worksheets. Which one should be analysed?
              </p>
              <div className="flex flex-wrap items-end gap-3">
                <Select
                  id="sheet-select"
                  label="Worksheet"
                  value={phase.selected}
                  onChange={(v) => setPhase({ ...phase, selected: v })}
                  options={phase.sheets.map((s) => ({ value: s, label: s }))}
                />
                <Button onClick={() => void upload(phase.file, phase.selected)}>Analyse this sheet</Button>
                <Button variant="ghost" onClick={() => setPhase({ kind: "idle" })}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card
        title="Or try a demo dataset"
        description="Fictional data with known patterns, useful for seeing what the app does. Demo results are always labelled as demo data."
      >
        {demos.length === 0 ? (
          <p className="text-sm text-zinc-500">Demo datasets are unavailable because the server could not be reached.</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-3">
            {demos.map((d) => (
              <li key={d.key} className="flex flex-col justify-between gap-3 rounded-lg border border-zinc-200 p-4">
                <div>
                  <p className="font-medium text-zinc-900">{d.title}</p>
                  <p className="mt-1 text-sm text-zinc-600">{d.description}</p>
                </div>
                <Button variant="secondary" disabled={busy} onClick={() => void loadDemo(d.key)} aria-label={`Load demo: ${d.title}`}>
                  Load demo
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {dataset && (
        <Card
          title={
            <span className="flex flex-wrap items-center gap-2">
              {dataset.filename}
              {dataset.is_demo && <Badge tone="amber">DEMO DATA</Badge>}
              <Badge tone="teal">Parsed successfully</Badge>
            </span>
          }
          description={`${formatNumber(dataset.rows)} rows × ${dataset.columns} columns${dataset.sheet ? ` · worksheet “${dataset.sheet}”` : ""} · loaded ${formatDate(dataset.loaded_at)}`}
          actions={<Button onClick={onContinue}>Continue to Profile →</Button>}
        >
          {dataset.parse_notes.length > 0 && (
            <div className="mb-4">
              <Alert tone="info" title="Changes made while reading the file">
                <ul className="list-disc pl-5">
                  {dataset.parse_notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </Alert>
            </div>
          )}
          <h3 className="mb-2 text-sm font-medium text-zinc-700">
            Preview: first {dataset.preview.rows.length} of {formatNumber(dataset.preview.total_rows)} rows (values exactly as read from the file)
          </h3>
          <DataTable columns={dataset.preview.columns} rows={dataset.preview.rows} caption={`Preview of ${dataset.filename}`} />
        </Card>
      )}
    </div>
  );
}
