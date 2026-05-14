from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric,
    SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, TimestampMixin, mapper_registry


class MemberStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BANNED = "BANNED"


class RoleType(str, Enum):
    PROVIDE = "PROVIDE"
    SEEK = "SEEK"


class DiagnosisLayer(str, Enum):
    environment = "environment"
    behavior = "behavior"
    capability = "capability"
    belief = "belief"
    identity = "identity"
    spirit = "spirit"


class Member(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "members"

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(100))
    verify_code: Mapped[str | None] = mapped_column(String(6))
    verify_code_expire: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(50))
    industry: Mapped[str | None] = mapped_column(String(50))
    annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    employee_count: Mapped[int | None] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    exp_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_power_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    action_power_frozen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    referrer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("members.id"))
    referrer_rate: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0.10"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=MemberStatus.ACTIVE.value)

    roles: Mapped[list["MemberRole"]] = relationship("MemberRole", back_populates="member", cascade="all, delete-orphan")
    interests: Mapped[list["MemberInterest"]] = relationship("MemberInterest", back_populates="member", cascade="all, delete-orphan")
    diagnoses: Mapped[list["MemberDiagnosis"]] = relationship("MemberDiagnosis", back_populates="member", cascade="all, delete-orphan")
    referrer: Mapped["Member | None"] = relationship("Member", remote_side="Member.id", foreign_keys=[referrer_id])

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 6", name="chk_member_level"),
    )


class MemberRole(UUIDMixin, Base):
    __tablename__ = "member_roles"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    role_type: Mapped[str] = mapped_column(String(10), nullable=False)
    role_code: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=Decimal("0.50"))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    member: Mapped["Member"] = relationship("Member", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("member_id", "role_type", "role_code", name="uq_member_role"),
        CheckConstraint("role_type IN ('PROVIDE','SEEK')", name="chk_member_role_type"),
        CheckConstraint("role_code IN ('partner','customer','inventor','supplier','mentor','expert','investor','cross_industry','team','media','ai_advisor')", name="chk_member_role_code"),
    )


class MemberInterest(UUIDMixin, Base):
    __tablename__ = "member_interests"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    tag_name: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=Decimal("0.50"))

    member: Mapped["Member"] = relationship("Member", back_populates="interests")

    __table_args__ = (
        UniqueConstraint("member_id", "tag_name", name="uq_member_tag"),
    )


class MemberDiagnosis(UUIDMixin, Base):
    __tablename__ = "member_diagnosis"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    layer: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False, default=Decimal("0.50"))
    context: Mapped[str | None] = mapped_column(Text)
    diagnosed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    member: Mapped["Member"] = relationship("Member", back_populates="diagnoses")

    __table_args__ = (
        UniqueConstraint("member_id", "layer", name="uq_member_layer"),
        CheckConstraint("score BETWEEN 1 AND 10", name="chk_diagnosis_score"),
        CheckConstraint("layer IN ('environment','behavior','capability','belief','identity','spirit')", name="chk_diagnosis_layer"),
    )