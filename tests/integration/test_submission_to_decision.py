"""
Integration test — submission intake to pub/sub event.

Submits a real invoice to submission-service and verifies:
  1. The service returns 202 with a tracking_id.
  2. The submission is persisted (GET /submissions/{id} returns it).
  3. The submission status moves away from PENDING within the timeout
     (confirming that the submission.created event was consumed by
     ai-agent-service).

Requires: docker compose up -d --wait
Run:      pytest tests/integration/test_submission_to_decision.py -v -m integration
"""
import time
import uuid

import pytest

from .conftest import INV_1001, SUBMISSION_URL, GATEWAY_URL


@pytest.mark.integration
def test_submit_returns_202_with_tracking_id(http):
    payload = {**INV_1001, "invoiceNumber": f"INT-{uuid.uuid4().hex[:8]}"}
    resp = http.post(f"{SUBMISSION_URL}/submissions", json=payload)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "tracking_id" in body
    assert body["status"] == "PENDING"


@pytest.mark.integration
def test_submit_event_consumed_by_agent(http):
    """
    After submission the status must leave PENDING within 30 s,
    proving that submission.created was published to pub/sub and
    ai-agent-service consumed it.
    """
    payload = {**INV_1001, "invoiceNumber": f"INT-{uuid.uuid4().hex[:8]}"}
    resp = http.post(f"{SUBMISSION_URL}/submissions", json=payload)
    assert resp.status_code == 202
    tracking_id = resp.json()["tracking_id"]

    deadline = time.time() + 30
    while time.time() < deadline:
        status_resp = http.get(f"{GATEWAY_URL}/submissions/{tracking_id}")
        if status_resp.status_code == 200:
            status = status_resp.json().get("status")
            if status != "PENDING":
                assert status in {"AUTO_APPROVED", "ESCALATED", "PAID", "PAYMENT_FAILED", "REJECTED"}
                return
        time.sleep(2)

    pytest.fail(f"Submission {tracking_id} still PENDING after 30 s — event was not consumed")


@pytest.mark.integration
def test_submit_health_check(http):
    resp = http.get(f"{SUBMISSION_URL}/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"
