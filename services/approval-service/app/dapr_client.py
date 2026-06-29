import json
import logging
import httpx
from typing import Optional
from .config import settings

logger = logging.getLogger(__name__)
DAPR_BASE = f"http://localhost:{settings.dapr_http_port}"


async def publish_event(topic: str, data: dict, correlation_id: str) -> None:
    url = f"{DAPR_BASE}/v1.0/publish/{settings.pubsub_name}/{topic}"
    headers = {"Content-Type": "application/json", "X-Correlation-ID": correlation_id}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, content=json.dumps(data), headers=headers, timeout=10.0)
        resp.raise_for_status()
    logger.info("published event", extra={"correlation_id": correlation_id, "topic": topic})


async def save_hitl_state(submission_id: str, state: dict) -> None:
    key = f"hitl:{submission_id}"
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=[{"key": key, "value": state}], timeout=5.0)
        resp.raise_for_status()
    logger.info("hitl state saved", extra={"submission_id": submission_id})


async def get_hitl_state(submission_id: str) -> Optional[dict]:
    key = f"hitl:{submission_id}"
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}/{key}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=5.0)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


async def delete_hitl_state(submission_id: str) -> None:
    key = f"hitl:{submission_id}"
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}/{key}"
    async with httpx.AsyncClient() as client:
        resp = await client.delete(url, timeout=5.0)
        resp.raise_for_status()
    logger.info("hitl state deleted", extra={"submission_id": submission_id})
