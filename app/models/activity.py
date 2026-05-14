from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, TimestampMixin


class ActivityStatus(str, Enum):
    open = "open"
    full = "full"
    closed = "closed"
    cancelled = "cancelled"


class ActivityType(str, Enum):
    golf = "golf"
    dinner = "dinner"
    salon = "salon"
    visit = "visit"
    training = "training"
    other = "other"


class Activity(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "activities"

    organizer_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    activity_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ActivityType.other.value)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    max_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    current_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ActivityStatus.open.value)
    action_power_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    organizer: Mapped["Member"] = relationship("Member", foreign_keys=[organizer_id])
    participants: Mapped[list["ActivityParticipant"]] = relationship("ActivityParticipant", back_populates="activity", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("status IN ('open','full','closed','cancelled')", name="chk_activity_status"),
        CheckConstraint("activity_type IN ('golf','dinner','salon','visit','training','other')", name="chk_activity_type"),
    )


class ActivityParticipant(UUIDMixin, Base):
    __tablename__ = "activity_participants"

    activity_id: Mapped[str] = mapped_column(String(36), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id", ondelete="CASCADE"), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="joined")

    activity: Mapped["Activity"] = relationship("Activity", back_populates="participants")
    member: Mapped["Member"] = relationship("Member")

    __table_args__ = (
        # UniqueConstraint("activity_id", "member_id", name="uq_activity_member"),
    )
