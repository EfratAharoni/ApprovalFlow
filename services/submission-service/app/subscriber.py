"""
SubmissionStatusService — updates submission status from downstream event topics.

All I/O is injected so the class is fully testable without a real database or Dapr.
"""
import logging
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


class SubmissionStatusService:
    def __init__(
        self,
        get_by_tracking_id: Callable[[str], Awaitable[Optional[dict]]],
        update_submission: Callable[..., Awaitable[dict]],
    ) -> None:
        self._get = get_by_tracking_id
        self._update = update_submission

    async def handle_decision_made(self, payload: dict) -> None:
        route = payload.get("route", "")
        status_map = {
            "auto_approve": "APPROVED",
            "human_review": "ESCALATED",
            "reject": "REJECTED",
            "duplicate": "DUPLICATE",
        }
        status = status_map.get(route)
        if not status:
            logger.warning("handle_decision_made: unknown route %r", route)
            return
        tracking_id = payload.get("submission_id", "")
        await self._update(
            tracking_id,
            status=status,
            plain_language_reason=payload.get("plain_language_reason"),
        )
        logger.info(
            "decision.made processed",
            extra={"tracking_id": tracking_id, "route": route, "new_status": status},
        )

    async def handle_approval_decided(self, payload: dict) -> None:
        action_map = {
            "APPROVE": "APPROVED",
            "REJECT": "REJECTED",
            "REQUEST_INFO": "PENDING_INFO",
            "TIMEOUT": "TIMED_OUT",
        }
        action = (payload.get("action") or "").upper()
        status = action_map.get(action)
        if not status:
            logger.warning("handle_approval_decided: unknown action %r", action)
            return
        tracking_id = payload.get("submission_id", "")
        await self._update(tracking_id, status=status)
        logger.info(
            "approval.decided processed",
            extra={"tracking_id": tracking_id, "action": action, "new_status": status},
        )

    async def handle_payment_completed(self, payload: dict) -> None:
        tracking_id = payload.get("submission_id", "")
        await self._update(
            tracking_id,
            status="PAID",
            external_payment_ref=payload.get("external_payment_ref"),
        )
        logger.info(
            "payment.completed processed",
            extra={"tracking_id": tracking_id, "new_status": "PAID"},
        )

    async def handle_payment_failed(self, payload: dict) -> None:
        tracking_id = payload.get("submission_id", "")
        reason = payload.get("reason", "unknown")
        await self._update(
            tracking_id,
            status="PAYMENT_FAILED",
            plain_language_reason=f"Payment failed: {reason}",
        )
        logger.info(
            "payment.failed processed",
            extra={"tracking_id": tracking_id, "new_status": "PAYMENT_FAILED"},
        )
