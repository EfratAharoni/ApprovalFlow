"""
Department budget management via Dapr state store with ETag/CAS.
Prevents double-spend under concurrent saga executions (INV-1014 scenario).
"""
import logging
from decimal import Decimal

from . import dapr_client

logger = logging.getLogger(__name__)

_RETRY_LIMIT = 3

_DEFAULT_BUDGETS = {
    "marketing-2026Q2": 1000.0,
    "engineering-2026Q2": 50000.0,
    "sales-2026Q2": 20000.0,
}


class InsufficientBudgetError(Exception):
    pass


class BudgetCASError(Exception):
    pass


def _budget_key(department_id: str) -> str:
    return f"budget:{department_id}"


def _default_balance(department_id: str) -> float:
    return _DEFAULT_BUDGETS.get(department_id, 10000.0)


async def reserve_budget(department_id: str, amount: Decimal, correlation_id: str) -> None:
    """Deduct amount from department budget using ETag/CAS. Raises on insufficient funds."""
    key = _budget_key(department_id)
    for attempt in range(1, _RETRY_LIMIT + 1):
        data, etag = await dapr_client.get_state_with_etag(key)
        balance = Decimal(str(data.get("balance", _default_balance(department_id))))
        if balance < amount:
            raise InsufficientBudgetError(
                f"{department_id}: balance {balance} < required {amount}"
            )
        new_balance = float(balance - amount)
        saved = await dapr_client.save_state_with_etag(key, {"balance": new_balance}, etag)
        if saved:
            logger.info(
                "budget reserved",
                extra={
                    "correlation_id": correlation_id,
                    "department_id": department_id,
                    "amount": str(amount),
                    "new_balance": new_balance,
                },
            )
            return
        logger.warning(
            "budget CAS conflict, retrying",
            extra={"correlation_id": correlation_id, "attempt": attempt, "department_id": department_id},
        )
    raise BudgetCASError(f"budget reserve failed after {_RETRY_LIMIT} retries for {department_id}")


async def release_budget(department_id: str, amount: Decimal, correlation_id: str) -> None:
    """Add amount back to department budget — compensation step. Best-effort with retries."""
    key = _budget_key(department_id)
    for attempt in range(1, _RETRY_LIMIT + 1):
        data, etag = await dapr_client.get_state_with_etag(key)
        balance = Decimal(str(data.get("balance", _default_balance(department_id))))
        new_balance = float(balance + amount)
        saved = await dapr_client.save_state_with_etag(key, {"balance": new_balance}, etag)
        if saved:
            logger.info(
                "budget released",
                extra={
                    "correlation_id": correlation_id,
                    "department_id": department_id,
                    "amount": str(amount),
                },
            )
            return
        logger.warning(
            "budget release CAS conflict, retrying",
            extra={"correlation_id": correlation_id, "attempt": attempt},
        )
    logger.error(
        "budget release failed after retries — manual reconciliation needed",
        extra={"correlation_id": correlation_id, "department_id": department_id, "amount": str(amount)},
    )
