"""Dataset profile and data-quality assessment.

Issues are split into two groups so users can tell fact from suspicion:

* confirmed – objectively true of the file (a value is missing, a row is an
  exact duplicate, a value is not a valid number for a numeric column).
* potential – worth investigating but possibly legitimate (an unusually large
  value, a negative amount that might be a refund, two spellings of a label).

Nothing is changed in the data because of an issue. Duplicates are counted,
not removed; outliers are flagged, not excluded.
"""

from __future__ import annotations

import pandas as pd

from .analysis import category_frequency, date_range, numeric_summary, pct
from .inference import TypedColumn, TypedTable
from .parsing import ParsedTable
from .schemas import ColumnProfile, DataIssue, DatasetProfile

PLACEHOLDER_LABELS = {"unknown", "tbc", "tbd", "?", "not known", "not applicable", "missing", "blank", "xxx"}
SENTINEL_NUMBERS = {-1.0, -9.0, -99.0, -999.0, 99.0, 999.0, 9999.0, 99999.0}


def duplicate_rows(frame: pd.DataFrame) -> int:
    """Rows identical in every column to an earlier row (the first copy is not counted)."""
    if frame.empty:
        return 0
    return int(frame.fillna("\u0000<missing>").duplicated(keep="first").sum())


def _sample_values(col: TypedColumn) -> list[str]:
    values = col.values.dropna()
    if col.kind == "datetime":
        return [v.date().isoformat() if v == v.normalize() else v.isoformat() for v in values.head(3)]
    if col.kind == "numeric":
        return [f"{v:g}" for v in values.head(3)]
    return [str(v)[:60] for v in values.drop_duplicates().head(3)]


def column_profile(col: TypedColumn, n_rows: int) -> ColumnProfile:
    present = col.values.dropna()
    unique = int(present.nunique())
    non_missing = n_rows - col.missing_count
    profile = ColumnProfile(
        name=col.name,
        inferred_type=col.kind,
        role=col.role,
        non_missing=non_missing,
        missing=col.missing_count,
        missing_pct=pct(col.missing_count, n_rows),
        invalid=col.invalid_count,
        invalid_examples=col.invalid_examples,
        unique=unique,
        unique_pct=pct(unique, len(present)),
        is_constant=bool(non_missing > 0 and unique == 1 and col.invalid_count == 0),
        likely_identifier=col.role == "identifier",
        candidate_date=col.kind == "datetime",
        notes=list(col.notes),
        sample_values=_sample_values(col),
    )
    if col.kind == "numeric" and len(present):
        profile.numeric = numeric_summary(col.values)
    if col.kind in {"categorical", "boolean", "text"} and len(present):
        profile.top_categories = category_frequency(col, top=10 if col.kind != "text" else 5).rows
    if col.kind == "datetime" and len(present):
        profile.date_range = date_range(col)
    return profile


