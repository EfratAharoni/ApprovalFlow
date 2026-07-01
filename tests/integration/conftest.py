"""
Shared fixtures for integration tests.
Requires: docker compose up -d --wait
"""
import pytest
import httpx

SUBMISSION_URL = "http://localhost:8001"
GATEWAY_URL = "http://localhost:8000"

# INV-1001 — auto-approve fixture (meals, $42, known vendor, receipt present)
INV_1001 = {
    "vendor": "Bistro 19",
    "vendorKnown": True,
    "invoiceNumber": "NW-INV-7781",
    "currency": "USD",
    "category": "meals",
    "attendees": 1,
    "lineItems": [{"description": "Team lunch", "quantity": 1, "unitPrice": 38.89}],
    "taxAmount": 3.11,
    "total": 42.0,
    "receiptPresent": True,
    "date": "2026-05-12",
    "notes": "Solo working lunch.",
    "submitter": "dana.cohen@northwind.example",
    "department": "engineering-2026Q2",
}


@pytest.fixture(scope="session")
def http():
    """Synchronous httpx client for integration tests."""
    with httpx.Client(timeout=10.0) as client:
        yield client
