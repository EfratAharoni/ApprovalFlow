import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from . import store
from .config import settings
from .database import create_tables
from .logging_config import configure_logging
from .service import AuditService

configure_logging()
logger = logging.getLogger(__name__)

_svc: AuditService = None  # type: ignore[assignment]

_SUBSCRIBED_TOPICS = [
    "submission.created",
    "decision.made",
    "approval.decided",
    "payment.completed",
    "payment.failed",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _svc
    logger.info("audit-service starting", extra={"service": settings.service_name})
    await create_tables()
    _svc = AuditService(
        record_event=store.record_event,
        get_by_submission=store.get_by_submission,
        get_all=store.get_all,
    )
    logger.info("audit-service ready", extra={"service": settings.service_name})
    yield
    logger.info("audit-service shutting down")


app = FastAPI(title="Audit Service", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    correlation_id = request.headers.get("X-Correlation-ID", "unknown")
    logger.error(
        "unhandled exception",
        extra={"correlation_id": correlation_id, "error": str(exc), "path": request.url.path},
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.service_name}


# ─── Dapr pub/sub ─────────────────────────────────────────────────────────────

@app.get("/dapr/subscribe")
async def subscribe() -> list:
    return [
        {"pubsubname": settings.pubsub_name, "topic": t, "route": f"/events/{t.replace('.', '-')}"}
        for t in _SUBSCRIBED_TOPICS
    ]


async def _handle_topic(request: Request, topic: str) -> dict:
    body = await request.json()
    dapr_event_id = body.get("id", str(uuid.uuid4()))
    payload = body.get("data", body)
    correlation_id = payload.get("correlation_id", str(uuid.uuid4()))

    logger.info(
        f"{topic} received",
        extra={
            "correlation_id": correlation_id,
            "submission_id": payload.get("submission_id"),
            "event_id": dapr_event_id,
        },
    )
    try:
        await _svc.handle_event(topic=topic, payload=payload, dapr_event_id=dapr_event_id)
    except Exception as exc:
        logger.error(
            "failed to record audit event",
            extra={"topic": topic, "event_id": dapr_event_id, "error": str(exc)},
        )
        # Return SUCCESS so Dapr doesn't redeliver — we log the error and move on
    return {"status": "SUCCESS"}


@app.post("/events/submission-created")
async def on_submission_created(request: Request) -> dict:
    return await _handle_topic(request, "submission.created")

@app.post("/events/decision-made")
async def on_decision_made(request: Request) -> dict:
    return await _handle_topic(request, "decision.made")

@app.post("/events/approval-decided")
async def on_approval_decided(request: Request) -> dict:
    return await _handle_topic(request, "approval.decided")

@app.post("/events/payment-completed")
async def on_payment_completed(request: Request) -> dict:
    return await _handle_topic(request, "payment.completed")

@app.post("/events/payment-failed")
async def on_payment_failed(request: Request) -> dict:
    return await _handle_topic(request, "payment.failed")


# ─── Query endpoints ──────────────────────────────────────────────────────────

@app.get(
    "/audit/prove-ceiling",
    summary="Proof that the autonomy ceiling was never breached",
    description=(
        "Scans all recorded audit events and verifies that no submission was auto-approved "
        "above the configured `AUTONOMY_CEILING` ($250). Returns `violation_found: false` if the "
        "ceiling held for every decision in the audit log. This is the cryptographic proof of M12. "
        "**Possible responses:** 200 OK."
    ),
    responses={200: {"description": "Ceiling compliance check result"}},
)
async def prove_ceiling() -> dict:
    return await _svc.prove_ceiling()


@app.get(
    "/audit/dashboard",
    summary="Aggregated submission statistics",
    description=(
        "Returns a real-time dashboard with counts and breakdowns across all submissions: "
        "total processed, auto-approved, escalated, rejected, paid, failed. "
        "**Possible responses:** 200 OK."
    ),
    responses={200: {"description": "Dashboard statistics"}},
)
async def dashboard() -> dict:
    return await _svc.get_dashboard()


@app.get(
    "/audit/{submission_id}",
    summary="Full audit trail for a submission",
    description=(
        "Returns the complete chronological event history for a submission: "
        "submission.created → decision.made → approval.decided (if escalated) → "
        "payment.completed | payment.failed. Each event includes timestamp, topic, and payload snapshot. "
        "**Possible responses:** 200 OK, 404 Not Found."
    ),
    responses={
        200: {"description": "Chronological list of audit events"},
        404: {"description": "No audit events found for this submission"},
    },
)
async def get_trail(submission_id: str) -> list:
    trail = await _svc.get_trail(submission_id)
    if not trail:
        raise HTTPException(status_code=404, detail=f"No audit events for {submission_id}")
    return trail
