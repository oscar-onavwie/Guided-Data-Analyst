"""Pydantic models: the validated shape of every API response.

The frontend's TypeScript types (frontend/src/lib/types.ts) mirror these.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["confirmed", "potential"]
Strength = Literal["strong", "moderate", "weak"]

# --------------------------------------------------------------------------- #
# Upload / dataset
# --------------------------------------------------------------------------- #


class Preview(BaseModel):
    columns: list[str]
    rows: list[list[str | None]]
    offset: int
    limit: int
    total_rows: int


class DatasetSummary(BaseModel):
    dataset_id: str
    filename: str
    file_type: Literal["csv", "xlsx"]
    sheet: str | None = None
    sheets: list[str] = Field(default_factory=list)
    is_demo: bool = False
    demo_key: str | None = None
    rows: int
    columns: int
    column_names: list[str]
    parse_notes: list[str]
    loaded_at: str
    expires_at: str
    preview: Preview


class SheetList(BaseModel):
    filename: str
    sheets: list[str]


class DemoDataset(BaseModel):
    key: str
    title: str
    description: str
    filename: str


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #


class OutlierInfo(BaseModel):
    method: str
    lower_fence: float
    upper_fence: float
    count: int
    pct: float
    extreme_count: int
    examples: list[float]


class NumericSummary(BaseModel):
    count: int
    mean: float
    median: float
    std: float | None
    min: float
    max: float
    q1: float
    q3: float
    iqr: float
    sum: float
    negatives: int
    zeros: int
    skewness: float | None
    outliers: OutlierInfo


class CategoryCount(BaseModel):
    value: str
    count: int
    pct: float


class DateRange(BaseModel):
    min: str
    max: str
    span_days: int
    future_count: int
    pre_1900_count: int


class ColumnProfile(BaseModel):
    name: str
    inferred_type: str
    role: str
    non_missing: int
    missing: int
    missing_pct: float
    invalid: int
    invalid_examples: list[str]
    unique: int
    unique_pct: float
    is_constant: bool
    likely_identifier: bool
    candidate_date: bool
    notes: list[str]
    numeric: NumericSummary | None = None
    top_categories: list[CategoryCount] | None = None
    date_range: DateRange | None = None
    sample_values: list[str]


class DataIssue(BaseModel):
    id: str
    severity: Severity
    category: str
    column: str | None = None
    message: str
    count: int | None = None


class DatasetProfile(BaseModel):
    rows: int
    columns: int
    duplicate_rows: int
    duplicate_pct: float
    missing_cells: int
    missing_cells_pct: float
    type_counts: dict[str, int]
    column_profiles: list[ColumnProfile]
    issues: list[DataIssue]
    parse_notes: list[str]


# --------------------------------------------------------------------------- #
# Explore
# --------------------------------------------------------------------------- #


class HistogramBin(BaseModel):
    start: float
    end: float
    count: int


class BoxPlot(BaseModel):
    lower_whisker: float
    q1: float
    median: float
    q3: float
    upper_whisker: float
    outliers: list[float]
    outlier_count: int


class NumericAnalysis(BaseModel):
    column: str
    summary: NumericSummary
    histogram: list[HistogramBin]
    box: BoxPlot


class CategoryFrequency(BaseModel):
    column: str
    non_missing: int
    missing: int
    unique: int
    rows: list[CategoryCount]
    other_count: int
    other_categories: int


class TimePoint(BaseModel):
    period: str  # ISO date of period start
    label: str
    count: int
    value: float | None = None


class TimeSeries(BaseModel):
    date_column: str
    value_column: str | None = None
    agg: Literal["count", "sum", "mean"]
    granularity: Literal["day", "week", "month", "quarter", "year"]
    points: list[TimePoint]
    first_period_partial: bool
    last_period_partial: bool


class DateAnalysis(BaseModel):
    column: str
    range: DateRange
    records_over_time: TimeSeries


class CorrelationPair(BaseModel):
    x: str
    y: str
    r: float
    n: int
    strength: Strength


class CorrelationMatrix(BaseModel):
    method: str
    columns: list[str]
    matrix: list[list[float | None]]
    pairs: list[CorrelationPair]


class GroupRow(BaseModel):
    group: str
    count: int
    mean: float | None
    median: float | None
    sum: float | None
    share_of_total: float | None


class GroupedSummary(BaseModel):
    category_column: str
    value_column: str
    rows: list[GroupRow]
    total: float
    shares_valid: bool
    note: str | None = None


class ScatterPoint(BaseModel):
    x: float
    y: float


class ScatterData(BaseModel):
    x: str
    y: str
    points: list[ScatterPoint]
    n_total: int
    n_shown: int
    r: float | None


class AnalysisBundle(BaseModel):
    numeric: list[NumericAnalysis]
    categorical: list[CategoryFrequency]
    dates: list[DateAnalysis]
    correlation: CorrelationMatrix | None
    default_grouped: GroupedSummary | None
    default_timeseries: TimeSeries | None
    default_scatter: ScatterData | None
    measures: list[str]
    dimensions: list[str]
    date_columns: list[str]
    skipped: list[str]


class GroupedRequest(BaseModel):
    category_column: str = Field(min_length=1, max_length=200)
    value_column: str = Field(min_length=1, max_length=200)


class ScatterRequest(BaseModel):
    x: str = Field(min_length=1, max_length=200)
    y: str = Field(min_length=1, max_length=200)


class TimeSeriesRequest(BaseModel):
    date_column: str = Field(min_length=1, max_length=200)
    value_column: str | None = Field(default=None, max_length=200)
    agg: Literal["count", "sum", "mean"] = "count"
    granularity: Literal["auto", "day", "week", "month", "quarter", "year"] = "auto"


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #


class Evidence(BaseModel):
    label: str
    value: str
    calculation: str


class Finding(BaseModel):
    id: str
    kind: str
    title: str
    description: str
    evidence: list[Evidence]
    columns: list[str]
    period: str | None = None
    why_it_matters: str
    caveat: str
    follow_up: str
    score: float
    strength: Strength
    statement_type: Literal["descriptive"] = "descriptive"


class FindingsResult(BaseModel):
    findings: list[Finding]
    message: str | None
    ranking_method: list[str]


# --------------------------------------------------------------------------- #
# AI
# --------------------------------------------------------------------------- #


class AIRequest(BaseModel):
    consent: bool = Field(description="User has acknowledged that summaries are sent to an external AI service.")


class AIFindingExplanation(BaseModel):
    finding_id: str
    explanation: str
    unverified_numbers: list[str] = Field(default_factory=list)


class AIFollowUp(BaseModel):
    question: str
    finding_ids: list[str]


class AIExplanation(BaseModel):
    summary: str
    explanations: list[AIFindingExplanation]
    follow_ups: list[AIFollowUp]
    model: str
    warnings: list[str]
    disclaimer: str


class AppConfig(BaseModel):
    max_upload_mb: int
    max_rows: int
    max_columns: int
    session_ttl_minutes: int
    ai_available: bool
    data_retention: str
