"""Turning uploaded bytes into a clean table of text values.

Design choices (documented in docs/methodology.md):

* Files are parsed from memory. Nothing is written to disk, so there is no
  temporary file to leak and no file path a user can influence.
* Every cell is first read as *text*. Type inference happens afterwards in
  `inference.py`, so we decide explicitly how blanks, currency symbols and
  dates are handled instead of letting a library guess silently.
* Excel workbooks are opened with `data_only=True`: we read the values Excel
  last saved for formula cells and never evaluate formulas or macros.
* Anything we change (renamed headers, removed blank rows, trimmed spaces) is
  recorded in `notes` so the user is told about it.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from dataclasses import dataclass, field

import pandas as pd

from .config import Settings
from .errors import AppError

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

# Cell contents treated as missing (compared after trimming, case-insensitive).
# Note: "0" is deliberately NOT here — a blank is never treated as zero, and a
# zero is never treated as blank.
MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "#n/a", "-", "--"}

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class ParsedTable:
    filename: str
    file_type: str  # "csv" | "xlsx"
    frame: pd.DataFrame  # object dtype; every cell is a str or None
    sheet: str | None = None
    sheets: list[str] = field(default_factory=list)
    encoding: str | None = None
    delimiter: str | None = None
    notes: list[str] = field(default_factory=list)
    removed_blank_rows: int = 0
    removed_blank_columns: int = 0
    renamed_headers: list[dict[str, str]] = field(default_factory=list)
    trimmed_cells: dict[str, int] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# File-level validation
# --------------------------------------------------------------------------- #


def safe_filename(name: str | None) -> str:
    """Keep only the final path component and strip control characters.

    The name is used for display only and never to build a filesystem path,
    but we sanitise it anyway (defence in depth against path traversal such as
    ``../../etc/passwd`` and against odd characters in the report).
    """
    if not name:
        return "uploaded-file"
    base = name.replace("\\", "/").split("/")[-1]
    base = _CONTROL_CHARS.sub("", base).strip()
    if base in {"", ".", ".."}:
        return "uploaded-file"
    return base[:120]


def file_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        if ext in {".xls", ".xlsm", ".xlsb"}:
            raise AppError(
                415,
                "unsupported_excel_format",
                f"{ext} files are not supported. Please save the workbook as .xlsx (macro-free) or export the sheet as .csv.",
            )
        raise AppError(
            415,
            "unsupported_file_type",
            f"Unsupported file type '{ext or 'none'}'. Upload a .csv or .xlsx file.",
        )
    return ext


def validate_size(data: bytes, settings: Settings) -> None:
    if len(data) == 0:
        raise AppError(422, "empty_file", "The file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise AppError(
            413,
            "file_too_large",
            f"The file is larger than the {settings.max_upload_mb} MB limit.",
            {"max_mb": settings.max_upload_mb},
        )


def _check_xlsx_container(data: bytes) -> None:
    """An .xlsx file is a ZIP archive. Reject anything else before parsing."""
    if not data.startswith(b"PK"):
        raise AppError(
            422,
            "invalid_excel_file",
            "This does not look like a valid .xlsx workbook. If it is a CSV, rename it to .csv.",
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "xl/workbook.xml" not in names:
                raise AppError(422, "invalid_excel_file", "The workbook is missing its sheet index.")
            # Zip-bomb guard: refuse archives that expand to something enormous.
            expanded = sum(info.file_size for info in zf.infolist())
            if expanded > 400 * 1024 * 1024:
                raise AppError(413, "file_too_large", "The workbook expands to more than 400 MB.")
    except zipfile.BadZipFile as exc:
        raise AppError(422, "invalid_excel_file", "The workbook appears to be corrupted.") from exc


# --------------------------------------------------------------------------- #
# Excel
# --------------------------------------------------------------------------- #


def list_sheets(data: bytes) -> list[str]:
    _check_xlsx_container(data)
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many different exception types
        raise AppError(422, "invalid_excel_file", "The workbook could not be opened.") from exc
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _excel_cell_to_text(value: object) -> str | None:
    """Convert an openpyxl cell value to text without losing meaning."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()  # datetime/date/time
    return str(value)


