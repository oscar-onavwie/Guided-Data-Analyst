"""Findings generated from datasets with known, planted patterns."""

import re

import numpy as np
from conftest import analyse_csv


def kinds(result):
    return [f.kind for f in result.findings.findings]


def by_kind(result, kind):
    return [f for f in result.findings.findings if f.kind == kind]


def test_upward_trend_detected_with_exact_change():
    # Monthly totals 100,110,...,210 (12 complete months, 1 row per day on the 1st and last day)
    rows = []
    for m in range(1, 13):
        total = 100 + 10 * (m - 1)
        last_day = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        rows.append(f"2025-{m:02d}-01,{total / 2}")
        rows.append(f"2025-{m:02d}-{last_day},{total / 2}")
    r = analyse_csv("date,revenue\n" + "\n".join(rows) + "\n")
    trend = by_kind(r, "trend")
    assert len(trend) == 1
    # first 4 months avg = (100+110+120+130)/4 = 115; last 4 = (180+190+200+210)/4 = 195; change = 80/115 = 69.6%
    assert "+69.6%" in [e.value for e in trend[0].evidence]
    assert "increased" in trend[0].title
    assert trend[0].period == "Jan 2025 – Dec 2025"


def test_flat_series_produces_no_trend():
    rows = [f"2025-{m:02d}-01,100\n2025-{m:02d}-28,100" for m in range(1, 13)]
    r = analyse_csv("date,revenue\n" + "\n".join(rows) + "\n")
    assert "trend" not in kinds(r)


def test_concentration_detected():
    body = "\n".join(["Big,100"] * 6 + ["Mid,20"] * 3 + ["Small,10"] * 2 + ["Tiny,5"])
    r = analyse_csv("store,sales\n" + body + "\n")
    c = by_kind(r, "concentration")
    # Big = 600 of 600+60+20+5 = 685 -> 87.6%
    assert c and c[0].title.startswith("'Big' accounts for 88%")
    assert c[0].evidence[0].value == "87.6%"


def test_strong_correlation_detected_without_causal_language():
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 100, 60)
    y = 3 * x + rng.normal(0, 5, 60)
    r = analyse_csv("ad_spend,visits\n" + "\n".join(f"{a:.2f},{b:.2f}" for a, b in zip(x, y, strict=True)) + "\n")
    corr = by_kind(r, "correlation")
    assert corr and corr[0].strength == "strong"
    assert "not causation" in corr[0].caveat


def test_group_difference_detected():
    body = "\n".join([f"A,{v}" for v in (50, 52, 49, 51, 50, 48)] + [f"B,{v}" for v in (20, 22, 19, 21, 20, 18)])
    r = analyse_csv("team,tickets_resolved\n" + body + "\n")
    g = by_kind(r, "group_difference")
    assert g and "'A' has the highest" in g[0].description


def test_outliers_missing_negatives_and_duplicates():
    vals = [10, 11, 12, 13, 12, 11, 10, 12, 11, 13] * 3 + [500]
    body = "\n".join(f"{v},{'x' if i % 2 else ''}" for i, v in enumerate(vals))
    r = analyse_csv("amount,note\n" + body + "\n-3,x\n-3,x\n")
    k = set(kinds(r))
    assert {"outliers", "missing_data", "negative_values", "duplicates"} <= k
    # 500 and the two -3 values lie outside the fences (Q1=11, Q3=12, IQR=1 -> 9.5 to 13.5)
    assert by_kind(r, "outliers")[0].title.startswith("3 potential outlier")


def test_every_finding_has_required_fields_and_ranked_scores():
    body = "\n".join(["Big,100"] * 6 + ["Mid,20"] * 3 + ["Small,10"] * 2 + ["Tiny,5"])
    r = analyse_csv("store,sales\n" + body + "\n")
    scores = [f.score for f in r.findings.findings]
    assert scores == sorted(scores, reverse=True)
    for i, f in enumerate(r.findings.findings, start=1):
        assert f.id == f"F{i}"
        assert f.title and f.description and f.evidence and f.why_it_matters and f.caveat and f.follow_up
        assert all(e.value and e.calculation for e in f.evidence)
    assert any("weight" in line for line in r.findings.ranking_method)


def test_no_findings_message_when_nothing_meets_thresholds():
    r = analyse_csv("colour,size\nred,1\nblue,2\ngreen,3\n")
    assert r.findings.findings == []
    assert "No patterns met the documented thresholds" in r.findings.message


def test_findings_never_claim_causation():
    rng = np.random.default_rng(1)
    rows = "\n".join(
        f"2025-{1 + i % 12:02d}-{1 + i % 27:02d},{['N', 'S', 'E'][i % 3]},{rng.uniform(1, 100):.1f},{rng.uniform(1, 100):.1f}"
        for i in range(200)
    )
    r = analyse_csv("date,region,a,b\n" + rows + "\n")
    text = " ".join(f.title + " " + f.description + " " + f.why_it_matters for f in r.findings.findings).lower()
    assert not re.search(r"\b(causes|caused by|drives|leads to|because of)\b", text)
