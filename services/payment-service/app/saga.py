"""
Payment Saga — Choreography, 4 steps with compensation.

All external dependencies are injected so the saga is fully unit-testable
without a real database, Dapr sidecar, or payment provider.

Steps:
  1. RESERVE_BUDGET    — deduct from department budget via ETag/CAS
  2. CREATE_PAYMENT_RECORD — persist saga state to DB
  3. EXECUTE_PAYMENT   — call payment gateway (injectable failure for INV-1012)
  4. CONFIRM           — mark complete, publish payment.completed

Failure in any step triggers compensations in reverse order.
"""
import logging
import uuid
from decimal import Decimal
from typing import Callable

logger = logging.getLogger(__name__)


class PaymentSaga:
    def __init__(
        self,
        reserve_budget: Callable,       # async (dept_id, amount, corr_id) -> None
        release_budget: Callable,       # async (dept_id, amount, corr_id) -> None
        payment_gateway: Callable,      # async (submission_id, idem_key, amount, corr_id) -> str
        get_payment: Callable,          # async (submission_id) -> Optional[dict]
        create_payment: Callable,       # async (data: dict) -> dict
        update_payment: Callable,       # async (payment_id: str, **kwargs) -> dict
        publish_completed: Callable,    # async (data: dict, corr_id: str) -> None
        publish_failed: Callable,       # async (data: dict, corr_id: str) -> None
    ) -> None:
        self._reserve_budget = reserve_budget
        self._release_budget = release_budget
        self._payment_gateway = payment_gateway
        self._get_payment = get_payment
        self._create_payment = create_payment
        self._update_payment = update_payment
        self._publish_completed = publish_completed
        self._publish_failed = publish_failed

    async def execute(
        self,
        submission_id: str,
        tracking_id: str,
        amount_usd: float,
        department_id: str,
        correlation_id: str,
    ) -> dict:
        # ── Idempotency: return existing record if already processed ──────────
        existing = await self._get_payment(submission_id)
        if existing is not None:
            logger.info(
                "saga idempotent: payment already exists",
                extra={"correlation_id": correlation_id, "submission_id": submission_id, "status": existing.get("status")},
            )
            return existing

        amount = Decimal(str(amount_usd))

        # Create the initial DB record (status=INITIATED)
        payment = await self._create_payment(
            {
                "submission_id": submission_id,
                "tracking_id": tracking_id,
                "correlation_id": correlation_id,
                "amount_usd": amount_usd,
                "department_id": department_id,
                "status": "INITIATED",
                "saga_log": [],
            }
        )
        payment_id: str = payment["id"]
        completed_steps: list = []

        try:
            # ── Step 1: RESERVE_BUDGET ────────────────────────────────────────
            await self._reserve_budget(department_id, amount, correlation_id)
            completed_steps.append("RESERVE_BUDGET")
            payment = await self._update_payment(
                payment_id, status="RESERVED", saga_log=list(completed_steps)
            )
            logger.info("saga step 1 done", extra={"correlation_id": correlation_id, "step": "RESERVE_BUDGET"})

            # ── Step 2: CREATE_PAYMENT_RECORD ─────────────────────────────────
            completed_steps.append("CREATE_PAYMENT_RECORD")
            payment = await self._update_payment(
                payment_id, status="RECORD_CREATED", saga_log=list(completed_steps)
            )
            logger.info("saga step 2 done", extra={"correlation_id": correlation_id, "step": "CREATE_PAYMENT_RECORD"})

            # ── Step 3: EXECUTE_PAYMENT ───────────────────────────────────────
            idempotency_key = str(uuid.uuid5(uuid.NAMESPACE_DNS, submission_id))
            external_ref = await self._payment_gateway(
                submission_id, idempotency_key, float(amount), correlation_id
            )
            completed_steps.append("EXECUTE_PAYMENT")
            payment = await self._update_payment(
                payment_id,
                status="EXECUTED",
                external_payment_ref=external_ref,
                saga_log=list(completed_steps),
            )
            logger.info("saga step 3 done", extra={"correlation_id": correlation_id, "step": "EXECUTE_PAYMENT", "external_ref": external_ref})

            # ── Step 4: CONFIRM ───────────────────────────────────────────────
            payment = await self._update_payment(
                payment_id, status="COMPLETED", saga_log=list(completed_steps)
            )
            completed_steps.append("CONFIRM")

            await self._publish_completed(
                {
                    "submission_id": submission_id,
                    "tracking_id": tracking_id,
                    "correlation_id": correlation_id,
                    "external_payment_ref": external_ref,
                    "amount_usd": float(amount),
                },
                correlation_id,
            )
            logger.info(
                "saga completed",
                extra={"correlation_id": correlation_id, "submission_id": submission_id, "external_ref": external_ref},
            )
            return payment

        except Exception as exc:
            logger.error(
                "saga failed — running compensation",
                extra={
                    "correlation_id": correlation_id,
                    "submission_id": submission_id,
                    "error": str(exc),
                    "completed_steps": completed_steps,
                },
            )
            return await self._compensate(
                payment_id=payment_id,
                completed_steps=completed_steps,
                department_id=department_id,
                amount=amount,
                correlation_id=correlation_id,
                submission_id=submission_id,
                tracking_id=tracking_id,
                reason=str(exc),
            )

    async def _compensate(
        self,
        payment_id: str,
        completed_steps: list,
        department_id: str,
        amount: Decimal,
        correlation_id: str,
        submission_id: str,
        tracking_id: str,
        reason: str,
    ) -> dict:
        compensated: list = []

        for step in reversed(completed_steps):
            try:
                if step == "RESERVE_BUDGET":
                    await self._release_budget(department_id, amount, correlation_id)
                    compensated.append("RESERVE_BUDGET")
                elif step == "CREATE_PAYMENT_RECORD":
                    # DB record stays for audit; status updated to COMPENSATED below
                    compensated.append("CREATE_PAYMENT_RECORD")
                elif step == "EXECUTE_PAYMENT":
                    # Real system: call gateway void endpoint. Here: mark compensated.
                    compensated.append("EXECUTE_PAYMENT")
                elif step == "CONFIRM":
                    # A confirmed payment cannot be reversed — escalate to human
                    logger.error(
                        "cannot compensate CONFIRM step — manual intervention required",
                        extra={"correlation_id": correlation_id, "submission_id": submission_id},
                    )
            except Exception as comp_exc:
                logger.error(
                    "compensation step failed",
                    extra={"step": step, "error": str(comp_exc), "correlation_id": correlation_id},
                )

        payment = await self._update_payment(
            payment_id,
            status="COMPENSATED",
            failure_reason=reason,
            compensated_steps=compensated,
        )

        await self._publish_failed(
            {
                "submission_id": submission_id,
                "tracking_id": tracking_id,
                "correlation_id": correlation_id,
                "reason": reason,
                "compensated_steps": compensated,
            },
            correlation_id,
        )

        logger.info(
            "saga compensation complete",
            extra={
                "correlation_id": correlation_id,
                "submission_id": submission_id,
                "compensated_steps": compensated,
                "reason": reason,
            },
        )
        return payment
