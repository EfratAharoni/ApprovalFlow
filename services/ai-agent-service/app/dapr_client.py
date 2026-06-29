import json
import logging
import httpx
from .config import settings

logger = logging.getLogger(__name__)
DAPR_BASE = f"http://localhost:{settings.dapr_http_port}"


async def publish_decision(data: dict, correlation_id: str) -> None:
    url = f"{DAPR_BASE}/v1.0/publish/{settings.pubsub_name}/{settings.decision_made_topic}"
    headers = {"Content-Type": "application/json", "X-Correlation-ID": correlation_id}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, content=json.dumps(data), headers=headers, timeout=10.0)
        resp.raise_for_status()
    logger.info(
        "published decision.made",
        extra={"correlation_id": correlation_id, "route": data.get("route")},
    )
