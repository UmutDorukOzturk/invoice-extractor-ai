"""Excel report and CSV exports for the extracted invoices."""
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import DataPoint
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .model import InvoiceRecord

NAVY, BLUE, LIGHT, GREY = "1F3864", "2E75B6", "EEF3FA", "6B7280"
STATUS_STYLE = {  # fill, font
    "OK": ("E3F4EA", "16794A"),
    "Check": ("FFF1D6", "9A6200"),
    "Duplicate": ("ECEFF3", "4B5563"),
    "Unreadable": ("FDE4E1", "B42318"),
}
STATUS_ICON = {"OK": "✓ OK", "Check": "⚠ Check", "Duplicate": "⧉ Duplicate", "Unreadable": "✕ Unreadable"}
MONEY_FORMATS = {"EUR": "€#,##0.00", "GBP": "£#,##0.00", "USD": "$#,##0.00"}
DATE_FORMAT = "[$-409]d mmm yyyy"   # English month names whatever the Windows language
TABLE_STYLE = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)


def payable(rec: InvoiceRecord) -> bool:
    """Invoices that should be paid: everything except duplicates and invoices we could not read."""
    return rec.status in ("OK", "Check") and rec.total is not None


def money_format(currency: str) -> str:
    return MONEY_FORMATS.get(currency, f'#,##0.00 "{currency}"')


def write_report(records: list[InvoiceRecord], path: Path, run_at: datetime, source: str, ai_used: bool) -> None:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    invoices = wb.create_sheet("Invoices")
    lines = wb.create_sheet("Line items")
    suppliers = wb.create_sheet("By supplier")
    notes = wb.create_sheet("Notes")

    _invoices_sheet(invoices, records, run_at)
    _lines_sheet(lines, records)
    n_suppliers, status_rows = _suppliers_sheet(suppliers, records, run_at)
    _summary_sheet(summary, records, run_at, source, suppliers, n_suppliers, status_rows)
    _notes_sheet(notes, run_at, source, ai_used)
    wb.save(path)


def write_csvs(records: list[InvoiceRecord], out_dir: Path, stamp: str) -> tuple[Path, Path]:
    """Flat files for importing into accounting software (UTF-8 with BOM so Excel opens them correctly)."""
    inv_path = out_dir / f"invoices_{stamp}.csv"
    line_path = out_dir / f"line_items_{stamp}.csv"
    with open(inv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["status", "file", "supplier", "supplier_vat_id", "invoice_number", "invoice_date", "due_date",
                    "currency", "net", "vat_rate", "vat", "total", "read_by", "notes"])
        for r in records:
            w.writerow([r.status, r.file, r.supplier, r.supplier_vat_id, r.invoice_number,
                        r.invoice_date.isoformat() if r.invoice_date else "",
                        r.due_date.isoformat() if r.due_date else "", r.currency,
                        _num(r.net), _num(r.vat_rate, 4), _num(r.vat), _num(r.total), r.method, " | ".join(r.issues)])
    with open(line_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["file", "supplier", "invoice_number", "line", "code", "description", "quantity",
                    "unit_price", "amount"])
        for r in records:
            for i, li in enumerate(r.lines, start=1):
                w.writerow([r.file, r.supplier, r.invoice_number, i, li.code, li.description,
                            _num(li.quantity, 3), _num(li.unit_price), _num(li.amount)])
    return inv_path, line_path


def _num(value: Optional[float], decimals: int = 2) -> str:
    return "" if value is None else f"{value:.{decimals}f}"


# ---------------------------------------------------------------- helpers

def _headers(ws, row: int, headers: list[str], widths: list[float], start_col: int = 1) -> None:
    for i, (text, width) in enumerate(zip(headers, widths)):
        ws.cell(row, start_col + i, text)
        ws.column_dimensions[get_column_letter(start_col + i)].width = width


def _table(ws, name: str, first_row: int, last_row: int, first_col: int, last_col: int) -> None:
    ref = f"{get_column_letter(first_col)}{first_row}:{get_column_letter(last_col)}{max(last_row, first_row + 1)}"
    table = Table(displayName=name, ref=ref)
    table.tableStyleInfo = TABLE_STYLE
    ws.add_table(table)


def _status_cell(cell, status: str) -> None:
    fill, font = STATUS_STYLE.get(status, ("FFFFFF", NAVY))
    cell.value = STATUS_ICON.get(status, status)
    cell.fill = PatternFill("solid", fgColor=fill)
    cell.font = Font(bold=True, color=font)


