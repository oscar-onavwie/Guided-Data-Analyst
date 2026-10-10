"""The demo datasets have documented, planted patterns (sample-data/README.md).

These tests pin the expected results so any change to the engine that alters
them is noticed.
"""

import pytest
from conftest import analyse, sample


@pytest.fixture(scope="module")
def small_business():
    return analyse(sample("small_business_sales_expenses.csv"), "small_business_sales_expenses.csv")


@pytest.fixture(scope="module")
def retail():
    return analyse(sample("retail_product_performance.csv"), "retail_product_performance.csv")


@pytest.fixture(scope="module")
def workforce():
    return analyse(
        sample("workforce_operational_performance.xlsx"), "workforce_operational_performance.xlsx", sheet="Weekly Performance"
    )


def kinds(r):
    return {f.kind for f in r.findings.findings}


def test_small_business(small_business):
    r = small_business
    assert (r.profile.rows, r.profile.columns) == (368, 7)  # 365 days + 3 duplicates
    assert r.profile.duplicate_rows == 3
    cols = {c.name: c for c in r.profile.column_profiles}
    assert cols["payment_method"].missing == 91  # every 4th transaction, 365//4 = 91 (+0 from duplicates)
    assert cols["amount_gbp"].numeric.negatives == 2  # the two refunds
    assert cols["date"].date_range.min.startswith("2025-01-01") and cols["date"].date_range.max.startswith("2025-12-31")
    assert cols["transaction_id"].likely_identifier
    trend = [f for f in r.findings.findings if f.kind == "trend"]
    assert trend and "increased" in trend[0].title
    assert {"missing_data", "negative_values"} <= kinds(r)


def test_retail(retail):
    r = retail
    cols = {c.name: c for c in r.profile.column_profiles}
    assert cols["currency"].is_constant
    units = cols["units_sold"].numeric
    assert units.outliers.extreme_count >= 2 and units.max == 2551  # bulk orders 2400+37+1? -> rows 37 and 151
    assert cols["discount"].inferred_type == "numeric"  # "20%" parsed as 20
    pair = next(f for f in r.findings.findings if f.kind == "correlation" and set(f.columns) == {"units_sold", "revenue"})
    assert pair.strength == "strong"
    conc = next(f for f in r.findings.findings if f.kind == "concentration")
    assert conc.title.startswith("'Electronics' accounts for")


def test_workforce_xlsx(workforce):
    r = workforce
    assert (r.profile.rows, r.profile.columns) == (260, 8)
    assert r.parsed.sheets == ["Weekly Performance", "Team Directory"]
    cols = {c.name: c for c in r.profile.column_profiles}
    assert cols["csat_score"].missing == 65  # exactly 25%
    assert cols["week_start"].inferred_type == "datetime"
    corr = next(
        f for f in r.findings.findings if f.kind == "correlation" and set(f.columns) == {"overtime_hours", "absence_days"}
    )
    assert corr.strength == "strong"
    gap = next(f for f in r.findings.findings if f.kind == "group_difference" and "tickets_resolved" in f.columns)
    assert "'Delta' the lowest" in gap.description


def test_workforce_csv_matches_xlsx(workforce):
    csv = analyse(sample("workforce_operational_performance.csv"), "workforce_operational_performance.csv")
    xl = {c.name: c.numeric for c in workforce.profile.column_profiles if c.numeric}
    cs = {c.name: c.numeric for c in csv.profile.column_profiles if c.numeric}
    assert xl.keys() == cs.keys()
    for name in xl:
        assert xl[name].mean == pytest.approx(cs[name].mean) and xl[name].count == cs[name].count
