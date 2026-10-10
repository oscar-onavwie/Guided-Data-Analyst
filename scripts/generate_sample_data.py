"""Generate the synthetic demo datasets in ../sample-data.

All records are fictional. The generator is seeded, so running it again
produces byte-identical files. Each dataset has deliberate, documented
patterns (see sample-data/README.md) that the test-suite checks for.

Run:  python scripts/generate_sample_data.py
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from openpyxl import Workbook

OUT = Path(__file__).resolve().parent.parent / "sample-data"


def small_business() -> None:
    """Small-business sales & expenses, Jan–Dec 2025 (one transaction per day)."""
    rng = np.random.default_rng(2025)
    rows = []
    start = date(2025, 1, 1)
    for i in range(365):
        d = start + timedelta(days=i)
        month = d.month
        is_sale = i % 4 != 3  # 3 of every 4 transactions are sales
        if is_sale:
            category = [
                "Consulting",
                "Consulting",
                "Training",
                "Software",
                "Consulting",
                "Support",
            ][i % 6]
            # Sales grow steadily through the year (+~5% a month)
            base = {
                "Consulting": 420,
                "Training": 260,
                "Software": 180,
                "Support": 120,
            }[category]
            amount = round(base * (1 + 0.05 * (month - 1)) * rng.uniform(0.85, 1.15), 2)
            customer = ["New", "Returning"][i % 2]
        else:
            category = ["Rent", "Software subscriptions", "Marketing", "Travel"][
                (i // 4) % 4
            ]
            amount = round(
                {
                    "Rent": 400,
                    "Software subscriptions": 90,
                    "Marketing": 150,
                    "Travel": 70,
                }[category]
                * rng.uniform(0.9, 1.1),
                2,
            )
            customer = ""
        payment = ["Card", "Bank transfer", "Card", "Invoice"][i % 4]
        if i % 4 == 1:  # exactly 25% of payment methods missing
            payment = ""
        rows.append(
            [
                f"TX-{i + 1:04d}",
                d.isoformat(),
                "Sale" if is_sale else "Expense",
                category,
                f"{amount:.2f}",
                payment,
                customer,
            ]
        )
    # Two refunds (negative sales)
    rows[40][4] = "-180.00"
    rows[200][4] = "-95.50"
    # Three exact duplicate rows (double entries)
    rows += [list(rows[10]), list(rows[100]), list(rows[300])]
    with open(OUT / "small_business_sales_expenses.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "transaction_id",
                "date",
                "type",
                "category",
                "amount_gbp",
                "payment_method",
                "customer_type",
            ]
        )
        w.writerows(rows)


def retail() -> None:
    """Retail product performance: 200 product-region rows."""
    rng = np.random.default_rng(7)
    categories = {
        "Electronics": 180.0,
        "Home": 45.0,
        "Clothing": 30.0,
        "Toys": 22.0,
        "Garden": 38.0,
    }
    regions = ["North", "South", "East", "West"]
    rows = []
    for i in range(200):
        cat = list(categories)[i % 5]
        region = regions[(i // 5) % 4]
        price = round(categories[cat] * rng.uniform(0.8, 1.2), 2)
        discount = int(rng.integers(0, 6)) * 5  # 0–25%
        units = int(max(1, rng.normal(120, 25) * (1 + discount / 50)))
        if i in (37, 151):  # two extreme bulk orders
            units = 2400 + i
        revenue = round(units * price * (1 - discount / 100), 2)
        returns = round(float(rng.uniform(0.01, 0.08)), 3)
        rating = round(float(rng.uniform(3.2, 4.9)), 1)
        rows.append(
            [
                f"P{i + 1:03d}",
                f"{cat} item {i + 1}",
                cat,
                region,
                units,
                f"{price:.2f}",
                f"{discount}%",
                f"{revenue:.2f}",
                returns,
                rating,
                "GBP",
            ]
        )
    with open(OUT / "retail_product_performance.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "product_id",
                "product_name",
                "category",
                "region",
                "units_sold",
                "unit_price",
                "discount",
                "revenue",
                "return_rate",
                "store_rating",
                "currency",
            ]
        )
        w.writerows(rows)


def workforce() -> tuple[list[str], list[list]]:
    """Customer-support centre weekly team performance, 52 weeks x 5 teams."""
    rng = np.random.default_rng(11)
    teams = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    header = [
        "week_start",
        "team",
        "agents_on_shift",
        "tickets_resolved",
        "avg_handle_time_min",
        "overtime_hours",
        "absence_days",
        "csat_score",
    ]
    rows = []
    start = date(2025, 1, 6)  # a Monday
    n = 0
    for week in range(52):
        for t, team in enumerate(teams):
            agents = int(rng.integers(8, 13))
            overtime = round(float(rng.uniform(0, 40)), 1)
            absence = round(
                overtime * 0.18 + float(rng.normal(0, 0.8)), 1
            )  # absence rises with overtime
            absence = max(0.0, absence)
            productivity = (
                38 if team == "Delta" else 52
            )  # Delta resolves markedly fewer tickets
            tickets = int(agents * productivity * rng.uniform(0.92, 1.08))
            aht = round(float(rng.uniform(6.5, 9.5)), 1)
            csat = (
                "" if n % 4 == 0 else f"{rng.uniform(3.6, 4.8):.2f}"
            )  # exactly 25% missing
            rows.append(
                [
                    (start + timedelta(weeks=week)).isoformat(),
                    team,
                    agents,
                    tickets,
                    aht,
                    overtime,
                    absence,
                    csat,
                ]
            )
            n += 1
    with open(OUT / "workforce_operational_performance.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return header, rows


def workforce_xlsx(header: list[str], rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Weekly Performance"
    ws.append(header)
    for r in rows:
        r = list(r)
        r[0] = date.fromisoformat(r[0])
        r[7] = float(r[7]) if r[7] != "" else None
        ws.append(r)
    teams = wb.create_sheet("Team Directory")
    teams.append(["team", "manager", "site"])
    for team, manager, site in [
        ("Alpha", "J. Morgan", "Leeds"),
        ("Bravo", "S. Patel", "Leeds"),
        ("Charlie", "R. Okafor", "Bristol"),
        ("Delta", "L. Chen", "Bristol"),
        ("Echo", "M. Davies", "Glasgow"),
    ]:
        teams.append([team, manager, site])
    wb.save(OUT / "workforce_operational_performance.xlsx")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    small_business()
    retail()
    h, r = workforce()
    workforce_xlsx(h, r)
    print("Wrote sample datasets to", OUT)
