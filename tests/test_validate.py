from collections import Counter
from datetime import date
from pathlib import Path

from invoice_extractor import rules, validate
from invoice_extractor.model import InvoiceRecord, LineItem
from invoice_extractor.pdf_text import has_text_layer, read_text


def good_invoice(**changes) -> InvoiceRecord:
    rec = InvoiceRecord(file="x.pdf", supplier="Atlas", supplier_vat_id="NL001234567B01", invoice_number="A-1",
                        invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 31), net=100.0, vat_rate=0.21,
                        vat=21.0, total=121.0, method="Rules",
                        lines=[LineItem("Paper", 4, 20.0, 80.0), LineItem("Pens", 2, 10.0, 20.0)])
    for key, value in changes.items():
        setattr(rec, key, value)
    return rec


def test_clean_invoice_has_no_issues():
    rec = good_invoice()
    validate.check(rec)
    validate.set_status(rec)
    assert rec.issues == [] and rec.status == "OK"


def test_wrong_line_total_and_wrong_vat_are_reported():
    rec = good_invoice(lines=[LineItem("Paper", 4, 20.0, 82.0), LineItem("Pens", 2, 10.0, 20.0)], vat=27.0,
                       total=127.0)
    validate.check(rec)
    assert any("Line 1: 4 × 20.00 = 80.00" in issue for issue in rec.issues)
    assert any("Line items add up to 102.00" in issue for issue in rec.issues)
    assert any("VAT 21% of 100.00 is 21.00" in issue for issue in rec.issues)


def test_second_copy_is_a_duplicate():
    first, second = good_invoice(file="a.pdf"), good_invoice(file="a-reminder.pdf")
    validate.mark_duplicates([first, second])
    validate.set_status(first)
    validate.set_status(second)
    assert (first.status, second.status) == ("OK", "Duplicate")
    assert second.duplicate_of == "a.pdf"


def test_scan_without_ai_is_unreadable():
    rec = InvoiceRecord(file="scan.pdf", has_text=False)
    validate.check(rec)
    validate.set_status(rec)
    assert rec.status == "Unreadable"


def test_sample_folder_end_to_end():
    folder = Path(__file__).resolve().parents[1] / "sample_invoices"
    records = []
    for pdf in sorted(folder.glob("*.pdf"), key=lambda p: p.name.lower()):
        text = read_text(pdf)
        records.append(rules.extract(text, pdf.name) if has_text_layer(text)
                       else InvoiceRecord(file=pdf.name, has_text=False))
    for rec in records:
        validate.check(rec)
    validate.mark_duplicates(records)
    for rec in records:
        validate.set_status(rec)
    assert Counter(r.status for r in records) == {"OK": 16, "Check": 2, "Duplicate": 1, "Unreadable": 2}
