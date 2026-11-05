"""Settings for your company. Change these before using the tool on your own invoices."""

# Your own company appears on every invoice ("Bill to"). Its name and VAT number are ignored
# when looking for the supplier.
BUYER_NAMES = ["Harbor & Pine Cafés B.V."]
BUYER_VAT_IDS = ["NL812345678B01"]

# Used when an invoice does not show a currency.
DEFAULT_CURRENCY = "EUR"

# Claude model for the AI step (only used with --ai).
AI_MODEL = "claude-opus-5-5"
