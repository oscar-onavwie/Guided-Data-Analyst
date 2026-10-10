from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis import build_analysis  # noqa: E402
from app.config import Settings  # noqa: E402
from app.findings import build_findings  # noqa: E402
from app.inference import TypedTable, infer_table  # noqa: E402
from app.parsing import ParsedTable, parse_upload  # noqa: E402
from app.profiling import build_profile  # noqa: E402
from app.schemas import AnalysisBundle, DatasetProfile, FindingsResult  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "sample-data"


@dataclass
class Result:
    parsed: ParsedTable
    table: TypedTable
    profile: DatasetProfile
    analysis: AnalysisBundle
    findings: FindingsResult


@pytest.fixture
def settings() -> Settings:
    return Settings()


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def xlsx_bytes(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        ws.title = name
        first = False
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def analyse(data: bytes, filename: str = "data.csv", sheet: str | None = None, settings: Settings | None = None) -> Result:
    parsed = parse_upload(data, filename, settings or Settings(), sheet=sheet)
    table = infer_table(parsed.frame)
    profile = build_profile(table, parsed)
    return Result(parsed, table, profile, build_analysis(table), build_findings(table, profile))


def analyse_csv(text: str) -> Result:
    return analyse(csv_bytes(text))


def sample(name: str) -> bytes:
    return (SAMPLE_DIR / name).read_bytes()
