from datetime import date

from invoice_extractor.rules import extract

ENGLISH = """TAX INVOICE Evergreen Packaging Ltd
VAT: IE6388047V
Ref: EVP-2026-3391
Invoice Date: Oct 02, 2026
Terms: 30 days
Invoice to:
Harbor & Pine Cafés B.V.
VAT: NL812345678B01
Code Description Qty Unit price Total
CUP-12 Paper cups 12 oz (1000) 2 €64.00 €128.00
NAP-2 Napkins 2-ply (2000) 1 €29.90 €29.90
Sub-total €157.90
VAT @ 21% €33.16
TOTAL DUE €191.06
"""

DUTCH = """FACTUUR
Delta Zuivel Groothandel
Melkweg 3, 2801 AB Gouda · BTW-nr NL004567890B01
Factuurnummer: DD-77812
Factuurdatum: 01-10-2026
Harbor & Pine Cafés B.V. Vervaldatum: 31-10-2026
Omschrijving Aantal Prijs Bedrag
Volle melk 1 L 60 1,09 65,40
Slagroom 1 L 12 3,85 46,20
Subtotaal € 111,60
BTW 9% € 10,04
Totaal te betalen € 121,64
"""


def test_english_layout_with_codes_and_payment_terms():
    rec = extract(ENGLISH, "a.pdf")
    assert rec.supplier == "Evergreen Packaging Ltd"
    assert rec.supplier_vat_id == "IE6388047V"          # the buyer's VAT number is ignored
    assert rec.invoice_number == "EVP-2026-3391"
    assert rec.invoice_date == date(2026, 10, 2)
    assert rec.due_date == date(2026, 11, 1)            # 30 days from the invoice date
    assert (rec.net, rec.vat, rec.vat_rate, rec.total) == (157.90, 33.16, 0.21, 191.06)
    assert [li.code for li in rec.lines] == ["CUP-12", "NAP-2"]
    assert rec.lines[0].description == "Paper cups 12 oz (1000)"


def test_dutch_layout_with_mixed_columns():
    rec = extract(DUTCH, "b.pdf")
    assert rec.supplier == "Delta Zuivel Groothandel"   # "2801 AB" is a postcode, not a company suffix
    assert rec.invoice_number == "DD-77812"
    assert rec.invoice_date == date(2026, 10, 1)
    assert rec.due_date == date(2026, 10, 31)
    assert (rec.net, rec.vat, rec.total) == (111.60, 10.04, 121.64)
    assert rec.lines[0].description == "Volle melk 1 L"
    assert rec.lines[0].quantity == 60
