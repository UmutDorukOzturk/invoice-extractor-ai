"""Checks that catch extraction errors and supplier mistakes before anything is paid."""
import re

from .model import InvoiceRecord

CENT = 0.011
VAT_TOLERANCE = 0.021   # suppliers sometimes round VAT per line: allow 2 cents


def _money(v: float) -> str:
    return f"{v:,.2f}"


def check(rec: InvoiceRecord) -> None:
    """Fill rec.issues with everything that does not add up."""
    if not rec.has_text and rec.method != "AI":
        rec.issues.append("Scanned image with no text layer: run with --ai to read it, or enter it by hand")
        return
    missing = rec.missing()
    if missing:
        rec.issues.append("Could not find: " + ", ".join(missing))

    for i, line in enumerate(rec.lines, start=1):
        expected = round(line.quantity * line.unit_price, 2)
        if abs(expected - line.amount) > CENT:
            rec.issues.append(f"Line {i}: {line.quantity:g} × {_money(line.unit_price)} = {_money(expected)}, "
                              f"but the invoice says {_money(line.amount)}")
    if rec.lines and rec.net is not None:
        lines_sum = round(sum(line.amount for line in rec.lines), 2)
        if abs(lines_sum - rec.net) > CENT:
            rec.issues.append(f"Line items add up to {_money(lines_sum)}, but the subtotal says {_money(rec.net)}")
    if None not in (rec.net, rec.vat, rec.vat_rate):
        expected = round(rec.net * rec.vat_rate, 2)
        if abs(expected - rec.vat) > VAT_TOLERANCE:
            rec.issues.append(f"VAT {rec.vat_rate:.0%} of {_money(rec.net)} is {_money(expected)}, "
                              f"but the invoice says {_money(rec.vat)}")
    if None not in (rec.net, rec.vat, rec.total) and abs(rec.net + rec.vat - rec.total) > CENT:
        rec.issues.append(f"Subtotal + VAT = {_money(rec.net + rec.vat)}, but the total says {_money(rec.total)}")
    if rec.invoice_date and rec.due_date and rec.due_date < rec.invoice_date:
        rec.issues.append("Due date is before the invoice date")


def _key(rec: InvoiceRecord) -> tuple[str, str]:
    supplier = rec.supplier_vat_id or re.sub(r"\W", "", rec.supplier.lower())
    return supplier, re.sub(r"\W", "", rec.invoice_number.lower())


def mark_duplicates(records: list[InvoiceRecord]) -> None:
    """The second copy of the same supplier + invoice number is a duplicate (e.g. a re-sent reminder)."""
    seen: dict[tuple[str, str], InvoiceRecord] = {}
    for rec in records:
        if not rec.invoice_number:
            continue
        key = _key(rec)
        if key in seen:
            rec.duplicate_of = seen[key].file
            rec.issues.insert(0, f"Duplicate of {seen[key].file}: same supplier and invoice number. Pay only once")
        else:
            seen[key] = rec


def set_status(rec: InvoiceRecord) -> None:
    if rec.duplicate_of:
        rec.status = "Duplicate"
    elif not rec.has_text and rec.method != "AI":
        rec.status = "Unreadable"
    elif rec.issues:
        rec.status = "Check"
    else:
        rec.status = "OK"
