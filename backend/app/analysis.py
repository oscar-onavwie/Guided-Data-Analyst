"""Exploratory data analysis: deterministic statistics and chart-ready data.

Conventions (also in docs/methodology.md):

* Missing and invalid values are excluded from each calculation; the number of
  values actually used (`count` / `n`) is always returned.
* Quartiles use linear interpolation (pandas default; same as Excel
  QUARTILE.INC). Standard deviation is the sample standard deviation (n-1,
  same as Excel STDEV.S).
* Potential outliers use the 1.5 x IQR rule (Tukey's fences). Values beyond
  3 x IQR are counted as "extreme". If the IQR is zero the rule is not applied.
* Correlation is Pearson's r on pairs where both values are present, computed
  only when at least 10 such pairs exist and neither column is constant.
* Percentages are shares of non-missing values unless stated otherwise.
  Shares of a total are only reported when every value is non-negative, because
  "share of total" is meaningless when negative values cancel positive ones.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from .errors import AppError
from .inference import TypedColumn, TypedTable, now_utc_naive
from .schemas import (
    AnalysisBundle,
    BoxPlot,
    CategoryCount,
    CategoryFrequency,
    CorrelationMatrix,
    CorrelationPair,
    DateAnalysis,
    DateRange,
    GroupedSummary,
    GroupRow,
    HistogramBin,
    NumericAnalysis,
    NumericSummary,
    OutlierInfo,
    ScatterData,
    ScatterPoint,
    TimePoint,
    TimeSeries,
)

MIN_CORRELATION_PAIRS = 10
MAX_CORRELATION_COLUMNS = 12
MAX_SCATTER_POINTS = 500
MAX_GROUPS = 15

_MEASURE_HINT = re.compile(
    r"revenue|sales|amount|total|value|profit|income|cost|spend|units|quantity|qty|resolved|completed|orders|tickets|sold|price",
    re.I,
)


def rnd(value: float | None, digits: int = 6) -> float | None:
    """Round for display/JSON; turn NaN/inf into None."""
    if value is None:
        return None
    value = float(value)
    if not math.isfinite(value):
        return None
    return round(value, digits)


def safe_div(numerator: float, denominator: float) -> float | None:
    """Division that returns None instead of failing or producing inf."""
    if denominator == 0 or denominator is None or not math.isfinite(denominator):
        return None
    return numerator / denominator


def pct(part: float, whole: float) -> float:
    value = safe_div(part, whole)
    return 0.0 if value is None else round(100.0 * value, 2)


# --------------------------------------------------------------------------- #
# Column-level statistics
# --------------------------------------------------------------------------- #


def outlier_info(values: pd.Series, q1: float, q3: float) -> OutlierInfo:
    iqr = q3 - q1
    n = len(values)
    if iqr == 0:
        return OutlierInfo(
            method="IQR rule not applied: the middle 50% of values are identical (IQR = 0).",
            lower_fence=q1,
            upper_fence=q3,
            count=0,
            pct=0.0,
            extreme_count=0,
            examples=[],
        )
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    mask = (values < lower) | (values > upper)
    extreme = (values < q1 - 3 * iqr) | (values > q3 + 3 * iqr)
    flagged = values[mask]
    # Most extreme first, by distance from the nearest fence
    distance = np.maximum(lower - flagged, flagged - upper)
    examples = flagged.loc[distance.sort_values(ascending=False).index].head(5)
    return OutlierInfo(
        method="Tukey fences: below Q1 - 1.5*IQR or above Q3 + 1.5*IQR",
        lower_fence=rnd(lower),
        upper_fence=rnd(upper),
        count=int(mask.sum()),
        pct=pct(int(mask.sum()), n),
        extreme_count=int(extreme.sum()),
        examples=[rnd(v) for v in examples.tolist()],
    )


def numeric_summary(values: pd.Series) -> NumericSummary:
    v = values.dropna().astype(float)
    if v.empty:
        raise AppError(422, "no_numeric_values", "The column has no valid numeric values.")
    q1, median, q3 = (float(x) for x in v.quantile([0.25, 0.5, 0.75]))
    std = float(v.std(ddof=1)) if len(v) >= 2 else None
    skew = float(v.skew()) if len(v) >= 3 and std not in (None, 0.0) else None
    return NumericSummary(
        count=int(len(v)),
        mean=rnd(v.mean()),
        median=rnd(median),
        std=rnd(std),
        min=rnd(v.min()),
        max=rnd(v.max()),
        q1=rnd(q1),
        q3=rnd(q3),
        iqr=rnd(q3 - q1),
        sum=rnd(v.sum()),
        negatives=int((v < 0).sum()),
        zeros=int((v == 0).sum()),
        skewness=rnd(skew, 4),
        outliers=outlier_info(v, q1, q3),
    )


def histogram(values: pd.Series) -> list[HistogramBin]:
    v = values.dropna().astype(float).to_numpy()
    if len(v) == 0:
        return []
    lo, hi = float(v.min()), float(v.max())
    if lo == hi:
        return [HistogramBin(start=lo, end=hi, count=int(len(v)))]
    bins = int(min(20, max(5, math.ceil(math.log2(len(v)) + 1))))  # Sturges' rule, capped
    counts, edges = np.histogram(v, bins=bins, range=(lo, hi))
    return [HistogramBin(start=rnd(edges[i]), end=rnd(edges[i + 1]), count=int(counts[i])) for i in range(len(counts))]


def box_plot(values: pd.Series, summary: NumericSummary) -> BoxPlot:
    v = values.dropna().astype(float)
    o = summary.outliers
    inside = v[(v >= o.lower_fence) & (v <= o.upper_fence)] if summary.iqr else v
    outside = v[(v < o.lower_fence) | (v > o.upper_fence)] if summary.iqr else v.iloc[0:0]
    return BoxPlot(
        lower_whisker=rnd(inside.min() if len(inside) else summary.min),
        q1=summary.q1,
        median=summary.median,
        q3=summary.q3,
        upper_whisker=rnd(inside.max() if len(inside) else summary.max),
        outliers=[rnd(x) for x in outside.sort_values().tolist()[:100]],
        outlier_count=int(len(outside)),
    )


def category_frequency(col: TypedColumn, top: int = 10) -> CategoryFrequency:
    present = col.values.dropna().astype(str)
    counts = present.value_counts(sort=True)
    # Stable ordering for ties: count desc, then value asc
    counts = counts.sort_index().sort_values(ascending=False, kind="mergesort")
    n = int(len(present))
    rows = [CategoryCount(value=str(k), count=int(c), pct=pct(int(c), n)) for k, c in counts.head(top).items()]
    rest = counts.iloc[top:]
    return CategoryFrequency(
        column=col.name,
        non_missing=n,
        missing=int(col.values.isna().sum()),
        unique=int(len(counts)),
        rows=rows,
        other_count=int(rest.sum()),
        other_categories=int(len(rest)),
    )


def date_range(col: TypedColumn) -> DateRange:
    d = col.values.dropna()
    if d.empty:
        raise AppError(422, "no_dates", f"'{col.name}' has no valid dates.")
    now = now_utc_naive()
    return DateRange(
        min=d.min().isoformat(),
        max=d.max().isoformat(),
        span_days=int((d.max() - d.min()).days),
        future_count=int((d > now).sum()),
        pre_1900_count=int((d < pd.Timestamp("1900-01-01")).sum()),
    )


# --------------------------------------------------------------------------- #
# Time series
# --------------------------------------------------------------------------- #

_FREQ = {"day": "D", "week": "W-SUN", "month": "M", "quarter": "Q", "year": "Y"}


def choose_granularity(start: pd.Timestamp, end: pd.Timestamp) -> str:
    span = (end - start).days
    if span <= 45:
        return "day"
    if span <= 180:
        return "week"
    if span <= 365 * 4:
        return "month"
    if span <= 365 * 12:
        return "quarter"
    return "year"


def _label(period: pd.Period, granularity: str) -> str:
    start = period.start_time
    if granularity == "day":
        return start.strftime("%d %b %Y")
    if granularity == "week":
        return "w/c " + start.strftime("%d %b %Y")
    if granularity == "month":
        return start.strftime("%b %Y")
    if granularity == "quarter":
        return f"{period.year} Q{period.quarter}"
    return str(period.year)


def time_series(
    table: TypedTable,
    date_column: str,
    value_column: str | None = None,
    agg: str = "count",
    granularity: str = "auto",
) -> TimeSeries:
    dcol = table.get(date_column)
    if dcol is None:
        raise AppError(404, "column_not_found", f"Column '{date_column}' does not exist.")
    if dcol.kind != "datetime":
        raise AppError(422, "not_a_date_column", f"'{date_column}' is not a date column.")
    vcol = None
    if agg != "count":
        if not value_column:
            raise AppError(422, "value_column_required", f"A numeric column is required for '{agg}'.")
        vcol = table.get(value_column)
        if vcol is None:
            raise AppError(404, "column_not_found", f"Column '{value_column}' does not exist.")
        if vcol.kind != "numeric":
            raise AppError(422, "not_numeric", f"'{value_column}' is not numeric, so it cannot be summed or averaged.")

    frame = pd.DataFrame({"date": dcol.values})
    if vcol is not None:
        frame["value"] = vcol.values
    frame = frame.dropna(subset=["date"])
    if frame.empty:
        raise AppError(422, "no_dates", f"'{date_column}' has no valid dates.")
    start, end = frame["date"].min(), frame["date"].max()
    gran = choose_granularity(start, end) if granularity == "auto" else granularity
    freq = _FREQ[gran]

    frame["period"] = frame["date"].dt.to_period(freq)
    all_periods = pd.period_range(frame["period"].min(), frame["period"].max(), freq=freq)
    if len(all_periods) > 1000:
        raise AppError(422, "too_many_periods", "That granularity produces too many periods; choose a coarser one.")

    counts = frame.groupby("period").size()
    values = None
    if vcol is not None:
        grouped = frame.dropna(subset=["value"]).groupby("period")["value"]
        values = grouped.sum() if agg == "sum" else grouped.mean()

    points = []
    for p in all_periods:
        c = int(counts.get(p, 0))
        val = None
        if values is not None and p in values.index and c > 0:
            val = rnd(values[p])
        points.append(TimePoint(period=p.start_time.date().isoformat(), label=_label(p, gran), count=c, value=val))

    first, last = all_periods[0], all_periods[-1]
    first_partial = gran != "day" and start.normalize() > first.start_time.normalize()
    last_partial = gran != "day" and end.normalize() < last.end_time.normalize()
    return TimeSeries(
        date_column=date_column,
        value_column=vcol.name if vcol is not None else None,
        agg=agg,  # type: ignore[arg-type]
        granularity=gran,  # type: ignore[arg-type]
        points=points,
        first_period_partial=bool(first_partial),
        last_period_partial=bool(last_partial),
    )


# --------------------------------------------------------------------------- #
# Relationships
# --------------------------------------------------------------------------- #


def correlation_strength(r: float) -> str:
    a = abs(r)
    if a >= 0.7:
        return "strong"
    if a >= 0.4:
        return "moderate"
    return "weak"


def analysable_measures(table: TypedTable) -> list[TypedColumn]:
    return [c for c in table.columns if c.kind == "numeric" and c.role == "measure" and c.valid.nunique() > 1]


def correlation_matrix(table: TypedTable) -> CorrelationMatrix | None:
    measures = analysable_measures(table)
    measures = sorted(measures, key=lambda c: -len(c.valid))[:MAX_CORRELATION_COLUMNS]
    measures = sorted(measures, key=lambda c: [x.name for x in table.columns].index(c.name))
    if len(measures) < 2:
        return None
    frame = pd.DataFrame({c.name: c.values for c in measures})
    corr = frame.corr(method="pearson", min_periods=MIN_CORRELATION_PAIRS)
    notna = frame.notna().astype(int)
    pair_counts = notna.T @ notna
    names = [c.name for c in measures]
    matrix = [[rnd(corr.loc[a, b], 4) for b in names] for a in names]
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            r = corr.loc[a, b]
            if pd.notna(r):
                pairs.append(
                    CorrelationPair(x=a, y=b, r=rnd(r, 4), n=int(pair_counts.loc[a, b]), strength=correlation_strength(float(r)))
                )
    pairs.sort(key=lambda p: -abs(p.r))
    return CorrelationMatrix(method="Pearson r (pairwise complete, min 10 pairs)", columns=names, matrix=matrix, pairs=pairs)


def grouped_summary(table: TypedTable, category_column: str, value_column: str) -> GroupedSummary:
    ccol, vcol = table.get(category_column), table.get(value_column)
    for name, col in ((category_column, ccol), (value_column, vcol)):
        if col is None:
            raise AppError(404, "column_not_found", f"Column '{name}' does not exist.")
    assert ccol is not None and vcol is not None
    if ccol.kind not in {"categorical", "boolean", "text"}:
        raise AppError(422, "not_categorical", f"'{category_column}' is not a category column.")
    if vcol.kind != "numeric":
        raise AppError(422, "not_numeric", f"'{value_column}' is not numeric.")

    frame = pd.DataFrame({"group": ccol.values.fillna("(missing)").astype(str), "value": vcol.values})
    used = frame.dropna(subset=["value"])
    excluded = len(frame) - len(used)
    g = used.groupby("group")["value"]
    stats = pd.DataFrame({"count": g.size(), "mean": g.mean(), "median": g.median(), "sum": g.sum()})
    total = float(used["value"].sum())
    shares_valid = bool((used["value"] >= 0).all() and total > 0)
    order_key = "sum" if shares_valid else "mean"
    stats = stats.sort_index().sort_values(order_key, ascending=False, kind="mergesort")

    rows: list[GroupRow] = []
    for name, s in stats.head(MAX_GROUPS).iterrows():
        rows.append(
            GroupRow(
                group=str(name),
                count=int(s["count"]),
                mean=rnd(s["mean"]),
                median=rnd(s["median"]),
                sum=rnd(s["sum"]),
                share_of_total=pct(float(s["sum"]), total) if shares_valid else None,
            )
        )
    rest = stats.iloc[MAX_GROUPS:]
    if len(rest):
        rest_values = used[used["group"].isin(rest.index)]["value"]
        rows.append(
            GroupRow(
                group=f"Other ({len(rest)} groups)",
                count=int(len(rest_values)),
                mean=rnd(rest_values.mean()),
                median=rnd(rest_values.median()),
                sum=rnd(rest_values.sum()),
                share_of_total=pct(float(rest_values.sum()), total) if shares_valid else None,
            )
        )
    notes = []
    if excluded:
        notes.append(f"{excluded} row(s) with no valid '{value_column}' value were excluded.")
    if not shares_valid:
        notes.append("Shares of total are not shown because the values include negatives or sum to zero.")
    return GroupedSummary(
        category_column=category_column,
        value_column=value_column,
        rows=rows,
        total=rnd(total),
        shares_valid=shares_valid,
        note=" ".join(notes) or None,
    )


def scatter(table: TypedTable, x: str, y: str) -> ScatterData:
    xc, yc = table.get(x), table.get(y)
    for name, col in ((x, xc), (y, yc)):
        if col is None:
            raise AppError(404, "column_not_found", f"Column '{name}' does not exist.")
        if col.kind != "numeric":
            raise AppError(422, "not_numeric", f"'{name}' is not numeric.")
    assert xc is not None and yc is not None
    frame = pd.DataFrame({"x": xc.values, "y": yc.values}).dropna()
    n = len(frame)
    r = None
    if n >= MIN_CORRELATION_PAIRS and frame["x"].nunique() > 1 and frame["y"].nunique() > 1:
        r = rnd(frame["x"].corr(frame["y"]), 4)
    shown = frame if n <= MAX_SCATTER_POINTS else frame.sample(MAX_SCATTER_POINTS, random_state=42).sort_index()
    return ScatterData(
        x=x,
        y=y,
        points=[ScatterPoint(x=rnd(a), y=rnd(b)) for a, b in zip(shown["x"], shown["y"], strict=True)],
        n_total=int(n),
        n_shown=int(len(shown)),
        r=r,
    )


# --------------------------------------------------------------------------- #
# Defaults & bundle
# --------------------------------------------------------------------------- #


def main_measure(table: TypedTable) -> TypedColumn | None:
    measures = analysable_measures(table)
    if not measures:
        return None
    hinted = [c for c in measures if _MEASURE_HINT.search(c.name)]
    # Prefer columns literally named like revenue/sales/amount over price/units
    for word in ("revenue", "sales", "amount", "total", "value", "profit"):
        for c in hinted:
            if word in c.name.lower():
                return c
    return hinted[0] if hinted else measures[0]


def grouping_dimensions(table: TypedTable) -> list[TypedColumn]:
    dims = [
        c
        for c in table.columns
        if c.kind in {"categorical", "boolean"} and c.role == "dimension" and 2 <= c.valid.nunique() <= 50
    ]
    return sorted(dims, key=lambda c: (c.values.isna().sum(), c.valid.nunique()))


def build_analysis(table: TypedTable) -> AnalysisBundle:
    skipped: list[str] = []
    numeric = []
    for c in table.columns:
        if c.kind != "numeric":
            continue
        if c.role == "identifier":
            skipped.append(f"'{c.name}' looks like an identifier, so averages and totals were not calculated.")
            continue
        if c.valid.empty:
            skipped.append(f"'{c.name}' has no valid numbers.")
            continue
        s = numeric_summary(c.values)
        numeric.append(NumericAnalysis(column=c.name, summary=s, histogram=histogram(c.values), box=box_plot(c.values, s)))

    categorical = [category_frequency(c) for c in table.columns if c.kind in {"categorical", "boolean"} and not c.valid.empty]
    for c in table.columns:
        if c.kind == "text":
            skipped.append(f"'{c.name}' is mostly unique text, so frequency tables are not meaningful.")
        if c.kind == "empty":
            skipped.append(f"'{c.name}' is empty.")

    dates = []
    for c in table.columns:
        if c.kind == "datetime" and not c.valid.empty:
            dates.append(DateAnalysis(column=c.name, range=date_range(c), records_over_time=time_series(table, c.name)))

    corr = correlation_matrix(table)
    if corr is None and len(analysable_measures(table)) < 2:
        skipped.append("Correlation needs at least two non-constant numeric columns.")

    measure = main_measure(table)
    dims = grouping_dimensions(table)
    default_grouped = grouped_summary(table, dims[0].name, measure.name) if measure and dims else None
    default_ts = None
    if dates:
        default_ts = time_series(table, dates[0].column, measure.name, "sum") if measure else dates[0].records_over_time
    default_scatter = None
    if corr and corr.pairs:
        top = corr.pairs[0]
        default_scatter = scatter(table, top.x, top.y)

    return AnalysisBundle(
        numeric=numeric,
        categorical=categorical,
        dates=dates,
        correlation=corr,
        default_grouped=default_grouped,
        default_timeseries=default_ts,
        default_scatter=default_scatter,
        measures=[c.name for c in analysable_measures(table)],
        dimensions=[c.name for c in grouping_dimensions(table)],
        date_columns=[d.column for d in dates],
        skipped=skipped,
    )
