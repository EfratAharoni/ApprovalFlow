import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update as sql_update

from .config import settings
from .logging_config import configure_logging
from .database import create_tables, AsyncSessionLocal
from .routes import router
from .subscriber import SubmissionStatusService
from .models import Submission

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("submission-service starting", extra={"service": settings.service_name})
    await create_tables()
    logger.info("database tables ready", extra={"service": settings.service_name})
    yield
    logger.info("submission-service shutting down", extra={"service": settings.service_name})


app = FastAPI(
    title="Submission Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    import uuid
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


app.include_router(router)


# ─── Real DB update callable ──────────────────────────────────────────────────

async def _db_update_submission(tracking_id: str, **kwargs) -> dict:
    async with AsyncSessionLocal() as session:
        await session.execute(
            sql_update(Submission)
            .where(Submission.tracking_id == tracking_id)
            .values(**{k: v for k, v in kwargs.items() if v is not None})
        )
        await session.commit()
    return {"tracking_id": tracking_id, **kwargs}


async def _db_get_by_tracking_id(tracking_id: str):
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(Submission).where(Submission.tracking_id == tracking_id)
        )


def _make_svc() -> SubmissionStatusService:
    return SubmissionStatusService(
        get_by_tracking_id=_db_get_by_tracking_id,
        update_submission=_db_update_submission,
    )


# ─── Dapr pub/sub subscription registration ──────────────────────────────────

_SUBSCRIBED_TOPICS = [
    (settings.decision_made_topic, "/events/decision-made"),
    (settings.approval_decided_topic, "/events/approval-decided"),
    (settings.payment_completed_topic, "/events/payment-completed"),
    (settings.payment_failed_topic, "/events/payment-failed"),
]


@app.get("/dapr/subscribe")
async def dapr_subscribe() -> list:
    return [
        {"pubsubname": settings.pubsub_name, "topic": topic, "route": route}
        for topic, route in _SUBSCRIBED_TOPICS
    ]


async def _handle_event(request: Request, handler_name: str) -> dict:
    body = await request.json()
    payload = body.get("data", body)
    event_id = body.get("id", str(uuid.uuid4()))
    correlation_id = payload.get("correlation_id", "")
    tracking_id = payload.get("submission_id", "")
    logger.info(
        f"{handler_name} received",
        extra={"correlation_id": correlation_id, "tracking_id": tracking_id, "event_id": event_id},
    )
    svc = _make_svc()
    try:
        await getattr(svc, handler_name)(payload)
    except Exception as exc:
        logger.error(
            f"{handler_name} failed",
            extra={"error": str(exc), "tracking_id": tracking_id},
            exc_info=True,
        )
    return {"status": "SUCCESS"}


@app.post("/events/decision-made")
async def on_decision_made(request: Request) -> dict:
    return await _handle_event(request, "handle_decision_made")


@app.post("/events/approval-decided")
async def on_approval_decided(request: Request) -> dict:
    return await _handle_event(request, "handle_approval_decided")


@app.post("/events/payment-completed")
async def on_payment_completed(request: Request) -> dict:
    return await _handle_event(request, "handle_payment_completed")


@app.post("/events/payment-failed")
async def on_payment_failed(request: Request) -> dict:
    return await _handle_event(request, "handle_payment_failed")
