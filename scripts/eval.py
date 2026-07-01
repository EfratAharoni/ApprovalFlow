"""
ApprovalFlow Eval Harness — B1

Runs all 19 labeled fixtures from sample-invoices.json against a live system
and produces a metrics report.

Usage:
    docker compose up -d --wait
    python scripts/eval.py

Output:
    - Console report (pass/fail per fixture, accuracy, timing, by-route breakdown)
    - docs/eval-report.json  (machine-readable, committed as evidence)

Stateful fixtures:
    INV-1007  (duplicate-of:INV-1001) — INV-1001 is submitted first if needed.
    INV-1014A/B (concurrency-pair)    — submitted in parallel via asyncio.gather.
    INV-1003/1004/1012                — end at ESCALATED; counted as human_review
                                        without waiting for a human to decide.
"""
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import httpx

BASE_URL = "http://localhost:8000"
FIXTURES_PATH = Path("sample-invoices.json")
REPORT_PATH = Path("docs/eval-report.json")

# Each run appends a short unique suffix to all invoice numbers so that
# repeated eval runs against a persistent DB don't collide on the same
# idempotency key.  Duplicate-pair fixtures (INV-1007 → INV-1001) track
# the modified invoice number within this run so idempotency still fires.
import uuid as _uuid
RUN_ID = _uuid.uuid4().hex[:6].upper()  # e.g. "A3F9C1"

POLL_INTERVAL = 2        # seconds between status checks
POLL_TIMEOUT = 60        # seconds per fixture before giving up
STARTUP_GRACE = 8        # extra seconds after health-check before first submission
                         # (Dapr pub/sub subscription registration lags behind health)

# Terminal statuses that end the polling loop
TERMINAL_STATUSES = {
    "PAID", "AUTO_APPROVED", "ESCALATED",
    "REJECTED", "DUPLICATE", "PAYMENT_FAILED",
}

# Map submission status → deterministic-router route label
STATUS_TO_ROUTE: dict[str, str] = {
    "PAID":           "auto_approve",
    "AUTO_APPROVED":  "auto_approve",
    "ESCALATED":      "human_review",
    "PENDING_INFO":   "human_review",
    "PAYMENT_FAILED": "human_review",   # saga compensated → still a human-review path
    "REJECTED":       "reject",
    "DUPLICATE":      "duplicate",
}


@dataclass
class EvalResult:
    fixture_id: str
    expected_route: str
    actual_route: str
    actual_status: str
    passed: bool
    reason: str = ""
    processing_time_ms: float = 0.0


# ── Payload builder ────────────────────────────────────────────────────────────

def build_payload(fixture: dict, invoice_override=None) -> dict:
    """Convert a sample-invoices.json fixture into a submission payload.

    invoice_override: pass the run-scoped invoice number so duplicate pairs
    share exactly the same idempotency key within a run.
    """
    return {
        "vendor":         fixture["vendor"],
        "vendorKnown":    fixture.get("vendorKnown", True),
        "invoiceNumber":  invoice_override or f"{fixture['invoiceNumber']}-{RUN_ID}",
        "currency":       fixture.get("currency", "USD"),
        "category":       fixture["category"],
        "department":     fixture.get("department"),
        "notes":          fixture.get("notes"),
        "submitter":      fixture.get("submitter", "eval@northwind.example"),
        "receiptPresent": fixture.get("receiptPresent", True),
        "attendees":      fixture.get("attendees"),
        "lineItems":      fixture.get("lineItems", []),
        "taxAmount":      fixture.get("taxAmount", 0.0),
        "total":          fixture["total"],
        "date":           fixture.get("date", "2026-05-12"),
    }


# ── Single fixture runner ──────────────────────────────────────────────────────

