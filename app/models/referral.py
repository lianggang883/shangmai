from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, func,
)
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, mapper_registry


class ReferralRecord(UUIDMixin, Base):
    __tablename__ = "referral_records"

    referrer_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    referee_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=Decimal("0.10"))
    total_earned: Mapped[int | None] = mapped_column(Integer, default=0)
    pending_remainder: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    referrer: Mapped["Member"] = relationship("Member", foreign_keys=[referrer_id])
    referee: Mapped["Member"] = relationship("Member", foreign_keys=[referee_id])