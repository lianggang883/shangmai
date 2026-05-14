from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, JSON, SmallInteger, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, UUIDMixin, TimestampMixin, mapper_registry


class GameTaskType(str, Enum):
    daily = "daily"
    weekly = "weekly"
    mainline = "mainline"
    cooperation = "cooperation"


class GameProfile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "game_profiles"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False, unique=True)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    badges: Mapped[dict | None] = mapped_column(JSON, default=[])
    cards: Mapped[dict | None] = mapped_column(JSON, default=[])
    daily_checkin_streak: Mapped[int | None] = mapped_column(Integer, default=0)
    last_checkin: Mapped[date | None] = mapped_column(Date)
    total_points: Mapped[int | None] = mapped_column(Integer, default=0)

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 6", name="chk_game_profile_level"),
    )


class GameTask(UUIDMixin, Base):
    __tablename__ = "game_tasks"

    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    points_reward: Mapped[int | None] = mapped_column(Integer, default=0)
    exp_reward: Mapped[int | None] = mapped_column(Integer, default=0)
    badge_reward: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    progress_list: Mapped[list["GameTaskProgress"]] = relationship("GameTaskProgress", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("task_type IN ('daily','weekly','mainline','cooperation')", name="chk_game_task_type"),
    )


class GameTaskProgress(UUIDMixin, Base):
    __tablename__ = "game_task_progress"

    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("game_tasks.id"), nullable=False)
    progress: Mapped[int | None] = mapped_column(Integer, default=0)
    target: Mapped[int | None] = mapped_column(Integer, default=1)
    completed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])
    task: Mapped["GameTask"] = relationship("GameTask", back_populates="progress_list")

    __table_args__ = (
        UniqueConstraint("member_id", "task_id", name="uq_member_task"),
    )


class GameLeaderboard(UUIDMixin, Base):
    __tablename__ = "game_leaderboard"

    season_id: Mapped[str] = mapped_column(String(50), nullable=False)
    member_id: Mapped[str] = mapped_column(String(36), ForeignKey("members.id"), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    member: Mapped["Member"] = relationship("Member", foreign_keys=[member_id])