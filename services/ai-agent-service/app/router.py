"""
Deterministic router — enforces the autonomy ceiling and all hard stops.

The LLM agent only RECOMMENDS. This module makes the FINAL routing decision,
reading submission.amount_usd (a typed Decimal set at intake) — never any
field the LLM writes. This makes M12 provable: the router is pure Python
with no LLM calls, unit-testable to 100% branch coverage.

Route ordering (stops at first match for duplicate/reject; collects all for human_review):
  1. GLOBAL-DUP   → duplicate  (immediate return)
  2. MEAL-03      → reject     (immediate return)
  3-13. Hard stops → human_review (all collected, then return)
  14-15. Post-LLM → human_review (confidence / ceiling gate 2)
  16. Otherwise   → auto_approve
"""
import logging
from decimal import Decimal
from typing import Awaitable, Callable, Protocol

from .policy import PolicyConfig, fetch_policy_clause
from .schemas import AgentDecision, PolicyViolation, RouterDecision, SubmissionEvent

logger = logging.getLogger(__name__)


class BaseAgent(Protocol):
    async def decide(self, event: SubmissionEvent, policy: PolicyConfig) -> AgentDecision:
        ...


async def route_submission(
    event: SubmissionEvent,
    policy: PolicyConfig,
    agent: BaseAgent,
    is_duplicate_fn: Callable[[str], Awaitable[bool]],
) -> RouterDecision:
    """
    Pure routing logic. Injectable dependencies keep this unit-testable without
    any database or LLM infrastructure.
    """
    amount_usd = Decimal(event.amount_usd)

    # ── 1. GLOBAL-DUP ────────────────────────────────────────────────────────
    if event.idempotency_key and await is_duplicate_fn(event.idempotency_key):
        logger.info("GLOBAL-DUP triggered", extra={"correlation_id": event.correlation_id})
        return RouterDecision(
            route="duplicate",
            ceiling_guard_triggered=False,
            agent_recommendation=None,
            policy_violations=[PolicyViolation(
                rule_id="GLOBAL-DUP",
                description="Duplicate invoice: same vendor, invoice number, and total already processed.",
            )],
            plain_language_reason="This invoice was already submitted and processed. No second payment will be issued.",
        )

    # ── 2. MEAL-03 (hard reject — no human override) ─────────────────────────
    if _is_alcohol_only(event):
        logger.info("MEAL-03 triggered (reject)", extra={"correlation_id": event.correlation_id})
        return RouterDecision(
            route="reject",
            ceiling_guard_triggered=False,
            agent_recommendation=None,
            policy_violations=[PolicyViolation(
                rule_id="MEAL-03",
                description=fetch_policy_clause("MEAL-03"),
            )],
            plain_language_reason="Rejected: alcohol-only receipts are not reimbursable per company policy.",
        )

    # ── 3–13. Collect all hard-stop violations ───────────────────────────────
    violations: list[PolicyViolation] = []
    _check_global_math(event, violations)
    _check_global_fraud(event, violations)
    _check_global_vendor(event, violations)
    _check_global_receipt(event, policy, violations)
    _check_travel(event, policy, violations)
    _check_hardware(event, policy, violations)
    _check_global_fx(event, policy, violations)
    _check_saas(event, policy, violations)
    _check_meal(event, policy, violations)
    _check_autonomy_ceiling(amount_usd, policy, violations)

    ceiling_guard = any(v.rule_id == "AUTONOMY-CEILING" for v in violations)

    if violations:
        logger.info(
            "hard-stop violation(s), escalating",
            extra={
                "correlation_id": event.correlation_id,
                "rules": [v.rule_id for v in violations],
                "ceiling_guard": ceiling_guard,
            },
        )
        return RouterDecision(
            route="human_review",
            ceiling_guard_triggered=ceiling_guard,
            agent_recommendation=None,
            policy_violations=violations,
            plain_language_reason=_build_human_review_reason(violations),
        )

    # ── LLM call ─────────────────────────────────────────────────────────────
    logger.info("no hard stops — calling AI agent", extra={"correlation_id": event.correlation_id})
    try:
        agent_decision = await agent.decide(event, policy)
    except Exception as exc:
        logger.error(
            "LLM provider error — escalating for safety",
            extra={"correlation_id": event.correlation_id, "error": str(exc)},
        )
        return RouterDecision(
            route="human_review",
            ceiling_guard_triggered=False,
            agent_recommendation=None,
            policy_violations=[PolicyViolation(rule_id="SYSTEM-ERROR", description=str(exc))],
            plain_language_reason="AI service error — escalated for manual review.",
        )

    # ── 14. Confidence gate ───────────────────────────────────────────────────
    if agent_decision.confidence < policy.autonomy_confidence:
        logger.info(
            "AUTONOMY-CONFIDENCE triggered",
            extra={
                "correlation_id": event.correlation_id,
                "confidence": agent_decision.confidence,
                "threshold": policy.autonomy_confidence,
            },
        )
        return RouterDecision(
            route="human_review",
            ceiling_guard_triggered=False,
            agent_recommendation=agent_decision,
            policy_violations=[PolicyViolation(
                rule_id="AUTONOMY-CONFIDENCE",
                description=f"Agent confidence {agent_decision.confidence:.2f} below required {policy.autonomy_confidence:.2f}.",
            )],
            plain_language_reason=f"Escalated: agent confidence ({agent_decision.confidence:.0%}) below required threshold.",
        )

    # ── 15. Ceiling gate 2 — defense-in-depth (reads original amount, not LLM output) ──
    if amount_usd > policy.autonomy_ceiling:
        logger.warning(
            "ceiling_guard gate 2 triggered (should have been caught in gate 1)",
            extra={"correlation_id": event.correlation_id, "amount_usd": str(amount_usd)},
        )
        return RouterDecision(
            route="human_review",
            ceiling_guard_triggered=True,
            agent_recommendation=agent_decision,
            policy_violations=[PolicyViolation(
                rule_id="AUTONOMY-CEILING",
                description=f"Amount ${amount_usd} exceeds ceiling ${policy.autonomy_ceiling}.",
            )],
            plain_language_reason="Escalated: amount exceeds auto-approval ceiling.",
        )

    # ── 16. Agent recommendation ──────────────────────────────────────────────
    if agent_decision.recommendation != "approve":
        return RouterDecision(
            route="human_review",
            ceiling_guard_triggered=False,
            agent_recommendation=agent_decision,
            policy_violations=agent_decision.policy_violations,
            plain_language_reason=f"Escalated based on AI analysis: {agent_decision.reasoning[:200]}",
        )

    logger.info("auto_approve", extra={"correlation_id": event.correlation_id, "vendor": event.vendor})
    return RouterDecision(
        route="auto_approve",
        ceiling_guard_triggered=False,
        agent_recommendation=agent_decision,
        policy_violations=[],
        plain_language_reason=f"Automatically approved: {agent_decision.reasoning[:200]}",
    )


