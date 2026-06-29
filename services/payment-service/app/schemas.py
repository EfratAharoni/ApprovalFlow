from typing import Optional
from pydantic import BaseModel


class DecisionMadeEvent(BaseModel):
    submission_id: str
    tracking_id: str
    correlation_id: str
    route: str                          # auto_approve | human_review | reject | duplicate
    amount_usd: Optional[str] = None
    category: Optional[str] = None
    vendor: Optional[str] = None
    submitted_by: Optional[str] = None


class ApprovalDecidedEvent(BaseModel):
    submission_id: str
    tracking_id: str
    correlation_id: str
    action: str                         # APPROVE | REJECT | REQUEST_INFO
    amount_usd: Optional[str] = None
    category: Optional[str] = None
    department_id: Optional[str] = None
