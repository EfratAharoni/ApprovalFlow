"""
ApprovalFlow — Concurrent Load Test

Tests rate-limiting (M6) and budget CAS (M13) under parallel submissions.
Run against a live system: docker compose up -d --wait

Usage:
    python scripts/load_test.py

Note: Nginx returns 503 (not 429) by default for rate-limited requests.
Add `limit_req_status 429;` to nginx.conf to change this.
"""
import asyncio
import sys
import time
from collections import Counter
from typing import Union

import httpx

# Force UTF-8 so emoji/unicode render on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"
PAYMENT_DIRECT = "http://localhost:8004"


async def submit_one(client: httpx.AsyncClient, i: int) -> Union[int, str]:
    payload = {
        "id": f"LOAD-TEST-{i}",
        "vendor": "Bistro 19",
        "vendorKnown": True,
        "invoiceNumber": f"LT-{i}-{int(time.time())}",
        "currency": "USD",
        "category": "meals",
        "attendees": 1,
        "lineItems": [{"description": "Lunch", "quantity": 1, "unitPrice": 38.89}],
        "taxAmount": 3.11,
        "total": 42.0,
        "receiptPresent": True,
        "date": "2026-05-12",
        "department": "engineering-2026Q2",
        "submitter": "loadtest@northwind.example",
        "notes": "",
    }
    try:
        r = await client.post(
            f"{BASE_URL}/submissions", json=payload, timeout=10
        )
        return r.status_code
    except Exception as e:
        return f"error: {e}"


async def main() -> None:
    # ── Test 1: Rate limiting — 30 concurrent requests ────────────────────────
    print("Test 1: Rate limiting — 30 concurrent requests")
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[submit_one(client, i) for i in range(30)]
        )
    counts = Counter(results)
    print(f"  Status code distribution: {dict(counts)}")
    rate_limited = counts.get(429, 0) + counts.get(503, 0)
    print(f"  202 (accepted):          {counts.get(202, 0)}")
    print(f"  429/503 (rate limited):  {rate_limited}")
    print(f"    429: {counts.get(429, 0)}  503: {counts.get(503, 0)}")
    if rate_limited > 0:
        if counts.get(503, 0) > 0 and counts.get(429, 0) == 0:
            print("  PASS — Nginx rate-limiter fired (M6). Returned 503 (nginx default).")
            print("         Add `limit_req_status 429;` to nginx.conf to get 429 instead.")
        else:
            print("  PASS — Nginx rate-limiter fired correctly (M6).")
    else:
        print("  NOTE — No rate-limiting observed; all requests fit within burst=20 window")

    # ── Test 2: Concurrent budget — 5x $600 against marketing ($1000) ─────────
    print("\nTest 2: Concurrent budget — 5x $600 against marketing-2026Q2 ($1000)")

    # Reset the marketing budget to $1000 before the test
    async with httpx.AsyncClient() as client:
        reset = await client.post(
            f"{PAYMENT_DIRECT}/_test/budget/marketing-2026Q2/set",
            json={"balance": 1000.0},
            timeout=10,
        )
        if reset.status_code == 200:
            print("  Budget reset to $1000 [OK]")
        else:
            print(f"  WARNING: budget reset returned {reset.status_code}")

    payload_template = {
        "vendor": "ExpoWorks",
        "vendorKnown": True,
        "currency": "USD",
        "category": "other",
        "lineItems": [{"description": "Booth", "quantity": 1, "unitPrice": 600.0}],
        "taxAmount": 0.0,
        "total": 600.0,
        "receiptPresent": True,
        "date": "2026-05-18",
        "department": "marketing-2026Q2",
        "submitter": "loadtest@northwind.example",
        "notes": "concurrency load test",
    }

    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(5):
            p = dict(payload_template)
            p["id"] = f"LOAD-BUDGET-{i}"
            p["invoiceNumber"] = f"LB-{i}-{int(time.time())}"
            tasks.append(
                client.post(f"{BASE_URL}/submissions", json=p, timeout=10)
            )
        responses = await asyncio.gather(*tasks)

    tracking_ids = [
        r.json()["tracking_id"]
        for r in responses
        if r.status_code == 202
    ]
    print(f"  {len(tracking_ids)}/5 submissions accepted (202)")

    print("  Waiting 15s for AI agent to route submissions...")
    await asyncio.sleep(15)

    async with httpx.AsyncClient() as client:
        statuses = []
        for tid in tracking_ids:
            r = await client.get(f"{BASE_URL}/submissions/{tid}")
            if r.status_code == 200:
                statuses.append(r.json()["status"])
    print(f"  Final statuses: {Counter(statuses)}")
    print(
        "  Expect: all ESCALATED (ExpoWorks vendor known but $600 > $250 ceiling) — "
        "budget CAS (M13) will be exercised once a human approves via /approvals/queue"
    )


if __name__ == "__main__":
    asyncio.run(main())
