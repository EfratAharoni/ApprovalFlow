import json
import logging
import httpx
from .config import settings

logger = logging.getLogger(__name__)

DAPR_BASE = f"http://localhost:{settings.dapr_http_port}"


async def publish_event(topic: str, data: dict, correlation_id: str) -> None:
    url = f"{DAPR_BASE}/v1.0/publish/{settings.pubsub_name}/{topic}"
    headers = {
        "Content-Type": "application/json",
        "X-Correlation-ID": correlation_id,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, content=json.dumps(data), headers=headers, timeout=10.0)
        resp.raise_for_status()
    logger.info("published event", extra={"topic": topic, "correlation_id": correlation_id})


async def save_state(key: str, value: dict) -> None:
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}"
    payload = [{"key": key, "value": value}]
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10.0)
        resp.raise_for_status()


async def get_state(key: str) -> dict | None:
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}/{key}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()