# ─── Hard-stop check helpers ──────────────────────────────────────────────────

def _is_alcohol_only(event: SubmissionEvent) -> bool:
    if event.category.lower() != "meals":
        return False
    notes = (event.notes or "").lower()
    if "alcohol" in notes and "only" in notes:
        return True
    if event.line_items and all("alcohol" in (item.description or "").lower() for item in event.line_items):
        return True
    return False


def _check_global_math(event: SubmissionEvent, violations: list[PolicyViolation]) -> None:
    try:
        total = Decimal(event.total)
        tax = Decimal(event.tax_amount or "0")
        line_sum = sum(
            Decimal(str(item.quantity)) * Decimal(str(item.unitPrice))
            for item in event.line_items
        )
        expected = line_sum + tax
        if abs(expected - total) > Decimal("0.02"):
            violations.append(PolicyViolation(
                rule_id="GLOBAL-MATH",
                description=f"Math mismatch: line items ({line_sum}) + tax ({tax}) = {expected}, but total = {total}.",
            ))
    except Exception:
        pass  # malformed amounts are caught by schema validation upstream


def _check_global_fraud(event: SubmissionEvent, violations: list[PolicyViolation]) -> None:
    amount_usd = Decimal(event.amount_usd)
    is_round_and_large = amount_usd >= 500 and amount_usd % 1 == 0
    is_new_vendor = not event.vendor_known
    is_single_vague = len(event.line_items) == 1
    if is_round_and_large and is_new_vendor and is_single_vague:
        violations.append(PolicyViolation(
            rule_id="GLOBAL-FRAUD",
            description="Fraud signals: round-number amount, unknown vendor, single vague line item.",
        ))


