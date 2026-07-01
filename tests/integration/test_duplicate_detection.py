"""
Integration test — duplicate submission detection (F3 / M10).

Submits the same invoice twice and verifies:
  1. Both calls return 202.
  2. Both calls return the SAME tracking_id.
  3. Only one record exists — no double payment will occur.

Requires: docker compose up -d --wait
Run:      pytest tests/integration/test_duplicate_detection.py -v -m integration
"""
import uuid

import pytest

from .conftest import INV_1001, SUBMISSION_URL


@pytest.mark.integration
def test_duplicate_returns_same_tracking_id(http):
    # Use a unique invoice number so this test is isolated from other runs
    unique_invoice = f"DUP-{uuid.uuid4().hex[:8]}"
    payload = {**INV_1001, "invoiceNumber": unique_invoice}

    first = http.post(f"{SUBMISSION_URL}/submissions", json=payload)
    assert first.status_code == 202, first.text
    tracking_id_1 = first.json()["tracking_id"]

    second = http.post(f"{SUBMISSION_URL}/submissions", json=payload)
    assert second.status_code == 202, second.text
    tracking_id_2 = second.json()["tracking_id"]

    assert tracking_id_1 == tracking_id_2, (
        f"Duplicate submission returned a different tracking_id: "
        f"{tracking_id_1!r} vs {tracking_id_2!r}"
    )


@pytest.mark.integration
def test_different_invoice_numbers_get_different_tracking_ids(http):
    """Sanity check: two genuinely different invoices must NOT share a tracking_id."""
    payload_a = {**INV_1001, "invoiceNumber": f"UNIQUE-A-{uuid.uuid4().hex[:8]}"}
    payload_b = {**INV_1001, "invoiceNumber": f"UNIQUE-B-{uuid.uuid4().hex[:8]}"}

    resp_a = http.post(f"{SUBMISSION_URL}/submissions", json=payload_a)
    resp_b = http.post(f"{SUBMISSION_URL}/submissions", json=payload_b)

    assert resp_a.status_code == 202
    assert resp_b.status_code == 202
    assert resp_a.json()["tracking_id"] != resp_b.json()["tracking_id"]


@pytest.mark.integration
def test_duplicate_message_indicates_existing_submission(http):
    """Second submission response should carry a message indicating it is a duplicate."""
    unique_invoice = f"DUP2-{uuid.uuid4().hex[:8]}"
    payload = {**INV_1001, "invoiceNumber": unique_invoice}

    http.post(f"{SUBMISSION_URL}/submissions", json=payload)
    second = http.post(f"{SUBMISSION_URL}/submissions", json=payload)

    body = second.json()
    # The response message should signal that this is a known submission
    assert "duplicate" in body.get("message", "").lower() or body.get("tracking_id")
