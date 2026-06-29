from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class PolicyViolation(BaseModel):
    rule_id: str
    description: str


class AgentDecision(BaseModel):
    # reasoning is FIRST — Schema-Guided Reasoning forces chain-of-thought before conclusion
    reasoning: str
    recommendation: str          # "approve" | "escalate" | "reject"
    confidence: float = Field(ge=0.0, le=1.0)
    policy_violations: list[PolicyViolation]


class RouterDecision(BaseModel):
    route: str                              # auto_approve | human_review | reject | duplicate
    ceiling_guard_triggered: bool
    agent_recommendation: Optional[AgentDecision]
    policy_violations: list[PolicyViolation]
    plain_language_reason: str


class LineItem(BaseModel):
    description: str = ""
    quantity: float = 1.0
    unitPrice: float = 0.0


class SubmissionEvent(BaseModel):
    submission_id: str
    tracking_id: str = ""
    correlation_id: str
    vendor: str
    vendor_known: bool = True
    invoice_number: str
    currency: str = "USD"
    amount: str
    amount_usd: str
    category: str
    department: Optional[str] = None
    submitted_by: str = ""
    receipt_present: bool = False
    attendees: Optional[int] = None
    line_items: list[LineItem] = []
    tax_amount: str = "0"
    total: str
    date: str = ""
    notes: Optional[str] = None
    description: Optional[str] = None
    idempotency_key: str = ""
