import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .agent import create_agent
from .config import settings
from .database import AsyncSessionLocal, create_tables
from .logging_config import configure_logging
from .models import Decision
from .policy import load_policy_config
from .router import route_submission
from .schemas import SubmissionEvent
from . import dapr_client

configure_logging()
logger = logging.getLogger(__name__)

_agent = None
_policy = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _policy
    logger.info("ai-agent-service starting", extra={"service": settings.service_name})
    await create_tables()
    _agent = create_agent()
    _policy = load_policy_config()
    logger.info(
        "agent ready",
        extra={
            "service": settings.service_name,
            "llm_mock": settings.llm_mock,
            "autonomy_ceiling": str(_policy.autonomy_ceiling),
        },
    )
    yield
    logger.info("ai-agent-service shutting down")


app = FastAPI(title="AI Agent Service", version="1.0.0", lifespan=lifespan)


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
    return {
        "status": "ok",
        "service": settings.service_name,
        "llm_mock": settings.llm_mock,
        "autonomy_ceiling": str(_policy.autonomy_ceiling) if _policy else "loading",
    }


# ─── Dapr pub/sub subscription ───────────────────────────────────────────────

@app.get("/dapr/subscribe")
async def subscribe() -> list[dict]:
    return [
        {
            "pubsubname": settings.pubsub_name,
            "topic": settings.submission_created_topic,
            "route": "/events/submission-created",
        }
    ]


@app.post("/events/submission-created")
async def handle_submission_created(request: Request) -> dict:
    body = await request.json()
    # Dapr wraps messages in CloudEvents envelope; actual payload is in "data"
    event_data = body.get("data", body)
    correlation_id = event_data.get("correlation_id", str(uuid.uuid4()))

    logger.info(
        "submission.created received",
        extra={
            "correlation_id": correlation_id,
            "submission_id": event_data.get("submission_id"),
            "vendor": event_data.get("vendor"),
            "amount_usd": event_data.get("amount_usd"),
        },
    )

    try:
        event = SubmissionEvent(**event_data)
    except Exception as exc:
        logger.error(
            "invalid submission event payload",
            extra={"correlation_id": correlation_id, "error": str(exc)},
        )
        return {"status": "DROP"}  # tell Dapr not to redeliver a malformed event

    decision = await route_submission(
        event=event,
        policy=_policy,
        agent=_agent,
        is_duplicate_fn=_is_duplicate,
    )

    async with AsyncSessionLocal() as db:
        db.add(Decision(
            submission_id=event.submission_id,
            correlation_id=correlation_id,
            idempotency_key=event.idempotency_key,
            route=decision.route,
            ceiling_guard_triggered=decision.ceiling_guard_triggered,
            agent_reasoning=decision.agent_recommendation.reasoning if decision.agent_recommendation else None,
            agent_recommendation=decision.agent_recommendation.recommendation if decision.agent_recommendation else None,
            confidence=decision.agent_recommendation.confidence if decision.agent_recommendation else None,
            policy_violations=[v.model_dump() for v in decision.policy_violations],
            plain_language_reason=decision.plain_language_reason,
        ))
        await db.commit()

    try:
        await dapr_client.publish_decision(
            data={
                "submission_id": event.submission_id,
                "tracking_id": event.tracking_id,
                "correlation_id": correlation_id,
                "route": decision.route,
                "ceiling_guard_triggered": decision.ceiling_guard_triggered,
                "agent_recommendation": decision.agent_recommendation.model_dump() if decision.agent_recommendation else None,
                "policy_violations": [v.model_dump() for v in decision.policy_violations],
                "plain_language_reason": decision.plain_language_reason,
                # Fields needed by payment-service and audit-service
                "amount_usd": str(event.amount_usd),
                "category": event.category,
                "vendor": event.vendor,
                "submitted_by": event.submitted_by,
            },
            correlation_id=correlation_id,
        )
    except Exception as exc:
        logger.error(
            "failed to publish decision.made",
            extra={"correlation_id": correlation_id, "error": str(exc)},
        )

    logger.info(
        "decision made",
        extra={
            "correlation_id": correlation_id,
            "route": decision.route,
            "ceiling_guard_triggered": decision.ceiling_guard_triggered,
        },
    )
    return {"status": "SUCCESS"}


async def _is_duplicate(idempotency_key: str) -> bool:
    """Check whether this idempotency_key was already routed (secondary defense against duplicates)."""
    if not idempotency_key:
        return False
    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(Decision).where(
                Decision.idempotency_key == idempotency_key,
                Decision.route.in_(["auto_approve", "human_review", "reject"]),
            )
        )
        return existing is not None
