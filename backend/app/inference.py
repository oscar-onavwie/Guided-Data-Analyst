"""Deciding what kind of data each column holds.

Every column arrives as text (or missing). We try, in order:

1. empty      – no values at all
2. boolean    – only true/false/yes/no style values
3. numeric    – at least 95% of values parse as numbers (after removing
                currency symbols, thousands separators and a trailing %)
4. datetime   – at least 95% of values parse as dates using ONE consistent
                format (UK day-first is preferred when day/month is ambiguous)
5. text       – mostly-unique free text (e.g. names, comments, IDs)
6. categorical– everything else (repeated labels such as region or status)

Values that do not fit a column's chosen type are counted as *invalid*,
excluded from calculations and reported — never silently replaced by zero.

Separately we assign a *role*: identifier, date, measure (numeric to analyse),
dimension (category to group by) or other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd

TYPE_THRESHOLD = 0.95

_BOOL_TRUE = {"true", "yes", "y"}
_BOOL_FALSE = {"false", "no", "n"}

_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_CURRENCY = "£$€¥"

_ID_NAME_RE = re.compile(r"(^id$|_id$|^id_|\bid\b|identifier|uuid|guid|(^|_)(ref|reference|code|number|no)$)", re.I)

_QUANTITY_NAME_RE = re.compile(r"amount|sales|revenue|total|count|qty|quantity|units|price|cost|value|score|hours|days", re.I)

# Explicit date formats tried in order. Day-first comes before month-first so
# that an ambiguous date such as 03/04/2025 is read as 3 April (UK convention).
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%Y/%m/%d",
    "%Y-%m",
]


@dataclass
class TypedColumn:
    name: str
    kind: str  # empty | boolean | numeric | datetime | categorical | text
    role: str  # identifier | date | measure | dimension | other
    values: pd.Series  # float64 for numeric, datetime64[ns] for datetime, object (str/None) otherwise
    missing_count: int  # blank in the source file
    invalid_count: int = 0  # present in the file but not valid for the inferred type
    invalid_examples: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    date_format: str | None = None
    ambiguous_day_month: bool = False
    is_integer: bool = False

    @property
    def valid(self) -> pd.Series:
        """Values usable for calculations (missing and invalid removed)."""
        return self.values.dropna()


@dataclass
class TypedTable:
    columns: list[TypedColumn]
    n_rows: int

    def get(self, name: str) -> TypedColumn | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    def by_role(self, role: str) -> list[TypedColumn]:
        return [c for c in self.columns if c.role == role]


# --------------------------------------------------------------------------- #
# Value parsers
# --------------------------------------------------------------------------- #


def parse_number(text: str) -> float | None:
    """Parse '£1,234.50', '(12)', '-3.5', '45%' etc. Return None if not a number."""
    s = text.strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    if s.endswith("%"):
        s = s[:-1]
    # currency symbol may come before or after a sign: £-5, -£5
    sign = ""
    if s[:1] in "+-":
        sign, s = s[0], s[1:]
    if s[:1] in _CURRENCY:
        s = s[1:]
    if s[:1] in "+-" and not sign:
        sign, s = s[0], s[1:]
    s = sign + s
    if _THOUSANDS_RE.match(s):
        s = s.replace(",", "")
    if not _NUMBER_RE.match(s):
        return None
    value = float(s)
    if not np.isfinite(value):
        return None
    return -value if negative else value


def _try_date_format(values: pd.Series, fmt: str) -> pd.Series:
    return pd.to_datetime(values, format=fmt, errors="coerce")


def _looks_date_like(sample: list[str]) -> bool:
    hits = sum(1 for v in sample if re.search(r"\d{1,4}[-/.\s]\w{1,9}[-/.\s,]+\d{2,4}|^\d{4}-\d{2}$", v))
    return hits >= max(1, int(0.8 * len(sample)))


def parse_dates(values: pd.Series) -> tuple[pd.Series, str | None, bool, list[str]]:
    """Parse a text Series to datetimes.

    Returns (parsed series, format used, ambiguous_day_month, notes).
    Time-zone aware values are converted to UTC and stored without a zone.
    """
    present = values.dropna()
    notes: list[str] = []
    best: tuple[float, str | None, pd.Series] = (0.0, None, pd.Series(pd.NaT, index=values.index))
    for fmt in DATE_FORMATS:
        parsed = _try_date_format(values, fmt)
        rate = parsed[present.index].notna().mean() if len(present) else 0.0
        if rate > best[0]:
            best = (float(rate), fmt, parsed)
        if rate == 1.0:
            break

    # Mixed formats in one column (common after copy-pasting between systems):
    # start from the best single format and fill gaps with the others in order.
    if best[0] < TYPE_THRESHOLD and best[1] is not None:
        combined = best[2].copy()
        used = {best[1]}
        for fmt in DATE_FORMATS:
            gaps = combined.isna() & values.notna()
            if not gaps.any():
                break
            filled = _try_date_format(values[gaps], fmt)
            if filled.notna().any():
                used.add(fmt)
                combined[gaps] = filled
        rate = float(combined[present.index].notna().mean()) if len(present) else 0.0
        if rate >= TYPE_THRESHOLD and len(used) > 1:
            notes.append(
                f"Dates were written in {len(used)} different formats; each value was read with the "
                "first matching format (day-first preferred)."
            )
            best = (rate, "mixed", combined)

    # Values carrying a timezone offset (e.g. 2025-01-01T10:00:00+01:00)
    if best[0] < TYPE_THRESHOLD:
        try:
            parsed = pd.to_datetime(values, format="ISO8601", errors="coerce", utc=True)
            rate = float(parsed[present.index].notna().mean()) if len(present) else 0.0
            if rate > best[0]:
                has_offset = present.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).any()
                if has_offset:
                    notes.append("Values included time-zone offsets and were converted to UTC.")
                best = (rate, "ISO8601", parsed.dt.tz_convert(None))
        except (ValueError, TypeError):
            pass

    ambiguous = False
    if best[1] in {"%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"}:
        us = best[1].replace("%d/%m", "%m/%d")
        us_rate = float(_try_date_format(values, us)[present.index].notna().mean()) if len(present) else 0.0
        if us_rate >= best[0]:
            ambiguous = True
            notes.append(
                "Day and month order is ambiguous in every value (e.g. 03/04/2025); "
                "dates were read as day/month/year (UK convention)."
            )
    series = best[2]
    if not pd.api.types.is_datetime64_any_dtype(series):
        series = pd.to_datetime(series, errors="coerce")
    # pandas stores dates as nanoseconds, which only covers 1677-2262. Dates
    # outside that range (e.g. a 2999-12-31 "no end date" placeholder) are
    # treated as invalid rather than crashing or wrapping around.
    out_of_range = series.notna() & ((series < pd.Timestamp.min) | (series > pd.Timestamp.max))
    if out_of_range.any():
        series = series.where(~out_of_range)
        notes.append(f"{int(out_of_range.sum())} date(s) outside the supported range 1677–2262 were treated as invalid.")
    return series.astype("datetime64[ns]"), best[1], ambiguous, notes


# --------------------------------------------------------------------------- #
# Column inference
# --------------------------------------------------------------------------- #


def _as_text(raw: pd.Series) -> pd.Series:
    """Object Series of str or None (never NaN), so missing stays explicit."""
    out = raw.map(lambda v: None if v is None or (isinstance(v, float) and v != v) else str(v))
    return out.astype(object).where(out.notna(), None)


def infer_column(name: str, raw: pd.Series) -> TypedColumn:
    raw = _as_text(raw)
    present = raw.dropna().astype(str)
    missing = int(len(raw) - len(present))
    n = len(present)

    if n == 0:
        return TypedColumn(name, "empty", "other", pd.Series([None] * len(raw), index=raw.index, dtype=object), missing)

    lowered = present.str.lower()

    # Boolean
    if lowered.isin(_BOOL_TRUE | _BOOL_FALSE).all() and lowered.nunique() <= 2:
        mapped = _as_text(raw.map(lambda v: None if v is None else ("True" if v.lower() in _BOOL_TRUE else "False")))
        return TypedColumn(name, "boolean", "dimension", mapped, missing)

    # Numeric
    numbers = present.map(parse_number)
    num_ok = numbers.notna()
    if num_ok.mean() >= TYPE_THRESHOLD:
        values = pd.Series(np.nan, index=raw.index, dtype="float64")
        values[numbers[num_ok].index] = numbers[num_ok].astype(float)
        invalid_idx = numbers[~num_ok].index
        col = TypedColumn(
            name,
            "numeric",
            "measure",
            values,
            missing,
            invalid_count=int(len(invalid_idx)),
            invalid_examples=[str(raw[i]) for i in invalid_idx[:3]],
        )
        valid = values.dropna()
        col.is_integer = bool(len(valid) and np.all(np.mod(valid, 1) == 0))
        if present.str.contains("%").mean() > 0.5:
            col.notes.append("Values were percentages; the % sign was removed (45% is stored as 45).")
        if present.str.contains(f"[{_CURRENCY}]").any():
            col.notes.append("Currency symbols were removed before calculation.")
        if present.str.match(r"^\(.*\)$").any():
            col.notes.append("Values in brackets, e.g. (12), were read as negative numbers.")
        col.role = _numeric_role(name, col)
        return col

    # Datetime (only if the values look like dates — avoids reading codes as dates)
    sample = present.head(50).tolist()
    if _looks_date_like(sample):
        parsed, fmt, ambiguous, notes = parse_dates(raw)
        rate = float(parsed[present.index].notna().mean())
        if rate >= TYPE_THRESHOLD:
            invalid_idx = present.index[parsed[present.index].isna()]
            return TypedColumn(
                name,
                "datetime",
                "date",
                parsed,
                missing,
                invalid_count=int(len(invalid_idx)),
                invalid_examples=[str(raw[i]) for i in invalid_idx[:3]],
                notes=notes,
                date_format=fmt,
                ambiguous_day_month=ambiguous,
            )

    # Text vs categorical
    unique = present.nunique()
    unique_ratio = unique / n
    values = raw
    if unique_ratio > 0.9 and unique > 20:
        role = "identifier" if (_ID_NAME_RE.search(name) or unique == n) else "other"
        return TypedColumn(name, "text", role, values, missing)

    role = "identifier" if _ID_NAME_RE.search(name) and unique_ratio > 0.2 else "dimension"
    return TypedColumn(name, "categorical", role, values, missing)


def _numeric_role(name: str, col: TypedColumn) -> str:
    valid = col.valid
    n = len(valid)
    if n == 0:
        return "other"
    if _ID_NAME_RE.search(name) and col.is_integer:
        return "identifier"
    # Unique integers counting up from 0 or 1 (0, 1, 2 … / 1, 2, 3 …) behave like row
    # numbers - unless the name says it is a quantity (e.g. "units", "sales").
    if col.is_integer and n >= 10 and valid.nunique() == n and valid.iloc[0] in (0, 1) and not _QUANTITY_NAME_RE.search(name):
        diffs = np.diff(valid.to_numpy())
        if len(diffs) and np.all(diffs == 1):
            return "identifier"
    return "measure"


def infer_table(frame: pd.DataFrame) -> TypedTable:
    columns = [infer_column(str(c), frame[c]) for c in frame.columns]
    return TypedTable(columns=columns, n_rows=len(frame))


def now_utc_naive() -> datetime:
    """Current time in UTC without a zone, matching how dates are stored."""
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)
