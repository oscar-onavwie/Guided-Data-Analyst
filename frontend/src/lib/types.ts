// TypeScript mirror of the backend's Pydantic models (backend/app/schemas.py).
// Keep the two in sync when either changes.

export type Severity = "confirmed" | "potential";
export type Strength = "strong" | "moderate" | "weak";

export interface Preview {
  columns: string[];
  rows: (string | null)[][];
  offset: number;
  limit: number;
  total_rows: number;
}

export interface DatasetSummary {
  dataset_id: string;
  filename: string;
  file_type: "csv" | "xlsx";
  sheet: string | null;
  sheets: string[];
  is_demo: boolean;
  demo_key: string | null;
  rows: number;
  columns: number;
  column_names: string[];
  parse_notes: string[];
  loaded_at: string;
  expires_at: string;
  preview: Preview;
}

export interface SheetList {
  filename: string;
  sheets: string[];
}

export interface DemoDataset {
  key: string;
  title: string;
  description: string;
  filename: string;
}

export interface AppConfig {
  max_upload_mb: number;
  max_rows: number;
  max_columns: number;
  session_ttl_minutes: number;
  ai_available: boolean;
  data_retention: string;
}

export interface OutlierInfo {
  method: string;
  lower_fence: number;
  upper_fence: number;
  count: number;
  pct: number;
  extreme_count: number;
  examples: number[];
}

export interface NumericSummary {
  count: number;
  mean: number;
  median: number;
  std: number | null;
  min: number;
  max: number;
  q1: number;
  q3: number;
  iqr: number;
  sum: number;
  negatives: number;
  zeros: number;
  skewness: number | null;
  outliers: OutlierInfo;
}

export interface CategoryCount {
  value: string;
  count: number;
  pct: number;
}

export interface DateRange {
  min: string;
  max: string;
  span_days: number;
  future_count: number;
  pre_1900_count: number;
}

export interface ColumnProfile {
  name: string;
  inferred_type: "empty" | "boolean" | "numeric" | "datetime" | "categorical" | "text";
  role: "identifier" | "date" | "measure" | "dimension" | "other";
  non_missing: number;
  missing: number;
  missing_pct: number;
  invalid: number;
  invalid_examples: string[];
  unique: number;
  unique_pct: number;
  is_constant: boolean;
  likely_identifier: boolean;
  candidate_date: boolean;
  notes: string[];
  numeric: NumericSummary | null;
  top_categories: CategoryCount[] | null;
  date_range: DateRange | null;
  sample_values: string[];
}

export interface DataIssue {
  id: string;
  severity: Severity;
  category: string;
  column: string | null;
  message: string;
  count: number | null;
}

export interface DatasetProfile {
  rows: number;
  columns: number;
  duplicate_rows: number;
  duplicate_pct: number;
  missing_cells: number;
  missing_cells_pct: number;
  type_counts: Record<string, number>;
  column_profiles: ColumnProfile[];
  issues: DataIssue[];
  parse_notes: string[];
}

export interface HistogramBin {
  start: number;
  end: number;
  count: number;
}

export interface BoxPlot {
  lower_whisker: number;
  q1: number;
  median: number;
  q3: number;
  upper_whisker: number;
  outliers: number[];
  outlier_count: number;
}

export interface NumericAnalysis {
  column: string;
  summary: NumericSummary;
  histogram: HistogramBin[];
  box: BoxPlot;
}

export interface CategoryFrequency {
  column: string;
  non_missing: number;
  missing: number;
  unique: number;
  rows: CategoryCount[];
  other_count: number;
  other_categories: number;
}

export type Granularity = "day" | "week" | "month" | "quarter" | "year";
export type Aggregation = "count" | "sum" | "mean";

export interface TimePoint {
  period: string;
  label: string;
  count: number;
  value: number | null;
}

export interface TimeSeries {
  date_column: string;
  value_column: string | null;
  agg: Aggregation;
  granularity: Granularity;
  points: TimePoint[];
  first_period_partial: boolean;
  last_period_partial: boolean;
}

export interface DateAnalysis {
  column: string;
  range: DateRange;
  records_over_time: TimeSeries;
}

export interface CorrelationPair {
  x: string;
  y: string;
  r: number;
  n: number;
  strength: Strength;
}

export interface CorrelationMatrix {
  method: string;
  columns: string[];
  matrix: (number | null)[][];
  pairs: CorrelationPair[];
}

export interface GroupRow {
  group: string;
  count: number;
  mean: number | null;
  median: number | null;
  sum: number | null;
  share_of_total: number | null;
}

export interface GroupedSummary {
  category_column: string;
  value_column: string;
  rows: GroupRow[];
  total: number;
  shares_valid: boolean;
  note: string | null;
}

export interface ScatterPoint {
  x: number;
  y: number;
}

export interface ScatterData {
  x: string;
  y: string;
  points: ScatterPoint[];
  n_total: number;
  n_shown: number;
  r: number | null;
}

export interface AnalysisBundle {
  numeric: NumericAnalysis[];
  categorical: CategoryFrequency[];
  dates: DateAnalysis[];
  correlation: CorrelationMatrix | null;
  default_grouped: GroupedSummary | null;
  default_timeseries: TimeSeries | null;
  default_scatter: ScatterData | null;
  measures: string[];
  dimensions: string[];
  date_columns: string[];
  skipped: string[];
}

export interface Evidence {
  label: string;
  value: string;
  calculation: string;
}

export interface Finding {
  id: string;
  kind: string;
  title: string;
  description: string;
  evidence: Evidence[];
  columns: string[];
  period: string | null;
  why_it_matters: string;
  caveat: string;
  follow_up: string;
  score: number;
  strength: Strength;
  statement_type: "descriptive";
}

export interface FindingsResult {
  findings: Finding[];
  message: string | null;
  ranking_method: string[];
}

export interface AIFindingExplanation {
  finding_id: string;
  explanation: string;
  unverified_numbers: string[];
}

export interface AIExplanation {
  summary: string;
  explanations: AIFindingExplanation[];
  follow_ups: { question: string; finding_ids: string[] }[];
  model: string;
  warnings: string[];
  disclaimer: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}
