"""
Unit tests for the Payment Saga.

No database, no Dapr, no real network.
All external dependencies are replaced with in-memory mock implementations.
"""
import asyncio
import uuid
from decimal import Decimal
from typing import Dict, Optional

import pytest

from app.budget import InsufficientBudgetError
from app.saga import PaymentSaga


# ─── Mock implementations ─────────────────────────────────────────────────────


class MockBudgetClient:
    """
    Thread-safe (asyncio-safe) in-memory budget store.
    Uses an asyncio.Lock to simulate the atomicity of ETag/CAS in real Dapr.
    """

    def __init__(self, initial_balance: float = 10000.0):
        self._balances: Dict[str, float] = {}
        self._default_balance = initial_balance
        self._lock = asyncio.Lock()

    def set_balance(self, dept_id: str, balance: float) -> None:
        self._balances[dept_id] = balance

    def get_balance(self, dept_id: str) -> float:
        return self._balances.get(dept_id, self._default_balance)

    async def reserve(self, dept_id: str, amount: Decimal, corr_id: str) -> None:
        async with self._lock:
            balance = Decimal(str(self._balances.get(dept_id, self._default_balance)))
            if balance < amount:
                raise InsufficientBudgetError(
                    f"{dept_id}: balance {balance} < required {amount}"
                )
            self._balances[dept_id] = float(balance - amount)

    async def release(self, dept_id: str, amount: Decimal, corr_id: str) -> None:
        async with self._lock:
            balance = self._balances.get(dept_id, self._default_balance)
            self._balances[dept_id] = balance + float(amount)


class MockPaymentStore:
    """In-memory payment store keyed by submission_id."""

    def __init__(self):
        self._by_submission: Dict[str, dict] = {}
        self._by_id: Dict[str, dict] = {}

    async def get_payment(self, submission_id: str) -> Optional[dict]:
        return self._by_submission.get(submission_id)

    async def create_payment(self, data: dict) -> dict:
        record = {**data, "id": str(uuid.uuid4())}
        self._by_submission[data["submission_id"]] = record
        self._by_id[record["id"]] = record
        return record

    async def update_payment(self, payment_id: str, **kwargs) -> dict:
        record = self._by_id[payment_id]
        record.update(kwargs)
        return record


class MockGateway:
    """Deterministic mock payment gateway. Call count is observable for idempotency tests."""

    def __init__(self, should_fail: bool = False):
        self._should_fail = should_fail
        self.call_count = 0

    async def execute(
        self, submission_id: str, idempotency_key: str, amount: float, corr_id: str
    ) -> str:
        self.call_count += 1
        if self._should_fail:
            raise RuntimeError("Payment gateway failure (injected for test)")
        return f"PAY-{uuid.uuid4().hex[:12].upper()}"


class MockPublishClient:
    """Captures all published events for assertion in tests."""

    def __init__(self):
        self.completed: list = []
        self.failed: list = []

    async def publish_completed(self, data: dict, corr_id: str) -> None:
        self.completed.append(data)

    async def publish_failed(self, data: dict, corr_id: str) -> None:
        self.failed.append(data)


