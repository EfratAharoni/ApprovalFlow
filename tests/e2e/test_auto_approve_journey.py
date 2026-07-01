"""
E2E test — Auto-approve journey (INV-1001 pattern).

Journey:
  POST /submissions → 202 + tracking_id
  → poll until status=PAID (no human touch)
  → GET /audit/{tracking_id} → full trail present

Requires: docker compose up -d --wait (LLM_MOCK=true is fine)
Run:      pytest tests/e2e/test_auto_approve_journey.py -v -m e2e
"""
import pytest

from .conftest import (
    AUDIT_URL,
    GATEWAY_URL,
    INV_1001_TEMPLATE,
    unique_invoice,
    wait_for_status,
)

TERMINAL_STATUSES = {"PAID", "AUTO_APPROVED", "PAYMENT_FAILED"}


@pytest.mark.e2e
def test_auto_approve_reaches_paid(http):
    """A clean in-policy submission must end up PAID with no human intervention."""
    payload = {**INV_1001_TEMPLATE, "invoiceNumber": unique_invoice("AUTO")}

    resp = http.post(f"{GATEWAY_URL}/submissions", json=payload)
    assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "tracking_id" in body
    tracking_id = body["tracking_id"]

    final_status = wait_for_status(http, tracking_id, TERMINAL_STATUSES, timeout=60)
    assert final_status in {"PAID", "AUTO_APPROVED"}, (
        f"Expected PAID/AUTO_APPROVED, got {final_status!r}"
    )


@pytest.mark.e2e
def test_auto_approve_audit_trail_is_complete(http):
    """After PAID, audit trail must contain submission.created and decision.made events."""
    payload = {**INV_1001_TEMPLATE, "invoiceNumber": unique_invoice("TRAIL")}

    resp = http.post(f"{GATEWAY_URL}/submissions", json=payload)
    assert resp.status_code == 202
    tracking_id = resp.json()["tracking_id"]

    wait_for_status(http, tracking_id, TERMINAL_STATUSES, timeout=60)

    trail_resp = http.get(f"{AUDIT_URL}/audit/{tracking_id}")
    assert trail_resp.status_code == 200, (
        f"Audit trail missing for {tracking_id}: {trail_resp.status_code}"
    )
    trail = trail_resp.json()
    assert len(trail) >= 1, "Audit trail must have at least one event"

    event_types = {e["event_type"] for e in trail}
    assert "submission.created" in event_types, (
        f"submission.created missing from trail. Found: {event_types}"
    )


@pytest.mark.e2e
def test_auto_approve_decision_route_is_auto_approve(http):
    """The decision.made event in the trail must carry route=auto_approve."""
    payload = {**INV_1001_TEMPLATE, "invoiceNumber": unique_invoice("ROUTE")}

    resp = http.post(f"{GATEWAY_URL}/submissions", json=payload)
    assert resp.status_code == 202
    tracking_id = resp.json()["tracking_id"]

    wait_for_status(http, tracking_id, TERMINAL_STATUSES, timeout=60)

    trail = http.get(f"{AUDIT_URL}/audit/{tracking_id}").json()
    decision_events = [e for e in trail if e["event_type"] == "decision.made"]

    assert decision_events, "No decision.made event found in audit trail"
    route = decision_events[0]["payload"].get("route")
    assert route == "auto_approve", f"Expected route=auto_approve, got {route!r}"


@pytest.mark.e2e
def test_status_endpoint_returns_plain_language_reason(http):
    """After processing, plain_language_reason must be non-empty."""
    payload = {**INV_1001_TEMPLATE, "invoiceNumber": unique_invoice("REASON")}

    resp = http.post(f"{GATEWAY_URL}/submissions", json=payload)
    assert resp.status_code == 202
    tracking_id = resp.json()["tracking_id"]

    wait_for_status(http, tracking_id, TERMINAL_STATUSES, timeout=60)

    status_resp = http.get(f"{GATEWAY_URL}/submissions/{tracking_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body.get("plain_language_reason"), (
        "plain_language_reason must be non-empty after processing"
    )
