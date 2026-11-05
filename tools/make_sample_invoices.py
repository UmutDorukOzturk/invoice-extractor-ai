"""Generate the fictional sample invoices used by this demo.

21 PDFs from 6 made-up suppliers, each with its own layout, language, date format and
number format - the way invoices really arrive. Three contain problems on purpose:
a re-sent duplicate, a wrong VAT amount and a wrong line total. Two are scans with no
text layer at all.

    python tools/make_sample_invoices.py            # writes to sample_invoices/
"""
import io
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

W, H = A4
OUT = Path(__file__).resolve().parents[1] / "sample_invoices"
BUYER = ["Harbor & Pine Cafés B.V.", "Attn: Accounts Payable", "Oostelijke Handelskade 12",
         "1019 BM Amsterdam", "VAT: NL812345678B01"]


@dataclass
class Invoice:
    file: str
    number: str
    issued: date
    lines: list                      # (description, qty, unit price)
    vat_rate: float
    terms_days: int = 30
    wrong_line: tuple = None         # (index, printed amount)
    wrong_vat: float = None          # printed VAT instead of the correct one
    reminder: bool = False
    amounts: list = field(default_factory=list)

    def __post_init__(self):
        self.amounts = [round(q * p, 2) for _, q, p in self.lines]
        if self.wrong_line:
            self.amounts[self.wrong_line[0]] = self.wrong_line[1]
        self.subtotal = round(sum(self.amounts), 2)
        self.vat = self.wrong_vat if self.wrong_vat is not None else round(self.subtotal * self.vat_rate, 2)
        self.total = round(self.subtotal + self.vat, 2)
        self.due = self.issued + timedelta(days=self.terms_days)


def nl(v: float) -> str:          # 1.234,56
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def en(v: float) -> str:          # 1,234.56
    return f"{v:,.2f}"


def right(c, x, y, text, font="Helvetica", size=9.5):
    c.setFont(font, size)
    c.drawRightString(x, y, text)


def left(c, x, y, text, font="Helvetica", size=9.5):
    c.setFont(font, size)
    c.drawString(x, y, text)


def reminder_stamp(c):
    c.saveState()
    c.setFillColor(HexColor("#c0392b"))
    c.setFont("Helvetica-Bold", 22)
    c.translate(W / 2 + 40, H - 235)
    c.rotate(12)
    c.drawCentredString(0, 0, "PAYMENT REMINDER")
    c.restoreState()


# ------------------------------------------------------------------ layouts

def atlas(c, inv: Invoice):
    blue = HexColor("#1f4e79")
    c.setFillColor(blue)
    c.rect(50, H - 78, 34, 34, fill=1, stroke=0)
    c.setFillColor(white)
    left(c, 59, H - 68, "A", "Helvetica-Bold", 20)
    c.setFillColor(HexColor("#111111"))
    left(c, 94, H - 58, "Atlas Office Supplies B.V.", "Helvetica-Bold", 14)
    for i, t in enumerate(["Industrieweg 41", "3044 AS Rotterdam", "VAT: NL001234567B01"]):
        left(c, 94, H - 72 - i * 11, t, size=8.5)
    right(c, W - 50, H - 62, "INVOICE", "Helvetica-Bold", 24)
    info = [("Invoice number:", inv.number), ("Invoice date:", inv.issued.strftime("%d-%m-%Y")),
            ("Due date:", inv.due.strftime("%d-%m-%Y")), ("Customer no.:", "HP-2291")]
    for i, (k, v) in enumerate(info):
        left(c, W - 230, H - 100 - i * 14, k)
        right(c, W - 50, H - 100 - i * 14, v, "Helvetica-Bold")
    left(c, 50, H - 175, "Bill to", "Helvetica-Bold", 10)
    for i, t in enumerate(BUYER):
        left(c, 50, H - 190 - i * 12, t)
    y = H - 285
    c.setFillColor(blue)
    c.rect(45, y - 6, W - 90, 20, fill=1, stroke=0)
    c.setFillColor(white)
    left(c, 52, y, "Description", "Helvetica-Bold")
    right(c, 330, y, "Qty", "Helvetica-Bold")
    right(c, 430, y, "Unit price", "Helvetica-Bold")
    right(c, W - 52, y, "Amount", "Helvetica-Bold")
    c.setFillColor(HexColor("#111111"))
    for (desc, q, p), amount in zip(inv.lines, inv.amounts):
        y -= 22
        left(c, 52, y, desc)
        right(c, 330, y, str(q))
        right(c, 430, y, nl(p))
        right(c, W - 52, y, nl(amount))
        c.setStrokeColor(HexColor("#d9d9d9"))
        c.line(45, y - 7, W - 45, y - 7)
    y -= 34
    for label, value, bold in (("Subtotal", inv.subtotal, False), (f"VAT {inv.vat_rate:.0%}", inv.vat, False),
                               ("Total", inv.total, True)):
        font = "Helvetica-Bold" if bold else "Helvetica"
        left(c, W - 230, y, label, font, 10.5 if bold else 9.5)
        right(c, W - 52, y, f"€ {nl(value)}", font, 10.5 if bold else 9.5)
        y -= 16
    c.setFillColor(HexColor("#555555"))
    left(c, 50, 60, "Please pay within 30 days to IBAN NL00 DEMO 0123 4567 89, stating the invoice number.", size=8)
    left(c, 50, 48, "Atlas Office Supplies B.V. · KvK 12345678 · info@atlas-office.example", size=8)


