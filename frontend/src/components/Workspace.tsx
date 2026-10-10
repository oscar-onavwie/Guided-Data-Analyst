"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { AIExplanation, AnalysisBundle, AppConfig, DatasetProfile, DatasetSummary, DemoDataset, FindingsResult } from "@/lib/types";
import { StageNav, type Stage } from "./StageNav";
import { DatasetStatus } from "./DatasetStatus";
import { Alert, Button } from "./ui";
import { UploadStage } from "./stages/UploadStage";
import { ProfileStage } from "./stages/ProfileStage";
import { ExploreStage } from "./stages/ExploreStage";
import { DiscoverStage } from "./stages/DiscoverStage";
import { ReportStage } from "./stages/ReportStage";

export type Loadable<T> = { status: "idle" } | { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: string; code?: string };

const IDLE = { status: "idle" } as const;

export function Workspace() {
  const [stage, setStage] = useState<Stage>("upload");
  const [config, setConfig] = useState<Loadable<AppConfig>>(IDLE);
  const [demos, setDemos] = useState<DemoDataset[]>([]);
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [profile, setProfile] = useState<Loadable<DatasetProfile>>(IDLE);
  const [analysis, setAnalysis] = useState<Loadable<AnalysisBundle>>(IDLE);
  const [findings, setFindings] = useState<Loadable<FindingsResult>>(IDLE);
  const [ai, setAi] = useState<AIExplanation | null>(null);
  const [expired, setExpired] = useState(false);
  const mainRef = useRef<HTMLDivElement>(null);

  // Load server settings and the demo list once.
  useEffect(() => {
    setConfig({ status: "loading" });
    api
      .config()
      .then((data) => setConfig({ status: "ready", data }))
      .catch((e) => setConfig({ status: "error", error: errorMessage(e) }));
    api
      .demos()
      .then(setDemos)
      .catch(() => setDemos([]));
  }, []);

  const handleError = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.code === "dataset_not_found") setExpired(true);
    return { status: "error" as const, error: errorMessage(e), code: e instanceof ApiError ? e.code : undefined };
  }, []);

  // Fetch each stage's data the first time it is needed, then keep it.
  useEffect(() => {
    if (!dataset) return;
    const id = dataset.dataset_id;
    if ((stage === "profile" || stage === "report") && profile.status === "idle") {
      setProfile({ status: "loading" });
      api.profile(id).then((data) => setProfile({ status: "ready", data })).catch((e) => setProfile(handleError(e)));
    }
    if ((stage === "explore" || stage === "report") && analysis.status === "idle") {
      setAnalysis({ status: "loading" });
      api.analysis(id).then((data) => setAnalysis({ status: "ready", data })).catch((e) => setAnalysis(handleError(e)));
    }
    if ((stage === "discover" || stage === "report") && findings.status === "idle") {
      setFindings({ status: "loading" });
      api.findings(id).then((data) => setFindings({ status: "ready", data })).catch((e) => setFindings(handleError(e)));
    }
  }, [stage, dataset, profile.status, analysis.status, findings.status, handleError]);

  const goTo = useCallback((next: Stage) => {
    setStage(next);
    // Move focus to the workspace so keyboard and screen-reader users land on the new content.
    requestAnimationFrame(() => mainRef.current?.focus());
  }, []);

  const onLoaded = useCallback((summary: DatasetSummary) => {
    setDataset(summary);
    setProfile(IDLE);
    setAnalysis(IDLE);
    setFindings(IDLE);
    setAi(null);
    setExpired(false);
  }, []);

  const onRemove = useCallback(async () => {
    if (dataset) {
      try {
        await api.remove(dataset.dataset_id);
      } catch {
        // The dataset may already have expired; removing it locally is still correct.
      }
    }
    setDataset(null);
    setProfile(IDLE);
    setAnalysis(IDLE);
    setFindings(IDLE);
    setAi(null);
    setExpired(false);
    goTo("upload");
  }, [dataset, goTo]);

  const cfg = config.status === "ready" ? config.data : null;

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900">
      <a href="#workspace" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        Skip to workspace
      </a>
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-teal-700 text-sm font-bold text-white" aria-hidden="true">
              GD
            </span>
            <div>
              <h1 className="text-base font-semibold leading-tight">Guided Data Analyst</h1>
              <p className="text-xs text-zinc-500">Upload · understand · discover · report</p>
            </div>
          </div>
          <DatasetStatus dataset={dataset} onRemove={onRemove} />
        </div>
      </header>

      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 md:flex-row md:gap-6 md:py-6">
        <StageNav active={stage} onSelect={goTo} hasDataset={!!dataset} />
        <main id="workspace" ref={mainRef} tabIndex={-1} className="min-w-0 flex-1 space-y-4 outline-none">
          {config.status === "error" && (
            <Alert tone="error" title="The analysis server is not reachable">
              {config.error}
            </Alert>
          )}
          {expired && (
            <Alert tone="warning" title="This dataset has expired">
              Datasets are kept in server memory for a limited time and then deleted.{" "}
              <Button variant="secondary" className="ml-2 mt-2" onClick={onRemove}>
                Upload again
              </Button>
            </Alert>
          )}

          {stage === "upload" && (
            <UploadStage config={cfg} demos={demos} dataset={dataset} onLoaded={onLoaded} onContinue={() => goTo("profile")} />
          )}
          {stage === "profile" && dataset && <ProfileStage profile={profile} onContinue={() => goTo("explore")} />}
          {stage === "explore" && dataset && <ExploreStage datasetId={dataset.dataset_id} analysis={analysis} onContinue={() => goTo("discover")} />}
          {stage === "discover" && dataset && (
            <DiscoverStage
              datasetId={dataset.dataset_id}
              findings={findings}
              aiAvailable={!!cfg?.ai_available}
              ai={ai}
              onAi={setAi}
              onContinue={() => goTo("report")}
            />
          )}
          {stage === "report" && dataset && <ReportStage dataset={dataset} profile={profile} analysis={analysis} findings={findings} aiIncluded={!!ai} />}

          <footer className="pt-4 text-xs text-zinc-500">
            {cfg?.data_retention ?? "Files are processed in memory and deleted automatically. Use non-sensitive data only."} This is a learning
            project and is not suitable for confidential, personal or patient data.
          </footer>
        </main>
      </div>
    </div>
  );
}