def _variant_groups(col: TypedColumn) -> list[list[str]]:
    """Labels that differ only by case or internal spacing, e.g. 'North' / 'north'."""
    values = col.values.dropna().astype(str).unique()
    groups: dict[str, set[str]] = {}
    for v in values:
        key = " ".join(v.lower().split())
        groups.setdefault(key, set()).add(v)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def build_issues(table: TypedTable, profiles: list[ColumnProfile], dup_rows: int, parsed: ParsedTable) -> list[DataIssue]:
    issues: list[DataIssue] = []

    def add(severity: str, category: str, message: str, column: str | None = None, count: int | None = None) -> None:
        issues.append(
            DataIssue(id=f"Q{len(issues) + 1}", severity=severity, category=category, column=column, message=message, count=count)
        )

    n = table.n_rows
    if dup_rows:
        add(
            "confirmed",
            "duplicates",
            f"{dup_rows} row(s) ({pct(dup_rows, n)}%) are exact duplicates of an earlier row. "
            "They have NOT been removed; check whether they are genuine repeat records or double entries.",
            count=dup_rows,
        )
    for rename in parsed.renamed_headers:
        original = rename["original"] or "(blank)"
        add("confirmed", "structure", f"Header '{original}' was renamed to '{rename['new']}' (blank or duplicate name).")

    for col, prof in zip(table.columns, profiles, strict=True):
        if col.kind == "empty":
            add("confirmed", "missing", f"'{col.name}' contains no values at all.", col.name, n)
            continue
        if col.missing_count:
            add(
                "confirmed",
                "missing",
                f"'{col.name}' has {col.missing_count} missing value(s) ({prof.missing_pct}%). "
                "Missing values are excluded from calculations, not treated as zero.",
                col.name,
                col.missing_count,
            )
        if col.invalid_count:
            examples = ", ".join(f"'{e}'" for e in col.invalid_examples)
            kind = "numbers" if col.kind == "numeric" else "valid dates"
            add(
                "confirmed",
                "invalid_values",
                f"{col.invalid_count} value(s) in '{col.name}' are not {kind} (e.g. {examples}) and were excluded from calculations.",
                col.name,
                col.invalid_count,
            )
        if prof.is_constant and n > 1:
            add(
                "confirmed",
                "constant",
                f"'{col.name}' has the same value in every row, so it adds no analytical information.",
                col.name,
            )

        # ---- potential issues -------------------------------------------------
        if col.kind == "numeric" and prof.numeric and col.role == "measure":
            s = prof.numeric
            if s.outliers.count:
                fences = f"{s.outliers.lower_fence:g} to {s.outliers.upper_fence:g}"
                if s.outliers.pct > 10:
                    message = (
                        f"'{col.name}' has {s.outliers.count} value(s) ({s.outliers.pct}%) outside {fences} (1.5×IQR rule). "
                        "So many values usually means the column mixes groups on different scales or is heavily skewed, "
                        "rather than individual errors."
                    )
                else:
                    message = (
                        f"'{col.name}' has {s.outliers.count} value(s) outside the typical range ({fences}, 1.5×IQR rule). "
                        "They may be genuine — investigate before excluding them."
                    )
                add("potential", "outliers", message, col.name, s.outliers.count)
            if 0 < s.negatives <= 0.1 * s.count:
                add(
                    "potential",
                    "negative_values",
                    f"'{col.name}' is mostly positive but has {s.negatives} negative value(s). "
                    "These could be refunds/adjustments or data-entry errors.",
                    col.name,
                    s.negatives,
                )
            valid = col.valid
            for sentinel in SENTINEL_NUMBERS:
                hits = int((valid == sentinel).sum())
                if hits >= 2 and sentinel in (valid.max(), valid.min()):
                    add(
                        "potential",
                        "placeholder_values",
                        f"'{col.name}' contains the value {sentinel:g} {hits} times at the edge of its range; "
                        "this is sometimes used as a code for 'unknown'.",
                        col.name,
                        hits,
                    )
        if col.kind == "datetime" and prof.date_range:
            if prof.date_range.future_count:
                add(
                    "potential",
                    "future_dates",
                    f"'{col.name}' has {prof.date_range.future_count} date(s) in the future.",
                    col.name,
                    prof.date_range.future_count,
                )
            if prof.date_range.pre_1900_count:
                add(
                    "potential",
                    "implausible_dates",
                    f"'{col.name}' has {prof.date_range.pre_1900_count} date(s) before 1900.",
                    col.name,
                    prof.date_range.pre_1900_count,
                )
            if col.ambiguous_day_month:
                add("potential", "ambiguous_dates", col.notes[0] if col.notes else "Day/month order is ambiguous.", col.name)
            if col.date_format == "mixed":
                add("potential", "mixed_formats", f"'{col.name}' mixes several date formats.", col.name)
        if col.kind in {"categorical", "boolean"}:
            for group in _variant_groups(col)[:5]:
                add(
                    "potential",
                    "inconsistent_labels",
                    f"'{col.name}' has labels that differ only by capitalisation or spacing: "
                    + ", ".join(f"'{g}'" for g in group)
                    + ". They are currently counted as separate categories.",
                    col.name,
                )
            placeholders = col.values.dropna().astype(str)
            hits = int(placeholders.str.strip().str.lower().isin(PLACEHOLDER_LABELS).sum())
            if hits:
                add(
                    "potential",
                    "placeholder_values",
                    f"'{col.name}' has {hits} value(s) such as 'Unknown' or 'TBC' that may really mean missing.",
                    col.name,
                    hits,
                )
        if col.name in parsed.trimmed_cells:
            add(
                "potential",
                "whitespace",
                f"{parsed.trimmed_cells[col.name]} value(s) in '{col.name}' had leading/trailing spaces, which were trimmed.",
                col.name,
                parsed.trimmed_cells[col.name],
            )
    # Confirmed first, then potential; stable within each group
    issues.sort(key=lambda i: 0 if i.severity == "confirmed" else 1)
    for i, issue in enumerate(issues, start=1):
        issue.id = f"Q{i}"
    return issues


def build_profile(table: TypedTable, parsed: ParsedTable) -> DatasetProfile:
    profiles = [column_profile(c, table.n_rows) for c in table.columns]
    dups = duplicate_rows(parsed.frame)
    missing_cells = sum(c.missing_count for c in table.columns)
    total_cells = table.n_rows * len(table.columns)
    type_counts: dict[str, int] = {}
    for c in table.columns:
        type_counts[c.kind] = type_counts.get(c.kind, 0) + 1
    return DatasetProfile(
        rows=table.n_rows,
        columns=len(table.columns),
        duplicate_rows=dups,
        duplicate_pct=pct(dups, table.n_rows),
        missing_cells=missing_cells,
        missing_cells_pct=pct(missing_cells, total_cells),
        type_counts=type_counts,
        column_profiles=profiles,
        issues=build_issues(table, profiles, dups, parsed),
        parse_notes=list(parsed.notes),
    )