def brightline(c, inv: Invoice):
    brown = HexColor("#3b2a20")
    c.setFillColor(brown)
    c.rect(0, H - 100, W, 100, fill=1, stroke=0)
    c.setFillColor(white)
    left(c, 50, H - 52, "BRIGHTLINE", "Helvetica-Bold", 22)
    left(c, 50, H - 70, "Coffee Roasters · Specialty coffee since 2011", size=9)
    right(c, W - 50, H - 58, "INVOICE", "Helvetica", 20)
    c.setFillColor(HexColor("#222222"))
    left(c, 50, H - 140, f"Invoice #{inv.number}", "Helvetica-Bold", 15)
    left(c, 50, H - 160, f"Date: {inv.issued.day} {inv.issued:%B %Y}")
    left(c, 50, H - 174, f"Payment due: {inv.due.day} {inv.due:%B %Y}")
    left(c, 50, H - 210, "Brightline Coffee Roasters B.V. · Kanaalweg 8, 3526 KL Utrecht · VAT NL002345678B01", size=8)
    left(c, 360, H - 140, "Bill To", "Helvetica-Bold", 10)
    for i, t in enumerate(BUYER[:1] + BUYER[2:]):
        left(c, 360, H - 155 - i * 12, t, size=9)
    y = H - 260
    c.setStrokeColor(brown)
    c.setLineWidth(1.2)
    c.line(50, y - 6, W - 50, y - 6)
    left(c, 50, y, "Item", "Helvetica-Bold")
    right(c, 340, y, "Quantity", "Helvetica-Bold")
    right(c, 440, y, "Price", "Helvetica-Bold")
    right(c, W - 50, y, "Line total", "Helvetica-Bold")
    c.setLineWidth(0.5)
    for (desc, q, p), amount in zip(inv.lines, inv.amounts):
        y -= 21
        left(c, 50, y, desc)
        right(c, 340, y, str(q))
        right(c, 440, y, en(p))
        right(c, W - 50, y, en(amount))
    y -= 40
    c.setFillColor(HexColor("#f4ede6"))
    c.rect(W - 260, y - 42, 210, 66, fill=1, stroke=0)
    c.setFillColor(HexColor("#222222"))
    for label, value, bold in (("Net amount", inv.subtotal, False), (f"VAT ({inv.vat_rate:.0%})", inv.vat, False),
                               ("Amount due", inv.total, True)):
        font = "Helvetica-Bold" if bold else "Helvetica"
        left(c, W - 250, y, label, font)
        right(c, W - 60, y, f"EUR {en(value)}", font)
        y -= 18
    left(c, 50, 70, "Thank you for brewing with us! Bank: NL00 DEMO 0234 5678 90 · BIC DEMONL2A", size=8.5)


