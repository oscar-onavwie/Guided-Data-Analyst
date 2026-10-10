import math

import pandas as pd
import pytest

from app.inference import infer_column, parse_number


@pytest.mark.parametrize(
    "text,expected",
    [
        ("12", 12.0),
        ("-3.5", -3.5),
        ("£1,234.50", 1234.5),
        ("-£20", -20.0),
        ("£-20", -20.0),
        ("(150)", -150.0),
        ("45%", 45.0),
        ("1e3", 1000.0),
        (" 7 ", 7.0),
        ("1,23", None),  # not a valid thousands pattern
        ("abc", None),
        ("inf", None),
        ("12-04", None),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def col(values):
    return pd.Series(values, dtype=object)


def test_numeric_with_invalid_values_counted_not_zeroed():
    values = [str(i) for i in range(1, 40)] + ["oops", None]
    c = infer_column("amount", col(values))
    assert c.kind == "numeric"
    assert c.invalid_count == 1 and c.invalid_examples == ["oops"]
    assert c.missing_count == 1
    assert len(c.valid) == 39
    assert math.isnan(c.values.iloc[-2])  # 'oops' is excluded, not 0
    assert c.valid.sum() == sum(range(1, 40))


def test_negative_numbers_kept():
    c = infer_column("balance", col(["-5", "10", "(3)", "2"]))
    assert c.kind == "numeric"
    assert c.valid.tolist() == [-5.0, 10.0, -3.0, 2.0]


def test_iso_dates():
    c = infer_column("date", col(["2025-01-01", "2025-01-15", "2025-02-01"]))
    assert c.kind == "datetime" and c.role == "date"
    assert c.values.iloc[1] == pd.Timestamp("2025-01-15")


def test_uk_day_first_dates_and_ambiguity_flag():
    c = infer_column("d", col(["03/04/2025", "05/06/2025", "07/08/2025"]))
    assert c.kind == "datetime"
    assert c.values.iloc[0] == pd.Timestamp("2025-04-03")  # 3 April, not 4 March
    assert c.ambiguous_day_month is True


def test_unambiguous_day_first_dates():
    c = infer_column("d", col(["25/12/2025", "26/12/2025", "03/01/2026"]))
    assert c.values.iloc[2] == pd.Timestamp("2026-01-03")
    assert c.ambiguous_day_month is False


def test_invalid_dates_counted():
    values = [f"2025-01-{d:02d}" for d in range(1, 31)] + ["2025-02-30"]
    c = infer_column("d", col(values))
    assert c.kind == "datetime"
    assert c.invalid_count == 1 and c.invalid_examples == ["2025-02-30"]


def test_mostly_invalid_dates_fall_back_to_category():
    c = infer_column("d", col(["2025-01-01", "not a date", "2025-13-45", "tomorrow"]))
    assert c.kind != "datetime"


def test_timezone_offsets_converted_to_utc():
    c = infer_column("ts", col(["2025-06-01T10:00:00+01:00", "2025-06-01T12:00:00+00:00", "2025-06-02T08:30:00Z"]))
    assert c.kind == "datetime"
    assert c.values.iloc[0] == pd.Timestamp("2025-06-01 09:00:00")
    assert any("UTC" in n for n in c.notes)


def test_mixed_date_formats():
    values = [f"2025-01-{d:02d}" for d in range(1, 21)] + ["21/01/2025", "22/01/2025"]
    c = infer_column("d", col(values))
    assert c.kind == "datetime" and c.date_format == "mixed"
    assert c.values.iloc[-1] == pd.Timestamp("2025-01-22")


def test_boolean():
    c = infer_column("active", col(["Yes", "no", "YES", None]))
    assert c.kind == "boolean"
    assert c.values.tolist() == ["True", "False", "True", None]


def test_identifier_detection():
    assert infer_column("customer_id", col([str(i % 7) for i in range(50)])).role == "identifier"
    assert infer_column("row", col([str(i) for i in range(1, 30)])).role == "identifier"  # 1,2,3… sequence
    assert infer_column("order_ref", col([f"ORD-{i}" for i in range(40)])).role == "identifier"
    assert infer_column("price", col([str(i * 1.5) for i in range(40)])).role == "measure"


def test_text_vs_categorical():
    assert infer_column("comment", col([f"note number {i}" for i in range(40)])).kind == "text"
    assert infer_column("region", col(["N", "S", "E", "W"] * 10)).kind == "categorical"


def test_empty_column():
    c = infer_column("blank", col([None, None]))
    assert c.kind == "empty" and c.missing_count == 2
