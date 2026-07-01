"""
Shared fixtures for end-to-end tests.
Requires: docker compose up -d --wait  (full system including Dapr sidecars)
"""
import time
import uuid

import httpx
import pytest

GATEWAY_URL = "http://localhost:8000"
AUDIT_URL = "http://localhost:8005"

# INV-1001 — guaranteed auto-approve: meals $42, known vendor, receipt, math OK
INV_1001_TEMPLATE = {
    "vendor": "Bistro 19",
    "vendorKnown": True,
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
    with httpx.Client(timeout=15.0) as client:
        yield client


def wait_for_status(http, tracking_id: str, target_statuses: set, timeout: int = 60) -> str:
    """Poll GET /submissions/{id} until status is in target_statuses or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = http.get(f"{GATEWAY_URL}/submissions/{tracking_id}")
        if resp.status_code == 200:
            status = resp.json().get("status", "")
            if status in target_statuses:
                return status
        time.sleep(2)
    raise TimeoutError(
        f"Submission {tracking_id} did not reach {target_statuses} within {timeout}s"
    )


def unique_invoice(prefix: str = "E2E") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
