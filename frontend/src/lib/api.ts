// Thin, typed client for the FastAPI backend. Every response is checked for
// the fields the UI relies on before it is used, and every failure becomes an
// ApiError with a plain-English message.

import type {
  AIExplanation,
  AnalysisBundle,
  AppConfig,
  DatasetProfile,
  DatasetSummary,
  DemoDataset,
  FindingsResult,
  GroupedSummary,
  ScatterData,
  SheetList,
  TimeSeries,
  Aggregation,
  Granularity,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message: string,
    public readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Minimal runtime validation: required keys must be present. */
function expectKeys<T>(value: unknown, keys: string[], what: string): T {
  if (!isRecord(value) || keys.some((k) => !(k in value))) {
    throw new ApiError("invalid_response", 0, `The server sent an unexpected response for ${what}.`);
  }
  return value as T;
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new ApiError(
      "network_error",
      0,
      `Cannot reach the analysis server at ${API_URL}. Make sure the backend is running (see README).`,
    );
  }
  if (response.status === 204) return null;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    if (!response.ok) throw new ApiError("http_error", response.status, `The server returned an error (HTTP ${response.status}).`);
    throw new ApiError("invalid_response", response.status, "The server sent a response that could not be read.");
  }
  if (!response.ok) {
    if (isRecord(body) && isRecord(body.error) && typeof body.error.message === "string") {
      const err = body.error;
      throw new ApiError(String(err.code ?? "error"), response.status, err.message as string, isRecord(err.details) ? err.details : {});
    }
    throw new ApiError("http_error", response.status, `The server returned an error (HTTP ${response.status}).`);
  }
  return body;
}

const json = (data: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(data),
});

export const api = {
  async config(): Promise<AppConfig> {
    return expectKeys<AppConfig>(await request("/api/config"), ["max_upload_mb", "ai_available", "data_retention"], "settings");
  },

  async demos(): Promise<DemoDataset[]> {
    const body = await request("/api/demo-datasets");
    if (!Array.isArray(body)) throw new ApiError("invalid_response", 0, "Unexpected demo dataset list.");
    return body.map((d) => expectKeys<DemoDataset>(d, ["key", "title", "description"], "a demo dataset"));
  },

  async sheets(file: File): Promise<SheetList> {
    const form = new FormData();
    form.append("file", file);
    return expectKeys<SheetList>(await request("/api/files/sheets", { method: "POST", body: form }), ["sheets"], "worksheets");
  },

  async upload(file: File, sheet?: string): Promise<DatasetSummary> {
    const form = new FormData();
    form.append("file", file);
    if (sheet) form.append("sheet", sheet);
    return expectKeys<DatasetSummary>(
      await request("/api/datasets", { method: "POST", body: form }),
      ["dataset_id", "rows", "columns", "preview"],
      "the upload",
    );
  },

  async loadDemo(key: string): Promise<DatasetSummary> {
    return expectKeys<DatasetSummary>(
      await request(`/api/demo-datasets/${encodeURIComponent(key)}`, { method: "POST" }),
      ["dataset_id", "rows", "columns", "preview"],
      "the demo dataset",
    );
  },

  async remove(datasetId: string): Promise<void> {
    await request(`/api/datasets/${encodeURIComponent(datasetId)}`, { method: "DELETE" });
  },

  async profile(datasetId: string): Promise<DatasetProfile> {
    return expectKeys<DatasetProfile>(
      await request(`/api/datasets/${encodeURIComponent(datasetId)}/profile`),
      ["rows", "column_profiles", "issues"],
      "the profile",
    );
  },

  async analysis(datasetId: string): Promise<AnalysisBundle> {
    return expectKeys<AnalysisBundle>(
      await request(`/api/datasets/${encodeURIComponent(datasetId)}/analysis`),
      ["numeric", "categorical", "dates", "measures", "dimensions"],
      "the analysis",
    );
  },

  async grouped(datasetId: string, categoryColumn: string, valueColumn: string): Promise<GroupedSummary> {
    return expectKeys<GroupedSummary>(
      await request(
        `/api/datasets/${encodeURIComponent(datasetId)}/explore/grouped`,
        json({ category_column: categoryColumn, value_column: valueColumn }),
      ),
      ["rows", "shares_valid"],
      "the group comparison",
    );
  },

  async scatter(datasetId: string, x: string, y: string): Promise<ScatterData> {
    return expectKeys<ScatterData>(
      await request(`/api/datasets/${encodeURIComponent(datasetId)}/explore/scatter`, json({ x, y })),
      ["points", "n_total"],
      "the scatter plot",
    );
  },

  async timeseries(
    datasetId: string,
    dateColumn: string,
    valueColumn: string | null,
    agg: Aggregation,
    granularity: Granularity | "auto",
  ): Promise<TimeSeries> {
    return expectKeys<TimeSeries>(
      await request(
        `/api/datasets/${encodeURIComponent(datasetId)}/explore/timeseries`,
        json({ date_column: dateColumn, value_column: valueColumn, agg, granularity }),
      ),
      ["points", "granularity"],
      "the time series",
    );
  },

  async findings(datasetId: string): Promise<FindingsResult> {
    return expectKeys<FindingsResult>(
      await request(`/api/datasets/${encodeURIComponent(datasetId)}/findings`),
      ["findings", "ranking_method"],
      "the findings",
    );
  },

  async aiExplanation(datasetId: string, consent: boolean): Promise<AIExplanation> {
    return expectKeys<AIExplanation>(
      await request(`/api/datasets/${encodeURIComponent(datasetId)}/ai-explanation`, json({ consent })),
      ["summary", "explanations", "disclaimer"],
      "the AI explanation",
    );
  },

  reportUrl(datasetId: string, download = true): string {
    return `${API_URL}/api/datasets/${encodeURIComponent(datasetId)}/report.html${download ? "" : "?download=false"}`;
  },

  exportUrl(datasetId: string, table: string): string {
    return `${API_URL}/api/datasets/${encodeURIComponent(datasetId)}/export/${encodeURIComponent(table)}.csv`;
  },
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
