// Pure formatting and validation helpers. No imports, so they can be unit
// tested directly with Node's test runner (see tests/format.test.ts).

/** Format a number for display: thousands separators, sensible decimals, "–" for missing. */
export function formatNumber(value: number | null | undefined, maxDecimals = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const abs = Math.abs(value);
  const decimals = Number.isInteger(value) ? 0 : abs >= 1000 ? 0 : abs >= 1 ? maxDecimals : Math.max(maxDecimals, 3);
  return value.toLocaleString("en-GB", { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
}

/** Short axis labels: 1,200 -> 1.2k, 3,400,000 -> 3.4M. */
export function compactNumber(value: number): string {
  if (!Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}k`;
  return formatNumber(value);
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  return `${value.toFixed(decimals)}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const ACCEPTED_EXTENSIONS = [".csv", ".xlsx"] as const;

export type FileCheck = { ok: true; extension: ".csv" | ".xlsx" } | { ok: false; message: string };

/** Client-side pre-check. The backend re-validates everything; this just gives faster feedback. */
export function checkFile(name: string, size: number, maxMb: number): FileCheck {
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  if (ext === ".xls" || ext === ".xlsm" || ext === ".xlsb") {
    return { ok: false, message: `${ext} files are not supported. Save the workbook as .xlsx or export the sheet as .csv.` };
  }
  if (ext !== ".csv" && ext !== ".xlsx") {
    return { ok: false, message: `Unsupported file type${ext ? ` “${ext}”` : ""}. Upload a .csv or .xlsx file.` };
  }
  if (size === 0) return { ok: false, message: "The file is empty." };
  if (size > maxMb * 1024 * 1024) {
    return { ok: false, message: `The file is ${formatBytes(size)}, which is over the ${maxMb} MB limit.` };
  }
  return { ok: true, extension: ext as ".csv" | ".xlsx" };
}

/** Diverging colour for a correlation coefficient in [-1, 1] (teal = positive, red = negative). */
export function correlationColour(r: number | null): string {
  if (r === null || !Number.isFinite(r)) return "transparent";
  const a = Math.min(1, Math.abs(r));
  return r >= 0 ? `rgba(15, 118, 110, ${0.08 + a * 0.82})` : `rgba(185, 28, 28, ${0.08 + a * 0.82})`;
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
