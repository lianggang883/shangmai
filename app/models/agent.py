from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, SmallInteger, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, mapper_registry


class SkillInvocationStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class AgentType(str, Enum):
    MASTER = "MASTER"
    MATCH = "MATCH"
    NAMECARD = "NAMECARD"
    ACTIVITY = "ACTIVITY"
    SECRETARY = "SECRETARY"
    COACH = "COACH"
    INDUSTRY = "INDUSTRY"
    FINANCE = "FINANCE"
    CUSTOM = "CUSTOM"


class AgentTaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class SkillInvocation(UUIDMixin, Base):
    __tablename__ = "skill_invocations"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    skill_name: Mapped[str] = mapped_column(String(50), nullable=False)
    input_data: Mapped[dict | None] = mapped_column(JSON)
    output_data: Mapped[dict | None] = mapped_column(JSON)
    action_power_cost: Mapped[int | None] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(20), default=SkillInvocationStatus.COMPLETED.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])

    __table_args__ = (
        CheckConstraint("status IN ('COMPLETED','FAILED','TIMEOUT')", name="chk_skill_invocation_status"),
    )


class AgentTask(UUIDMixin, Base):
    __tablename__ = "agent_tasks"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_tasks.id"))
    input_data: Mapped[dict | None] = mapped_column(JSON)
    output_data: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String(20), default=AgentTaskStatus.PENDING.value)
    action_power_cost: Mapped[int | None] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])
    parent_task: Mapped["AgentTask | None"] = relationship("AgentTask", remote_side="AgentTask.id", foreign_keys=[parent_task_id])