def _bar_chart(title: str, cats: Reference, vals: Reference, horizontal: bool, color: str,
               label_fmt: Optional[str] = None, point_colors: Optional[list[str]] = None,
               value_max: Optional[float] = None) -> BarChart:
    chart = BarChart()
    chart.type = "bar" if horizontal else "col"
    chart.title = title
    chart.title.overlay = False
    chart.add_data(vals, titles_from_data=False)
    chart.set_categories(cats)
    chart.legend = None
    chart.varyColors = False
    chart.gapWidth = 55
    series = chart.series[0]
    series.graphicalProperties.solidFill = color
    series.graphicalProperties.line.solidFill = color
    for i, c in enumerate(point_colors or []):
        point = DataPoint(idx=i)
        point.graphicalProperties.solidFill = c
        point.graphicalProperties.line.solidFill = c
        series.dPt.append(point)
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    for flag in ("showSerName", "showCatName", "showLegendKey", "showPercent"):
        setattr(chart.dataLabels, flag, False)
    if label_fmt:
        chart.dataLabels.numFmt = label_fmt
    chart.x_axis.delete = False
    chart.y_axis.delete = True
    chart.y_axis.majorGridlines = None
    if value_max:
        chart.y_axis.scaling.min = 0
        chart.y_axis.scaling.max = value_max   # headroom so the value labels fit next to the bars
    if horizontal:
        chart.x_axis.scaling.orientation = "maxMin"
    chart.width, chart.height = 12.6, 7.6
    return chart


# ---------------------------------------------------------------- sheets

def _invoices_sheet(ws, records: list[InvoiceRecord], run_at: datetime) -> None:
    headers = ["Status", "File", "Supplier", "Supplier VAT ID", "Invoice no.", "Invoice date", "Due date",
               "Due in (days)", "Net", "VAT %", "VAT", "Total", "Currency", "Lines", "Read by", "Notes"]
    _headers(ws, 1, headers, [15, 31, 28, 17, 15, 13, 13, 14, 12, 8, 11, 12, 10, 7, 9, 90])
    today = run_at.date()
    for r, rec in enumerate(records, start=2):
        _status_cell(ws.cell(r, 1), rec.status)
        ws.cell(r, 2, rec.file)
        ws.cell(r, 3, rec.supplier)
        ws.cell(r, 4, rec.supplier_vat_id)
        ws.cell(r, 5, rec.invoice_number)
        for c, value in ((6, rec.invoice_date), (7, rec.due_date)):
            if value:
                ws.cell(r, c, value).number_format = DATE_FORMAT
        if rec.due_date and rec.status != "Duplicate":
            days = (rec.due_date - today).days
            cell = ws.cell(r, 8, days)
            cell.alignment = Alignment(horizontal="center")
            if days < 0:
                cell.font = Font(bold=True, color="B42318")
        fmt = money_format(rec.currency)
        for c, value in ((9, rec.net), (11, rec.vat), (12, rec.total)):
            if value is not None:
                ws.cell(r, c, value).number_format = fmt
        if rec.vat_rate is not None:
            ws.cell(r, 10, rec.vat_rate).number_format = "0%"
        ws.cell(r, 13, rec.currency)
        ws.cell(r, 14, len(rec.lines) or None)
        ws.cell(r, 15, rec.method or "—")
        ws.cell(r, 16, " | ".join(rec.issues))
    _table(ws, "Invoices", 1, len(records) + 1, 1, len(headers))
    ws.freeze_panes = "C2"


def _lines_sheet(ws, records: list[InvoiceRecord]) -> None:
    headers = ["File", "Supplier", "Invoice no.", "Line", "Code", "Description", "Qty", "Unit price", "Amount",
               "Check"]
    _headers(ws, 1, headers, [31, 28, 15, 7, 10, 42, 8, 12, 12, 30])
    r = 2
    for rec in records:
        fmt = money_format(rec.currency)
        for i, li in enumerate(rec.lines, start=1):
            values = [rec.file, rec.supplier, rec.invoice_number, i, li.code, li.description, li.quantity]
            for c, value in enumerate(values, start=1):
                ws.cell(r, c, value)
            ws.cell(r, 8, li.unit_price).number_format = fmt
            ws.cell(r, 9, li.amount).number_format = fmt
            expected = round(li.quantity * li.unit_price, 2)
            if abs(expected - li.amount) > 0.011:
                cell = ws.cell(r, 10, f"✕ should be {expected:,.2f}")
                cell.font = Font(bold=True, color="B42318")
            else:
                ws.cell(r, 10, "✓").font = Font(color="16794A")
            r += 1
    _table(ws, "LineItems", 1, r - 1, 1, len(headers))
    ws.freeze_panes = "A2"


