import io

import pytest
from conftest import csv_bytes, xlsx_bytes
from openpyxl import Workbook

from app.config import Settings
from app.errors import AppError
from app.parsing import list_sheets, parse_upload, safe_filename


def test_csv_basic(settings):
    p = parse_upload(csv_bytes("a,b\n1,x\n2,y\n"), "test.csv", settings)
    assert p.file_type == "csv"
    assert list(p.frame.columns) == ["a", "b"]
    assert p.frame.shape == (2, 2)
    assert p.frame.iloc[0].tolist() == ["1", "x"]  # every cell read as text first


def test_csv_semicolon_and_utf8_bom(settings):
    data = "﻿name;value\nAlpha;1\nBeta;2\n".encode()
    p = parse_upload(data, "semi.csv", settings)
    assert list(p.frame.columns) == ["name", "value"]
    assert any("semicolon" in n for n in p.notes)


def test_csv_windows_1252_fallback(settings):
    data = "item,price\nCafé,£3\n".encode("cp1252")
    p = parse_upload(data, "legacy.csv", settings)
    assert p.frame.iloc[0, 0] == "Café"
    assert any("Windows-1252" in n for n in p.notes)


def test_missing_tokens_become_none_and_zero_stays_zero(settings):
    # Row 2 keeps a value in column c, so it is not a fully blank row.
    p = parse_upload(csv_bytes("a,b,c\n0,NA,x\n,n/a,y\n5,null,z\n"), "t.csv", settings)
    assert p.frame["a"].tolist() == ["0", None, "5"]
    assert p.frame["b"].tolist() == [None, None, None]


def test_blank_rows_removed_and_reported(settings):
    p = parse_upload(csv_bytes("a,b\n1,2\n,\n,\n3,4\n"), "t.csv", settings)
    assert len(p.frame) == 2
    assert p.removed_blank_rows == 2
    assert any("2 completely blank row" in n for n in p.notes)


def test_blank_and_duplicate_headers_renamed(settings):
    p = parse_upload(csv_bytes("id,,id,Name\n1,a,2,x\n"), "t.csv", settings)
    assert list(p.frame.columns) == ["id", "column_2", "id (2)", "Name"]
    assert {"original": "", "new": "column_2"} in p.renamed_headers
    assert {"original": "id", "new": "id (2)"} in p.renamed_headers


def test_empty_unnamed_columns_dropped(settings):
    p = parse_upload(csv_bytes("a,,\n1,,\n2,,\n"), "t.csv", settings)
    assert list(p.frame.columns) == ["a"]
    assert p.removed_blank_columns == 2


@pytest.mark.parametrize(
    "data,code",
    [
        (b"", "empty_file"),
        (b"   \n\n", "empty_file"),
        (b"a,b,c\n", "no_rows"),
        (b"a,b\n1,2\n3,4,5,6\n", "malformed_csv"),
        (b"\x00\x01\x02binary", "binary_file"),
    ],
)
def test_csv_errors(settings, data, code):
    with pytest.raises(AppError) as exc:
        parse_upload(data, "bad.csv", settings)
    assert exc.value.code == code
    assert exc.value.status in (413, 422)


@pytest.mark.parametrize(
    "name,code,status",
    [
        ("data.txt", "unsupported_file_type", 415),
        ("data.xls", "unsupported_excel_format", 415),
        ("macro.xlsm", "unsupported_excel_format", 415),
        ("noext", "unsupported_file_type", 415),
    ],
)
def test_unsupported_extensions(settings, name, code, status):
    with pytest.raises(AppError) as exc:
        parse_upload(b"a\n1\n", name, settings)
    assert (exc.value.code, exc.value.status) == (code, status)


def test_fake_xlsx_rejected(settings):
    with pytest.raises(AppError) as exc:
        parse_upload(b"a,b\n1,2\n", "pretend.xlsx", settings)
    assert exc.value.code == "invalid_excel_file"


def test_file_size_limit(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    small = Settings()
    big = b"a\n" + b"1\n" * (600 * 1024)  # ~1.2 MB
    with pytest.raises(AppError) as exc:
        parse_upload(big, "big.csv", small)
    assert exc.value.code == "file_too_large" and exc.value.status == 413


def test_row_and_column_limits(monkeypatch):
    monkeypatch.setenv("MAX_ROWS", "10")
    monkeypatch.setenv("MAX_COLUMNS", "3")
    s = Settings()
    rows = "a\n" + "1\n" * 11
    with pytest.raises(AppError) as exc:
        parse_upload(rows.encode(), "rows.csv", s)
    assert exc.value.code == "too_many_rows"
    with pytest.raises(AppError) as exc:
        parse_upload(b"a,b,c,d\n1,2,3,4\n", "cols.csv", s)
    assert exc.value.code == "too_many_columns"


@pytest.mark.parametrize("name", ["../../etc/passwd.csv", "..\\..\\windows\\x.csv", "/abs/path/data.csv"])
def test_filename_path_components_stripped(name):
    cleaned = safe_filename(name)
    assert "/" not in cleaned and "\\" not in cleaned and not cleaned.startswith("..")
    assert cleaned.endswith(".csv")


def test_xlsx_single_sheet(settings):
    data = xlsx_bytes({"Data": [["region", "sales"], ["North", 10], ["South", 20.5]]})
    p = parse_upload(data, "book.xlsx", settings)
    assert p.sheet == "Data"
    assert p.frame["sales"].tolist() == ["10", "20.5"]


def test_xlsx_multiple_sheets_requires_choice(settings):
    data = xlsx_bytes({"First": [["a"], [1]], "Second": [["b", "c"], [2, 3], [4, 5]]})
    assert list_sheets(data) == ["First", "Second"]
    with pytest.raises(AppError) as exc:
        parse_upload(data, "book.xlsx", settings)
    assert exc.value.code == "sheet_required"
    assert exc.value.details["sheets"] == ["First", "Second"]
    p = parse_upload(data, "book.xlsx", settings, sheet="Second")
    assert list(p.frame.columns) == ["b", "c"] and len(p.frame) == 2
    with pytest.raises(AppError) as exc:
        parse_upload(data, "book.xlsx", settings, sheet="Missing")
    assert exc.value.code == "sheet_not_found"


def test_xlsx_formulas_are_not_executed(settings):
    wb = Workbook()
    ws = wb.active
    ws.append(["a", "b", "formula"])
    ws.append([1, 2, "=A2+B2"])
    ws.append([3, 4, '=HYPERLINK("http://example.com","x")'])
    buf = io.BytesIO()
    wb.save(buf)  # openpyxl stores formulas without cached results
    p = parse_upload(buf.getvalue(), "f.xlsx", settings)
    # We read the stored (cached) value only; with no cached value the cell is missing.
    assert p.frame["formula"].tolist() == [None, None]
    assert any("not executed" in n for n in p.notes)


def test_xlsx_dates_and_booleans_converted_to_text(settings):
    from datetime import datetime

    data = xlsx_bytes({"S": [["when", "flag", "n"], [datetime(2025, 3, 4), True, 3.0], [datetime(2025, 3, 5), False, 2.5]]})
    p = parse_upload(data, "d.xlsx", settings)
    assert p.frame["when"].tolist() == ["2025-03-04T00:00:00", "2025-03-05T00:00:00"]
    assert p.frame["flag"].tolist() == ["TRUE", "FALSE"]
    assert p.frame["n"].tolist() == ["3", "2.5"]