def cedar(c, inv: Invoice):
    left(c, 50, H - 60, "CEDAR CLEANING SERVICES", "Courier-Bold", 16)
    left(c, 50, H - 76, "Commercial cleaning · Amsterdam · VAT NL003456789B01", "Courier", 9)
    c.line(50, H - 86, W - 50, H - 86)
    left(c, 50, H - 115, "BILL", "Courier-Bold", 20)
    for i, (k, v) in enumerate((("Bill No.:", inv.number), ("Issued on:", inv.issued.isoformat()),
                                ("Pay by:", inv.due.isoformat()))):
        left(c, 50, H - 140 - i * 13, f"{k:<11}{v}", "Courier", 10)
    left(c, 330, H - 115, "Client:", "Courier-Bold", 10)
    for i, t in enumerate(BUYER[:1] + BUYER[2:4]):
        left(c, 330, H - 130 - i * 12, t, "Courier", 9.5)
    y = H - 230
    left(c, 50, y, "Service", "Courier-Bold", 10)
    right(c, 360, y, "Hours", "Courier-Bold", 10)
    right(c, 450, y, "Rate", "Courier-Bold", 10)
    right(c, W - 50, y, "Total", "Courier-Bold", 10)
    c.line(50, y - 5, W - 50, y - 5)
    for (desc, q, p), amount in zip(inv.lines, inv.amounts):
        y -= 18
        left(c, 50, y, desc, "Courier", 9.5)
        right(c, 360, y, str(q), "Courier", 9.5)
        right(c, 450, y, f"{p:.2f}", "Courier", 9.5)
        right(c, W - 50, y, f"{amount:.2f}", "Courier", 9.5)
    c.line(50, y - 8, W - 50, y - 8)
    y -= 30
    for label, value in (("Total excl. VAT", inv.subtotal), (f"VAT {inv.vat_rate:.0%}", inv.vat),
                         ("Total incl. VAT", inv.total)):
        left(c, 300, y, label, "Courier-Bold" if "incl" in label else "Courier", 10)
        right(c, W - 50, y, f"{value:.2f}", "Courier-Bold" if "incl" in label else "Courier", 10)
        y -= 15
    left(c, 50, 70, "Amounts in EUR. Transfer to NL00 DEMO 0345 6789 01.", "Courier", 9)


def delta(c, inv: Invoice):
    green = HexColor("#2e7d32")
    c.setFillColor(green)
    c.rect(50, H - 82, 6, 40, fill=1, stroke=0)
    c.setFillColor(HexColor("#1b1b1b"))
    left(c, 66, H - 58, "Delta Zuivel Groothandel", "Helvetica-Bold", 15)
    left(c, 66, H - 74, "Melkweg 3, 2801 AB Gouda · BTW-nr NL004567890B01", size=8.5)
    right(c, W - 50, H - 60, "FACTUUR", "Helvetica-Bold", 22)
    info = [("Factuurnummer:", inv.number), ("Factuurdatum:", inv.issued.strftime("%d-%m-%Y")),
            ("Vervaldatum:", inv.due.strftime("%d-%m-%Y")), ("Klantnummer:", "40112")]
    for i, (k, v) in enumerate(info):
        left(c, W - 240, H - 100 - i * 14, k)
        right(c, W - 50, H - 100 - i * 14, v, "Helvetica-Bold")
    left(c, 66, H - 110, "Factuuradres", "Helvetica-Bold", 10)
    for i, t in enumerate(BUYER[:1] + BUYER[2:4]):
        left(c, 66, H - 125 - i * 12, t)
    y = H - 240
    c.setFillColor(HexColor("#e8f5e9"))
    c.rect(50, y - 6, W - 100, 20, fill=1, stroke=0)
    c.setFillColor(HexColor("#1b1b1b"))
    left(c, 56, y, "Omschrijving", "Helvetica-Bold")
    right(c, 340, y, "Aantal", "Helvetica-Bold")
    right(c, 440, y, "Prijs", "Helvetica-Bold")
    right(c, W - 56, y, "Bedrag", "Helvetica-Bold")
    for (desc, q, p), amount in zip(inv.lines, inv.amounts):
        y -= 21
        left(c, 56, y, desc)
        right(c, 340, y, str(q))
        right(c, 440, y, nl(p))
        right(c, W - 56, y, nl(amount))
    y -= 36
    for label, value, bold in (("Subtotaal", inv.subtotal, False), (f"BTW {inv.vat_rate:.0%}", inv.vat, False),
                               ("Totaal te betalen", inv.total, True)):
        font = "Helvetica-Bold" if bold else "Helvetica"
        left(c, W - 240, y, label, font)
        right(c, W - 56, y, f"€ {nl(value)}", font)
        y -= 16
    left(c, 56, 64, "Betaling binnen 30 dagen op NL00 DEMO 0456 7890 12 o.v.v. het factuurnummer.", size=8.5)