def _read_excel(data: bytes, sheet: str | None, settings: Settings) -> tuple[list[list[str | None]], str, list[str]]:
    sheets = list_sheets(data)
    if not sheets:
        raise AppError(422, "no_sheets", "The workbook has no worksheets.")
    if sheet is None:
        if len(sheets) > 1:
            raise AppError(
                422,
                "sheet_required",
                "This workbook has several worksheets. Choose which one to analyse.",
                {"sheets": sheets},
            )
        sheet = sheets[0]
    if sheet not in sheets:
        raise AppError(
            422,
            "sheet_not_found",
            f"Worksheet '{sheet}' was not found in the workbook.",
            {"sheets": sheets},
        )

    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb[sheet]
        rows: list[list[str | None]] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i > settings.max_rows + 1:  # +1 for the header row
                raise AppError(
                    413,
                    "too_many_rows",
                    f"The sheet has more than {settings.max_rows:,} data rows.",
                    {"max_rows": settings.max_rows},
                )
            if len(row) > settings.max_columns + 50:  # generous: trailing blanks are trimmed later
                raise AppError(
                    413,
                    "too_many_columns",
                    f"The sheet has more than {settings.max_columns} columns.",
                    {"max_columns": settings.max_columns},
                )
            rows.append([_excel_cell_to_text(v) for v in row])
    finally:
        wb.close()
    return rows, sheet, sheets


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #


