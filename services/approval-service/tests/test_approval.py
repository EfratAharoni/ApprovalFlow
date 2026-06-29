"""
Unit tests for ApprovalService.

No database, no Dapr, no real network.
All dependencies are replaced with in-memory mocks.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import pytest

from app.service import ApprovalService


# ─── Mock implementations ─────────────────────────────────────────────────────


class MockTaskStore:
    def __init__(self):
        self._tasks: Dict[str, dict] = {}

    def seed(self, task: dict) -> dict:
        """Pre-populate the store for test setup (bypasses service logic)."""
        record = {**task, "id": task.get("id", str(uuid.uuid4()))}
        self._tasks[task["submission_id"]] = record
        return record

    async def get_task(self, submission_id: str) -> Optional[dict]:
        return self._tasks.get(submission_id)

    async def get_all_pending(self) -> list:
        return [t for t in self._tasks.values() if t.get("status") == "PENDING"]

    async def create_task(self, data: dict) -> dict:
        record = {**data, "id": str(uuid.uuid4())}
        if "paused_timestamp" not in record:
            record["paused_timestamp"] = datetime.now(timezone.utc).isoformat()
        self._tasks[data["submission_id"]] = record
        return record

    async def update_task(self, submission_id: str, **kwargs) -> dict:
        if submission_id not in self._tasks:
            raise ValueError(f"Task not found: {submission_id}")
        self._tasks[submission_id].update(kwargs)
        return self._tasks[submission_id]


class MockHITLState:
    def __init__(self):
        self._state: Dict[str, dict] = {}

    async def save_hitl_state(self, submission_id: str, state: dict) -> None:
        self._state[submission_id] = state

    async def get_hitl_state(self, submission_id: str) -> Optional[dict]:
        return self._state.get(submission_id)

    async def delete_hitl_state(self, submission_id: str) -> None:
        self._state.pop(submission_id, None)

    def has_state(self, submission_id: str) -> bool:
        return submission_id in self._state


class MockPublishClient:
    def __init__(self):
        self.events: List[dict] = []

    async def publish_decided(self, data: dict, corr_id: str) -> None:
        self.events.append(data)

    def last_event(self) -> Optional[dict]:
        return self.events[-1] if self.events else None


def _make_service(
    store: MockTaskStore,
    hitl: MockHITLState,
    publish: MockPublishClient,
) -> ApprovalService:
    return ApprovalService(
        get_task=store.get_task,
        get_all_pending=store.get_all_pending,
        create_task=store.create_task,
        update_task=store.update_task,
        save_hitl_state=hitl.save_hitl_state,
        get_hitl_state=hitl.get_hitl_state,
        delete_hitl_state=hitl.delete_hitl_state,
        publish_decided=publish.publish_decided,
    )


# ─── Shared fixture data ──────────────────────────────────────────────────────

_DECISION_MADE_EVENT = {
    "submission_id": "inv-1003",
    "tracking_id": "t-1003",
    "correlation_id": "c-1003",
    "route": "human_review",
    "ceiling_guard_triggered": False,
    "agent_recommendation": {
        "reasoning": "Client dinner exceeds $75/attendee threshold.",
        "recommendation": "escalate",
        "confidence": 0.82,
        "policy_violations": [],
    },
    "policy_violations": [
        {"rule_id": "MEAL-02", "description": "Per-attendee cost exceeds $75 limit"}
    ],
    "plain_language_reason": "Per-attendee cost exceeds the $75/person meal policy.",
    "amount_usd": "1820.00",
    "category": "meals",
    "vendor": "The Capital Grille",
    "submitted_by": "david.levy@northwind.example",
}


# ─── Tests ────────────────────────────────────────────────────────────────────


async def test_decision_made_creates_task():
    """
    Receiving decision.made(route=human_review) must:
    - create an approval_task with status=PENDING
    - save the HITL state to Dapr
    """
    store = MockTaskStore()
    hitl = MockHITLState()
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    await svc.handle_decision_made(_DECISION_MADE_EVENT)

    task = await store.get_task("inv-1003")
    assert task is not None, "Task must be created"
    assert task["status"] == "PENDING"
    assert task["vendor"] == "The Capital Grille"
    assert task["amount_usd"] == pytest.approx(1820.0)

    # HITL state must be saved
    assert hitl.has_state("inv-1003"), "HITL state must be saved in Dapr"
    state = await hitl.get_hitl_state("inv-1003")
    assert state["paused_at_step"] == "awaiting_human_decision"
    assert "timeout_at" in state


async def test_decision_made_idempotent():
    """Receiving the same event twice must not create duplicate tasks."""
    store = MockTaskStore()
    hitl = MockHITLState()
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    await svc.handle_decision_made(_DECISION_MADE_EVENT)
    await svc.handle_decision_made(_DECISION_MADE_EVENT)  # duplicate

    pending = await store.get_all_pending()
    assert len(pending) == 1, f"Expected 1 task, got {len(pending)}"


async def test_approve_publishes_event():
    """
    POST /decide(action=APPROVE) must:
    - update task status to APPROVED
    - delete HITL state from Dapr
    - publish approval.decided with action=APPROVE
    """
    store = MockTaskStore()
    hitl = MockHITLState()
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    # Create the task and hitl state first
    await svc.handle_decision_made(_DECISION_MADE_EVENT)

    result = await svc.decide(
        submission_id="inv-1003",
        action="APPROVE",
        decided_by="john.smith@northwind.example",
        notes="Client is a major account — approved.",
        correlation_id="c-1003",
    )

    assert result["status"] == "APPROVE", f"Expected APPROVE, got {result['status']}"
    assert not hitl.has_state("inv-1003"), "HITL state must be deleted after decision"

    event = publish.last_event()
    assert event is not None
    assert event["action"] == "APPROVE"
    assert event["decided_by"] == "john.smith@northwind.example"
    assert event["submission_id"] == "inv-1003"
    assert "department_id" in event  # needed by payment-service


async def test_reject_publishes_event():
    """POST /decide(action=REJECT) must publish approval.decided(action=REJECT)."""
    store = MockTaskStore()
    hitl = MockHITLState()
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    await svc.handle_decision_made(_DECISION_MADE_EVENT)

    result = await svc.decide(
        submission_id="inv-1003",
        action="REJECT",
        decided_by="john.smith@northwind.example",
        notes="Cannot justify this expense.",
        correlation_id="c-1003",
    )

    assert result["status"] == "REJECT"
    event = publish.last_event()
    assert event["action"] == "REJECT"
    assert not hitl.has_state("inv-1003")


async def test_request_info_publishes_event():
    """POST /decide(action=REQUEST_INFO) must publish approval.decided(action=REQUEST_INFO)."""
    store = MockTaskStore()
    hitl = MockHITLState()
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    await svc.handle_decision_made(_DECISION_MADE_EVENT)

    result = await svc.decide(
        submission_id="inv-1003",
        action="REQUEST_INFO",
        decided_by="john.smith@northwind.example",
        notes="Please provide attendee list.",
        correlation_id="c-1003",
    )

    assert result["status"] == "REQUEST_INFO"
    event = publish.last_event()
    assert event["action"] == "REQUEST_INFO"
    assert not hitl.has_state("inv-1003")


async def test_restart_recovery():
    """
    If a PENDING task exists in DB but its HITL state is absent (e.g. Redis cleared),
    startup recovery must restore the state.
    """
    store = MockTaskStore()
    hitl = MockHITLState()   # starts empty — simulates Redis data loss after restart
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    # Seed the DB with a PENDING task (no corresponding HITL state)
    timeout_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()
    store.seed({
        "submission_id": "inv-1003",
        "tracking_id": "t-1003",
        "correlation_id": "c-1003",
        "status": "PENDING",
        "amount_usd": 1820.0,
        "vendor": "The Capital Grille",
        "category": "meals",
        "agent_recommendation": None,
        "policy_violations": [],
        "plain_language_reason": "Escalated for review.",
        "paused_timestamp": datetime.now(timezone.utc).isoformat(),
        "timeout_at": timeout_at,
    })

    assert not hitl.has_state("inv-1003"), "Pre-condition: HITL state must be absent"

    restored = await svc.recover_pending_tasks()

    assert restored == 1, f"Expected 1 restored task, got {restored}"
    assert hitl.has_state("inv-1003"), "HITL state must be restored"
    state = await hitl.get_hitl_state("inv-1003")
    assert state["paused_at_step"] == "awaiting_human_decision"
    assert state["submission_id"] == "inv-1003"


async def test_queue_returns_pending_only():
    """GET /approvals/queue must return only PENDING tasks, not APPROVED/REJECTED."""
    store = MockTaskStore()
    hitl = MockHITLState()
    publish = MockPublishClient()
    svc = _make_service(store, hitl, publish)

    timeout_at = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

    # One PENDING task
    store.seed({
        "submission_id": "inv-1003", "status": "PENDING",
        "amount_usd": 1820.0, "vendor": "The Capital Grille",
        "category": "meals", "timeout_at": timeout_at,
    })
    # One already APPROVED
    store.seed({
        "submission_id": "inv-1004", "status": "APPROVED",
        "amount_usd": 500.0, "vendor": "Delta Airlines",
        "category": "travel", "timeout_at": timeout_at,
    })
    # One REJECTED
    store.seed({
        "submission_id": "inv-1005", "status": "REJECTED",
        "amount_usd": 60.0, "vendor": "Bistro 19",
        "category": "meals", "timeout_at": timeout_at,
    })

    queue = await svc.get_queue()

    assert len(queue) == 1, f"Queue must contain only PENDING tasks, got {len(queue)}"
    assert queue[0]["submission_id"] == "inv-1003"
    assert queue[0]["status"] == "PENDING"
