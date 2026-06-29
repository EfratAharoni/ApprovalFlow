import json
import logging
import httpx
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


async def get_state_with_etag(key: str) -> tuple:
    """Returns (data_dict, etag_str). data_dict is {} when key absent."""
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}/{key}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=5.0)
    etag = resp.headers.get("etag", "")
    if resp.status_code == 204 or not resp.content:
        return {}, etag
    return resp.json(), etag


async def save_state_with_etag(key: str, value: dict, etag: str) -> bool:
    """
    Conditional save (first-write concurrency). Returns True on success, False on ETag conflict.
    When etag is empty (new key), saves unconditionally.
    """
    url = f"{DAPR_BASE}/v1.0/state/{settings.statestore_name}"
    item: dict = {"key": key, "value": value}
    if etag:
        item["etag"] = etag
        item["options"] = {"concurrency": "first-write", "consistency": "strong"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=[item], timeout=5.0)
    if resp.status_code == 409:   # ETag conflict
        return False
    resp.raise_for_status()
    return True
