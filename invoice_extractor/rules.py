"""Rule-based extraction for invoices with a text layer.

Layout-independent: fields are found by their labels (English, Dutch and German synonyms),
whatever column or position they are printed in. Line items are read from the table that
follows a header row such as "Description  Qty  Unit price  Amount".
"""
import re
from datetime import timedelta
from typing import Optional

from . import config
from .model import InvoiceRecord, LineItem
from .numbers import last_amount, parse_amount, parse_date

NUMBER_LABEL = re.compile(
    r"(?i)(?:invoice\s*(?:number|no\.?|nr\.?|#)|bill\s*no\.?|factuurnummer|factuurnr\.?|rechnungsnummer|"
    r"\bref(?:erence)?\.?)\s*[:#]?\s*([A-Z0-9][A-Z0-9\-/_.]*\d[A-Z0-9\-/_]*)")

INVOICE_DATE_LABELS = [r"invoice\s*date", r"date\s*of\s*issue", r"issue\s*date", r"issued\s*on", r"factuurdatum",
                       r"rechnungsdatum", r"datum", r"date"]
DUE_DATE_LABELS = [r"due\s*date", r"payment\s*due", r"pay\s*by", r"due\s*on", r"vervaldatum", r"f[äa]llig\w*",
                   r"zahlbar\s*bis"]
DUE_WORDS = re.compile(r"(?i)(due|pay|verval|fällig|zahlbar)\W*$")
TERMS = re.compile(r"(?i)(?:terms|payment\s*terms|within|binnen|betalingstermijn)\D{0,12}(\d{1,3})\s*(?:days|dagen|tage)")

SUFFIX = r"(?:B\.V\.|BV|N\.V\.|Ltd\.?|Limited|GmbH|Inc\.?|LLC|LLP|plc|S\.A\.|SARL|S\.L\.|ApS)"
COMPANY = re.compile(rf"([A-Z][\w&'.,-]*(?:\s+[\w&'.,-]+){{0,6}}?\s+{SUFFIX})(?=\s|$|[·,])")
GENERIC_WORDS = {"invoice", "tax", "bill", "factuur", "rechnung", "credit", "note", "receipt", "proforma", "to"}
VAT_ID = re.compile(r"\b(NL\d{9}B\d{2}|IE\d{7}[A-Z]{1,2}|DE\d{9}|BE[01]\d{9}|FR[0-9A-Z]{2}\d{9}|GB\d{9}|"
                    r"ATU\d{8}|ES[0-9A-Z]\d{7}[0-9A-Z]|IT\d{11}|DK\d{8}|SE\d{12}|PL\d{10}|TR\d{10})\b")

SUBTOTAL = re.compile(r"(?i)\b(sub-?\s?total|subtotaal|net\s*amount|net\s*total|amount\s*excl|zwischensumme|"
                      r"nettobetrag|total\s*excl)")
TOTAL = re.compile(r"(?i)(\b(total\s*due|amount\s*due|balance\s*due|total\s*incl|totaal\s*te\s*betalen|te\s*betalen|"
                   r"total\s*to\s*pay|grand\s*total|gesamtbetrag|invoice\s*total)|^total\b|^totaal\b)")
