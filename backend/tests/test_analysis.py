"""Statistics checked against values worked out by hand."""

import math

import pandas as pd
import pytest
from conftest import analyse_csv

from app.analysis import (
    category_frequency,
    correlation_matrix,
    grouped_summary,
    histogram,
    numeric_summary,
    pct,
    safe_div,
    scatter,
    time_series,
)
from app.errors import AppError
from app.inference import infer_column, infer_table


def test_numeric_summary_hand_calculated():
    # Values 1,2,3,4,100
    # mean = 110/5 = 22; median = 3; Q1 = 2, Q3 = 4 (linear interpolation); IQR = 2
    # sample variance = (441+400+361+324+6084)/4 = 1902.5 -> sd = 43.6176...
    # fences: 2-3 = -1 and 4+3 = 7 -> 100 is an outlier; 3xIQR upper = 10 -> extreme
    s = numeric_summary(pd.Series([1, 2, 3, 4, 100], dtype=float))
    assert s.count == 5 and s.mean == 22 and s.median == 3
    assert (s.q1, s.q3, s.iqr) == (2, 4, 2)
    assert s.std == pytest.approx(math.sqrt(1902.5), rel=1e-6)
    assert (s.min, s.max, s.sum) == (1, 100, 110)
    assert s.outliers.count == 1 and s.outliers.extreme_count == 1
    assert (s.outliers.lower_fence, s.outliers.upper_fence) == (-1, 7)
    assert s.outliers.examples == [100]


def test_numeric_summary_ignores_missing_and_counts_negatives_and_zeros():
    s = numeric_summary(pd.Series([-2, 0, 0, 4, float("nan")]))
    assert s.count == 4 and s.mean == 0.5 and s.negatives == 1 and s.zeros == 2


def test_single_value_has_no_std():
    s = numeric_summary(pd.Series([5.0]))
    assert s.std is None and s.skewness is None


def test_constant_column_iqr_zero_skips_outlier_rule():
    s = numeric_summary(pd.Series([3.0] * 10))
    assert s.iqr == 0 and s.outliers.count == 0
    assert "not applied" in s.outliers.method


def test_zero_denominators_are_safe():
    assert safe_div(5, 0) is None
    assert pct(0, 0) == 0.0
    assert pct(1, 4) == 25.0


def test_histogram_counts_sum_to_n():
    bins = histogram(pd.Series(range(100), dtype=float))
    assert sum(b.count for b in bins) == 100
    assert bins[0].start == 0 and bins[-1].end == 99
    assert histogram(pd.Series([7.0, 7.0]))[0].count == 2


def test_category_frequency():
    c = infer_column("fruit", pd.Series(["apple"] * 5 + ["pear"] * 3 + ["fig"] * 2 + [None], dtype=object))
    f = category_frequency(c, top=2)
    assert [(r.value, r.count, r.pct) for r in f.rows] == [("apple", 5, 50.0), ("pear", 3, 30.0)]
    assert (f.other_count, f.other_categories, f.missing, f.unique) == (2, 1, 1, 3)


def test_monthly_time_series_and_partial_periods():
    # 3 rows in Jan (from 15th: partial), 0 in Feb, 2 in Mar (to 31st: complete)
    frame = pd.DataFrame(
        {
            "date": ["2025-01-15", "2025-01-20", "2025-01-31", "2025-03-01", "2025-03-31"],
            "amount": ["10", "20", "30", "5", "-1"],
        }
    )
    table = infer_table(frame)
    ts = time_series(table, "date", "amount", "sum", "month")
    assert [p.label for p in ts.points] == ["Jan 2025", "Feb 2025", "Mar 2025"]
    assert [p.count for p in ts.points] == [3, 0, 2]
    assert [p.value for p in ts.points] == [60, None, 4]  # empty month is a gap, not 0
    assert ts.first_period_partial is True and ts.last_period_partial is False
    counts = time_series(table, "date", granularity="month")
    assert [p.count for p in counts.points] == [3, 0, 2]
    mean = time_series(table, "date", "amount", "mean", "month")
    assert mean.points[0].value == 20 and mean.points[2].value == 2


def test_time_series_validation():
    table = infer_table(pd.DataFrame({"d": ["2025-01-01", "2025-01-02"], "t": ["a", "b"]}))
    with pytest.raises(AppError) as e:
        time_series(table, "t")
    assert e.value.code == "not_a_date_column"
    with pytest.raises(AppError) as e:
        time_series(table, "d", "t", "sum")
    assert e.value.code == "not_numeric"
    with pytest.raises(AppError) as e:
        time_series(table, "nope")
    assert e.value.status == 404


def test_correlation_known_values():
    n = 12
    frame = pd.DataFrame(
        {
            "x": [str(i) for i in range(n)],
            "double": [str(2 * i + 1) for i in range(n)],
            "neg": [str(-i) for i in range(n)],
            "const": ["5"] * n,
        }
    )
    table = infer_table(frame)
    # 'x' is 0..11 sequential -> treated as a row identifier, so it is excluded
    assert table.get("x").role == "identifier"
    m = correlation_matrix(table)
    assert m.columns == ["double", "neg"]  # constant column excluded
    assert m.pairs[0].r == -1.0 and m.pairs[0].n == n and m.pairs[0].strength == "strong"


def test_correlation_requires_ten_pairs():
    frame = pd.DataFrame({"a": ["1", "3", "2", "5"], "b": ["2", "6", "4", "10"]})
    m = correlation_matrix(infer_table(frame))
    assert m.pairs == []  # fewer than 10 pairs -> not computed
    assert m.matrix[0][1] is None


def test_correlation_hand_calculated():
    # x = 1..10 shuffled-ish, y = x with one change; r computed by pandas and checked against a manual formula
    x = [2, 4, 1, 3, 5, 7, 6, 9, 8, 10]
    y = [1, 3, 2, 5, 4, 6, 8, 7, 10, 9]
    frame = pd.DataFrame({"a": [str(v) for v in x], "b": [str(v) for v in y]})
    mx, my = sum(x) / 10, sum(y) / 10
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    r = cov / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    m = correlation_matrix(infer_table(frame))
    assert m.pairs[0].r == pytest.approx(r, abs=1e-4)


def test_grouped_summary_shares_and_negative_guard():
    res = analyse_csv("team,sales\nA,10\nA,30\nB,60\nC,\n")
    g = grouped_summary(res.table, "team", "sales")
    assert [(r.group, r.count, r.sum, r.share_of_total) for r in g.rows] == [("B", 1, 60, 60.0), ("A", 2, 40, 40.0)]
    assert g.shares_valid and "excluded" in g.note
    neg = analyse_csv("team,profit\nA,10\nA,-30\nB,60\n")
    g2 = grouped_summary(neg.table, "team", "profit")
    assert g2.shares_valid is False and all(r.share_of_total is None for r in g2.rows)


def test_grouped_summary_rejects_wrong_types():
    res = analyse_csv("team,sales\nA,10\nB,20\n")
    with pytest.raises(AppError) as e:
        grouped_summary(res.table, "sales", "team")
    assert e.value.code == "not_categorical"


def test_scatter_samples_deterministically():
    rows = "\n".join(f"{i * 0.5},{i * 2 + 1.5}" for i in range(800))
    res = analyse_csv("a,b\n" + rows + "\n")
    s1 = scatter(res.table, "a", "b")
    s2 = scatter(res.table, "a", "b")
    assert s1.n_total == 800 and s1.n_shown == 500
    assert s1.points == s2.points and s1.r == 1.0
