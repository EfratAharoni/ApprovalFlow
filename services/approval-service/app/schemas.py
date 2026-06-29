from typing import Optional
from pydantic import BaseModel


class DecisionMadeEvent(BaseModel):
    submission_id: str
    tracking_id: str
    correlation_id: str
    route: str
    ceiling_guard_triggered: bool = False
    agent_recommendation: Optional[dict] = None
    policy_violations: list = []
    plain_language_reason: str = ""
    amount_usd: Optional[str] = None
    category: Optional[str] = None
    vendor: Optional[str] = None
    submitted_by: Optional[str] = None


class DecideRequest(BaseModel):
    action: str          # APPROVE | REJECT | REQUEST_INFO
    decided_by: str
    notes: str = ""
