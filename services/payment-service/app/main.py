import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import dapr_client, store, inject as _inject
from .budget import reserve_budget, release_budget
from .config import settings
from .database import create_tables
from .gateway import simulate_payment_gateway
from .logging_config import configure_logging
from .saga import PaymentSaga
from .schemas import ApprovalDecidedEvent, DecisionMadeEvent

configure_logging()
logger = logging.getLogger(__name__)

_saga: PaymentSaga = None  # type: ignore[assignment]


def _category_to_department(category: str) -> str:
    mapping = {
        "meals": "marketing-2026Q2",
        "travel": "sales-2026Q2",
        "hardware": "engineering-2026Q2",
        "saas": "engineering-2026Q2",
    }
    return mapping.get((category or "").lower(), "engineering-2026Q2")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _saga
    logger.info("payment-service starting", extra={"service": settings.service_name})
    await create_tables()

    _saga = PaymentSaga(
        reserve_budget=reserve_budget,
        release_budget=release_budget,
        payment_gateway=simulate_payment_gateway,
        get_payment=store.get_payment,
        create_payment=store.create_payment,
        update_payment=store.update_payment,
        publish_completed=lambda data, corr_id: dapr_client.publish_event(
            settings.payment_completed_topic, data, corr_id
        ),
        publish_failed=lambda data, corr_id: dapr_client.publish_event(
            settings.payment_failed_topic, data, corr_id
        ),
    )
    logger.info(
        "payment-service ready",
        extra={"service": settings.service_name, "failure_inject": settings.payment_failure_inject or "none"},
    )
    yield
    logger.info("payment-service shutting down")


app = FastAPI(title="Payment Service", version="1.0.0", lifespan=lifespan)


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
        "failure_inject": settings.payment_failure_inject or "none",
    }


# ─── Dapr pub/sub subscriptions ──────────────────────────────────────────────

@app.get("/dapr/subscribe")
async def subscribe() -> list:
    return [
        {
            "pubsubname": settings.pubsub_name,
            "topic": settings.decision_made_topic,
            "route": "/events/decision-made",
        },
        {
            "pubsubname": settings.pubsub_name,
            "topic": settings.approval_decided_topic,
            "route": "/events/approval-decided",
        },
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

    if event.route != "auto_approve":
        return {"status": "SUCCESS"}  # only handle auto_approve here

    logger.info(
        "decision.made(auto_approve) received",
        extra={"correlation_id": correlation_id, "submission_id": event.submission_id, "amount_usd": event.amount_usd},
    )

    department_id = _category_to_department(event.category or "")
    amount_usd = float(event.amount_usd or "0")

    await _saga.execute(
        submission_id=event.submission_id,
        tracking_id=event.tracking_id,
        amount_usd=amount_usd,
        department_id=department_id,
        correlation_id=correlation_id,
    )
    return {"status": "SUCCESS"}


# ─── Test-support endpoints (verify script only, not behind gateway) ─────────

@app.post(
    "/_test/inject-failure/{submission_id}",
    summary="[Test only] Inject a payment gateway failure",
    description=(
        "Registers a runtime failure for the given submission ID. "
        "The payment-service will simulate a gateway failure when it processes this submission, "
        "triggering the budget-release compensating transaction. "
        "Not exposed through the API Gateway — test/verify scripts access port 8004 directly."
    ),
    tags=["Test Support"],
)
async def test_inject_failure(submission_id: str) -> dict:
    _inject.register(submission_id)
    logger.warning("failure injection registered", extra={"submission_id": submission_id})
    return {"ok": True, "submission_id": submission_id}


@app.delete(
    "/_test/inject-failure/{submission_id}",
    summary="[Test only] Clear an injected payment failure",
    tags=["Test Support"],
)
async def test_clear_failure(submission_id: str) -> dict:
    _inject.clear(submission_id)
    return {"ok": True, "submission_id": submission_id}


@app.get(
    "/_test/budget/{department_id}",
    summary="[Test only] Read department budget from Dapr state",
    description="Returns the current Dapr state-store balance for a department. Used by the verify script to confirm budget was released after a payment failure.",
    tags=["Test Support"],
)
async def test_get_budget(department_id: str) -> dict:
    from .dapr_client import get_state_with_etag
    data, _ = await get_state_with_etag(f"budget:{department_id}")
    from .budget import _default_balance
    balance = data.get("balance", _default_balance(department_id)) if data else _default_balance(department_id)
    return {"department_id": department_id, "balance": balance}


@app.post("/_test/budget/{department_id}/set")
async def test_set_budget(department_id: str, request: Request) -> dict:
    body = await request.json()
    from .dapr_client import save_state_with_etag, get_state_with_etag
    from .budget import _default_balance
    balance = float(body.get("balance", _default_balance(department_id)))
    key = f"budget:{department_id}"
    for _ in range(5):
        _, etag = await get_state_with_etag(key)
        if await save_state_with_etag(key, {"balance": balance}, etag):
            return {"department_id": department_id, "balance": balance, "reset": True}
    raise Exception(f"CAS conflict after 5 retries for {department_id}")


@app.post("/events/approval-decided")
async def handle_approval_decided(request: Request) -> dict:
    body = await request.json()
    event_data = body.get("data", body)
    correlation_id = event_data.get("correlation_id", str(uuid.uuid4()))

    try:
        event = ApprovalDecidedEvent(**event_data)
    except Exception as exc:
        logger.error("invalid approval.decided payload", extra={"correlation_id": correlation_id, "error": str(exc)})
        return {"status": "DROP"}

    if event.action.upper() != "APPROVE":
        return {"status": "SUCCESS"}  # only handle human approvals

    logger.info(
        "approval.decided(APPROVE) received",
        extra={"correlation_id": correlation_id, "submission_id": event.submission_id, "amount_usd": event.amount_usd},
    )

    department_id = event.department_id or _category_to_department(event.category or "")
    amount_usd = float(event.amount_usd or "0")

    await _saga.execute(
        submission_id=event.submission_id,
        tracking_id=event.tracking_id,
        amount_usd=amount_usd,
        department_id=department_id,
        correlation_id=correlation_id,
    )
    return {"status": "SUCCESS"}