def _make_saga(budget: MockBudgetClient, gateway: MockGateway, store: MockPaymentStore, publish: MockPublishClient) -> PaymentSaga:
    return PaymentSaga(
        reserve_budget=budget.reserve,
        release_budget=budget.release,
        payment_gateway=gateway.execute,
        get_payment=store.get_payment,
        create_payment=store.create_payment,
        update_payment=store.update_payment,
        publish_completed=publish.publish_completed,
        publish_failed=publish.publish_failed,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────


async def test_saga_happy_path():
    """All 4 steps complete: RESERVED → RECORD_CREATED → EXECUTED → COMPLETED."""
    budget = MockBudgetClient(initial_balance=10000.0)
    gateway = MockGateway(should_fail=False)
    store = MockPaymentStore()
    publish = MockPublishClient()
    saga = _make_saga(budget, gateway, store, publish)

    result = await saga.execute(
        submission_id="inv-1001",
        tracking_id="t-1001",
        amount_usd=42.0,
        department_id="marketing-2026Q2",
        correlation_id="c-1001",
    )

    assert result["status"] == "COMPLETED", f"Expected COMPLETED, got {result['status']}"
    assert len(publish.completed) == 1, "payment.completed must be published exactly once"
    assert len(publish.failed) == 0, "payment.failed must not be published on success"
    assert budget.get_balance("marketing-2026Q2") == pytest.approx(10000.0 - 42.0)
    assert result["external_payment_ref"] is not None


async def test_saga_compensation_inv1012():
    """
    Step 3 (EXECUTE_PAYMENT) fails → compensations run in reverse →
    status=COMPENSATED, budget fully restored, payment.failed published.
    """
    budget = MockBudgetClient(initial_balance=10000.0)
    gateway = MockGateway(should_fail=True)  # inject failure at Step 3
    store = MockPaymentStore()
    publish = MockPublishClient()
    saga = _make_saga(budget, gateway, store, publish)

    initial_balance = budget.get_balance("engineering-2026Q2")

    result = await saga.execute(
        submission_id="inv-1012",
        tracking_id="t-1012",
        amount_usd=9500.0,
        department_id="engineering-2026Q2",
        correlation_id="c-1012",
    )

    assert result["status"] == "COMPENSATED", f"Expected COMPENSATED, got {result['status']}"
    assert result["failure_reason"] is not None, "failure_reason must be set"

    # payment.failed must be published with compensated_steps
    assert len(publish.failed) == 1, "payment.failed must be published"
    assert len(publish.completed) == 0, "payment.completed must not be published on failure"
    failed_event = publish.failed[0]
    assert "compensated_steps" in failed_event
    assert len(failed_event["compensated_steps"]) > 0

    # RESERVE_BUDGET must appear in compensated_steps (budget was reserved in Step 1)
    assert "RESERVE_BUDGET" in result["compensated_steps"], \
        f"compensated_steps: {result['compensated_steps']}"

    # Budget must be fully restored — no orphaned reservation
    final_balance = budget.get_balance("engineering-2026Q2")
    assert final_balance == pytest.approx(initial_balance), \
        f"Budget must be restored to {initial_balance}, got {final_balance}"


async def test_idempotency_double_payment():
    """
    Sending the same submission_id twice must not result in a second payment.
    Gateway is called exactly once; the second call returns the existing record.
    """
    budget = MockBudgetClient(initial_balance=10000.0)
    gateway = MockGateway(should_fail=False)
    store = MockPaymentStore()
    publish = MockPublishClient()
    saga = _make_saga(budget, gateway, store, publish)

    result1 = await saga.execute(
        submission_id="inv-1001",
        tracking_id="t-1001",
        amount_usd=42.0,
        department_id="marketing-2026Q2",
        correlation_id="c-1001",
    )
    result2 = await saga.execute(
        submission_id="inv-1001",   # same submission_id — duplicate
        tracking_id="t-1001",
        amount_usd=42.0,
        department_id="marketing-2026Q2",
        correlation_id="c-1001-retry",
    )

    assert result1["id"] == result2["id"], "Both calls must return the same payment record"
    assert gateway.call_count == 1, \
        f"Gateway must be called exactly once, was called {gateway.call_count} times"
    # Budget deducted once, not twice
    assert budget.get_balance("marketing-2026Q2") == pytest.approx(10000.0 - 42.0)


async def test_concurrent_budget_inv1014():
    """
    Two concurrent $600 sagas sharing a $1,000 department budget.
    Exactly one must succeed (COMPLETED) and one must fail (COMPENSATED).
    Final budget balance must be $400 (not negative).
    """
    budget = MockBudgetClient()
    budget.set_balance("marketing-2026Q2", 1000.0)
    gateway = MockGateway(should_fail=False)
    store = MockPaymentStore()
    publish = MockPublishClient()
    saga = _make_saga(budget, gateway, store, publish)

    results = await asyncio.gather(
        saga.execute("inv-1014A", "t-1014A", 600.0, "marketing-2026Q2", "c-1014A"),
        saga.execute("inv-1014B", "t-1014B", 600.0, "marketing-2026Q2", "c-1014B"),
        return_exceptions=True,
    )

    # Both should return dicts (exceptions are caught inside the saga and converted to COMPENSATED)
    assert all(isinstance(r, dict) for r in results), \
        f"Both results should be dicts, got: {[type(r) for r in results]}"

    statuses = [r["status"] for r in results]
    assert statuses.count("COMPLETED") == 1, f"Exactly 1 must succeed, got: {statuses}"
    assert statuses.count("COMPENSATED") == 1, f"Exactly 1 must be compensated, got: {statuses}"

    final_balance = budget.get_balance("marketing-2026Q2")
    assert final_balance >= 0, f"Budget must not go negative, got: {final_balance}"
    assert final_balance == pytest.approx(400.0), \
        f"Final balance should be 400 (1000 - 600), got: {final_balance}"