def _suppliers_sheet(ws, records: list[InvoiceRecord], run_at: datetime):
    groups = defaultdict(list)
    for rec in records:
        if payable(rec):
            groups[rec.supplier].append(rec)
    rows = sorted(groups.items(), key=lambda kv: -sum(r.total for r in kv[1]))
    headers = ["Supplier", "VAT ID", "Invoices", "Net", "VAT", "Total", "Overdue", "Next due"]
    _headers(ws, 1, headers, [30, 17, 10, 13, 12, 13, 10, 13])
    today = run_at.date()
    for r, (supplier, recs) in enumerate(rows, start=2):
        upcoming = sorted(x.due_date for x in recs if x.due_date and x.due_date >= today)
        values = [supplier, recs[0].supplier_vat_id, len(recs), sum(x.net or 0 for x in recs),
                  sum(x.vat or 0 for x in recs), sum(x.total for x in recs),
                  sum(1 for x in recs if x.due_date and x.due_date < today), upcoming[0] if upcoming else None]
        for c, value in enumerate(values, start=1):
            cell = ws.cell(r, c, value)
            if c in (4, 5, 6):
                cell.number_format = money_format(recs[0].currency)
            if c == 8 and value:
                cell.number_format = DATE_FORMAT
            if c == 7 and value:
                cell.font = Font(bold=True, color="B42318")
    _table(ws, "Suppliers", 1, len(rows) + 1, 1, len(headers))

    # status counts behind the Summary chart
    counts = Counter(rec.status for rec in records)
    ws["J1"], ws["K1"] = "Status", "Invoices"
    statuses = ["OK", "Check", "Duplicate", "Unreadable"]
    for i, status in enumerate(statuses, start=2):
        ws.cell(i, 10, status)
        ws.cell(i, 11, counts.get(status, 0))
    _table(ws, "StatusCounts", 1, 5, 10, 11)
    ws.column_dimensions["I"].width = 3
    ws.column_dimensions["J"].width = 13
    ws.column_dimensions["K"].width = 11
    return len(rows), (2, 5)


def _kpi_card(ws, col: int, label: str, value, note: str, fmt: Optional[str] = None, alert: bool = False) -> None:
    fill = PatternFill("solid", fgColor="FDECEA" if alert else LIGHT)
    accent = Side(style="thick", color="B42318" if alert else BLUE)
    for row in (5, 6, 7):
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
        for c in (col, col + 1):
            ws.cell(row, c).fill = fill
        ws.cell(row, col).border = Border(left=accent)
        ws.cell(row, col).alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.cell(5, col, label.upper()).font = Font(size=9, bold=True, color=GREY)
    big = ws.cell(6, col, value)
    big.font = Font(size=20, bold=True, color="B42318" if alert else NAVY)
    if fmt:
        big.number_format = fmt
    ws.cell(7, col, note).font = Font(size=9, color=GREY)


