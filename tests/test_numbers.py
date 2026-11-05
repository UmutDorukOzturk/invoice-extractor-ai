from datetime import date

import pytest

from invoice_extractor.numbers import last_amount, parse_amount, parse_date


@pytest.mark.parametrize("text, expected", [
    ("€ 1.234,56", 1234.56), ("EUR 1,234.56", 1234.56), ("1234.56", 1234.56), ("€64.00", 64.0),
    ("12,50", 12.5), ("1.234", 1234.0), ("1,234", 1234.0), ("-12,50", -12.5), ("60", 60.0),
    ("1.234.567,89", 1234567.89), ("abc", None), ("", None),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("03-10-2026", date(2026, 10, 3)), ("16/10/2026", date(2026, 10, 16)), ("03.10.2026", date(2026, 10, 3)),
    ("2026-10-14", date(2026, 10, 14)), ("7 October 2026", date(2026, 10, 7)), ("Oct 02, 2026", date(2026, 10, 2)),
    ("15 oktober 2026", date(2026, 10, 15)), ("10/25/2026", date(2026, 10, 25)),   # month-first only when day-first is impossible
    ("no date here", None),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_last_amount_ignores_vat_numbers_and_text():
    assert last_amount("VAT 21% € 36,92") == 36.92
    assert last_amount("Amount due EUR 416.60") == 416.60
    assert last_amount("VAT: NL812345678B01") is None
    assert last_amount("Please pay within 30 days.") is None
