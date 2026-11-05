"""Tests the AI step through the real Anthropic SDK, with the network replaced by a fake server.

Checks the request that would be sent (model, PDF document block, JSON schema, refusal
fallback) and that a response is turned into an InvoiceRecord. No API key or money needed.
"""
import json
from datetime import date

import anthropic
import httpx2
import pytest

from invoice_extractor.ai import AIExtractionError, extract_with_claude, to_record

ANSWER = {
    "supplier_name": "Fresh Fields Produce", "supplier_vat_id": "NL005678901B01",
    "invoice_number": "2026-118", "invoice_date": "2026-10-16", "due_date": None, "currency": "EUR",
    "net_amount": 69.0, "vat_rate_percent": 9, "vat_amount": 6.21, "total_amount": 75.21,
    "line_items": [{"description": "Avocados (box of 20)", "quantity": 2, "unit_price": 24.0, "amount": 48.0}],
}


def fake_client(answer: dict, stop_reason: str = "end_turn"):
    sent = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent["headers"] = dict(request.headers)
        sent["body"] = json.loads(request.content)
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": json.dumps(answer)}] if stop_reason != "refusal" else [],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 1500, "output_tokens": 200},
        })

    client = anthropic.Anthropic(api_key="test-key", max_retries=0,
                                 http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    return client, sent


def test_request_shape_and_parsing():
    client, sent = fake_client(ANSWER)
    data = extract_with_claude(b"%PDF-1.4 fake", client)

    body = sent["body"]
    assert body["model"] == "claude-opus-5-5"
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in sent["headers"]["anthropic-beta"]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    document = body["messages"][0]["content"][0]
    assert document["type"] == "document"
    assert document["source"]["media_type"] == "application/pdf"

    rec = to_record(data, "scan.pdf")
    assert rec.method == "AI"
    assert rec.supplier == "Fresh Fields Produce"
    assert rec.invoice_date == date(2026, 10, 16)
    assert rec.vat_rate == pytest.approx(0.09)
    assert rec.lines[0].amount == 48.0


def test_refusal_is_reported_not_parsed():
    client, _ = fake_client(ANSWER, stop_reason="refusal")
    with pytest.raises(AIExtractionError, match="declined"):
        extract_with_claude(b"%PDF-1.4 fake", client)
