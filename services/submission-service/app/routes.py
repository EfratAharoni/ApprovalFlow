import uuid
import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .database import get_db
from .models import Submission
from .schemas import SubmissionRequest, SubmissionResponse, StatusResponse
from .idempotency import compute_idempotency_key
from .fx import to_usd
from . import dapr_client
from .config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=202,
    summary="Submit an expense invoice",
    description=(
        "Accepts a new expense invoice for AI-powered policy evaluation. "
        "Returns immediately with a `tracking_id`; processing is asynchronous via Dapr pub/sub. "
        "Duplicate submissions (same vendor + invoiceNumber + total + date) are short-circuited "
        "and return the existing `tracking_id`. "
        "**Possible responses:** 202 Accepted, 409 Conflict (not used — duplicates return 202), "
        "422 Validation Error."
    ),
    responses={
        202: {"description": "Submission accepted and queued for processing"},
        422: {"description": "Invalid request payload"},
    },
)
async def create_submission(
    req: SubmissionRequest,
    db: AsyncSession = Depends(get_db),
) -> SubmissionResponse:
    correlation_id = str(uuid.uuid4())
    idempotency_key = compute_idempotency_key(
        vendor=req.vendor,
        amount=req.total,
        invoice_number=req.invoice_number,
        date=req.date,
    )

    logger.info(
        "submission received",
        extra={
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "vendor": req.vendor,
            "amount": str(req.total),
            "currency": req.currency,
        },
    )

    # Idempotency check: same invoice already submitted?
    existing = await db.scalar(
        select(Submission).where(Submission.idempotency_key == idempotency_key)
    )
    if existing is not None:
        logger.info(
            "duplicate submission short-circuited",
            extra={"correlation_id": str(existing.correlation_id), "tracking_id": existing.tracking_id},
        )
        return SubmissionResponse(
            tracking_id=existing.tracking_id,
            status=existing.status,
            message="Duplicate submission. Returning existing tracking id.",
        )

    amount_usd = to_usd(req.total, req.currency)
    tracking_id = str(uuid.uuid4())

    submission = Submission(
        tracking_id=tracking_id,
        idempotency_key=idempotency_key,
        vendor_name=req.vendor,
        vendor_known=req.vendor_known,
        invoice_number=req.invoice_number,
        currency=req.currency,
        amount=req.total,
        amount_usd=amount_usd,
        category=req.category,
        department=req.department,
        description=req.description,
        notes=req.notes,
        submitted_by=req.submitted_by,
        receipt_present=req.receipt_present,
        attendees=req.attendees,
        line_items=[
            {k: float(v) if isinstance(v, Decimal) else v for k, v in item.model_dump(by_alias=True).items()}
            for item in req.line_items
        ],
        tax_amount=req.tax_amount,
        date=req.date,
        status="PENDING",
        correlation_id=uuid.UUID(correlation_id),
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    # Publish async — never block the 202 response on processing
    try:
        await dapr_client.publish_event(
            topic=settings.submission_created_topic,
            data={
                "submission_id": tracking_id,
                "tracking_id": tracking_id,
                "correlation_id": correlation_id,
                "vendor": req.vendor,
                "vendor_known": req.vendor_known,
                "invoice_number": req.invoice_number,
                "currency": req.currency,
                "amount": str(req.total),
                "amount_usd": str(amount_usd),
                "category": req.category,
                "department": req.department,
                "submitted_by": req.submitted_by,
                "receipt_present": req.receipt_present,
                "attendees": req.attendees,
                "line_items": [
                    {k: float(v) if isinstance(v, Decimal) else v for k, v in item.model_dump(by_alias=True).items()}
                    for item in req.line_items
                ],
                "tax_amount": str(req.tax_amount),
                "total": str(req.total),
                "date": req.date,
                "notes": req.notes,
                "idempotency_key": idempotency_key,
            },
            correlation_id=correlation_id,
        )
    except Exception as exc:
        # Dapr publish failure must not lose the submission — it's already in DB.
        # The ai-agent-service can be triggered via a reconciliation job later.
        logger.error(
            "failed to publish submission.created event",
            extra={"correlation_id": correlation_id, "error": str(exc)},
        )

    logger.info(
        "submission accepted",
        extra={"correlation_id": correlation_id, "tracking_id": tracking_id},
    )
    return SubmissionResponse(tracking_id=tracking_id, status="PENDING")


@router.get(
    "/submissions/{tracking_id}",
    response_model=StatusResponse,
    summary="Get submission status",
    description=(
        "Returns the current processing status of a submitted invoice. "
        "Statuses: `PENDING` → `AUTO_APPROVED` | `ESCALATED` | `REJECTED` | `DUPLICATE` → `PAID` | `PAYMENT_FAILED`. "
        "Poll this endpoint after submitting to track progress. "
        "**Possible responses:** 200 OK, 404 Not Found."
    ),
    responses={
        200: {"description": "Current submission status and metadata"},
        404: {"description": "Submission not found"},
    },
)
async def get_status(
    tracking_id: str,
    db: AsyncSession = Depends(get_db),
) -> StatusResponse:
    submission = await db.scalar(
        select(Submission).where(Submission.tracking_id == tracking_id)
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    logger.info(
        "status requested",
        extra={"tracking_id": tracking_id, "correlation_id": str(submission.correlation_id)},
    )
    return StatusResponse(
        tracking_id=submission.tracking_id,
        status=submission.status,
        plain_language_reason=submission.plain_language_reason,
        external_payment_ref=submission.external_payment_ref,
        correlation_id=str(submission.correlation_id),
        submitted_by=submission.submitted_by,
        vendor=submission.vendor_name,
        amount_usd=submission.amount_usd,
        category=submission.category,
        submitted_at=submission.created_at.isoformat(),
        updated_at=submission.updated_at.isoformat(),
    )


@router.post("/submissions/{submission_id}/status")
async def update_status(
    submission_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Internal endpoint called by other services via Dapr service invocation to update status."""
    from sqlalchemy import update as sql_update
    import uuid as uuid_mod
    await db.execute(
        sql_update(Submission)
        .where(Submission.id == uuid_mod.UUID(submission_id))
        .values(
            status=payload.get("status"),
            plain_language_reason=payload.get("plain_language_reason"),
        )
    )
    await db.commit()
    logger.info(
        "status updated",
        extra={
            "submission_id": submission_id,
            "new_status": payload.get("status"),
            "correlation_id": payload.get("correlation_id", ""),
        },
    )
    return {"ok": True}
