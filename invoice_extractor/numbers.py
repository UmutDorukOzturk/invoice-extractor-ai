"""Parse amounts and dates the way they appear on real invoices.

Amounts:  "€ 1.234,56"  "EUR 1,234.56"  "1234.56"  "€64.00"  "-12,50"
Dates:    "03-10-2026"  "16/10/2026"  "2026-10-14"  "7 October 2026"  "Oct 02, 2026"  "15 oktober 2026"
Numeric dates are read day-first (European style) unless the day-first reading is impossible.
"""
import re
from datetime import date
from typing import Optional

MONEY = re.compile(r"^(?:[€$£]|EUR|USD|GBP)?\s?-?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{2})?$|"
                   r"^(?:[€$£]|EUR|USD|GBP)?\s?-?\d+(?:[.,]\d{2})?$", re.IGNORECASE)

MONTHS = {
    # English
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    # Dutch
    "januari": 1, "februari": 2, "maart": 3, "mei": 5, "juni": 6, "juli": 7, "augustus": 8, "oktober": 10,
    # German
    "januar": 1, "februar": 2, "märz": 3, "mai": 5, "dezember": 12,
}
_ABBREV = {name[:3]: num for name, num in MONTHS.items()}
_ABBREV.update({"okt": 10, "mrt": 3, "sept": 9})


def parse_amount(text: str) -> Optional[float]:
    """Return the amount as a float, or None if the text is not an amount."""
    if text is None:
        return None
    s = re.sub(r"(?i)[€$£]|\b(?:EUR|USD|GBP)\b", "", str(text)).strip().replace(" ", " ")
    s = s.replace(" ", "")
    if not re.fullmatch(r"-?[\d.,]+", s) or not re.search(r"\d", s):
        return None
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_dot >= 0 and last_comma >= 0:            # "1.234,56" / "1,234.56": the last one is the decimal mark
        decimal = "." if last_dot > last_comma else ","
    elif last_comma >= 0 or last_dot >= 0:           # one kind only: "12,50" "12.50" decimal; "1,234" "1.234.567" thousands
        sep = "," if last_comma >= 0 else "."
        digits_after = len(s) - s.rfind(sep) - 1
        decimal = None if s.count(sep) > 1 or digits_after == 3 else sep
    else:
        decimal = None
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    elif decimal == ".":
        s = s.replace(",", "")
    else:
        s = s.replace(",", "").replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def is_money(token: str) -> bool:
    return bool(MONEY.match(token.strip()))


def last_amount(line: str) -> Optional[float]:
    """The amount at the end of a line, e.g. 'VAT 21% € 36,92' -> 36.92."""
    # the amount must start a token: the "01" in "NL812345678B01" is not an amount
    match = re.search(r"(?:^|\s)((?:[€$£]|EUR|USD|GBP)?\s?-?\d[\d.,]*)\s*$", line, re.IGNORECASE)
    if not match or not is_money(match.group(1)):
        return None
    return parse_amount(match.group(1))


DATE_PATTERNS = [
    r"\d{4}-\d{1,2}-\d{1,2}",                                  # 2026-10-14
    r"\d{1,2}[-./]\d{1,2}[-./]\d{4}",                          # 03-10-2026, 16/10/2026, 03.10.2026
    r"\d{1,2}\.?\s+[A-Za-zäé]{3,10}\.?\s+\d{4}",               # 7 October 2026, 15 okt. 2026
    r"[A-Za-z]{3,10}\.?\s+\d{1,2},?\s+\d{4}",                  # Oct 02, 2026
]
DATE_RE = re.compile("|".join(f"(?:{p})" for p in DATE_PATTERNS))


def _month(name: str) -> Optional[int]:
    key = name.lower().rstrip(".")
    return MONTHS.get(key) or _ABBREV.get(key[:4]) or _ABBREV.get(key[:3])


def parse_date(text: str) -> Optional[date]:
    """Parse the first date found in the text."""
    match = DATE_RE.search(text or "")
    if not match:
        return None
    s = match.group(0)
    try:
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", s):
            y, m, d = map(int, s.split("-"))
            return date(y, m, d)
        if re.fullmatch(r"\d{1,2}[-./]\d{1,2}[-./]\d{4}", s):
            a, b, y = map(int, re.split(r"[-./]", s))
            day, month = (a, b) if b <= 12 else (b, a)      # day-first unless impossible
            return date(y, month, day)
        parts = re.findall(r"[A-Za-zäé]+|\d+", s)
        if parts[0].isdigit():                               # 7 October 2026
            day, month, year = int(parts[0]), _month(parts[1]), int(parts[2])
        else:                                                # Oct 02, 2026
            month, day, year = _month(parts[0]), int(parts[1]), int(parts[2])
        return date(year, month, day) if month else None
    except ValueError:
        return None
