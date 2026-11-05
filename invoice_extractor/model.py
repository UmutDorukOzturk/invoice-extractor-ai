"""The record every extraction method (rules or AI) fills in."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class LineItem:
    description: str
    quantity: float
    unit_price: float
    amount: float
    code: str = ""


@dataclass
class InvoiceRecord:
    file: str
    supplier: str = ""
    supplier_vat_id: str = ""
    invoice_number: str = ""
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: str = "EUR"
    net: Optional[float] = None
    vat_rate: Optional[float] = None      # 0.21 for 21 %
    vat: Optional[float] = None
    total: Optional[float] = None
    lines: list[LineItem] = field(default_factory=list)
    method: str = ""                      # "Rules" or "AI"
    has_text: bool = True                 # False for scans without a text layer
    issues: list[str] = field(default_factory=list)
    duplicate_of: str = ""
    status: str = ""                      # OK / Check / Duplicate / Unreadable

    REQUIRED = ("supplier", "invoice_number", "invoice_date", "total")

    def missing(self) -> list[str]:
        return [name.replace("_", " ") for name in self.REQUIRED if not getattr(self, name)]