def evergreen(c, inv: Invoice):
    left(c, 50, H - 64, "TAX INVOICE", "Helvetica-Bold", 22)
    c.setFillColor(HexColor("#1e6b52"))
    right(c, W - 50, H - 56, "Evergreen Packaging Ltd", "Helvetica-Bold", 13)
    c.setFillColor(HexColor("#333333"))
    for i, t in enumerate(["Unit 7, Harbour Park, Dublin D02 X285", "VAT: IE6388047V"]):
        right(c, W - 50, H - 70 - i * 11, t, size=8.5)
    for i, (k, v) in enumerate((("Ref:", inv.number), ("Invoice Date:", inv.issued.strftime("%b %d, %Y")),
                                ("Terms:", f"{inv.terms_days} days"))):
        left(c, 50, H - 100 - i * 14, k, "Helvetica-Bold")
        left(c, 130, H - 100 - i * 14, v)
    left(c, 50, H - 160, "Invoice to:", "Helvetica-Bold")
    for i, t in enumerate(BUYER[:1] + BUYER[2:]):
        left(c, 50, H - 174 - i * 12, t)
    y = H - 265
    c.setStrokeColor(HexColor("#1e6b52"))
    c.rect(48, y - 7, W - 96, 21, fill=0, stroke=1)
    left(c, 54, y, "Code", "Helvetica-Bold")
    left(c, 110, y, "Description", "Helvetica-Bold")
    right(c, 380, y, "Qty", "Helvetica-Bold")
    right(c, 460, y, "Unit price", "Helvetica-Bold")
    right(c, W - 54, y, "Total", "Helvetica-Bold")
    for (desc, q, p), amount in zip(inv.lines, inv.amounts):
        code, text = desc.split(" ", 1)
        y -= 21
        left(c, 54, y, code)
        left(c, 110, y, text)
        right(c, 380, y, str(q))
        right(c, 460, y, f"€{en(p)}")
        right(c, W - 54, y, f"€{en(amount)}")
    y -= 38
    for label, value, bold in (("Sub-total", inv.subtotal, False), (f"VAT @ {inv.vat_rate:.0%}", inv.vat, False),
                               ("TOTAL DUE", inv.total, True)):
        font = "Helvetica-Bold" if bold else "Helvetica"
        left(c, W - 220, y, label, font)
        right(c, W - 54, y, f"€{en(value)}", font)
        y -= 16
    left(c, 50, 64, "Payment by bank transfer to IE00 DEMO 9012 3456 7890 12. Thank you for your business.", size=8.5)


def fresh_fields(c, inv: Invoice):
    left(c, 60, H - 70, "Fresh Fields Produce", "Times-Bold", 20)
    left(c, 60, H - 88, "Market stall 14, Binnenrotte, Rotterdam  ·  VAT NL005678901B01", "Times-Roman", 10)
    left(c, 60, H - 130, f"Invoice {inv.number}", "Times-Bold", 13)
    left(c, 60, H - 147, f"Date {inv.issued:%d/%m/%Y}", "Times-Roman", 11)
    left(c, 60, H - 175, "To: Harbor & Pine Cafés B.V., Amsterdam", "Times-Roman", 11)
    y = H - 215
    for (desc, q, p), amount in zip(inv.lines, inv.amounts):
        left(c, 70, y, f"{q} x {desc}", "Times-Roman", 11.5)
        left(c, 330, y, f"@ {nl(p)}", "Times-Roman", 11.5)
        right(c, 500, y, nl(amount), "Times-Roman", 11.5)
        y -= 19
    c.line(330, y + 8, 500, y + 8)
    y -= 10
    left(c, 250, y, "Net", "Times-Roman", 11.5)
    right(c, 500, y, nl(inv.subtotal), "Times-Roman", 11.5)
    left(c, 250, y - 18, f"VAT {inv.vat_rate:.0%}", "Times-Roman", 11.5)
    right(c, 500, y - 18, nl(inv.vat), "Times-Roman", 11.5)
    left(c, 250, y - 40, "Total to pay EUR", "Times-Bold", 12.5)
    right(c, 500, y - 40, nl(inv.total), "Times-Bold", 12.5)
    left(c, 60, y - 90, "Paid in cash?  [ ]     Bank: NL00 DEMO 0567 8901 23", "Times-Italic", 10.5)


