"""
Unit tests for SubmissionStatusService.

No database, no Dapr, no network. All I/O is replaced with an in-memory mock.
"""
from typing import Dict, Optional

import pytest

from app.subscriber import SubmissionStatusService


# ─── Mock store ───────────────────────────────────────────────────────────────


class MockSubmissionStore:
    def __init__(self):
        self._data: Dict[str, dict] = {}

    def seed(self, record: dict) -> None:
        self._data[record["tracking_id"]] = dict(record)

    async def get_by_tracking_id(self, tracking_id: str) -> Optional[dict]:
        return self._data.get(tracking_id)

    async def update_submission(self, tracking_id: str, **kwargs) -> dict:
        if tracking_id not in self._data:
            raise KeyError(f"tracking_id {tracking_id!r} not found in mock store")
        self._data[tracking_id].update({k: v for k, v in kwargs.items() if v is not None})
        return self._data[tracking_id]


def _make_svc(store: MockSubmissionStore) -> SubmissionStatusService:
    return SubmissionStatusService(
        get_by_tracking_id=store.get_by_tracking_id,
        update_submission=store.update_submission,
    )


def _seeded_store(tracking_id: str = "TRK-001") -> MockSubmissionStore:
    store = MockSubmissionStore()
    store.seed({"tracking_id": tracking_id, "status": "PENDING", "plain_language_reason": None})
    return store


# ─── test_status_updates_from_events ─────────────────────────────────────────


async def test_decision_made_auto_approve():
    store = _seeded_store("TRK-001")
    svc = _make_svc(store)
    await svc.handle_decision_made({
        "submission_id": "TRK-001",
        "route": "auto_approve",
        "plain_language_reason": "Under ceiling, known vendor.",
    })
    assert store._data["TRK-001"]["status"] == "APPROVED"
    assert store._data["TRK-001"]["plain_language_reason"] == "Under ceiling, known vendor."


async def test_decision_made_human_review():
    store = _seeded_store("TRK-002")
    svc = _make_svc(store)
    await svc.handle_decision_made({"submission_id": "TRK-002", "route": "human_review"})
    assert store._data["TRK-002"]["status"] == "ESCALATED"


async def test_decision_made_reject():
    store = _seeded_store("TRK-003")
    svc = _make_svc(store)
    await svc.handle_decision_made({"submission_id": "TRK-003", "route": "reject"})
    assert store._data["TRK-003"]["status"] == "REJECTED"


async def test_decision_made_duplicate():
    store = _seeded_store("TRK-004")
    svc = _make_svc(store)
    await svc.handle_decision_made({"submission_id": "TRK-004", "route": "duplicate"})
    assert store._data["TRK-004"]["status"] == "DUPLICATE"


async def test_approval_decided_approve():
    store = _seeded_store("TRK-005")
    svc = _make_svc(store)
    await svc.handle_approval_decided({"submission_id": "TRK-005", "action": "APPROVE"})
    assert store._data["TRK-005"]["status"] == "APPROVED"


async def test_approval_decided_reject():
    store = _seeded_store("TRK-006")
    svc = _make_svc(store)
    await svc.handle_approval_decided({"submission_id": "TRK-006", "action": "REJECT"})
    assert store._data["TRK-006"]["status"] == "REJECTED"


async def test_approval_decided_request_info():
    store = _seeded_store("TRK-007")
    svc = _make_svc(store)
    await svc.handle_approval_decided({"submission_id": "TRK-007", "action": "REQUEST_INFO"})
    assert store._data["TRK-007"]["status"] == "PENDING_INFO"


async def test_approval_decided_timeout():
    store = _seeded_store("TRK-008")
    svc = _make_svc(store)
    await svc.handle_approval_decided({"submission_id": "TRK-008", "action": "TIMEOUT"})
    assert store._data["TRK-008"]["status"] == "TIMED_OUT"


