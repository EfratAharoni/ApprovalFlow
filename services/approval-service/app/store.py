"""
SQLAlchemy-backed approval task store.
Each function opens its own session.
"""
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import attributes

from .config import settings
from .database import AsyncSessionLocal
from .models import ApprovalTask

logger = logging.getLogger(__name__)


def _to_dict(t: ApprovalTask) -> dict:
    def _iso(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt is not None else None

    return {
        "id": t.id,
        "submission_id": t.submission_id,
        "tracking_id": t.tracking_id,
        "correlation_id": t.correlation_id,
        "amount_usd": float(t.amount_usd) if t.amount_usd is not None else None,
        "vendor": t.vendor,
        "category": t.category,
        "submitted_by": t.submitted_by,
        "agent_recommendation": t.agent_recommendation,
        "confidence": t.confidence,
        "policy_violations": t.policy_violations or [],
        "plain_language_reason": t.plain_language_reason,
        "status": t.status,
        "decided_by": t.decided_by,
        "decision_at": _iso(t.decision_at),
        "notes": t.notes,
        "paused_timestamp": _iso(t.paused_timestamp),
        "timeout_at": _iso(t.timeout_at),
    }


async def get_task(submission_id: str) -> Optional[dict]:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(
            select(ApprovalTask).where(ApprovalTask.submission_id == submission_id)
        )
        return _to_dict(row) if row is not None else None


async def get_all_pending() -> list:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(ApprovalTask).where(ApprovalTask.status == "PENDING")
            )
        ).all()
        return [_to_dict(r) for r in rows]


async def get_timed_out() -> list:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(ApprovalTask).where(
                    ApprovalTask.status == "PENDING",
                    ApprovalTask.timeout_at < now,
                )
            )
        ).all()
        return [_to_dict(r) for r in rows]


async def create_task(data: dict) -> dict:
    async with AsyncSessionLocal() as db:
        timeout_at_raw = data.get("timeout_at")
        if isinstance(timeout_at_raw, str):
            timeout_at = datetime.fromisoformat(timeout_at_raw.replace("Z", "+00:00"))
            if timeout_at.tzinfo is None:
                timeout_at = timeout_at.replace(tzinfo=timezone.utc)
        elif isinstance(timeout_at_raw, datetime):
            timeout_at = timeout_at_raw
        else:
            timeout_at = datetime.now(timezone.utc) + timedelta(hours=settings.hitl_timeout_hours)

        t = ApprovalTask(
            submission_id=data["submission_id"],
            tracking_id=data.get("tracking_id"),
            correlation_id=data.get("correlation_id"),
            amount_usd=Decimal(str(data["amount_usd"])) if data.get("amount_usd") is not None else None,
            vendor=data.get("vendor"),
            category=data.get("category"),
            submitted_by=data.get("submitted_by"),
            agent_recommendation=data.get("agent_recommendation"),
            confidence=data.get("confidence"),
            policy_violations=data.get("policy_violations", []),
            plain_language_reason=data.get("plain_language_reason"),
            status=data.get("status", "PENDING"),
            paused_timestamp=datetime.now(timezone.utc),
            timeout_at=timeout_at,
        )
        db.add(t)
        await db.commit()
        await db.refresh(t)
        return _to_dict(t)


async def update_task(submission_id: str, **kwargs) -> dict:
    async with AsyncSessionLocal() as db:
        t = await db.scalar(
            select(ApprovalTask).where(ApprovalTask.submission_id == submission_id)
        )
        if t is None:
            raise ValueError(f"ApprovalTask not found: {submission_id}")
        for key, value in kwargs.items():
            if key == "decision_at" and isinstance(value, str):
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            setattr(t, key, value)
            if key in ("policy_violations", "agent_recommendation"):
                attributes.flag_modified(t, key)
        await db.commit()
        await db.refresh(t)
        return _to_dict(t)
