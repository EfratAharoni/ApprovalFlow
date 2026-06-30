import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import dapr_client, store
from .config import settings
from .database import create_tables
from .logging_config import configure_logging
from .schemas import DecideRequest, DecisionMadeEvent
from .service import ApprovalService

configure_logging()
logger = logging.getLogger(__name__)

_svc: ApprovalService = None  # type: ignore[assignment]


def _make_service() -> ApprovalService:
    return ApprovalService(
        get_task=store.get_task,
        get_all_pending=store.get_all_pending,
        create_task=store.create_task,
        update_task=store.update_task,
        save_hitl_state=dapr_client.save_hitl_state,
        get_hitl_state=dapr_client.get_hitl_state,
        delete_hitl_state=dapr_client.delete_hitl_state,
        publish_decided=lambda data, corr_id: dapr_client.publish_event(
            settings.approval_decided_topic, data, corr_id
        ),
    )


async def _timeout_loop() -> None:
    """Background task: check for timed-out PENDING approvals every 10 minutes."""
    while True:
        await asyncio.sleep(settings.timeout_check_interval_seconds)
        try:
            timed_out = await store.get_timed_out()
            if timed_out:
                count = await _svc.check_timeouts(timed_out)
                if count:
                    logger.info("timeout sweep complete", extra={"count": count})
        except Exception as exc:
            logger.error("timeout sweep error", extra={"error": str(exc)})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _svc
    logger.info("approval-service starting", extra={"service": settings.service_name})
    await create_tables()
    _svc = _make_service()

    # Recover any PENDING tasks whose Dapr HITL state was lost
    try:
        restored = await _svc.recover_pending_tasks()
        logger.info("startup recovery done", extra={"restored": restored})
    except Exception as exc:
        logger.warning("startup recovery failed (Dapr may not be ready yet)", extra={"error": str(exc)})

    task = asyncio.create_task(_timeout_loop())
    logger.info("approval-service ready", extra={"service": settings.service_name})
    yield
    task.cancel()
    logger.info("approval-service shutting down")


app = FastAPI(title="Approval Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        {
            "pubsubname": settings.pubsub_name,
            "topic": settings.decision_made_topic,
            "route": "/events/decision-made",
        }
    ]


@app.post("/events/decision-made")
async def handle_decision_made(request: Request) -> dict:
    body = await request.json()
    event_data = body.get("data", body)
    correlation_id = event_data.get("correlation_id", str(uuid.uuid4()))

    try:
        event = DecisionMadeEvent(**event_data)
    except Exception as exc:
        logger.error("invalid decision.made payload", extra={"correlation_id": correlation_id, "error": str(exc)})
        return {"status": "DROP"}

    if event.route != "human_review":
        return {"status": "SUCCESS"}  # only handle human_review

    logger.info(
        "decision.made(human_review) received",
        extra={
            "correlation_id": correlation_id,
            "submission_id": event.submission_id,
            "vendor": event.vendor,
            "amount_usd": event.amount_usd,
        },
    )

    await _svc.handle_decision_made(event_data)
    return {"status": "SUCCESS"}


# ─── Approver API endpoints ───────────────────────────────────────────────────

@app.get("/approvals/queue")
async def get_queue() -> list:
    return await _svc.get_queue()


@app.get("/approvals/{submission_id}")
async def get_approval(submission_id: str) -> dict:
    task = await _svc.get_task(submission_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task for submission {submission_id}")
    return task


@app.post("/approvals/{submission_id}/decide")
async def decide(submission_id: str, body: DecideRequest, request: Request) -> dict:
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    logger.info(
        "decide request received",
        extra={
            "correlation_id": correlation_id,
            "submission_id": submission_id,
            "action": body.action,
            "decided_by": body.decided_by,
        },
    )
    try:
        task = await _svc.decide(
            submission_id=submission_id,
            action=body.action,
            decided_by=body.decided_by,
            notes=body.notes,
            correlation_id=correlation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return task