async def test_payment_completed():
    store = _seeded_store("TRK-009")
    svc = _make_svc(store)
    await svc.handle_payment_completed({
        "submission_id": "TRK-009",
        "external_payment_ref": "PAY-ABC123",
    })
    assert store._data["TRK-009"]["status"] == "PAID"
    assert store._data["TRK-009"]["external_payment_ref"] == "PAY-ABC123"


async def test_payment_failed():
    store = _seeded_store("TRK-010")
    svc = _make_svc(store)
    await svc.handle_payment_failed({
        "submission_id": "TRK-010",
        "reason": "Insufficient budget",
    })
    assert store._data["TRK-010"]["status"] == "PAYMENT_FAILED"
    assert "Insufficient budget" in store._data["TRK-010"]["plain_language_reason"]


async def test_unknown_route_is_noop():
    """An unrecognised decision route must not change the status."""
    store = _seeded_store("TRK-011")
    svc = _make_svc(store)
    await svc.handle_decision_made({"submission_id": "TRK-011", "route": "totally_unknown"})
    assert store._data["TRK-011"]["status"] == "PENDING"


# ─── test_human_review_flow ───────────────────────────────────────────────────


async def test_human_review_flow():
    """
    Full HITL flow: escalate → human approves → payment completes.
    Each step must produce the correct status transition in order.
    """
    store = MockSubmissionStore()
    store.seed({"tracking_id": "INV-1003", "status": "PENDING", "plain_language_reason": None})
    svc = _make_svc(store)

    # Step 1: AI escalates
    await svc.handle_decision_made({
        "submission_id": "INV-1003",
        "route": "human_review",
        "plain_language_reason": "Amount $1820 exceeds ceiling; client entertainment.",
    })
    assert store._data["INV-1003"]["status"] == "ESCALATED"

    # Step 2: Human approves
    await svc.handle_approval_decided({
        "submission_id": "INV-1003",
        "action": "APPROVE",
        "decided_by": "manager@northwind.example",
    })
    assert store._data["INV-1003"]["status"] == "APPROVED"

    # Step 3: Payment completes
    await svc.handle_payment_completed({
        "submission_id": "INV-1003",
        "external_payment_ref": "PAY-7F3A9C1E2B44",
    })
    assert store._data["INV-1003"]["status"] == "PAID"
    assert store._data["INV-1003"]["external_payment_ref"] == "PAY-7F3A9C1E2B44"


async def test_human_review_rejected():
    """Escalate → human rejects → status ends at REJECTED."""
    store = MockSubmissionStore()
    store.seed({"tracking_id": "INV-HITL-R", "status": "PENDING", "plain_language_reason": None})
    svc = _make_svc(store)

    await svc.handle_decision_made({"submission_id": "INV-HITL-R", "route": "human_review"})
    assert store._data["INV-HITL-R"]["status"] == "ESCALATED"

    await svc.handle_approval_decided({"submission_id": "INV-HITL-R", "action": "REJECT"})
    assert store._data["INV-HITL-R"]["status"] == "REJECTED"


async def test_human_review_payment_failed():
    """Escalate → human approves → payment fails → PAYMENT_FAILED."""
    store = MockSubmissionStore()
    store.seed({"tracking_id": "INV-1012", "status": "PENDING", "plain_language_reason": None})
    svc = _make_svc(store)

    await svc.handle_decision_made({"submission_id": "INV-1012", "route": "human_review"})
    assert store._data["INV-1012"]["status"] == "ESCALATED"

    await svc.handle_approval_decided({"submission_id": "INV-1012", "action": "APPROVE"})
    assert store._data["INV-1012"]["status"] == "APPROVED"

    await svc.handle_payment_failed({
        "submission_id": "INV-1012",
        "reason": "external gateway timeout",
    })
    assert store._data["INV-1012"]["status"] == "PAYMENT_FAILED"
    assert "external gateway timeout" in store._data["INV-1012"]["plain_language_reason"]
