from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: Decimal = Field(alias="unitPrice")

    model_config = {"populate_by_name": True}


class SubmissionRequest(BaseModel):
    id: Optional[str] = None  # fixture id like "INV-1001"
    vendor: str = Field(alias="vendor", min_length=1)
    vendor_known: bool = Field(default=True, alias="vendorKnown")
    invoice_number: str = Field(alias="invoiceNumber", min_length=1)
    currency: str = Field(default="USD", max_length=3)
    category: str = Field(min_length=1)
    department: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    submitted_by: str = Field(alias="submitter", min_length=1)
    receipt_present: bool = Field(default=False, alias="receiptPresent")
    attendees: Optional[int] = None
    line_items: List[LineItem] = Field(alias="lineItems")
    tax_amount: Decimal = Field(default=Decimal("0"), alias="taxAmount")
    total: Decimal
    date: str  # YYYY-MM-DD

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_total_positive(self) -> "SubmissionRequest":
        if self.total <= 0:
            raise ValueError("total must be positive")
        return self


class SubmissionResponse(BaseModel):
    tracking_id: str
    status: str
    message: str = "Submission accepted. Processing asynchronously."


class StatusResponse(BaseModel):
    tracking_id: str
    status: str
    plain_language_reason: Optional[str] = None
    external_payment_ref: Optional[str] = None
    correlation_id: str
    submitted_by: str
    vendor: str
    amount_usd: Decimal
    category: str
    submitted_at: str
    updated_at: str
