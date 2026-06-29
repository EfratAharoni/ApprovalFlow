"""
SQLAlchemy-backed payment store. Exposes the same callable interface as MockPaymentStore.
Each function opens its own session so saga steps are independently committed.
"""
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import attributes

from .database import AsyncSessionLocal
from .models import Payment

logger = logging.getLogger(__name__)


def _to_dict(p: Payment) -> dict:
    return {
        "id": p.id,
        "submission_id": p.submission_id,
        "tracking_id": p.tracking_id,
        "correlation_id": p.correlation_id,
        "amount_usd": float(p.amount_usd) if p.amount_usd is not None else None,
        "department_id": p.department_id,
        "status": p.status,
        "external_payment_ref": p.external_payment_ref,
        "saga_log": p.saga_log or [],
        "compensated_steps": p.compensated_steps,
        "failure_reason": p.failure_reason,
    }


async def get_payment(submission_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(Payment).where(Payment.submission_id == submission_id))
        return _to_dict(row) if row is not None else None


async def create_payment(data: dict) -> dict:
    async with AsyncSessionLocal() as db:
        p = Payment(
            submission_id=data["submission_id"],
            tracking_id=data.get("tracking_id"),
            correlation_id=data.get("correlation_id"),
            amount_usd=Decimal(str(data["amount_usd"])),
            department_id=data.get("department_id"),
            status=data.get("status", "INITIATED"),
            saga_log=data.get("saga_log", []),
        )
        db.add(p)
        await db.commit()
        await db.refresh(p)
        return _to_dict(p)


async def update_payment(payment_id: str, **kwargs) -> dict:
    async with AsyncSessionLocal() as db:
        p = await db.scalar(select(Payment).where(Payment.id == payment_id))
        if p is None:
            raise ValueError(f"Payment {payment_id} not found")
        for key, value in kwargs.items():
            setattr(p, key, value)
            # Explicitly mark JSONB columns as modified so SQLAlchemy tracks the change
            if key in ("saga_log", "compensated_steps"):
                attributes.flag_modified(p, key)
        await db.commit()
        await db.refresh(p)
        return _to_dict(p)
