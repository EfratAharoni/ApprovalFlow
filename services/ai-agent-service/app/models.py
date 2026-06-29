import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Text, DateTime, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = {"schema": "decisions"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    route: Mapped[str] = mapped_column(String(32), nullable=False)  # auto_approve|human_review|reject|duplicate
    ceiling_guard_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    agent_reasoning: Mapped[str] = mapped_column(Text, nullable=True)
    agent_recommendation: Mapped[str] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    policy_violations: Mapped[dict] = mapped_column(JSONB, nullable=True)
    llm_raw_response: Mapped[dict] = mapped_column(JSONB, nullable=True)
    plain_language_reason: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
