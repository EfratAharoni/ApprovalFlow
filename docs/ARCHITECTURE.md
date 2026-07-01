# ApprovalFlow — Architecture

## Service Overview

| Service | Responsibility | Port |
|---|---|---|
| api-gateway | Single external entry point, rate-limiting (Nginx) | 8000 |
| submission-service | Invoice intake, idempotency, FX conversion, status tracking | 8001 |
| ai-agent-service | LLM evaluation + deterministic router | 8002 |
| approval-service | Human-in-the-loop queue, durable pause/resume | 8003 |
| payment-service | Budget reservation, payment execution, saga compensation | 8004 |
| audit-service | Append-only event log, dashboard, ceiling proof | 8005 |

## Communication Patterns

| Pattern | Used for |
|---|---|
| **Dapr pub/sub** (async) | All cross-service event flow: `submission.created` → `decision.made` → `approval.decided` → `payment.completed` / `payment.failed` |
| **Dapr service invocation** (sync) | ai-agent-service → submission-service to update submission status |
| **Dapr state store** (Redis) | HITL durable pause state; department budget with CAS/ETag |

---

## Sequence Diagram 1 — Auto-Approve Flow

```mermaid
sequenceDiagram
  Client->>Gateway: POST /submissions
  Gateway->>SubmissionService: forward
  SubmissionService-->>Client: 202 + tracking_id
  SubmissionService->>PubSub: submission.created
  PubSub->>AIAgentService: consume
  AIAgentService->>AIAgentService: deterministic router (gate 1 — ceiling check)
  AIAgentService->>LLM: decide(event, policy)
  LLM-->>AIAgentService: AgentDecision (recommendation + confidence)
  AIAgentService->>AIAgentService: deterministic router (gate 2 — ceiling check)
  AIAgentService->>PubSub: decision.made (route=auto_approve)
  PubSub->>PaymentService: consume
  PaymentService->>PaymentService: saga steps 1–4
  PaymentService->>PubSub: payment.completed
  PubSub->>SubmissionService: consume → status=PAID
  PubSub->>AuditService: consume → record event
```

---

## Sequence Diagram 2 — Escalate-and-Resume Flow

```mermaid
sequenceDiagram
  Client->>Gateway: POST /submissions
  Gateway->>SubmissionService: forward
  SubmissionService-->>Client: 202 + tracking_id
  SubmissionService->>PubSub: submission.created
  PubSub->>AIAgentService: consume
  AIAgentService->>AIAgentService: hard-stop or confidence check → human_review
  AIAgentService->>PubSub: decision.made (route=human_review)
  PubSub->>ApprovalService: consume
  ApprovalService->>DaprState: save HITL state (durable pause)
  ApprovalService->>DB: create approval_task (status=PENDING)
  Note over ApprovalService: workflow paused — survives restart
  Approver->>Gateway: POST /approvals/{id}/decide (APPROVE)
  Gateway->>ApprovalService: forward
  ApprovalService->>DaprState: delete HITL state
  ApprovalService->>PubSub: approval.decided (action=APPROVE)
  PubSub->>PaymentService: consume → saga steps 1–4
  PaymentService->>PubSub: payment.completed
  PubSub->>SubmissionService: consume → status=PAID
```

---

## Sequence Diagram 3 — Payment Saga with Compensation

```mermaid
sequenceDiagram
  PaymentService->>DaprState: STEP 1: reserve_budget (CAS/ETag)
  Note over DaprState: budget atomically decremented
  PaymentService->>DB: STEP 2: create_payment_record (status=RESERVED)
  PaymentService->>ExternalGateway: STEP 3: execute_payment
  alt Payment succeeds
    ExternalGateway-->>PaymentService: external_ref
    PaymentService->>DB: STEP 4: status=COMPLETED
    PaymentService->>PubSub: payment.completed
  else Payment fails
    ExternalGateway-->>PaymentService: error
    Note over PaymentService: compensation runs in reverse order
    PaymentService->>DB: mark record status=COMPENSATED
    PaymentService->>DaprState: COMPENSATION: release_budget (CAS)
    Note over DaprState: budget fully restored
    PaymentService->>PubSub: payment.failed
    PubSub->>SubmissionService: consume → status=PAYMENT_FAILED
  end
```

---

## M12 — Ceiling Enforcement (Two-Gate Proof)

The AI agent is **provably incapable** of auto-approving above the configured ceiling ($250).

**Gate 1** — runs *before* the LLM call, inside `_check_autonomy_ceiling()` in `router.py`. If `amount_usd > ceiling`, the router immediately returns `human_review` without calling the LLM at all.

**Gate 2** — runs *after* the LLM call. Even if Gate 1 were somehow bypassed, the router re-reads `amount_usd` (a `Decimal` field set at intake by submission-service — never written by the LLM) and returns `human_review` if the ceiling is exceeded.

The LLM writes only to `recommendation`, `confidence`, `reasoning`, and `policy_violations`. It never writes to `amount_usd`. The router's routing decision reads only `amount_usd`.

Verification: `GET /audit/prove-ceiling` scans every `decision.made` event in the audit log and returns `violation_found: false` if the ceiling held for every auto-approved record.
