"""Read the text layer of a PDF. Scanned invoices have none, so they go to the AI step."""
from pathlib import Path

import pdfplumber

MIN_TEXT = 20  # fewer characters than this means "no usable text layer"


def read_text(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def has_text_layer(text: str) -> bool:
    return len(text.strip()) >= MIN_TEXT