def _decode(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise AppError(422, "unreadable_text", "The file's text encoding could not be read. Save it as UTF-8 CSV.")


def _sniff_delimiter(text: str) -> str:
    sample = text[:65536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _read_csv(data: bytes, settings: Settings) -> tuple[list[list[str | None]], str, str]:
    if b"\x00" in data[:8192]:
        raise AppError(422, "binary_file", "This file contains binary data and is not a CSV.")
    text, encoding = _decode(data)
    if text.strip() == "":
        raise AppError(422, "empty_file", "The file contains no data.")
    delimiter = _sniff_delimiter(text)
    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            header=None,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            skip_blank_lines=False,
            nrows=settings.max_rows + 2,
        )
    except pd.errors.ParserError as exc:
        raise AppError(
            422,
            "malformed_csv",
            "The CSV could not be parsed. A row probably has a different number of columns "
            f"than the header. Details: {str(exc)[:200]}",
        ) from exc
    except pd.errors.EmptyDataError as exc:
        raise AppError(422, "empty_file", "The file contains no data.") from exc
    if len(df) > settings.max_rows + 1:
        raise AppError(
            413,
            "too_many_rows",
            f"The file has more than {settings.max_rows:,} data rows.",
            {"max_rows": settings.max_rows},
        )
    rows = df.values.tolist()
    return rows, encoding, delimiter


# --------------------------------------------------------------------------- #
# Shared clean-up
# --------------------------------------------------------------------------- #


def _normalise_cell(value: object) -> tuple[str | None, bool]:
    """Return (clean value, was_trimmed)."""
    if value is None:
        return None, False
    text = str(value)
    stripped = text.strip()
    if stripped.lower() in MISSING_TOKENS:
        return None, False
    return stripped, stripped != text


def _build_frame(rows: list[list[str | None]], parsed: ParsedTable, settings: Settings) -> pd.DataFrame:
    # Drop trailing rows that are entirely blank *before* choosing the header.
    if not rows:
        raise AppError(422, "empty_file", "The file contains no data.")
    width = max(len(r) for r in rows)
    rows = [list(r) + [None] * (width - len(r)) for r in rows]

    # Find the header: first row with any non-blank cell.
    header_idx = None
    for i, row in enumerate(rows):
        if any(_normalise_cell(v)[0] is not None for v in row):
            header_idx = i
            break
    if header_idx is None:
        raise AppError(422, "empty_file", "The file contains no data.")
    if header_idx > 0:
        parsed.notes.append(f"Skipped {header_idx} blank line(s) above the header row.")

    raw_header = rows[header_idx]
    body = rows[header_idx + 1 :]

    # Clean the cells
    cleaned_body: list[list[str | None]] = []
    trimmed_counts = [0] * width
    for row in body:
        new_row = []
        for j, v in enumerate(row):
            clean, trimmed = _normalise_cell(v)
            if trimmed and clean is not None:
                trimmed_counts[j] += 1
            new_row.append(clean)
        cleaned_body.append(new_row)

    # Remove columns with no header and no values (common at the edge of Excel sheets)
    keep = []
    for j in range(width):
        header_blank = _normalise_cell(raw_header[j])[0] is None
        values_blank = all(r[j] is None for r in cleaned_body)
        if header_blank and values_blank:
            parsed.removed_blank_columns += 1
        else:
            keep.append(j)
    if parsed.removed_blank_columns:
        parsed.notes.append(f"Removed {parsed.removed_blank_columns} completely empty unnamed column(s).")

    if len(keep) > settings.max_columns:
        raise AppError(
            413,
            "too_many_columns",
            f"The file has {len(keep)} columns; the limit is {settings.max_columns}.",
            {"max_columns": settings.max_columns},
        )

    # Headers: trim, fill blanks, de-duplicate — and report every change.
    headers: list[str] = []
    used: set[str] = set()
    for position, j in enumerate(keep, start=1):
        original = raw_header[j]
        name = _CONTROL_CHARS.sub("", str(original)).strip() if original is not None else ""
        if name == "":
            name = f"column_{position}"
        base = name[:100]
        candidate = base
        suffix = 2
        while candidate.lower() in used:
            candidate = f"{base} ({suffix})"
            suffix += 1
        used.add(candidate.lower())
        if candidate != (str(original).strip() if original is not None else ""):
            parsed.renamed_headers.append({"original": "" if original is None else str(original), "new": candidate})
        headers.append(candidate)
    if parsed.renamed_headers:
        parsed.notes.append(f"Renamed {len(parsed.renamed_headers)} blank or duplicate column header(s).")

    data_rows = [[r[j] for j in keep] for r in cleaned_body]

    # Remove rows where every cell is blank — and say how many.
    non_blank = [r for r in data_rows if any(v is not None for v in r)]
    parsed.removed_blank_rows = len(data_rows) - len(non_blank)
    if parsed.removed_blank_rows:
        parsed.notes.append(f"Removed {parsed.removed_blank_rows} completely blank row(s).")

    if not non_blank:
        raise AppError(422, "no_rows", "The file has a header row but no data rows.")
    if len(non_blank) * len(headers) > settings.max_cells:
        raise AppError(
            413,
            "too_many_cells",
            f"The dataset has more than {settings.max_cells:,} cells.",
            {"max_cells": settings.max_cells},
        )

    for j, h in zip(keep, headers, strict=True):
        if trimmed_counts[j]:
            parsed.trimmed_cells[h] = trimmed_counts[j]
    if parsed.trimmed_cells:
        total = sum(parsed.trimmed_cells.values())
        parsed.notes.append(f"Trimmed leading/trailing spaces from {total} cell(s).")

    return pd.DataFrame(non_blank, columns=headers, dtype=object)


def parse_upload(data: bytes, filename: str | None, settings: Settings, sheet: str | None = None) -> ParsedTable:
    """Validate and parse an uploaded file into a ParsedTable."""
    name = safe_filename(filename)
    ext = file_extension(name)
    validate_size(data, settings)

    if ext == ".csv":
        rows, encoding, delimiter = _read_csv(data, settings)
        parsed = ParsedTable(filename=name, file_type="csv", frame=pd.DataFrame(), encoding=encoding, delimiter=delimiter)
        if encoding != "utf-8-sig":
            parsed.notes.append("File was not valid UTF-8; read using Windows-1252 encoding.")
        if delimiter != ",":
            label = {"\t": "tab", ";": "semicolon", "|": "pipe"}.get(delimiter, delimiter)
            parsed.notes.append(f"Detected {label}-separated values.")
    else:
        rows, chosen, sheets = _read_excel(data, sheet, settings)
        parsed = ParsedTable(filename=name, file_type="xlsx", frame=pd.DataFrame(), sheet=chosen, sheets=sheets)
        parsed.notes.append("Formula cells were read as their last saved values; formulas and macros were not executed.")

    parsed.frame = _build_frame(rows, parsed, settings)
    return parsed
