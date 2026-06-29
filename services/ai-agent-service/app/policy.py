from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# Stable rule texts — matches policy.md §1–§6
POLICY_RULES: dict[str, str] = {
    "MEAL-01": "Personal/team meals are reimbursable up to $75 per attendee. Submissions must include an attendee count; missing it is missing info.",
    "MEAL-02": "Client entertainment over $500 requires a business justification and a client name. Missing either — escalate.",
    "MEAL-03": "Alcohol-only receipts are not reimbursable.",
    "TRAVEL-01": "Economy flights, standard hotels, and standard/economy ground transport (taxi, rideshare, transit) are policy-eligible.",
    "TRAVEL-02": "Any single travel expense over $1,500 requires manager approval (never autonomous).",
    "TRAVEL-03": "First/business-class travel always requires approval.",
    "SAAS-01": "Subscriptions are policy-eligible up to $200/month.",
    "HW-01": "Hardware purchases are policy-eligible up to $1,000.",
    "HW-02": "Hardware over $1,000 is a Capital expense — always human-approved.",
    "GLOBAL-RECEIPT": "A receipt is required for any expense over $25. Missing — missing info — escalate.",
    "GLOBAL-VENDOR": "A new/unknown vendor is always reviewed by a human, regardless of amount/category.",
    "GLOBAL-FX": "Foreign-currency items are converted to USD. A converted amount above the autonomy ceiling (or any FX item over $1,000) is a hard stop — human.",
    "GLOBAL-DUP": "A duplicate (same vendor + invoiceNumber + total) is rejected as a duplicate — no second payment.",
    "GLOBAL-MATH": "The line items + tax must reconcile to total. A mismatch is a hard stop — escalate (never auto-approve).",
    "GLOBAL-FRAUD": "Fraud-pattern signals (round-number to a brand-new vendor, no line-item detail, off-hours, padded quantities) are a hard stop — human review with the signal recorded.",
    "AUTONOMY-CEILING": "The agent may auto-approve only when the USD amount is ≤ $250. Above this — human, even at confidence 1.0.",
    "AUTONOMY-CONFIDENCE": "The agent may auto-approve only when its confidence is ≥ 0.80. Below — human.",
    "SYSTEM-ERROR": "The AI decisioning service encountered an error and escalated for safety.",
}


def fetch_policy_clause(rule_id: str) -> str:
    return POLICY_RULES.get(rule_id, f"Rule '{rule_id}' not found in policy.")


@dataclass
class PolicyConfig:
    autonomy_ceiling: Decimal = Decimal("250")
    autonomy_confidence: float = 0.80
    fx_hard_stop: Decimal = Decimal("1000")
    receipt_threshold: Decimal = Decimal("25")
    saas_cap: Decimal = Decimal("200")
    hw_cap: Decimal = Decimal("1000")
    meal_per_attendee: Decimal = Decimal("75")
    client_entertain_cap: Decimal = Decimal("500")
    travel_manager_cap: Decimal = Decimal("1500")


def load_policy_config() -> PolicyConfig:
    """Load thresholds from settings. In production these come from the Dapr config store."""
    from .config import settings
    return PolicyConfig(
        autonomy_ceiling=settings.autonomy_ceiling,
        autonomy_confidence=settings.autonomy_confidence,
        fx_hard_stop=settings.fx_hard_stop,
        receipt_threshold=settings.receipt_threshold,
        saas_cap=settings.saas_cap,
        hw_cap=settings.hw_cap,
        meal_per_attendee=settings.meal_per_attendee,
        client_entertain_cap=settings.client_entertain_cap,
        travel_manager_cap=settings.travel_manager_cap,
    )
