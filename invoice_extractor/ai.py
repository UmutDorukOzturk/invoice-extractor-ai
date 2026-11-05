"""AI step: Claude reads invoices the rules cannot (scans, photos, unusual layouts).

The whole PDF is sent, so Claude sees the page the way a person does. The answer is forced
into a fixed JSON structure (structured outputs) and then goes through exactly the same
checks as the rule-based results, so an AI mistake is caught the same way a typo is.
"""
import base64
from datetime import date
from typing import Optional

import anthropic
from pydantic import BaseModel

from . import config
from .model import InvoiceRecord, LineItem

SYSTEM = (
    "You extract data from supplier invoices for an accounts-payable team. "
    "Copy every number exactly as it is printed, even if it looks wrong: a separate step checks the arithmetic. "
    "Dates as YYYY-MM-DD, currency as a 3-letter code (EUR, USD, GBP). "
    "If a field is not on the invoice, use null. The buyer (the company being billed) is not the supplier."
)


class AILineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class AIInvoice(BaseModel):
    supplier_name: str
    supplier_vat_id: Optional[str]
    invoice_number: str
    invoice_date: Optional[date]
    due_date: Optional[date]
    currency: str
    net_amount: Optional[float]
    vat_rate_percent: Optional[float]
    vat_amount: Optional[float]
    total_amount: Optional[float]
    line_items: list[AILineItem]


class AIExtractionError(Exception):
    pass


def make_client() -> anthropic.Anthropic:
    """Uses ANTHROPIC_API_KEY (or another configured Anthropic credential) from the environment."""
    return anthropic.Anthropic()


def extract_with_claude(pdf_bytes: bytes, client: anthropic.Anthropic, model: str = config.AI_MODEL) -> AIInvoice:
    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64", "media_type": "application/pdf",
                            "data": base64.standard_b64encode(pdf_bytes).decode("ascii")}},
                {"type": "text", "text": "Extract this invoice."},
            ],
        }],
        output_format=AIInvoice,
        output_config={"effort": "low"},          # simple extraction: low effort is enough and cheaper
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",                      # if the model declines, the API retries on a fallback model
    )
    if response.stop_reason == "refusal":
        raise AIExtractionError("the model declined to process this document")
    if response.stop_reason == "max_tokens":
        raise AIExtractionError("the answer was cut off")
    if response.parsed_output is None:
        raise AIExtractionError("no structured answer was returned")
    return response.parsed_output


def to_record(data: AIInvoice, file: str) -> InvoiceRecord:
    return InvoiceRecord(
        file=file,
        supplier=data.supplier_name.strip(),
        supplier_vat_id=(data.supplier_vat_id or "").replace(" ", ""),
        invoice_number=data.invoice_number.strip(),
        invoice_date=data.invoice_date,
        due_date=data.due_date,
        currency=(data.currency or config.DEFAULT_CURRENCY).upper(),
        net=data.net_amount,
        vat_rate=data.vat_rate_percent / 100 if data.vat_rate_percent is not None else None,
        vat=data.vat_amount,
        total=data.total_amount,
        lines=[LineItem(li.description, li.quantity, li.unit_price, li.amount) for li in data.line_items],
        method="AI",
        has_text=False,
    )