def _check_global_vendor(event: SubmissionEvent, violations: list[PolicyViolation]) -> None:
    if not event.vendor_known:
        violations.append(PolicyViolation(
            rule_id="GLOBAL-VENDOR",
            description=f"Vendor '{event.vendor}' is unknown. New vendors always require human review.",
        ))


def _check_global_receipt(event: SubmissionEvent, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    total = Decimal(event.total)
    if total > policy.receipt_threshold and not event.receipt_present:
        violations.append(PolicyViolation(
            rule_id="GLOBAL-RECEIPT",
            description=f"Receipt required for expenses over ${policy.receipt_threshold} but not attached.",
        ))


def _check_travel(event: SubmissionEvent, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    if event.category.lower() != "travel":
        return
    amount_usd = Decimal(event.amount_usd)
    if amount_usd > policy.travel_manager_cap:
        violations.append(PolicyViolation(
            rule_id="TRAVEL-02",
            description=f"Single travel expense ${amount_usd} exceeds ${policy.travel_manager_cap} — manager approval required.",
        ))
    combined = " ".join([
        (event.notes or "").lower(),
        (event.description or "").lower(),
        " ".join((item.description or "").lower() for item in event.line_items),
    ])
    if any(kw in combined for kw in ["first class", "business class", "first-class", "business-class"]):
        violations.append(PolicyViolation(
            rule_id="TRAVEL-03",
            description="First/business-class travel requires human approval.",
        ))


def _check_hardware(event: SubmissionEvent, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    if event.category.lower() != "hardware":
        return
    amount_usd = Decimal(event.amount_usd)
    if amount_usd > policy.hw_cap:
        violations.append(PolicyViolation(
            rule_id="HW-02",
            description=f"Hardware ${amount_usd} is a Capital expense (over ${policy.hw_cap}) — always requires human approval.",
        ))


def _check_global_fx(event: SubmissionEvent, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    if event.currency.upper() == "USD":
        return
    amount_usd = Decimal(event.amount_usd)
    if amount_usd > policy.fx_hard_stop:
        violations.append(PolicyViolation(
            rule_id="GLOBAL-FX",
            description=f"FX expense ({event.currency} converted to ${amount_usd} USD) exceeds ${policy.fx_hard_stop} hard stop.",
        ))


def _check_saas(event: SubmissionEvent, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    if event.category.lower() != "saas":
        return
    amount_usd = Decimal(event.amount_usd)
    if amount_usd > policy.saas_cap:
        violations.append(PolicyViolation(
            rule_id="SAAS-01",
            description=f"SaaS subscription ${amount_usd}/month exceeds the ${policy.saas_cap}/month cap.",
        ))


def _check_meal(event: SubmissionEvent, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    if event.category.lower() != "meals":
        return
    if event.attendees is None or event.attendees == 0:
        violations.append(PolicyViolation(
            rule_id="MEAL-01",
            description="Meal submission is missing required attendee count.",
        ))
        return
    amount_usd = Decimal(event.amount_usd)
    per_attendee = amount_usd / event.attendees
    if per_attendee > policy.meal_per_attendee:
        violations.append(PolicyViolation(
            rule_id="MEAL-01",
            description=f"Meal cost ${per_attendee:.2f}/attendee exceeds the ${policy.meal_per_attendee}/attendee limit.",
        ))


def _check_autonomy_ceiling(amount_usd: Decimal, policy: PolicyConfig, violations: list[PolicyViolation]) -> None:
    if amount_usd > policy.autonomy_ceiling:
        violations.append(PolicyViolation(
            rule_id="AUTONOMY-CEILING",
            description=f"Amount ${amount_usd} exceeds the ${policy.autonomy_ceiling} autonomy ceiling.",
        ))


def _build_human_review_reason(violations: list[PolicyViolation]) -> str:
    rule_ids = [v.rule_id for v in violations]
    if len(rule_ids) == 1:
        return f"Requires human review: {violations[0].description}"
    return f"Requires human review: {len(rule_ids)} policy rules triggered ({', '.join(rule_ids)})."
