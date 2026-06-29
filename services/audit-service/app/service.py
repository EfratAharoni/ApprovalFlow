"""
AuditService — append-only event log with analytics.

All storage is injected so the service is fully unit-testable offline.
"""
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from .config import settings

logger = logging.getLogger(__name__)

# ── Topic metadata ─────────────────────────────────────────────────────────────

_TOPIC_SERVICE = {
    "submission.created": "submission-service",
    "decision.made": "ai-agent-service",
    "approval.decided": "approval-service",
    "payment.completed": "payment-service",
    "payment.failed": "payment-service",
}


def _service_for_topic(topic: str) -> str:
    return _TOPIC_SERVICE.get(topic, "unknown")


def _actor_for_topic(topic: str, payload: dict) -> Optional[str]:
    if topic == "submission.created":
        return payload.get("submitted_by")
    if topic == "decision.made":
        return "ai-agent-service"
    if topic == "approval.decided":
        return payload.get("decided_by") or "approver"
    if topic in ("payment.completed", "payment.failed"):
        return "payment-service"
    return "system"


class AuditService:
    def __init__(
        self,
        record_event: Callable,      # async (data: dict) -> Optional[dict]
        get_by_submission: Callable, # async (submission_id: str) -> list
        get_all: Callable,           # async () -> list
    ) -> None:
        self._record = record_event
        self._get_by_submission = get_by_submission
        self._get_all = get_all

    # ── Event ingestion ───────────────────────────────────────────────────────

    async def handle_event(
        self,
        topic: str,
        payload: dict,
        dapr_event_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        """Record a single audit event. Silently skips duplicates."""
        result = await self._record(
            {
                "event_id": dapr_event_id,
                "correlation_id": payload.get("correlation_id"),
                "submission_id": payload.get("submission_id"),
                "service_name": _service_for_topic(topic),
                "event_type": topic,
                "payload": payload,
                "actor": _actor_for_topic(topic, payload),
                "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            }
        )
        if result is None:
            logger.debug("duplicate event skipped", extra={"event_id": dapr_event_id, "topic": topic})
        else:
            logger.info(
                "audit event recorded",
                extra={
                    "correlation_id": payload.get("correlation_id"),
                    "submission_id": payload.get("submission_id"),
                    "topic": topic,
                    "actor": _actor_for_topic(topic, payload),
                },
            )

    # ── Queries ───────────────────────────────────────────────────────────────

    async def get_trail(self, submission_id: str) -> list:
        """Full decision trail for a submission, ordered by timestamp (F9)."""
        return await self._get_by_submission(submission_id)

    async def get_dashboard(self) -> dict:
        """Aggregate statistics across all submissions (F8)."""
        events = await self._get_all()

        # Count unique submissions (by submission.created events)
        submission_ids_seen = set()
        for e in events:
            if e["event_type"] == "submission.created" and e.get("submission_id"):
                submission_ids_seen.add(e["submission_id"])
        total_submissions = len(submission_ids_seen)

        # Decision counts (from decision.made events)
        auto_approved = 0
        human_reviewed = 0
        rejected = 0
        duplicates = 0
        total_amount_auto = 0.0

        for e in events:
            if e["event_type"] != "decision.made":
                continue
            route = e["payload"].get("route", "")
            if route == "auto_approve":
                auto_approved += 1
                try:
                    total_amount_auto += float(e["payload"].get("amount_usd") or 0)
                except (ValueError, TypeError):
                    pass
            elif route == "human_review":
                human_reviewed += 1
            elif route == "reject":
                rejected += 1
            elif route == "duplicate":
                duplicates += 1

        # Human-approved payment amounts (from approval.decided where action=APPROVE)
        total_amount_human = 0.0
        for e in events:
            if e["event_type"] == "approval.decided" and e["payload"].get("action") == "APPROVE":
                try:
                    total_amount_human += float(e["payload"].get("amount_usd") or 0)
                except (ValueError, TypeError):
                    pass

        # Auto-approval rate over all decided (non-duplicate) submissions
        total_decided = auto_approved + human_reviewed + rejected
        auto_rate = round(auto_approved / total_decided, 4) if total_decided > 0 else 0.0

        # Average processing time: submission.created → payment.completed per submission_id
        created_at: dict = {}
        completed_at: dict = {}
        for e in events:
            sid = e.get("submission_id")
            if not sid:
                continue
            if e["event_type"] == "submission.created":
                created_at[sid] = e["timestamp"]
            elif e["event_type"] == "payment.completed":
                completed_at[sid] = e["timestamp"]

        deltas = []
        for sid, start in created_at.items():
            end = completed_at.get(sid)
            if end and start:
                try:
                    t0 = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(end.replace("Z", "+00:00"))
                    deltas.append((t1 - t0).total_seconds())
                except (ValueError, TypeError):
                    pass
        avg_time = round(sum(deltas) / len(deltas), 2) if deltas else 0.0

        return {
            "total_submissions": total_submissions,
            "auto_approved": auto_approved,
            "human_reviewed": human_reviewed,
            "rejected": rejected,
            "duplicates": duplicates,
            "auto_approval_rate": auto_rate,
            "total_amount_auto_approved": round(total_amount_auto, 2),
            "total_amount_human_approved": round(total_amount_human, 2),
            "avg_processing_time_seconds": avg_time,
        }

    async def prove_ceiling(self, ceiling: Optional[float] = None) -> dict:
        """
        M12 ceiling proof endpoint (F10 / D5).
        Returns all auto_approve decisions, the maximum amount among them,
        and whether that maximum exceeds the configured ceiling.
        violation_found=True means the ceiling guard failed — this should never happen.
        """
        if ceiling is None:
            ceiling = settings.autonomy_ceiling

        events = await self._get_all()
        auto_approve_records = [
            e for e in events
            if e["event_type"] == "decision.made"
            and e["payload"].get("route") == "auto_approve"
        ]

        amounts = []
        for rec in auto_approve_records:
            try:
                amounts.append(float(rec["payload"].get("amount_usd") or 0))
            except (ValueError, TypeError):
                pass

        max_amount = max(amounts) if amounts else 0.0

        return {
            "ceiling": ceiling,
            "max_auto_approved_amount": max_amount,
            "violation_found": max_amount > ceiling,
            "records": auto_approve_records,
        }
