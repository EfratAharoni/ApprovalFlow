"""
ApprovalService — HITL escalation queue.

All external dependencies are injected so the service is fully unit-testable
without a real database or Dapr sidecar.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

from .config import settings

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"APPROVE", "REJECT", "REQUEST_INFO"}

_CATEGORY_TO_DEPT = {
    "meals": "marketing-2026Q2",
    "travel": "sales-2026Q2",
    "hardware": "engineering-2026Q2",
    "saas": "engineering-2026Q2",
}


def _dept(category: Optional[str]) -> str:
    return _CATEGORY_TO_DEPT.get((category or "").lower(), "engineering-2026Q2")


def _build_hitl_state(task: dict) -> dict:
    timeout_at = task.get("timeout_at") or (
        datetime.now(timezone.utc) + timedelta(hours=settings.hitl_timeout_hours)
    ).isoformat()
    return {
        "submission_id": task["submission_id"],
        "tracking_id": task.get("tracking_id", ""),
        "correlation_id": task.get("correlation_id", ""),
        "paused_at_step": "awaiting_human_decision",
        "agent_recommendation": task.get("agent_recommendation"),
        "policy_violations": task.get("policy_violations", []),
        "plain_language_reason": task.get("plain_language_reason", ""),
        "amount_usd": str(task.get("amount_usd") or "0"),
        "vendor": task.get("vendor", ""),
        "category": task.get("category", ""),
        "paused_timestamp": task.get("paused_timestamp") or datetime.now(timezone.utc).isoformat(),
        "timeout_at": timeout_at,
    }


class ApprovalService:
    def __init__(
        self,
        get_task: Callable,             # async (submission_id) -> Optional[dict]
        get_all_pending: Callable,      # async () -> list[dict]
        create_task: Callable,          # async (data: dict) -> dict
        update_task: Callable,          # async (submission_id, **kwargs) -> dict
        save_hitl_state: Callable,      # async (submission_id, state: dict) -> None
        get_hitl_state: Callable,       # async (submission_id) -> Optional[dict]
        delete_hitl_state: Callable,    # async (submission_id) -> None
        publish_decided: Callable,      # async (data: dict, corr_id: str) -> None
    ) -> None:
        self._get_task = get_task
        self._get_all_pending = get_all_pending
        self._create_task = create_task
        self._update_task = update_task
        self._save_hitl_state = save_hitl_state
        self._get_hitl_state = get_hitl_state
        self._delete_hitl_state = delete_hitl_state
        self._publish_decided = publish_decided

    # ── Event handler ─────────────────────────────────────────────────────────

    async def handle_decision_made(self, event_data: dict) -> None:
        """Create an escalation task for a human_review decision."""
        submission_id = event_data["submission_id"]
        correlation_id = event_data.get("correlation_id", "")

        # Idempotency: skip if task already exists
        existing = await self._get_task(submission_id)
        if existing is not None:
            logger.info(
                "task already exists (idempotent)",
                extra={"correlation_id": correlation_id, "submission_id": submission_id},
            )
            return

        agent_rec = event_data.get("agent_recommendation")
        confidence = agent_rec.get("confidence") if isinstance(agent_rec, dict) else None
        timeout_at = (
            datetime.now(timezone.utc) + timedelta(hours=settings.hitl_timeout_hours)
        ).isoformat()

        task_data = {
            "submission_id": submission_id,
            "tracking_id": event_data.get("tracking_id", ""),
            "correlation_id": correlation_id,
            "amount_usd": float(event_data.get("amount_usd") or 0),
            "vendor": event_data.get("vendor", ""),
            "category": event_data.get("category", ""),
            "submitted_by": event_data.get("submitted_by", ""),
            "agent_recommendation": agent_rec,
            "confidence": confidence,
            "policy_violations": event_data.get("policy_violations", []),
            "plain_language_reason": event_data.get("plain_language_reason", ""),
            "status": "PENDING",
            "timeout_at": timeout_at,
        }

        task = await self._create_task(task_data)

        hitl_state = _build_hitl_state(task)
        await self._save_hitl_state(submission_id, hitl_state)

        logger.info(
            "escalation task created",
            extra={
                "correlation_id": correlation_id,
                "submission_id": submission_id,
                "vendor": task.get("vendor"),
                "amount_usd": task.get("amount_usd"),
            },
        )

    # ── Approver actions ──────────────────────────────────────────────────────

    async def decide(
        self,
        submission_id: str,
        action: str,
        decided_by: str,
        notes: str,
        correlation_id: str = "",
    ) -> dict:
        """Record a human decision and resume the workflow."""
        action = action.upper()
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action '{action}'. Must be one of {_VALID_ACTIONS}")

        task = await self._get_task(submission_id)
        if task is None:
            raise ValueError(f"No task found for submission {submission_id}")
        if task["status"] != "PENDING":
            raise ValueError(
                f"Task {submission_id} is not PENDING (current: {task['status']})"
            )

        effective_corr = correlation_id or task.get("correlation_id", "")

        task = await self._update_task(
            submission_id,
            status=action,
            decided_by=decided_by,
            notes=notes,
            decision_at=datetime.now(timezone.utc).isoformat(),
        )

        await self._delete_hitl_state(submission_id)

        event_payload = {
            "submission_id": submission_id,
            "tracking_id": task.get("tracking_id", ""),
            "correlation_id": effective_corr,
            "action": action,
            "decided_by": decided_by,
            "notes": notes,
            "amount_usd": str(task.get("amount_usd") or "0"),
            "vendor": task.get("vendor", ""),
            "category": task.get("category", ""),
            "department_id": _dept(task.get("category")),
        }
        await self._publish_decided(event_payload, effective_corr)

        logger.info(
            "decision recorded",
            extra={
                "correlation_id": effective_corr,
                "submission_id": submission_id,
                "action": action,
                "decided_by": decided_by,
            },
        )
        return task

    async def get_queue(self) -> list:
        """Return all PENDING tasks for the approver UI."""
        return await self._get_all_pending()

    async def get_task(self, submission_id: str) -> Optional[dict]:
        return await self._get_task(submission_id)

    # ── Startup recovery ──────────────────────────────────────────────────────

    async def recover_pending_tasks(self) -> int:
        """
        On startup: ensure every PENDING DB task has a corresponding HITL state.
        Recreates state for any task whose state was lost (e.g. Redis restart).
        Returns the number of tasks restored.
        """
        pending = await self._get_all_pending()
        restored = 0
        for task in pending:
            state = await self._get_hitl_state(task["submission_id"])
            if state is None:
                await self._save_hitl_state(task["submission_id"], _build_hitl_state(task))
                restored += 1
                logger.info(
                    "hitl state recovered",
                    extra={
                        "submission_id": task["submission_id"],
                        "correlation_id": task.get("correlation_id"),
                    },
                )
        if restored:
            logger.info("startup recovery complete", extra={"restored": restored})
        return restored

    # ── Timeout sweep ─────────────────────────────────────────────────────────

    async def check_timeouts(self, timed_out_tasks: list) -> int:
        """
        Process a list of timed-out PENDING tasks (filtered externally).
        Marks each TIMED_OUT and publishes approval.decided(action=TIMEOUT).
        Returns count processed.
        """
        count = 0
        for task in timed_out_tasks:
            sid = task["submission_id"]
            corr_id = task.get("correlation_id", "")
            try:
                await self._update_task(sid, status="TIMED_OUT")
                await self._delete_hitl_state(sid)
                await self._publish_decided(
                    {
                        "submission_id": sid,
                        "tracking_id": task.get("tracking_id", ""),
                        "correlation_id": corr_id,
                        "action": "TIMEOUT",
                        "decided_by": "system",
                        "notes": "Approval timed out after 48 hours",
                        "amount_usd": str(task.get("amount_usd") or "0"),
                        "vendor": task.get("vendor", ""),
                        "category": task.get("category", ""),
                        "department_id": _dept(task.get("category")),
                    },
                    corr_id,
                )
                count += 1
                logger.warning(
                    "task timed out",
                    extra={"submission_id": sid, "correlation_id": corr_id},
                )
            except Exception as exc:
                logger.error(
                    "timeout processing failed",
                    extra={"submission_id": sid, "error": str(exc)},
                )
        return count