def _summary_sheet(ws, records, run_at, source, suppliers_ws, n_suppliers, status_rows) -> None:
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 2
    for col in range(2, 14):
        ws.column_dimensions[get_column_letter(col)].width = 11.5
    ws.row_dimensions[6].height = 30

    dated = [r.invoice_date for r in records if r.invoice_date]
    span = f"{min(dated):%d %b} – {max(dated):%d %b %Y}" if dated else "no dates found"
    ws["B2"] = "Supplier Invoices · Accounts Payable Report"
    ws["B2"].font = Font(size=20, bold=True, color=NAVY)
    ws["B3"] = (f"{len(records)} PDF files from '{source}'   ·   invoices dated {span}   ·   "
                f"processed {run_at:%d %b %Y, %H:%M}")
    ws["B3"].font = Font(size=10, color=GREY)

    today = run_at.date()
    to_pay = [r for r in records if payable(r)]
    read = [r for r in records if r.status in ("OK", "Check", "Duplicate")]
    attention = [r for r in records if r.status != "OK"]
    overdue = [r for r in to_pay if r.due_date and r.due_date < today]
    by_ai = sum(1 for r in read if r.method == "AI")
    fmt = money_format(to_pay[0].currency if to_pay else "EUR")
    _kpi_card(ws, 2, "Invoices", len(records), "PDF files processed")
    _kpi_card(ws, 4, "Read automatically", len(read),
              f"{len(read) / max(len(records), 1):.0%} of files" + (f" · {by_ai} by AI" if by_ai else ""))
    _kpi_card(ws, 6, "Need attention", len(attention), "listed below", alert=bool(attention))
    _kpi_card(ws, 8, "To pay (incl. VAT)", sum(r.total for r in to_pay), "duplicates excluded", fmt)
    _kpi_card(ws, 10, "Input VAT", sum(r.vat or 0 for r in to_pay), "deductible VAT", fmt)
    _kpi_card(ws, 12, "Overdue", len(overdue), f"€{sum(r.total for r in overdue):,.2f} past due date",
              alert=bool(overdue))

    supplier_totals = [suppliers_ws.cell(r, 6).value or 0 for r in range(2, 2 + n_suppliers)]
    chart = _bar_chart("Spend by supplier (incl. VAT)",
                       Reference(suppliers_ws, min_col=1, min_row=2, max_row=1 + n_suppliers),
                       Reference(suppliers_ws, min_col=6, min_row=2, max_row=1 + n_suppliers), True, BLUE,
                       value_max=max(supplier_totals, default=0) * 1.3 or None)
    ws.add_chart(chart, "B9")
    chart = _bar_chart("Invoices by status",
                       Reference(suppliers_ws, min_col=10, min_row=status_rows[0], max_row=status_rows[1]),
                       Reference(suppliers_ws, min_col=11, min_row=status_rows[0], max_row=status_rows[1]), False,
                       NAVY, point_colors=["2E9E5B", "E0A100", "8A94A6", "D64545"])
    ws.add_chart(chart, "H9")

    ws["B25"] = "Needs attention"
    ws["B25"].font = Font(size=13, bold=True, color=NAVY)
    if not attention:
        ws["B26"] = "Nothing to check: every invoice was read and adds up."
        ws["B26"].font = Font(color=GREY, italic=True)
        return
    head = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor=NAVY)
    line = Side(style="thin", color="D9E1F2")
    spans = ((2, 3, "Status"), (4, 6, "File"), (7, 13, "What to check"))
    for c1, c2, text in spans:
        ws.merge_cells(start_row=26, start_column=c1, end_row=26, end_column=c2)
        cell = ws.cell(26, c1, text)
        cell.font, cell.fill = head, head_fill
        cell.alignment = Alignment(indent=1, vertical="center")
        for c in range(c1, c2 + 1):
            ws.cell(26, c).fill = head_fill
    for i, rec in enumerate(attention, start=27):
        for c1, c2, _ in spans:
            ws.merge_cells(start_row=i, start_column=c1, end_row=i, end_column=c2)
        _status_cell(ws.cell(i, 2), rec.status)
        ws.cell(i, 4, rec.file)
        problem = rec.issues[0] if rec.issues else ""
        if len(rec.issues) > 1:
            problem += f"  (+{len(rec.issues) - 1} more)"
        ws.cell(i, 7, problem).font = Font(color="333333")
        ws.row_dimensions[i].height = 19
        for c in range(2, 14):
            ws.cell(i, c).border = Border(bottom=line)
            ws.cell(i, c).alignment = Alignment(vertical="center", indent=1 if c in (2, 4, 7) else 0)


def _notes_sheet(ws, run_at: datetime, source: str, ai_used: bool) -> None:
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 100
    ws["A1"] = "About this report"
    ws["A1"].font = Font(size=16, bold=True, color=NAVY)
    rows = [
        ("Source folder", source),
        ("Processed", f"{run_at:%d %B %Y, %H:%M}"),
        ("AI step", "On: invoices the rules could not read were sent to Claude" if ai_used
                    else "Off: scanned invoices are listed as 'Unreadable'. Run with --ai to read them with Claude"),
        ("How it works", "1. Text is read from each PDF. 2. Fields are found by their labels (English, Dutch, "
                         "German), whatever the layout. 3. Scans and unknown layouts can go to Claude (AI). "
                         "4. Every invoice is checked: qty × price, line items vs subtotal, VAT %, subtotal + VAT "
                         "vs total, and duplicates."),
        ("", ""),
        ("Status: OK", "Read completely and all amounts add up."),
        ("Status: Check", "Read, but something does not add up or a field is missing. See 'Notes'."),
        ("Status: Duplicate", "Same supplier and invoice number as an earlier file. Do not pay twice."),
        ("Status: Unreadable", "No text layer (scan or photo). Use the AI step or enter by hand."),
        ("Due in (days)", "Negative numbers (red) are overdue on the processing date."),
        ("", ""),
        ("Prepared by", "Umut Doruk Öztürk · Python automation & document data extraction"),
    ]
    for r, (key, value) in enumerate(rows, start=3):
        ws.cell(r, 1, key).font = Font(bold=True, color=NAVY)
        cell = ws.cell(r, 2, value)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 1).alignment = Alignment(vertical="top")