# ------------------------------------------------------------------ invoices

D = date
SUPPLIERS = {
    atlas: [
        Invoice("AOS-26-0412.pdf", "AOS-26-0412", D(2026, 10, 3), [
            ("A4 copy paper 80 g, box of 5 reams", 4, 21.50), ("Ballpoint pens, blue (50 pcs)", 2, 12.90),
            ("Toner cartridge, black", 1, 64.00)], 0.21),
        Invoice("AOS-26-0419.pdf", "AOS-26-0419", D(2026, 10, 9), [
            ("Receipt rolls 57 mm (50 pcs)", 3, 18.75), ("Cleaning cloths microfibre (10)", 2, 9.95)], 0.21),
        Invoice("AOS-26-0431.pdf", "AOS-26-0431", D(2026, 10, 16), [
            ("Label printer tape 12 mm", 6, 14.20), ("Stapler, heavy duty", 1, 27.50),
            ("Archive boxes A4 (10 pcs)", 2, 16.40), ("Whiteboard markers (8 colours)", 2, 8.95)], 0.21),
        Invoice("Atlas reminder AOS-26-0431.pdf", "AOS-26-0431", D(2026, 10, 16), [
            ("Label printer tape 12 mm", 6, 14.20), ("Stapler, heavy duty", 1, 27.50),
            ("Archive boxes A4 (10 pcs)", 2, 16.40), ("Whiteboard markers (8 colours)", 2, 8.95)], 0.21,
            reminder=True),
        Invoice("AOS-26-0447.pdf", "AOS-26-0447", D(2026, 10, 27), [
            ("A4 copy paper 80 g, box of 5 reams", 2, 21.50), ("Printer, colour laser", 1, 289.00)], 0.21),
    ],
    brightline: [
        Invoice("Invoice_BCR-10293.pdf", "BCR-10293", D(2026, 10, 7), [
            ("Espresso blend Harbor, 1 kg", 12, 18.40), ("Decaf Colombia, 1 kg", 3, 21.00),
            ("Filter roast Kenya AA, 1 kg", 4, 24.60)], 0.09),
        Invoice("Invoice_BCR-10307.pdf", "BCR-10307", D(2026, 10, 13), [
            ("Espresso blend Harbor, 1 kg", 10, 18.40), ("Chai concentrate, 1 L", 6, 9.80)], 0.09),
        Invoice("Invoice_BCR-10322.pdf", "BCR-10322", D(2026, 10, 20), [
            ("Espresso blend Harbor, 1 kg", 14, 18.40), ("Decaf Colombia, 1 kg", 2, 21.00)], 0.09,
            wrong_vat=27.86),  # correct VAT is 26.96: digits mistyped by the supplier
        Invoice("Invoice_BCR-10338.pdf", "BCR-10338", D(2026, 10, 27), [
            ("Espresso blend Harbor, 1 kg", 12, 18.40), ("Filter roast Kenya AA, 1 kg", 5, 24.60),
            ("Cold brew bags (20 pcs)", 4, 15.50)], 0.09),
    ],
    cedar: [
        Invoice("CCS_2026_118.pdf", "CCS/2026/118", D(2026, 10, 7), [
            ("Weekly cleaning - Prinsengracht", 12, 32.50), ("Window cleaning", 3, 32.50)], 0.21, terms_days=14),
        Invoice("CCS_2026_124.pdf", "CCS/2026/124", D(2026, 10, 14), [
            ("Weekly cleaning - Prinsengracht", 12, 32.50), ("Deep clean kitchen", 6, 38.00)], 0.21, terms_days=14),
        Invoice("CCS_2026_131.pdf", "CCS/2026/131", D(2026, 10, 21), [
            ("Weekly cleaning - Prinsengracht", 12, 32.50), ("Weekly cleaning - Oost", 8, 32.50)], 0.21, terms_days=14),
    ],
    delta: [
        Invoice("factuur DD-77812.pdf", "DD-77812", D(2026, 10, 1), [
            ("Volle melk 1 L", 60, 1.09), ("Slagroom 1 L", 12, 3.85), ("Boter ongezouten 250 g", 20, 2.45)], 0.09),
        Invoice("factuur DD-77901.pdf", "DD-77901", D(2026, 10, 8), [
            ("Volle melk 1 L", 72, 1.09), ("Griekse yoghurt 1 kg", 8, 4.20)], 0.09),
        Invoice("factuur DD-77988.pdf", "DD-77988", D(2026, 10, 15), [
            ("Volle melk 1 L", 60, 1.09), ("Slagroom 1 L", 10, 3.85), ("Havermelk barista 1 L", 24, 2.35)], 0.09),
        Invoice("factuur DD-78050.pdf", "DD-78050", D(2026, 10, 22), [
            ("Volle melk 1 L", 66, 1.09), ("Boter ongezouten 250 g", 16, 2.45),
            ("Griekse yoghurt 1 kg", 6, 4.20)], 0.09),
    ],
    evergreen: [
        Invoice("EVP-2026-3391 Harbor Pine.pdf", "EVP-2026-3391", D(2026, 10, 2), [
            ("CUP-12 Paper cups 12 oz (1000)", 2, 64.00), ("LID-90 Lids 90 mm (1000)", 2, 38.50),
            ("NAP-2 Napkins 2-ply (2000)", 1, 29.90)], 0.21),
        Invoice("EVP-2026-3420 Harbor Pine.pdf", "EVP-2026-3420", D(2026, 10, 16), [
            ("CUP-12 Paper cups 12 oz (1000)", 1, 64.00), ("LID-90 Lids 90 mm (1000)", 2, 38.50),
            ("BAG-K Kraft bags medium (500)", 1, 42.75)], 0.21,
            wrong_line=(1, 79.00)),  # 2 x 38.50 is 77.00
        Invoice("EVP-2026-3466 Harbor Pine.pdf", "EVP-2026-3466", D(2026, 10, 30), [
            ("CUP-8 Paper cups 8 oz (1000)", 2, 52.00), ("STR-P Paper straws (500)", 3, 11.60)], 0.21),
    ],
    fresh_fields: [
        Invoice("scan_2026-10-16_0932.pdf", "2026-118", D(2026, 10, 16), [
            ("Avocados (box of 20)", 2, 24.00), ("Lemons 5 kg", 1, 11.50), ("Fresh mint, bunch", 10, 0.95)], 0.09,
            terms_days=7),
        Invoice("scan_2026-10-30_1015.pdf", "2026-131", D(2026, 10, 30), [
            ("Avocados (box of 20)", 1, 24.00), ("Oranges for juice 10 kg", 2, 13.80),
            ("Fresh mint, bunch", 12, 0.95)], 0.09, terms_days=7),
    ],
}


def render(layout, inv: Invoice) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(inv.number)
    layout(c, inv)
    if inv.reminder:
        reminder_stamp(c)
    c.save()
    return buf.getvalue()


def as_scan(pdf_bytes: bytes, angle: float) -> bytes:
    """Rasterise a page like a cheap office scanner: grey, slightly rotated, a little blurry, no text layer."""
    page = pymupdf.open(stream=pdf_bytes, filetype="pdf")[0]
    pix = page.get_pixmap(dpi=110, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=246)
    img = img.filter(ImageFilter.GaussianBlur(0.6)).point(lambda v: min(255, int(v * 0.97) + 4))
    out = io.BytesIO()
    img.save(out, "PDF", resolution=110)
    return out.getvalue()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    count = 0
    for layout, invoices in SUPPLIERS.items():
        for i, inv in enumerate(invoices):
            data = render(layout, inv)
            if layout is fresh_fields:
                data = as_scan(data, angle=0.9 if i % 2 == 0 else -1.2)
            (OUT / inv.file).write_bytes(data)
            count += 1
    print(f"{count} sample invoices written to {OUT}")


if __name__ == "__main__":
    main()
