"""
SQLAlchemy-backed audit store. Append-only — no UPDATE, no DELETE.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import AsyncSessionLocal
from .models import AuditEvent

logger = logging.getLogger(__name__)


def _to_dict(e: AuditEvent) -> dict:
    return {
        "id": e.id,
        "event_id": e.event_id,
        "correlation_id": e.correlation_id,
        "submission_id": e.submission_id,
        "service_name": e.service_name,
        "event_type": e.event_type,
        "payload": e.payload,
        "actor": e.actor,
        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
    }


async def record_event(data: dict) -> Optional[dict]:
    """
    Insert a new audit event. Returns None (silently) if event_id already recorded.
    Guarantees append-only — no updates, no deletes.
    """
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(AuditEvent).where(AuditEvent.event_id == data["event_id"])
        )
        if existing is not None:
            return None

        ts_raw = data.get("timestamp")
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = datetime.now(timezone.utc)

        ev = AuditEvent(
            event_id=data["event_id"],
            correlation_id=data.get("correlation_id"),
            submission_id=data.get("submission_id"),
            service_name=data["service_name"],
            event_type=data["event_type"],
            payload=data.get("payload", {}),
            actor=data.get("actor"),
            timestamp=ts,
        )
        db.add(ev)
        try:
            await db.commit()
            await db.refresh(ev)
            return _to_dict(ev)
        except IntegrityError:
            # Race: another replica already inserted this event_id
            await db.rollback()
            return None


async def get_by_submission(submission_id: str) -> list:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(AuditEvent)
                .where(AuditEvent.submission_id == submission_id)
                .order_by(AuditEvent.timestamp)
            )
        ).all()
        return [_to_dict(r) for r in rows]


async def get_all() -> list:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(select(AuditEvent).order_by(AuditEvent.timestamp))
        ).all()
        return [_to_dict(r) for r in rows]
