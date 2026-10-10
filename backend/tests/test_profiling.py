import pytest
from conftest import analyse_csv


def issues(result, severity=None, category=None):
    return [
        i
        for i in result.profile.issues
        if (severity is None or i.severity == severity) and (category is None or i.category == category)
    ]


def test_profile_counts():
    r = analyse_csv("id,region,sales\n1,North,10\n2,North,\n3,South,30\n4,,40\n")
    p = r.profile
    assert (p.rows, p.columns) == (4, 3)
    sales = next(c for c in p.column_profiles if c.name == "sales")
    assert (sales.missing, sales.missing_pct, sales.non_missing) == (1, 25.0, 3)
    assert sales.numeric.mean == pytest.approx(80 / 3, abs=1e-6)
    region = next(c for c in p.column_profiles if c.name == "region")
    assert region.top_categories[0].value == "North" and region.top_categories[0].count == 2
    assert p.missing_cells == 2 and p.missing_cells_pct == round(100 * 2 / 12, 2)


def test_duplicates_counted_not_removed():
    r = analyse_csv("a,b\n1,x\n1,x\n2,y\n1,x\n")
    assert r.profile.duplicate_rows == 2
    assert r.profile.rows == 4  # still all rows
    dup = issues(r, "confirmed", "duplicates")
    assert dup and "NOT been removed" in dup[0].message


def test_duplicates_with_missing_values():
    r = analyse_csv("a,b,c\n1,,x\n1,,x\n1,2,x\n")
    assert r.profile.duplicate_rows == 1


def test_constant_column_detected():
    r = analyse_csv("a,b\n1,GBP\n2,GBP\n3,GBP\n")
    b = next(c for c in r.profile.column_profiles if c.name == "b")
    assert b.is_constant
    assert issues(r, "confirmed", "constant")[0].column == "b"


def test_invalid_numbers_are_confirmed_issue():
    rows = "\n".join(str(i) for i in range(1, 40))
    r = analyse_csv("amount\n" + rows + "\nN/K-value\n")
    inv = issues(r, "confirmed", "invalid_values")
    assert inv and inv[0].count == 1 and "N/K-value" in inv[0].message


def test_potential_issues_are_separate_from_confirmed():
    body = "\n".join(f"{c},{v}" for c, v in [("North", 10), ("north", 12), ("South", 11), ("Unknown", 9)] * 5)
    r = analyse_csv("region,sales\n" + body + "\nSouth,-4\nSouth,500\n")
    cats = {i.category for i in issues(r, "potential")}
    assert {"inconsistent_labels", "placeholder_values", "negative_values", "outliers"} <= cats
    assert all(i.severity == "potential" for i in issues(r, category="outliers"))
    # Ordering: confirmed issues always come first
    severities = [i.severity for i in r.profile.issues]
    assert severities == sorted(severities, key=lambda s: 0 if s == "confirmed" else 1)


def test_future_and_ancient_dates_flagged():
    body = "\n".join(f"2024-01-{d:02d}" for d in range(1, 25))
    r = analyse_csv("when\n" + body + "\n2099-01-01\n1850-05-05\n")
    cats = {i.category for i in issues(r, "potential")}
    assert {"future_dates", "implausible_dates"} <= cats


def test_dates_beyond_supported_range_are_invalid_not_a_crash():
    body = "\n".join(f"2024-01-{d:02d}" for d in range(1, 25))
    r = analyse_csv("when\n" + body + "\n2999-12-31\n")
    when = r.table.get("when")
    assert when.kind == "datetime" and when.invalid_count == 1
    assert any("1677" in n for n in when.notes)


def test_identifier_and_date_candidates():
    r = analyse_csv("order_id,date,amount\n" + "\n".join(f"A{i},2025-01-{i:02d},{i}" for i in range(1, 25)) + "\n")
    cols = {c.name: c for c in r.profile.column_profiles}
    assert cols["order_id"].likely_identifier
    assert cols["date"].candidate_date
    assert cols["date"].date_range.min.startswith("2025-01-01")
