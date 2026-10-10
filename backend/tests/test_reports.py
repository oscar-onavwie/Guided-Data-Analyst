import csv
import io
from datetime import UTC, datetime

import pytest
from conftest import analyse, analyse_csv, sample

from app.errors import AppError
from app.reports import EXPORT_TABLES, build_report, csv_safe, export_csv, render_html


def make_report(result, filename="data.csv", is_demo=False):
    return build_report(
        filename=filename,
        sheet=result.parsed.sheet,
        is_demo=is_demo,
        loaded_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        profile=result.profile,
        analysis=result.analysis,
        findings=result.findings,
        main_measure_name=result.analysis.measures[0] if result.analysis.measures else None,
    )


@pytest.fixture(scope="module")
def business():
    return analyse(sample("small_business_sales_expenses.csv"), "small_business_sales_expenses.csv")


def test_report_contains_real_analysis(business):
    rep = make_report(business, "small_business_sales_expenses.csv", is_demo=True)
    html = render_html(rep)
    for heading in [
        "Dataset overview",
        "Data-quality assessment",
        "Analytical methodology",
        "Key statistics",
        "Charts",
        "Prioritised findings",
        "Limitations and assumptions",
        "Suggested next steps",
    ]:
        assert heading in html
    assert "small_business_sales_expenses.csv" in html
    assert "02 Jan 2026, 03:04" in html  # load date
    assert rep["generated_at_iso"][:4] >= "2026"
    assert "DEMO DATA" in html
    assert "368" in html  # row count
    for f in business.findings.findings:
        assert f.id in html and f.caveat[:30] in html
    assert html.count("<svg") >= 2  # time series + grouped chart (+ histogram)
    assert "Descriptive" in html and "Interpretation" in html
    for placeholder in ["lorem ipsum", "TODO", "TBD:", "{{", "}}", "{%"]:
        assert placeholder.lower() not in html.lower()


def test_report_escapes_user_content():
    r = analyse_csv('"<script>alert(1)</script>",value\n"<img src=x onerror=alert(1)>",1\nb,2\n')
    html = render_html(make_report(r, filename="<b>evil</b>.csv"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x" not in html
    assert "<b>evil</b>" not in html


def test_report_without_findings_says_so():
    r = analyse_csv("colour,size\nred,1\nblue,2\n")
    html = render_html(make_report(r))
    assert "No patterns met the documented thresholds" in html
    assert "DEMO DATA" not in html


def test_csv_exports(business):
    for table in EXPORT_TABLES:
        if table == "correlations":
            with pytest.raises(AppError) as e:  # only one numeric measure in this dataset
                export_csv(table, business.profile, business.analysis, business.findings)
            assert e.value.status == 404
            continue
        text = export_csv(table, business.profile, business.analysis, business.findings)
        rows = list(csv.reader(io.StringIO(text)))
        assert len(rows) >= 2, table
    findings = list(csv.DictReader(io.StringIO(export_csv("findings", business.profile, business.analysis, business.findings))))
    assert [r["id"] for r in findings] == [f.id for f in business.findings.findings]
    ts = list(csv.DictReader(io.StringIO(export_csv("time_series", business.profile, business.analysis, business.findings))))
    assert len(ts) == 12 and ts[0]["label"] == "Jan 2025"
    monthly_total = sum(float(r["sum_amount_gbp"]) for r in ts)
    amount = next(c for c in business.profile.column_profiles if c.name == "amount_gbp").numeric.sum
    assert monthly_total == pytest.approx(amount, abs=0.05)  # export reconciles with the column total


def test_unknown_export():
    r = analyse_csv("a,b\nx,1\ny,2\n")
    with pytest.raises(AppError) as e:
        export_csv("../../secrets", r.profile, r.analysis, r.findings)
    assert e.value.code == "unknown_export"


@pytest.mark.parametrize(
    "value,expected",
    [("=SUM(A1)", "'=SUM(A1)"), ("+1", "'+1"), ("-cmd", "'-cmd"), ("@x", "'@x"), ("normal", "normal"), (-5.5, -5.5), (3, 3)],
)
def test_csv_formula_injection_guard(value, expected):
    assert csv_safe(value) == expected


def test_exported_issue_messages_are_guarded():
    r = analyse_csv("=cmd|' /C calc'!A0,v\na,1\na,1\n")
    text = export_csv("column_profile", r.profile, r.analysis, r.findings)
    assert "\n'=cmd" in text.replace("\r\n", "\n")
