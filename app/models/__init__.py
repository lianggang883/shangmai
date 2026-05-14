"""商脉系统 - 模型包"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, func, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, registry
mapper_registry = registry()
class Base(DeclarativeBase): registry = mapper_registry
class UUIDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

from app.models.member import Member, MemberRole, MemberInterest, MemberDiagnosis
from app.models.relationship import Relationship, Interaction
from app.models.cooperation import CooperationProject, ProjectTask
from app.models.billing import ActionPowerAccount, ActionPowerTransaction, Subscription
from app.models.game import GameProfile, GameTask, GameTaskProgress, GameLeaderboard
from app.models.agent import SkillInvocation, AgentTask
from app.models.knowledge import KnowledgeGraphNode, KnowledgeGraphEdge
from app.models.referral import ReferralRecord
from app.models.uploaded_file import UploadedFile
from app.models.activity import Activity, ActivityParticipant

__all__ = [
    "Base", "UUIDMixin", "TimestampMixin", "mapper_registry",
    "Member", "MemberRole", "MemberInterest", "MemberDiagnosis",
    "Relationship", "Interaction",
    "CooperationProject", "ProjectTask",
    "ActionPowerAccount", "ActionPowerTransaction", "Subscription",
    "GameProfile", "GameTask", "GameTaskProgress", "GameLeaderboard",
    "SkillInvocation", "AgentTask",
    "KnowledgeGraphNode", "KnowledgeGraphEdge",
    "ReferralRecord",
    "UploadedFile",
    "Activity", "ActivityParticipant",
]
