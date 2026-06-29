"""
Simulated external payment gateway.
In production this would call an actual payment provider.
Failure injection: set PAYMENT_FAILURE_INJECT=<submission_id> to force Step 3 to fail.
"""
import uuid
import logging
from .config import settings
from . import inject as _inject_registry

logger = logging.getLogger(__name__)


class PaymentGatewayError(Exception):
    pass


async def simulate_payment_gateway(
    submission_id: str,
    idempotency_key: str,
    amount: float,
    correlation_id: str,
) -> str:
    """Returns an external payment reference string on success."""
    if _inject_registry.should_force_fail(submission_id):
        logger.warning(
            "payment gateway failure injected (runtime)",
            extra={"correlation_id": correlation_id, "submission_id": submission_id},
        )
        raise PaymentGatewayError(f"Runtime-injected failure for submission {submission_id}")

    inject = settings.payment_failure_inject.strip()
    if inject and inject.lower() not in ("false", "0", "") and inject in submission_id:
        logger.warning(
            "payment gateway failure injected",
            extra={"correlation_id": correlation_id, "submission_id": submission_id, "inject_key": inject},
        )
        raise PaymentGatewayError(f"Injected failure for submission {submission_id}")

    external_ref = f"PAY-{uuid.uuid5(uuid.NAMESPACE_DNS, idempotency_key).hex[:12].upper()}"
    logger.info(
        "payment gateway success",
        extra={
            "correlation_id": correlation_id,
            "submission_id": submission_id,
            "external_ref": external_ref,
            "amount": amount,
        },
    )
    return external_ref
