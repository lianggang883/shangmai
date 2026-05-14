from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, TimestampMixin, mapper_registry


class TxType(str, Enum):
    RECHARGE = "RECHARGE"
    CONSUME = "CONSUME"
    GIFT = "GIFT"
    REFERRAL_INCOME = "REFERRAL_INCOME"
    REFUND = "REFUND"
    FREEZE = "FREEZE"
    UNFREEZE = "UNFREEZE"


class SubType(str, Enum):
    DAILY_REPORT = "DAILY_REPORT"
    AUTO_MATCH = "AUTO_MATCH"
    DECAY_ALERT = "DECAY_ALERT"


class ActionPowerAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "action_power_accounts"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False, unique=True)
    monthly_free: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    purchased: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gifted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    frozen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_gifted_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_month: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    daily_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])
    transactions: Mapped[list["ActionPowerTransaction"]] = relationship("ActionPowerTransaction", back_populates="account", cascade="all, delete-orphan")


class ActionPowerTransaction(UUIDMixin, Base):
    __tablename__ = "action_power_transactions"

    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("action_power_accounts.id"), nullable=False)
    tx_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    ref_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    account: Mapped["ActionPowerAccount"] = relationship("ActionPowerAccount", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("tx_type IN ('RECHARGE','CONSUME','GIFT','REFERRAL_INCOME','REFUND','FREEZE','UNFREEZE')", name="chk_tx_type"),
    )


class Subscription(UUIDMixin, Base):
    __tablename__ = "subscriptions"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    sub_type: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool | None] = mapped_column(Boolean, default=True)
    cost_per_trigger: Mapped[int | None] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])

    __table_args__ = (
        CheckConstraint("sub_type IN ('DAILY_REPORT','AUTO_MATCH','DECAY_ALERT')", name="chk_sub_type"),
    )