VAT_LINE = re.compile(r"(?i)\b(vat|btw|tax|mwst|ust|tva|iva)\b")
NOT_VAT_LINE = re.compile(r"(?i)\b(excl|incl|total|nr|number|reg|id)\b|[A-Z]{2}\d{6,}")
RATE = re.compile(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%")

HEADER = re.compile(r"(?i)\b(description|item|service|omschrijving|product|artikel|bezeichnung)\b.*"
                    r"\b(qty|quantity|hours|aantal|menge|units?|uren)\b")
ITEM = re.compile(r"^(?P<desc>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s+(?:[a-zA-Z]{1,5}\.?\s+)?"
                  r"(?P<price>(?:[€$£]|EUR)?\s?\d[\d.,]*)\s+(?P<amount>(?:[€$£]|EUR)?\s?-?\d[\d.,]*)$")
CODE = re.compile(r"^[A-Z0-9]{2,}(?:-[A-Z0-9]+)+$|^[A-Z]{2,}\d+$")


def extract(text: str, file: str) -> InvoiceRecord:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rec = InvoiceRecord(file=file, method="Rules")
    rec.invoice_number = _invoice_number(lines)
    rec.invoice_date = _labelled_date(lines, INVOICE_DATE_LABELS, skip_due=True)
    rec.due_date = _labelled_date(lines, DUE_DATE_LABELS)
    if rec.due_date is None and rec.invoice_date:
        terms = next((TERMS.search(line) for line in lines if TERMS.search(line)), None)
        if terms:
            rec.due_date = rec.invoice_date + timedelta(days=int(terms.group(1)))
    rec.supplier = _supplier(lines)
    rec.supplier_vat_id = _supplier_vat_id(text)
    rec.currency = _currency(text)
    rec.lines, after_items = _line_items(lines)
    _totals(lines[after_items:], rec)
    return rec


def _invoice_number(lines: list[str]) -> str:
    for line in lines:
        match = NUMBER_LABEL.search(line)
        if match:
            return match.group(1).rstrip(".")
    return ""


def _labelled_date(lines: list[str], labels: list[str], skip_due: bool = False):
    for label in labels:                       # most specific label first
        pattern = re.compile(rf"(?i)\b{label}\b\s*[:.]?\s*(.{{0,40}})")
        for line in lines:
            for match in pattern.finditer(line):
                if skip_due and DUE_WORDS.search(line[: match.start()]):
                    continue
                found = parse_date(match.group(1))
                if found:
                    return found
    return None


def _is_buyer(line: str) -> bool:
    return any(name.lower() in line.lower() for name in config.BUYER_NAMES)


def _supplier(lines: list[str]) -> str:
    for line in lines:
        if _is_buyer(line):
            continue
        match = COMPANY.search(line)
        if match:
            words = match.group(1).split()
            if len(words) >= 2 and words[-2].isdigit():   # "2801 BV" is a Dutch postcode, not a company
                continue
            while words and words[0].lower() in GENERIC_WORDS:
                words.pop(0)
            if len(words) >= 2:
                return " ".join(words)
    for line in lines[:8]:                      # no legal suffix: take the first "name-like" line at the top
        words = [w for w in line.split() if w.lower() not in GENERIC_WORDS]
        if (words and not _is_buyer(line) and ":" not in line and not re.search(r"\d", line)
                and len(" ".join(words)) > 3):
            name = " ".join(words)
            return name.title() if name.isupper() else name
    return ""


def _supplier_vat_id(text: str) -> str:
    return next((v for v in VAT_ID.findall(text) if v not in config.BUYER_VAT_IDS), "")


def _currency(text: str) -> str:
    if "€" in text or re.search(r"\bEUR\b", text):
        return "EUR"
    if "£" in text or re.search(r"\bGBP\b", text):
        return "GBP"
    if "$" in text or re.search(r"\bUSD\b", text):
        return "USD"
    return config.DEFAULT_CURRENCY


def _line_items(lines: list[str]) -> tuple[list[LineItem], int]:
    """Return the line items and the index of the first line after the table."""
    start = next((i for i, line in enumerate(lines) if HEADER.search(line)), None)
    if start is None:
        return [], 0
    has_code = bool(re.search(r"(?i)\bcode\b", lines[start]))
    items: list[LineItem] = []
    i = start + 1
    while i < len(lines):
        line = lines[i]
        match = ITEM.match(line)
        if SUBTOTAL.search(line) or TOTAL.search(line):
            break
        if not match and VAT_LINE.search(line) and last_amount(line) is not None:   # "VAT 21% 102.38"
            break
        if match:
            desc, code = match.group("desc"), ""
            if has_code and " " in desc and CODE.match(desc.split(" ", 1)[0]):
                code, desc = desc.split(" ", 1)
            items.append(LineItem(description=desc, quantity=parse_amount(match.group("qty")),
                                  unit_price=parse_amount(match.group("price")),
                                  amount=parse_amount(match.group("amount")), code=code))
        elif items:                              # a wrapped description continues on the next line
            items[-1].description += " " + line
        i += 1
    return items, i


def _totals(lines: list[str], rec: InvoiceRecord) -> None:
    for line in lines:
        amount = last_amount(line)
        if amount is None:
            continue
        if SUBTOTAL.search(line):
            rec.net = rec.net if rec.net is not None else amount
        elif TOTAL.search(line):
            rec.total = rec.total if rec.total is not None else amount
        elif VAT_LINE.search(line) and not NOT_VAT_LINE.search(line):
            rec.vat = rec.vat if rec.vat is not None else amount
            rate = RATE.search(line)
            if rate and rec.vat_rate is None:
                rec.vat_rate = parse_amount(rate.group(1)) / 100
