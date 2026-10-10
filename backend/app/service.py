"""Framework-independent application logic.

`main.py` is a thin FastAPI layer over these functions. Keeping the logic
here means it can be tested without a web server and swapped to another
framework without rewriting the analysis.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import ai as ai_module
from .analysis import build_analysis, grouped_summary, main_measure, scatter, time_series
from .config import Settings
from .errors import AppError
from .findings import build_findings
from .inference import infer_table
from .parsing import file_extension, list_sheets, parse_upload, safe_filename, validate_size
from .profiling import build_profile
from .reports import build_report, export_csv, render_html
from .schemas import (
    AIExplanation,
    AnalysisBundle,
    AppConfig,
    DatasetProfile,
    DatasetSummary,
    DemoDataset,
    FindingsResult,
    GroupedSummary,
    Preview,
    ScatterData,
    SheetList,
    TimeSeries,
)
from .store import Session, SessionStore

SAMPLE_DIR = Path(os.getenv("SAMPLE_DATA_DIR", Path(__file__).resolve().parents[2] / "sample-data"))

# Fixed allow-list: the key from the URL is only ever used to look up this
# dictionary, never to build a file path, so path traversal is impossible.
DEMO_DATASETS: dict[str, dict[str, str | None]] = {
    "small-business": {
        "title": "Small business: sales & expenses",
        "description": "A year of fictional daily transactions for a consultancy, with refunds, missing payment methods and duplicate entries.",
        "filename": "small_business_sales_expenses.csv",
        "sheet": None,
    },
    "retail": {
        "title": "Retail: product performance",
        "description": "200 fictional product-region records with prices, discounts, revenue and two extreme bulk orders.",
        "filename": "retail_product_performance.csv",
        "sheet": None,
    },
    "workforce": {
        "title": "Operations: support-centre teams",
        "description": "52 weeks of fictional team performance (Excel workbook with two worksheets).",
        "filename": "workforce_operational_performance.xlsx",
        "sheet": "Weekly Performance",
    },
}

DATA_RETENTION = (
    "Files are processed in memory and never written to disk. A loaded dataset is kept in server memory for "
    "{ttl} minutes after it was last used, until you remove it, or until the server restarts. "
    "Raw values are never logged. Use non-sensitive data only."
)

PREVIEW_ROWS = 50
MAX_PREVIEW_LIMIT = 200


def app_config(settings: Settings) -> AppConfig:
    return AppConfig(
        max_upload_mb=settings.max_upload_mb,
        max_rows=settings.max_rows,
        max_columns=settings.max_columns,
        session_ttl_minutes=settings.session_ttl_minutes,
        ai_available=settings.ai_available,
        data_retention=DATA_RETENTION.format(ttl=settings.session_ttl_minutes),
    )


def demo_list() -> list[DemoDataset]:
    return [
        DemoDataset(key=k, title=v["title"] or "", description=v["description"] or "", filename=v["filename"] or "")
        for k, v in DEMO_DATASETS.items()
    ]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def sheets_for_upload(data: bytes, filename: str | None, settings: Settings) -> SheetList:
    name = safe_filename(filename)
    ext = file_extension(name)
    validate_size(data, settings)
    if ext != ".xlsx":
        return SheetList(filename=name, sheets=[])
    return SheetList(filename=name, sheets=list_sheets(data))


def load_upload(
    store: SessionStore, data: bytes, filename: str | None, settings: Settings, sheet: str | None = None
) -> DatasetSummary:
    parsed = parse_upload(data, filename, settings, sheet=sheet)
    table = infer_table(parsed.frame)
    session = store.add(parsed, table)
    return summary(store, session)


def load_demo(store: SessionStore, key: str, settings: Settings) -> DatasetSummary:
    meta = DEMO_DATASETS.get(key)
    if meta is None:
        raise AppError(404, "demo_not_found", f"Unknown demo dataset '{key}'.", {"available": list(DEMO_DATASETS)})
    path = SAMPLE_DIR / str(meta["filename"])
    if not path.is_file():
        raise AppError(500, "demo_missing", "The demo data files are missing on the server. Run scripts/generate_sample_data.py.")
    parsed = parse_upload(path.read_bytes(), path.name, settings, sheet=meta["sheet"])
    table = infer_table(parsed.frame)
    session = store.add(parsed, table, is_demo=True, demo_key=key)
    return summary(store, session)


def _cell(value: Any) -> str | None:
    return None if value is None or (isinstance(value, float) and value != value) else str(value)


def preview(session: Session, offset: int = 0, limit: int = PREVIEW_ROWS) -> Preview:
    if offset < 0 or limit < 1 or limit > MAX_PREVIEW_LIMIT:
        raise AppError(422, "invalid_range", f"offset must be >= 0 and limit between 1 and {MAX_PREVIEW_LIMIT}.")
    frame = session.parsed.frame
    page = frame.iloc[offset : offset + limit]
    return Preview(
        columns=[str(c) for c in frame.columns],
        rows=[[_cell(v) for v in row] for row in page.itertuples(index=False, name=None)],
        offset=offset,
        limit=limit,
        total_rows=len(frame),
    )


def summary(store: SessionStore, session: Session) -> DatasetSummary:
    p = session.parsed
    return DatasetSummary(
        dataset_id=session.dataset_id,
        filename=p.filename,
        file_type=p.file_type,  # type: ignore[arg-type]
        sheet=p.sheet,
        sheets=p.sheets,
        is_demo=session.is_demo,
        demo_key=session.demo_key,
        rows=len(p.frame),
        columns=len(p.frame.columns),
        column_names=[str(c) for c in p.frame.columns],
        parse_notes=p.notes,
        loaded_at=session.loaded_at.replace(microsecond=0).isoformat(),
        expires_at=store.expires_at(session).replace(microsecond=0).isoformat(),
        preview=preview(session),
    )


# --------------------------------------------------------------------------- #
# Cached analysis
# --------------------------------------------------------------------------- #


def get_profile(session: Session) -> DatasetProfile:
    if "profile" not in session.cache:
        session.cache["profile"] = build_profile(session.table, session.parsed)
    return session.cache["profile"]


def get_analysis(session: Session) -> AnalysisBundle:
    if "analysis" not in session.cache:
        session.cache["analysis"] = build_analysis(session.table)
    return session.cache["analysis"]


def get_findings(session: Session) -> FindingsResult:
    if "findings" not in session.cache:
        session.cache["findings"] = build_findings(session.table, get_profile(session))
    return session.cache["findings"]


def explore_grouped(session: Session, category_column: str, value_column: str) -> GroupedSummary:
    return grouped_summary(session.table, category_column, value_column)


def explore_scatter(session: Session, x: str, y: str) -> ScatterData:
    return scatter(session.table, x, y)


def explore_timeseries(session: Session, date_column: str, value_column: str | None, agg: str, granularity: str) -> TimeSeries:
    return time_series(session.table, date_column, value_column, agg, granularity)


# --------------------------------------------------------------------------- #
# Report & exports
# --------------------------------------------------------------------------- #


def report_data(session: Session) -> dict[str, Any]:
    measure = main_measure(session.table)
    return build_report(
        filename=session.parsed.filename,
        sheet=session.parsed.sheet,
        is_demo=session.is_demo,
        loaded_at=session.loaded_at,
        profile=get_profile(session),
        analysis=get_analysis(session),
        findings=get_findings(session),
        ai=session.cache.get("ai"),
        main_measure_name=measure.name if measure else None,
    )


def report_html(session: Session) -> str:
    return render_html(report_data(session))


def report_filename(session: Session, ext: str) -> str:
    stem = os.path.splitext(session.parsed.filename)[0]
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem).strip("-")[:60] or "dataset"
    prefix = "DEMO-" if session.is_demo else ""
    return f"{prefix}{stem}-analysis.{ext}"


def export_table(session: Session, table: str) -> str:
    return export_csv(table, get_profile(session), get_analysis(session), get_findings(session))


def ai_explain(session: Session, settings: Settings, consent: bool) -> AIExplanation:
    if not consent:
        raise AppError(
            422,
            "consent_required",
            "Please confirm that you agree to send the dataset summary and findings (not the raw rows) to the external AI service.",
        )
    result = ai_module.explain(get_profile(session), get_findings(session), settings)
    session.cache["ai"] = result
    return result
