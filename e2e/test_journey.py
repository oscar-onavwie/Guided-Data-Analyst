"""Browser end-to-end test of the full user journey.

Requires the backend on :8000 and the frontend on :3000 (see the e2e job in
.github/workflows/ci.yml). Run with:  pytest e2e -q
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

BASE = os.getenv("E2E_BASE_URL", "http://localhost:3000")
ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "e2e" / "screenshots"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.console_errors = errors  # type: ignore[attr-defined]
    yield pg
    pg.close()


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def continue_to(page: Page, stage: str) -> None:
    page.get_by_role("button", name=f"Continue to {stage} →").click()


def test_demo_journey_upload_to_report(page: Page):
    page.goto(BASE)
    expect(page.get_by_role("heading", name="Guided Data Analyst")).to_be_visible()
    expect(page.get_by_text("No dataset loaded")).to_be_visible()
    shot(page, "01-upload-empty")

    page.get_by_role("button", name=re.compile("Load demo: Small business")).click()
    expect(page.get_by_text("Parsed successfully").first).to_be_visible()
    expect(page.get_by_text("DEMO DATA").first).to_be_visible()
    expect(page.get_by_role("cell", name="TX-0001")).to_be_visible()  # preview shows real rows
    shot(page, "02-upload-demo-loaded")

    continue_to(page, "Profile")
    expect(page.get_by_role("heading", name="Data-quality assessment")).to_be_visible()
    expect(page.get_by_text("are exact duplicates of an earlier row").first).to_be_visible()
    page.get_by_role("button", name="amount_gbp").click()  # expand column detail
    expect(page.get_by_text("Negative values").first).to_be_visible()
    shot(page, "03-profile")

    continue_to(page, "Explore")
    expect(page.get_by_text("Distribution of amount_gbp").first).to_be_visible()
    expect(page.locator(".recharts-surface").first).to_be_visible()
    page.get_by_role("tab", name="Over time").click()
    expect(page.get_by_text(re.compile("over time$")).first).to_be_visible()
    page.get_by_label("Period").select_option("quarter")
    expect(page.get_by_text("2025 Q4").first).to_be_attached()
    page.get_by_role("tab", name="Compare groups").click()
    expect(page.get_by_role("tabpanel")).to_contain_text("amount_gbp")
    shot(page, "04-explore")

    continue_to(page, "Discover")
    expect(page.get_by_role("heading", name=re.compile(r"^Findings \(\d+\)"))).to_be_visible()
    expect(page.get_by_text(re.compile("increased by")).first).to_be_visible()
    expect(page.get_by_text("Caveat:").first).to_be_visible()
    expect(page.get_by_text("AI explanations are switched off").first).to_be_visible()
    shot(page, "05-discover")

    continue_to(page, "Report")
    link = page.get_by_role("link", name="Download HTML report")
    expect(link).to_be_visible()
    report = page.request.get(link.get_attribute("href"))
    assert report.status == 200
    body = report.text()
    assert "DEMO DATA" in body and "Prioritised findings" in body and "small_business_sales_expenses.csv" in body
    csv_href = page.get_by_role("link", name="Download CSV").first.get_attribute("href")
    assert page.request.get(csv_href).status == 200
    shot(page, "06-report")

    assert page.console_errors == [], page.console_errors  # type: ignore[attr-defined]


def test_upload_csv_excel_and_errors(page: Page, tmp_path: Path):
    page.goto(BASE)
    file_input = page.locator("#file-input")

    file_input.set_input_files(str(ROOT / "sample-data" / "retail_product_performance.csv"))
    expect(page.get_by_text("Parsed successfully").first).to_be_visible()
    expect(page.get_by_text("200 rows × 11 cols").first).to_be_visible()
    expect(page.get_by_text("DEMO DATA")).to_have_count(0)  # an upload is never labelled as demo

    file_input.set_input_files(str(ROOT / "sample-data" / "workforce_operational_performance.xlsx"))
    expect(page.get_by_label("Worksheet")).to_be_visible()
    page.get_by_label("Worksheet").select_option("Weekly Performance")
    page.get_by_role("button", name="Analyse this sheet").click()
    expect(page.get_by_text("260 rows × 8 cols").first).to_be_visible()
    shot(page, "07-excel-sheet")

    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    file_input.set_input_files(str(bad))
    expect(page.get_by_role("alert")).to_contain_text("Unsupported file type")

    malformed = tmp_path / "broken.csv"
    malformed.write_text("a,b\n1,2\n3,4,5,6\n")
    file_input.set_input_files(str(malformed))
    expect(page.get_by_role("alert")).to_contain_text("could not be parsed")
    shot(page, "08-upload-error")


def test_mobile_layout_has_no_horizontal_scroll(browser):
    pg = browser.new_page(viewport={"width": 390, "height": 844})
    pg.goto(BASE)
    pg.get_by_role("button", name=re.compile("Load demo: Retail")).click()
    expect(pg.get_by_text("Parsed successfully").first).to_be_visible()
    for stage in ["Profile", "Explore", "Discover", "Report"]:
        pg.get_by_role("button", name=f"Continue to {stage} →").click()
        pg.wait_for_timeout(800)
        overflow = pg.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{stage} overflows by {overflow}px on a phone"
    shot(pg, "09-mobile-report")
    pg.close()


def test_stages_are_locked_until_data_is_loaded_and_keyboard_works(page: Page):
    page.goto(BASE)
    expect(page.get_by_role("button", name=re.compile("^Profile"))).to_be_disabled()
    page.keyboard.press("Tab")  # skip link is the first focusable element
    expect(page.get_by_role("link", name="Skip to workspace")).to_be_focused()
