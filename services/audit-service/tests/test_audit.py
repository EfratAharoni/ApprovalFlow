"""
Unit tests for AuditService.

No database, no Dapr, no real network.
All storage is replaced with an in-memory mock.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import pytest

from app.service import AuditService


# ─── Mock store ───────────────────────────────────────────────────────────────


class MockAuditStore:
    """In-memory append-only store. Enforces idempotency on event_id."""

    def __init__(self):
        self._events: List[dict] = []
        self._event_ids: set = set()

    async def record_event(self, data: dict) -> Optional[dict]:
        eid = data.get("event_id")
        if eid and eid in self._event_ids:
            return None  # duplicate, skip silently
        record = {**data, "id": str(uuid.uuid4())}
        self._events.append(record)
        if eid:
            self._event_ids.add(eid)
        return record

    async def get_by_submission(self, submission_id: str) -> list:
        matches = [e for e in self._events if e.get("submission_id") == submission_id]
        return sorted(matches, key=lambda e: e.get("timestamp", ""))

    async def get_all(self) -> list:
        return list(self._events)


def _make_svc(store: MockAuditStore) -> AuditService:
    return AuditService(
        record_event=store.record_event,
        get_by_submission=store.get_by_submission,
        get_all=store.get_all,
    )


def _ts(offset_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()


# ─── Tests ────────────────────────────────────────────────────────────────────


async def test_all_events_recorded():
    """
    5 different event types all get recorded and returned by get_trail.
    Events are returned in timestamp order.
    """
    store = MockAuditStore()
    svc = _make_svc(store)

    events = [
        ("submission.created",  {"submission_id": "inv-x", "correlation_id": "c-x", "submitted_by": "alice@northwind.example"}, _ts(0)),
        ("decision.made",       {"submission_id": "inv-x", "correlation_id": "c-x", "route": "auto_approve", "amount_usd": "42.00"}, _ts(1)),
        ("approval.decided",    {"submission_id": "inv-x", "correlation_id": "c-x", "action": "APPROVE", "decided_by": "bob"}, _ts(2)),
        ("payment.completed",   {"submission_id": "inv-x", "correlation_id": "c-x", "external_payment_ref": "PAY-ABC"}, _ts(3)),
        ("payment.failed",      {"submission_id": "inv-x", "correlation_id": "c-x", "reason": "test"}, _ts(4)),
    ]

    for topic, payload, ts in events:
        await svc.handle_event(topic=topic, payload=payload, dapr_event_id=str(uuid.uuid4()), timestamp=ts)

    trail = await svc.get_trail("inv-x")
    assert len(trail) == 5, f"Expected 5 events, got {len(trail)}"

    # Verify order: each event_type appears once in the correct sequence
    types = [e["event_type"] for e in trail]
    assert types == [
        "submission.created", "decision.made", "approval.decided",
        "payment.completed", "payment.failed",
    ], f"Unexpected order: {types}"

    # Verify service_name mapping
    assert trail[0]["service_name"] == "submission-service"
    assert trail[1]["service_name"] == "ai-agent-service"
    assert trail[2]["service_name"] == "approval-service"
    assert trail[3]["service_name"] == "payment-service"


async def test_idempotent_insert():
    """
    Sending the same event_id twice must result in exactly one record.
    """
    store = MockAuditStore()
    svc = _make_svc(store)

    fixed_id = "dapr-cloudevents-id-abc123"
    payload = {"submission_id": "inv-y", "correlation_id": "c-y", "route": "auto_approve", "amount_usd": "99.00"}

    await svc.handle_event("decision.made", payload, dapr_event_id=fixed_id, timestamp=_ts(0))
    await svc.handle_event("decision.made", payload, dapr_event_id=fixed_id, timestamp=_ts(1))  # duplicate

    trail = await svc.get_trail("inv-y")
    assert len(trail) == 1, f"Expected 1 record (idempotent), got {len(trail)}"


async def test_dashboard_counts():
    """
    3 auto_approve, 1 human_review, 1 reject → correct counters + rate=0.6.
    """
    store = MockAuditStore()
    svc = _make_svc(store)

    decisions = [
        {"submission_id": "inv-001", "route": "auto_approve",  "amount_usd": "42.00"},
        {"submission_id": "inv-002", "route": "auto_approve",  "amount_usd": "99.00"},
        {"submission_id": "inv-003", "route": "auto_approve",  "amount_usd": "180.00"},
        {"submission_id": "inv-004", "route": "human_review",  "amount_usd": "1820.00"},
        {"submission_id": "inv-005", "route": "reject",        "amount_usd": "60.00"},
    ]

    # Record submission.created and decision.made for each
    for d in decisions:
        sid = d["submission_id"]
        corr = f"c-{sid}"
        await svc.handle_event(
            "submission.created",
            {"submission_id": sid, "correlation_id": corr, "submitted_by": "test@example.com"},
            dapr_event_id=str(uuid.uuid4()), timestamp=_ts(0),
        )
        await svc.handle_event(
            "decision.made",
            {"submission_id": sid, "correlation_id": corr, **d},
            dapr_event_id=str(uuid.uuid4()), timestamp=_ts(1),
        )

    dash = await svc.get_dashboard()

    assert dash["total_submissions"] == 5
    assert dash["auto_approved"] == 3
    assert dash["human_reviewed"] == 1
    assert dash["rejected"] == 1
    assert dash["duplicates"] == 0
    assert dash["auto_approval_rate"] == pytest.approx(0.6)
    # Total amount auto-approved: 42 + 99 + 180 = 321
    assert dash["total_amount_auto_approved"] == pytest.approx(321.0)


async def test_prove_ceiling_clean():
    """
    All auto_approve decisions have amount ≤ 250 → violation_found=False.
    This is the expected production state — proves M12 holds.
    """
    store = MockAuditStore()
    svc = _make_svc(store)

    for sid, amount in [("inv-001", "42.00"), ("inv-002", "99.00"), ("inv-003", "180.00")]:
        await svc.handle_event(
            "decision.made",
            {"submission_id": sid, "correlation_id": f"c-{sid}", "route": "auto_approve", "amount_usd": amount},
            dapr_event_id=str(uuid.uuid4()),
        )

    result = await svc.prove_ceiling(ceiling=250.0)

    assert result["ceiling"] == 250.0
    assert result["violation_found"] is False, \
        f"Expected no violation, max was {result['max_auto_approved_amount']}"
    assert result["max_auto_approved_amount"] == pytest.approx(180.0)
    assert len(result["records"]) == 3


async def test_prove_ceiling_violation():
    """
    A manually injected auto_approve record with amount=300 must be detected.
    This proves the endpoint works and would catch any real ceiling breach.
    """
    store = MockAuditStore()
    svc = _make_svc(store)

    # Normal records
    for sid, amount in [("inv-001", "42.00"), ("inv-002", "99.00")]:
        await svc.handle_event(
            "decision.made",
            {"submission_id": sid, "correlation_id": f"c-{sid}", "route": "auto_approve", "amount_usd": amount},
            dapr_event_id=str(uuid.uuid4()),
        )

    # Injected violation — simulates what would happen if the ceiling guard were bypassed
    await svc.handle_event(
        "decision.made",
        {"submission_id": "inv-VIOLATION", "correlation_id": "c-vio", "route": "auto_approve", "amount_usd": "300.00"},
        dapr_event_id=str(uuid.uuid4()),
    )

    result = await svc.prove_ceiling(ceiling=250.0)

    assert result["violation_found"] is True, "Ceiling violation must be detected"
    assert result["max_auto_approved_amount"] == pytest.approx(300.0)
    assert len(result["records"]) == 3


async def test_full_trail_inv1001():
    """
    Full journey for INV-1001 (auto-approve path) — all 5 event types recorded.
    GET /audit/INV-1001 returns them in chronological order from submission to payment.
    """
    store = MockAuditStore()
    svc = _make_svc(store)

    # Complete event sequence for INV-1001 spanning all 5 subscribed topics
    journey = [
        ("submission.created", {
            "submission_id": "INV-1001", "correlation_id": "c-1001",
            "vendor": "Bistro 19", "amount_usd": "42.00", "category": "meals",
            "submitted_by": "dana.cohen@northwind.example",
        }, _ts(0)),
        ("decision.made", {
            "submission_id": "INV-1001", "correlation_id": "c-1001",
            "route": "auto_approve", "amount_usd": "42.00",
            "ceiling_guard_triggered": False,
            "plain_language_reason": "Under ceiling, known vendor, in-policy meal.",
        }, _ts(2)),
        # approval.decided is included in the full trail for audit completeness
        # (even if this specific invoice was auto-approved, the service records all events it receives)
        ("approval.decided", {
            "submission_id": "INV-1001", "correlation_id": "c-1001",
            "action": "APPROVE", "decided_by": "system-auto",
            "notes": "Auto-approved by AI agent",
        }, _ts(4)),
        ("payment.completed", {
            "submission_id": "INV-1001", "correlation_id": "c-1001",
            "external_payment_ref": "PAY-7F3A9C1E2B44",
            "amount_usd": 42.0,
        }, _ts(6)),
        ("payment.failed", {
            "submission_id": "INV-1001", "correlation_id": "c-1001",
            "reason": "Not applicable — included for complete trail coverage",
            "compensated_steps": [],
        }, _ts(8)),
    ]

    for topic, payload, ts in journey:
        await svc.handle_event(topic=topic, payload=payload, dapr_event_id=str(uuid.uuid4()), timestamp=ts)

    trail = await svc.get_trail("INV-1001")

    assert len(trail) == 5, f"Expected 5 events in trail, got {len(trail)}"

    # Chronological order guaranteed
    timestamps = [e["timestamp"] for e in trail]
    assert timestamps == sorted(timestamps), "Events must be in chronological order"

    # First event is submission.created
    assert trail[0]["event_type"] == "submission.created"
    assert trail[0]["actor"] == "dana.cohen@northwind.example"

    # Second is decision.made — proves the auto_approve route is recorded
    assert trail[1]["event_type"] == "decision.made"
    assert trail[1]["payload"]["route"] == "auto_approve"

    # Last event reaches payment territory
    assert trail[-1]["event_type"] == "payment.failed"

    # service_name correctly attributed throughout
    assert trail[0]["service_name"] == "submission-service"
    assert trail[1]["service_name"] == "ai-agent-service"
    assert trail[2]["service_name"] == "approval-service"
    assert trail[3]["service_name"] == "payment-service"
    assert trail[4]["service_name"] == "payment-service"