async def run_fixture(
    client: httpx.AsyncClient,
    fixture: dict,
    invoice_override=None,
) -> EvalResult:
    fid = fixture["id"]
    expected = fixture["expected"]["route"]
    payload = build_payload(fixture, invoice_override)

    t0 = time.perf_counter()

    # Submit
    try:
        resp = await client.post(f"{BASE_URL}/submissions", json=payload)
        resp.raise_for_status()
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        return EvalResult(
            fixture_id=fid,
            expected_route=expected,
            actual_route="ERROR",
            actual_status="ERROR",
            passed=False,
            reason=f"POST /submissions failed: {exc}",
            processing_time_ms=round(elapsed, 1),
        )

    body = resp.json()
    tracking_id = body["tracking_id"]

    # Duplicate detection: submission-service short-circuits and returns the
    # existing tracking_id with message="Duplicate submission...".
    # The polled status will be whatever the original reached (e.g. PAID),
    # not "DUPLICATE" — so we detect it here from the response message.
    if "duplicate" in body.get("message", "").lower():
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        passed = expected == "duplicate"
        return EvalResult(
            fixture_id=fid,
            expected_route=expected,
            actual_route="duplicate",
            actual_status="DUPLICATE",
            passed=passed,
            reason="" if passed else f"Got duplicate short-circuit, expected {expected!r}",
            processing_time_ms=elapsed,
        )

    # Poll
    deadline = time.time() + POLL_TIMEOUT
    actual_status = "PENDING"
    while time.time() < deadline:
        try:
            sr = await client.get(f"{BASE_URL}/submissions/{tracking_id}")
            if sr.status_code == 200:
                actual_status = sr.json().get("status", "PENDING")
                if actual_status in TERMINAL_STATUSES:
                    break
        except Exception:
            pass
        await asyncio.sleep(POLL_INTERVAL)
    else:
        elapsed = (time.perf_counter() - t0) * 1000
        return EvalResult(
            fixture_id=fid,
            expected_route=expected,
            actual_route="TIMEOUT",
            actual_status=actual_status,
            passed=False,
            reason=f"Status still {actual_status!r} after {POLL_TIMEOUT}s",
            processing_time_ms=round(elapsed, 1),
        )

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    actual_route = STATUS_TO_ROUTE.get(actual_status, "unknown")
    passed = actual_route == expected

    return EvalResult(
        fixture_id=fid,
        expected_route=expected,
        actual_route=actual_route,
        actual_status=actual_status,
        passed=passed,
        reason="" if passed else f"status={actual_status!r} → route={actual_route!r}, expected={expected!r}",
        processing_time_ms=elapsed_ms,
    )


# ── Harness orchestrator ───────────────────────────────────────────────────────

async def run_harness() -> list[EvalResult]:
    data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    fixtures: list[dict] = data["fixtures"]

    by_id = {f["id"]: f for f in fixtures}

    results: list[EvalResult] = []
    submitted_ids: set[str] = set()
    # Maps fixture_id → run-scoped invoice number used in this run.
    # Needed so duplicate-pair fixtures share the exact same invoice number.
    run_invoice: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=60.0, base_url=BASE_URL) as client:

        # Separate concurrency pairs from the rest
        concurrent_pairs: list[list[dict]] = []
        seen_pair_ids: set[str] = set()
        sequential: list[dict] = []

        for fx in fixtures:
            scenario = fx.get("scenario", "")
            if scenario.startswith("concurrency-pair:"):
                partner_id = scenario.split(":", 1)[1]
                pair_key = frozenset([fx["id"], partner_id])
                if pair_key not in seen_pair_ids:
                    seen_pair_ids.add(pair_key)
                    partner = by_id.get(partner_id)
                    if partner:
                        concurrent_pairs.append([fx, partner])
            else:
                sequential.append(fx)

        # Run sequential fixtures one by one
        for fx in sequential:
            fid = fx["id"]
            scenario = fx.get("scenario", "")

            # Resolve the run-scoped invoice number for this fixture
            invoice = f"{fx['invoiceNumber']}-{RUN_ID}"
            run_invoice[fid] = invoice

            # If this is a duplicate, ensure the original was submitted first
            # AND reuse the original's run-scoped invoice so idempotency fires.
            if scenario.startswith("duplicate-of:"):
                original_id = scenario.split(":", 1)[1]
                if original_id not in submitted_ids:
                    original = by_id.get(original_id)
                    if original:
                        orig_invoice = f"{original['invoiceNumber']}-{RUN_ID}"
                        run_invoice[original_id] = orig_invoice
                        print(f"  [pre-req] submitting {original_id} before {fid}")
                        pre = await run_fixture(client, original, orig_invoice)
                        results.append(pre)
                        submitted_ids.add(original_id)
                        _print_result(pre)
                # Use the original's exact invoice number so idempotency triggers
                invoice = run_invoice.get(original_id, invoice)
                run_invoice[fid] = invoice

            result = await run_fixture(client, fx, invoice)
            results.append(result)
            submitted_ids.add(fid)
            _print_result(result)

        # Run concurrency pairs in parallel
        for pair in concurrent_pairs:
            ids = [f["id"] for f in pair]
            invoices = [f"{f['invoiceNumber']}-{RUN_ID}" for f in pair]
            for f, inv in zip(pair, invoices):
                run_invoice[f["id"]] = inv
            print(f"  [parallel] {ids[0]} + {ids[1]}")
            pair_results = await asyncio.gather(
                run_fixture(client, pair[0], invoices[0]),
                run_fixture(client, pair[1], invoices[1]),
            )
            for r in pair_results:
                results.append(r)
                submitted_ids.add(r.fixture_id)
                _print_result(r)

    return results


