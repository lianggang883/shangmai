from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship as _rel

from app.models import Base, UUIDMixin, TimestampMixin, mapper_registry


class ProjectStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class CooperationProject(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "cooperation_projects"

    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationships.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ProjectStatus.DRAFT.value)
    mvp_plan: Mapped[dict | None] = mapped_column(JSON)
    result_report: Mapped[dict | None] = mapped_column(JSON)
    action_power_budget: Mapped[int | None] = mapped_column(Integer, default=0)

    relationship: Mapped["Relationship"] = _rel("Relationship", back_populates="cooperation_projects")
    tasks: Mapped[list["ProjectTask"]] = _rel("ProjectTask", back_populates="project")


class ProjectTask(UUIDMixin, Base):
    __tablename__ = "project_tasks"

    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("cooperation_projects.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("members.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskStatus.PENDING.value)
    points_reward: Mapped[int | None] = mapped_column(Integer, default=0)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    project: Mapped["CooperationProject"] = _rel("CooperationProject", back_populates="tasks")
    assignee: Mapped['Member | None'] = _rel('Member', foreign_keys=[assignee_id])