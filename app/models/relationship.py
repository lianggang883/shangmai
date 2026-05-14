from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, Numeric,
    String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, TimestampMixin, mapper_registry


class RelationshipStatus(str, Enum):
    POTENTIAL = "POTENTIAL"
    VERIFIED = "VERIFIED"
    PARTNERING = "PARTNERING"


class DecayLevel(str, Enum):
    green = "green"
    yellow = "yellow"
    orange = "orange"
    red = "red"


class InteractionType(str, Enum):
    MESSAGE = "MESSAGE"
    MEETING = "MEETING"
    CALL = "CALL"
    COOPERATION = "COOPERATION"


class Relationship(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "relationships"

    member_a: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    member_b: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RelationshipStatus.POTENTIAL.value)
    role_match_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    industry_chain_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    motivation_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    activity_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=Decimal("0"))
    collaboration_dimensions: Mapped[dict | None] = mapped_column(JSON)
    ai_reason: Mapped[str | None] = mapped_column(Text)
    decay_level: Mapped[str | None] = mapped_column(String(10), default=DecayLevel.green.value)
    last_interaction_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member_a_rel: Mapped["Member"] = relationship("Member", foreign_keys=[member_a])
    member_b_rel: Mapped["Member"] = relationship("Member", foreign_keys=[member_b])
    interactions: Mapped[list["Interaction"]] = relationship("Interaction", back_populates="relationship", cascade="all, delete-orphan")
    cooperation_projects: Mapped[list["CooperationProject"]] = relationship("CooperationProject", back_populates="relationship")

    __table_args__ = (
        CheckConstraint("member_a != member_b", name="chk_no_self_relation"),
        Index("idx_rel_member_a", "member_a"),
        Index("idx_rel_member_b", "member_b"),
        Index("idx_rel_status", "status"),
        Index("idx_rel_total_score", "total_score"),
    )


class Interaction(UUIDMixin, Base):
    __tablename__ = "interactions"

    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationships.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    ai_generated: Mapped[bool | None] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    relationship: Mapped["Relationship"] = relationship("Relationship", back_populates="interactions")