def _print_result(r: EvalResult) -> None:
    icon = "✅" if r.passed else "❌"
    print(
        f"  {icon} {r.fixture_id:<10} expected={r.expected_route:<14} "
        f"actual={r.actual_route:<14} {r.processing_time_ms:.0f}ms"
    )
    if not r.passed:
        print(f"     ↳ {r.reason}")


# ── Report ─────────────────────────────────────────────────────────────────────

def print_report(results: list[EvalResult]) -> None:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    total = len(results)
    accuracy = len(passed) / total if total else 0.0

    times = [r.processing_time_ms for r in results]
    avg_ms = sum(times) / len(times) if times else 0.0

    # By-route breakdown
    routes: dict[str, list[bool]] = {}
    for r in results:
        routes.setdefault(r.expected_route, []).append(r.passed)

    print("\n" + "=" * 56)
    print("APPROVALFLOW EVAL HARNESS — B1")
    print("=" * 56)
    print(f"Run at:   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Fixtures: {total} | Passed: {len(passed)} | Failed: {len(failed)}")
    print(f"Accuracy: {accuracy * 100:.1f}%")

    print(f"\nPASSED ({len(passed)}):")
    for r in passed:
        print(
            f"  ✅ {r.fixture_id:<10} expected={r.expected_route:<14} "
            f"actual={r.actual_route:<14} {r.processing_time_ms:.0f}ms"
        )

    if failed:
        print(f"\nFAILED ({len(failed)}):")
        for r in failed:
            print(
                f"  ❌ {r.fixture_id:<10} expected={r.expected_route:<14} "
                f"actual={r.actual_route:<14}"
            )
            print(f"     reason: {r.reason}")

    print("\nBY ROUTE:")
    for route, outcomes in sorted(routes.items()):
        ok = sum(outcomes)
        n = len(outcomes)
        pct = ok / n * 100 if n else 0
        print(f"  {route:<16}: {ok}/{n}   ({pct:.0f}%)")

    print(f"\nTIMING:")
    print(
        f"  avg: {avg_ms:,.0f}ms | "
        f"min: {min(times):,.0f}ms | "
        f"max: {max(times):,.0f}ms"
    )
    print("=" * 56 + "\n")


def save_report(results: list[EvalResult]) -> None:
    passed = [r for r in results if r.passed]
    total = len(results)
    accuracy = len(passed) / total if total else 0.0

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": len(passed),
        "failed": total - len(passed),
        "accuracy": round(accuracy, 4),
        "results": [
            {
                "fixture_id":        r.fixture_id,
                "expected_route":    r.expected_route,
                "actual_route":      r.actual_route,
                "actual_status":     r.actual_status,
                "passed":            r.passed,
                "reason":            r.reason,
                "processing_time_ms": r.processing_time_ms,
            }
            for r in results
        ],
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved → {REPORT_PATH}")


# ── Entry point ────────────────────────────────────────────────────────────────

async def main() -> int:
    print("ApprovalFlow Eval Harness — B1")
    print(f"Target: {BASE_URL}")
    print(f"Fixtures: {FIXTURES_PATH}\n")

    # Quick health check
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{BASE_URL}/health")
            r.raise_for_status()
    except Exception as exc:
        print(f"ERROR: system not reachable at {BASE_URL} — {exc}")
        print("Run: docker compose up -d --wait")
        return 1

    # Dapr pub/sub subscription registration lags a few seconds behind health checks.
    # Without this grace period the first submitted event is dropped and stays PENDING.
    print(f"System healthy — waiting {STARTUP_GRACE}s for Dapr pub/sub to stabilise...")
    await asyncio.sleep(STARTUP_GRACE)
    print(f"Run ID: {RUN_ID}  (appended to all invoice numbers for isolation)\n")

    results = await run_harness()
    print_report(results)
    save_report(results)

    failed = sum(1 for r in results if not r.passed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
